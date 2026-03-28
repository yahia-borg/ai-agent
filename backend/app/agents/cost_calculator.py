from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.models.quotation import Quotation
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.agents.llm_client import get_llm_client
from app.models.project_data import ConstructionRequirements
from app.utils.language_detector import detect_language
from app.utils.category_utils import detect_category, detect_material_type, detect_material_group
from app.services.config_service import get_config_service
from sqlalchemy import text
import json
import logging
import re

logger = logging.getLogger(__name__)


class CostCalculatorAgent(BaseAgent):
    """
    Agent responsible for calculating construction costs using database values.

    All pricing, labor rates, and material costs are fetched from the database.
    No hardcoded values - fully data-driven.
    """

    def __init__(self):
        super().__init__("cost_calculator")
        self.currency = settings.DEFAULT_CURRENCY  # EGP
        self.currency_symbol = "EGP"
        self.llm = get_llm_client()
    
    def get_required_context(self) -> list[str]:
        return ["extracted_data"]
    
    
    # Room multipliers and area defaults are now loaded from config service.
    # See get_config_service() and _load_multipliers_from_config().

    async def _distribute_areas_to_rooms(
        self, extracted_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build a list of ``{"room_type": str, "area_sqm": float}`` entries.

        Priority:
        1. Use rooms[].area_sqm if provided.
        2. Else divide total size_sqm proportionally based on room counts
           and typical Egyptian layout percentages.
        3. If no rooms at all, return a single "generic" entry with full area.
        """
        config = get_config_service()

        size_sqm = extracted_data.get("size_sqm") or 0
        rooms = extracted_data.get("rooms") or []
        num_bathrooms = extracted_data.get("num_bathrooms")
        num_kitchens = extracted_data.get("num_kitchens")
        project_type = (extracted_data.get("project_type") or "residential").lower()

        is_commercial = any(
            kw in project_type
            for kw in ["commercial", "office", "bank", "تجاري"]
        )

        area_type = "commercial" if is_commercial else "residential"
        area_defaults = await config.get_area_defaults(area_type)

        result: List[Dict[str, Any]] = []

        # Case 1: rooms with explicit areas
        if rooms:
            total_explicit = 0.0
            rooms_without_area = []

            for room in rooms:
                count = room.get("count", 1) or 1
                area = room.get("area_sqm")
                rtype = room.get("room_type", "other")

                if area and area > 0:
                    for _ in range(count):
                        result.append({"room_type": rtype, "area_sqm": area})
                        total_explicit += area
                else:
                    rooms_without_area.append((rtype, count))

            remaining = max(size_sqm - total_explicit, 0)
            total_rooms_without = sum(c for _, c in rooms_without_area)

            if rooms_without_area and remaining > 0 and total_rooms_without > 0:
                per_room = remaining / total_rooms_without
                for rtype, count in rooms_without_area:
                    for _ in range(count):
                        result.append({"room_type": rtype, "area_sqm": per_room})
            elif rooms_without_area:
                weight_sum = sum(
                    area_defaults.get(rtype, 0.10) * count
                    for rtype, count in rooms_without_area
                )
                for rtype, count in rooms_without_area:
                    w = area_defaults.get(rtype, 0.10) * count
                    area = (w / weight_sum * size_sqm) / count if weight_sum > 0 else size_sqm / total_rooms_without
                    for _ in range(count):
                        result.append({"room_type": rtype, "area_sqm": area})

            return result

        # Case 2: no rooms list, but num_bathrooms / num_kitchens given
        if num_bathrooms is not None or num_kitchens is not None:
            nb = num_bathrooms or 0
            nk = num_kitchens or 0
            bath_area = size_sqm * area_defaults.get("bathroom", 0.06)
            kitchen_area = size_sqm * area_defaults.get("kitchen", 0.10)
            allocated = bath_area * nb + kitchen_area * nk

            for _ in range(nb):
                result.append({"room_type": "bathroom", "area_sqm": bath_area})
            for _ in range(nk):
                result.append({"room_type": "kitchen", "area_sqm": kitchen_area})

            rest = max(size_sqm - allocated, 0)
            if rest > 0:
                generic_type = "office" if is_commercial else "living_room"
                result.append({"room_type": generic_type, "area_sqm": rest})

            return result

        # Case 3: no room data at all
        generic_type = "open_plan" if is_commercial else "living_room"
        result.append({"room_type": generic_type, "area_sqm": size_sqm})
        return result

    async def _get_room_material_multiplier(
        self, room_type: str, material_category: str
    ) -> float:
        """Return the material multiplier for a room + material category pair."""
        config = get_config_service()
        room_mults = await config.get_room_multipliers(room_type, "material")
        cat_lower = material_category.lower()
        for key in room_mults:
            if key in cat_lower:
                return room_mults[key]
        return room_mults.get("default", 1.0)

    async def _get_room_labor_multiplier(
        self, room_type: str, trade_key: str
    ) -> float:
        """Return the labor multiplier for a room + trade pair."""
        config = get_config_service()
        room_mults = await config.get_room_multipliers(room_type, "labor")
        return room_mults.get(trade_key, room_mults.get("default", 1.0))

    async def _verify_and_enrich_phases(
        self,
        current_finish: str,
        target_finish: str,
        project_type: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Query Qdrant to verify and enrich phase information.

        Uses semantic search with the raw Arabic/English finish level text.
        The multilingual embedding model (paraphrase-multilingual-MiniLM-L12-v2)
        handles Arabic natively — no hardcoded phase_mapping needed.

        Args:
            current_finish: Current finish level as provided by the user/extraction
                            (e.g. "على_الطوب", "on_plaster", "plastered")
            target_finish:  Target finish level
                            (e.g. "تشطيب_كامل", "عالمفتاح", "fully_finished")
            project_type:   Type of project (e.g., "residential", "commercial")
            language:       Language preference ('en' or 'ar')

        Returns:
            Dictionary with enriched phase information from the knowledge base.
        """
        try:
            from app.services.qdrant_service import get_qdrant_service
            qdrant = get_qdrant_service()

            # Guard against None values
            if not current_finish or not target_finish:
                logger.warning(f"Missing finish levels: current={current_finish}, target={target_finish}")
                return {
                    "current_phase": {"name": current_finish or "unknown", "arabic_name": None},
                    "target_phase": {"name": target_finish or "unknown", "arabic_name": None}
                }

            # Humanise underscored values so the embedding sees natural text
            current_readable = current_finish.replace("_", " ")
            target_readable = target_finish.replace("_", " ")

            # Query 1 — current phase: use the raw value directly so the
            # multilingual model can match Arabic ("التشطيب من على الطوب الأحمر")
            # or English ("red brick stage") in the knowledge base.
            current_phase_query = (
                f"مرحلة التشطيب {current_readable} "
                f"{current_readable} finishing stage "
                f"{project_type} requirements materials labor"
            )
            logger.info(f"Qdrant phase query (current): {current_phase_query}")
            current_phase_results = qdrant.search_knowledge(current_phase_query, top_k=5)

            # Query 2 — target phase
            target_phase_query = (
                f"مرحلة التشطيب {target_readable} "
                f"{target_readable} finishing stage "
                f"{project_type} requirements materials labor"
            )
            logger.info(f"Qdrant phase query (target): {target_phase_query}")
            target_phase_results = qdrant.search_knowledge(target_phase_query, top_k=5)

            # Build current phase info from Qdrant results
            current_phase_info = {
                "name": current_finish,
                "arabic_name": None,
                "description": "",
                "status": "",
                "completed_work": [],
                "missing_work": []
            }

            target_phase_info = {
                "name": target_finish,
                "arabic_name": None,
                "description": "",
                "required_work": [],
                "materials_needed": []
            }

            if current_phase_results:
                current_phase_info["description"] = "\n".join(
                    [r.get("content", "")[:300] for r in current_phase_results[:3]]
                )
                for result in current_phase_results:
                    topic = result.get("topic", "")
                    arabic_match = re.search(r'\(([^)]+)\)', topic)
                    if arabic_match and any(ord(c) > 127 for c in arabic_match.group(1)):
                        current_phase_info["arabic_name"] = arabic_match.group(1)
                        break

            if target_phase_results:
                target_phase_info["description"] = "\n".join(
                    [r.get("content", "")[:300] for r in target_phase_results[:3]]
                )
                for result in target_phase_results:
                    topic = result.get("topic", "")
                    arabic_match = re.search(r'\(([^)]+)\)', topic)
                    if arabic_match and any(ord(c) > 127 for c in arabic_match.group(1)):
                        target_phase_info["arabic_name"] = arabic_match.group(1)
                        break

            logger.info(
                f"Phase enrichment: current='{current_finish}' matched {len(current_phase_results)} docs, "
                f"target='{target_finish}' matched {len(target_phase_results)} docs"
            )

            return {
                "current_phase": current_phase_info,
                "target_phase": target_phase_info
            }

        except Exception as e:
            logger.warning(f"Error verifying/enriching phases: {e}. Using defaults.")
            return {
                "current_phase": {"name": current_finish, "arabic_name": None},
                "target_phase": {"name": target_finish, "arabic_name": None}
            }

    # ── Phase transition requirement maps ──────────────────────────
    # Deterministic mapping: what materials and labor are needed
    # for each finishing transition. Replaces the nested LLM call.
    PHASE_REQUIREMENTS = {
        "core_shell": {
            # From core shell / red brick: need everything
            "materials": [
                "cement", "sand", "plaster", "waterproofing", "pipes", "electrical conduit",
                "wiring", "cable", "switch", "socket", "ceramic tile", "porcelain tile",
                "paint", "emulsion", "door", "window", "gypsum board", "marble",
                "steel", "rebar"
            ],
            "labor": [
                "mason", "electrician", "plumber", "plasterer", "tiler",
                "painter", "carpenter", "welder", "supervisor"
            ],
        },
        "on_plaster": {
            # From plastered: finishing only (no structural)
            "materials": [
                "ceramic tile", "porcelain tile", "paint", "emulsion",
                "door", "window", "switch", "socket", "wiring",
                "pipes", "fixtures", "marble", "waterproofing"
            ],
            "labor": [
                "electrician", "plumber", "tiler", "painter", "carpenter", "supervisor"
            ],
        },
        "semi_finished": {
            # From semi-finished: final touches only
            "materials": [
                "paint", "emulsion", "switch", "socket",
                "fixtures", "door handle", "accessories"
            ],
            "labor": [
                "painter", "electrician", "plumber", "carpenter"
            ],
        },
    }

    # Aliases for phase names (Arabic and English variants, including Egyptian colloquial)
    PHASE_ALIASES = {
        "core_shell": [
            "core_shell", "على_الطوب", "على الطوب", "عالطوب", "red brick", "red_brick",
            "على الطوب الأحمر", "العظم", "هيكل", "خرسانة", "core shell",
        ],
        "on_plaster": [
            "on_plaster", "plastered", "على_المحارة", "على المحارة", "عالمحارة",
            "on plaster", "محارة", "on_plaster", "بياض", "متمحر",
        ],
        "semi_finished": [
            "semi_finished", "نص_تشطيب", "نص تشطيب", "semi finished", "نصف تشطيب",
            "نص_تشطيب", "شبه متشطب",
        ],
    }

    def _resolve_phase(self, phase_name: str) -> str:
        """Resolve phase name aliases to canonical key."""
        if not phase_name:
            return "core_shell"  # Safest fallback when phase is unknown
        phase_lower = phase_name.lower().strip()
        for canonical, aliases in self.PHASE_ALIASES.items():
            if phase_lower in [a.lower() for a in aliases]:
                return canonical
        # Default: if it looks like core_shell keywords
        if any(kw in phase_lower for kw in ["طوب", "brick", "shell", "عظم"]):
            return "core_shell"
        if any(kw in phase_lower for kw in ["محارة", "plaster"]):
            return "on_plaster"
        if any(kw in phase_lower for kw in ["نص", "semi"]):
            return "semi_finished"
        return "core_shell"  # Most comprehensive fallback

    async def _query_qdrant_for_requirements(self, extracted_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Determine material and labor requirements using deterministic phase mapping.

        Uses Qdrant for supplementary knowledge but does NOT make an LLM call.
        The phase transition requirements are looked up from PHASE_REQUIREMENTS.
        """
        try:
            current_finish = extracted_data.get("current_finish_level") or "plastered"
            target_finish = extracted_data.get("target_finish_level") or "fully_finished"
            project_type = extracted_data.get("project_type") or "residential"

            logger.info(f"Determining requirements for: {current_finish} -> {target_finish}")

            # Resolve phase to canonical key
            phase_key = self._resolve_phase(current_finish)
            requirements = self.PHASE_REQUIREMENTS.get(phase_key, self.PHASE_REQUIREMENTS["core_shell"])

            materials = list(requirements["materials"])
            labor = list(requirements["labor"])

            # Optionally enrich from Qdrant (non-blocking, no LLM)
            try:
                from app.services.qdrant_service import get_qdrant_service
                qdrant = get_qdrant_service()

                current_readable = current_finish.replace("_", " ")
                target_readable = target_finish.replace("_", " ")

                query = (
                    f"مراحل تشطيب {current_readable} إلى {target_readable} "
                    f"مواد وعمالة مطلوبة {project_type}"
                )
                qdrant_results = qdrant.search_knowledge(query, top_k=3)

                if qdrant_results:
                    logger.info(f"Qdrant returned {len(qdrant_results)} supplementary results")
                    # Extract any additional material keywords from Qdrant content
                    for result in qdrant_results:
                        content = result.get("content", "").lower()
                        # Check for materials not already in list
                        for mat_kw in ["gypsum", "insulation", "vinyl", "parquet", "granite", "glass"]:
                            if mat_kw in content and mat_kw not in [m.lower() for m in materials]:
                                materials.append(mat_kw)

            except Exception as e:
                logger.warning(f"Qdrant enrichment failed (non-critical): {e}")

            logger.info(f"Deterministic requirements: {len(materials)} materials, {len(labor)} labor roles")
            return {"materials": materials, "labor": labor}

        except Exception as e:
            logger.warning(f"Error in requirement extraction: {e}. Using basic fallback.")
            return {
                "materials": ["cement", "sand", "tile", "paint", "plaster", "wiring", "pipes"],
                "labor": ["mason", "electrician", "plumber", "painter", "tiler"]
            }
    
    def _fetch_materials_from_db(self, material_queries: List[str], language: str = "en") -> List[Dict[str, Any]]:
        """
        Fetch materials from database based on queries from Qdrant.
        Uses PostgreSQL multilingual search function.
        NOTE: sync — call via asyncio.to_thread() from async context.

        Args:
            material_queries: List of material search queries
            language: Language preference ('en' or 'ar')

        Returns list of materials with pricing.
        """
        db = SessionLocal()
        try:
            materials = []
            seen_ids = set()
            # Track which query found each material (for fallback names)
            query_to_materials = {}

            for query in material_queries:
                query_to_materials[query] = []
                # Use PostgreSQL multilingual search function
                # Increased limit from 5 to 10 to find more materials
                result = db.execute(
                    text("""
                        SELECT * FROM search_materials_multilingual(
                            :query,
                            :language,
                            NULL,  -- category_id (optional filter)
                            10     -- limit (increased to find more materials)
                        )
                    """),
                    {"query": query, "language": language}
                )
                
                rows = result.fetchall()
                
                for row in rows:
                    # Skip duplicates
                    if row.id in seen_ids:
                        continue
                    seen_ids.add(row.id)
                    
                    # Get related data
                    material = db.query(Material).filter(Material.id == row.id).first()
                    if not material:
                        continue
                    
                    # Get category name (bilingual) - extract display name
                    category_name = None
                    category_display = None
                    if material.category:
                        category_name = material.category.name
                        if isinstance(category_name, dict):
                            category_display = category_name.get(language, category_name.get("en", ""))
                        else:
                            category_display = category_name
                    
                    # Get unit name (bilingual) - extract display name
                    unit_name = None
                    unit_display = None
                    if material.unit:
                        unit_name = material.unit.name
                        if isinstance(unit_name, dict):
                            unit_display = unit_name.get(language, unit_name.get("en", ""))
                        else:
                            unit_display = unit_name
                    
                    # Get currency symbol
                    currency_symbol = None
                    if material.currency:
                        currency_symbol = material.currency.symbol
                    
                    # Extract display name from JSONB
                    name_display = row.name_ar if language == "ar" else row.name_en

                    # If name is missing from database, use the search query as fallback
                    # This ensures we always have a meaningful name based on what was searched
                    if not name_display:
                        name_display = query.title()  # Use the search query that found this material
                        logger.warning(f"Material {row.id} has no name, using search query: {name_display}")


                    # Extract rich metadata
                    brand = material.brand
                    specifications = material.specifications  # JSONB
                    code = material.code
                    
                    # Store DB description (JSONB)
                    db_description_json = material.description 
                    
                    material_data = {
                        "name": name_display,  # Display name for compatibility
                        "name_bilingual": {
                            "en": row.name_en or query.title(),
                            "ar": row.name_ar or query.title()
                        },
                        "price": float(row.price),  # New schema uses 'price' not 'price_per_unit'
                        "price_per_unit": float(row.price),  # Keep for backward compatibility
                        "unit": unit_display or "unit",  # Fallback to 'unit' if missing
                        "unit_id": row.unit_id,
                        "currency": currency_symbol or "EGP",
                        "currency_id": row.currency_id,
                        "category": category_display or query.title(),
                        "category_id": row.category_id,
                        "source_query": query,  # Track the query that found this material
                        "brand": brand,
                        "specifications": specifications,
                        "code": code,
                        "db_description": db_description_json
                    }
                    materials.append(material_data)
                    query_to_materials[query].append(material_data)

            logger.info(f"Fetched {len(materials)} materials from database")
            return materials

        except Exception as e:
            logger.error(f"Error fetching materials from DB: {e}", exc_info=True)
            return []
        finally:
            db.close()
    
    def _fetch_labor_rates_from_db(self, labor_queries: List[str], language: str = "en", fallback_rates: dict = None) -> List[Dict[str, Any]]:
        """
        Fetch labor rates from database based on queries from Qdrant.
        Uses PostgreSQL multilingual search function.
        NOTE: sync — call via asyncio.to_thread() from async context.

        Args:
            labor_queries: List of labor role search queries
            language: Language preference ('en' or 'ar')
            fallback_rates: Pre-fetched dict of fallback rates (keys are role keywords, values are float rates)

        Returns list of labor rates.
        """
        if fallback_rates is None:
            fallback_rates = {}
        db = SessionLocal()
        try:
            labor_rates = []
            seen_ids = set()

            for query in labor_queries:
                # Use PostgreSQL multilingual search function
                # Increased limit from 3 to 5 to find more labor roles
                result = db.execute(
                    text("""
                        SELECT * FROM search_labor_rates_multilingual(
                            :query,
                            :language,
                            NULL,  -- category_id (optional filter)
                            5      -- limit (increased to find more labor roles)
                        )
                    """),
                    {"query": query, "language": language}
                )
                
                rows = result.fetchall()
                
                for row in rows:
                    # Skip duplicates
                    if row.id in seen_ids:
                        continue
                    seen_ids.add(row.id)
                    
                    # Get related data
                    labor = db.query(LaborRate).filter(LaborRate.id == row.id).first()
                    if not labor:
                        continue
                    
                    # Get currency symbol
                    currency_symbol = None
                    if labor.currency:
                        currency_symbol = labor.currency.symbol
                    
                    # Extract display name from JSONB
                    role_display = row.role_ar if language == "ar" else row.role_en
                    
                    if row.hourly_rate:
                        hourly_rate = float(row.hourly_rate)
                    else:
                        role_lower = str(row.role_en or "").lower()
                        hourly_rate = next(
                            (float(v) for k, v in fallback_rates.items() if k in role_lower),
                            float(fallback_rates.get("default", 50.0))
                        )

                    labor_rates.append({
                        "role": role_display,  # Display name for compatibility
                        "role_bilingual": {
                            "en": row.role_en,
                            "ar": row.role_ar
                        },
                        "hourly_rate": hourly_rate,
                        "daily_rate": float(row.daily_rate) if row.daily_rate else None,
                        "currency": currency_symbol or "EGP",
                        "currency_id": row.currency_id,
                        "skill_level": row.skill_level,
                        "category_id": row.category_id,
                        "db_description": labor.description # JSONB
                    })

            logger.info(f"Fetched {len(labor_rates)} labor rates from database")
            return labor_rates

        except Exception as e:
            logger.error(f"Error fetching labor rates from DB: {e}", exc_info=True)
            return []
        finally:
            db.close()
    
    
    async def _get_default_labor_rate(self, role: str) -> float:
        """Provide fallback rates for common roles if DB is missing data."""
        config = get_config_service()
        rates = await config.get_config("fallback_labor_rates")
        if not rates or not isinstance(rates, dict):
            return 50.0
        role_lower = str(role).lower()
        for key, rate in rates.items():
            if key in role_lower:
                return float(rate)
        return float(rates.get("default", 50.0))

    async def _deduplicate_materials(
        self,
        materials: List[Dict[str, Any]],
        quality_tier: str = "standard",
        project_description: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Smart deduplication: removes exact duplicates AND limits similar items per category.

        Rules:
        1. Remove exact name duplicates (case-insensitive)
        2. For each material type, keep only the best match based on quality tier
           - Tiles: 1 item (selects best match: economy/standard/premium)
           - Stone: 1 item (selects best match based on quality)
           - Paint: 2 items (may need base + finish coat)
           - Other types: varies (see MAX_PER_TYPE)
        3. Prefer items matching the requested quality tier
        4. Handle mutually exclusive flooring: If user explicitly requests marble/stone,
           remove all ceramic tiles (and vice versa)

        Args:
            materials: List of material dicts
            quality_tier: 'economy', 'standard', or 'premium' (used for selection)
            project_description: Project description to detect explicit flooring preferences
        """
        if not materials:
            return []

        quality_tier = quality_tier.lower()
        desc_lower = project_description.lower() if project_description else ""
        config = get_config_service()

        # Step 1: Remove exact duplicates
        seen_names = set()
        unique_materials = []

        for material in materials:
            name = material.get("name", "")
            if isinstance(name, dict):
                name = name.get("en", "") or name.get("ar", "")

            name_lower = str(name).lower().strip()

            if name_lower in seen_names or not name_lower:
                continue

            seen_names.add(name_lower)
            unique_materials.append(material)

        # Step 2: Detect explicit flooring preferences from user input
        flooring_prefs = await config.get_category_keywords("flooring_preference")
        stone_kws = flooring_prefs.get("stone", ["رخام", "marble", "granite", "جرانيت"])
        tiles_kws = flooring_prefs.get("tiles", ["سيراميك", "ceramic", "porcelain", "بلاط"])
        wood_kws = flooring_prefs.get("wood", ["خشب", "wood", "parquet", "باركيه"])
        user_wants_stone = any(kw in desc_lower for kw in stone_kws)
        user_wants_tiles = any(kw in desc_lower for kw in tiles_kws)
        user_wants_wood = any(kw in desc_lower for kw in wood_kws)

        # Step 3: Group by material type and limit similar items
        # Load from config service
        TYPE_KEYWORDS = await config.get_category_keywords("material_type")
        MAX_PER_TYPE = await config.get_config("max_per_material_type") or {
            "tiles": 1, "stone": 1, "paint": 2, "plaster": 1,
            "cement": 1, "steel": 1, "wood": 1, "pipes": 2,
            "electrical": 2, "glass": 1, "brick": 1, "vinyl": 1, "default": 2
        }

        def get_material_type(material: Dict) -> str:
            """Detect material type from name."""
            return detect_material_group(material.get("name", ""), TYPE_KEYWORDS)

        def matches_quality(material: Dict, quality: str) -> bool:
            """Check if material matches quality tier."""
            name = material.get("name", "")
            if isinstance(name, dict):
                name = name.get("en", "")
            name_lower = str(name).lower()
            return quality in name_lower

        # Group by type
        by_type = {}
        for material in unique_materials:
            mat_type = get_material_type(material)
            if mat_type not in by_type:
                by_type[mat_type] = []
            by_type[mat_type].append(material)

        # Step 4: Handle mutually exclusive flooring preferences
        # If user explicitly requested stone, remove all tiles (and vice versa)
        if user_wants_stone:
            # Remove tiles when stone is requested
            if "tiles" in by_type:
                logger.info(f"User requested stone/marble - removing {len(by_type['tiles'])} ceramic tile options")
                del by_type["tiles"]
        elif user_wants_tiles:
            # Remove stone when tiles are requested
            if "stone" in by_type:
                logger.info(f"User requested ceramic tiles - removing {len(by_type['stone'])} stone options")
                del by_type["stone"]
        
        # If user requested wood, remove tiles and stone
        if user_wants_wood:
            if "tiles" in by_type:
                logger.info(f"User requested wood - removing {len(by_type['tiles'])} ceramic tile options")
                del by_type["tiles"]
            if "stone" in by_type:
                logger.info(f"User requested wood - removing {len(by_type['stone'])} stone options")
                del by_type["stone"]

        # Step 5: Select best items per type
        final_materials = []
        for mat_type, items in by_type.items():
            max_items = MAX_PER_TYPE.get(mat_type, MAX_PER_TYPE["default"])

            if len(items) <= max_items:
                final_materials.extend(items)
            else:
                # Prioritize: 1) matching quality tier, 2) first items
                matching = [m for m in items if matches_quality(m, quality_tier)]
                non_matching = [m for m in items if not matches_quality(m, quality_tier)]

                selected = matching[:max_items]
                if len(selected) < max_items:
                    selected.extend(non_matching[:max_items - len(selected)])

                final_materials.extend(selected)

        logger.info(f"Deduplication: {len(materials)} -> {len(unique_materials)} unique -> {len(final_materials)} final (limited per type)")
        return final_materials

    async def _get_item_breakdown(self, item_name: str, category: str, total_price: float, language: str = "en") -> List[Dict[str, Any]]:
        """
        Split a single unit price into standard construction components based on industry norms.
        """
        config = get_config_service()
        category = category or "General"

        active_split = await config.get_cost_splits(category)
        labels = await config.get_split_labels()

        breakdown = []
        for key, percentage in active_split.items():
            lbl = labels.get(key, {"en": key.title(), "ar": key})
            label_en = lbl.get("en", key.title()) if isinstance(lbl, dict) else key.title()
            label_ar = lbl.get("ar", key) if isinstance(lbl, dict) else key
            label = f"{label_en} / {label_ar}" if language == "bilingual" else (label_ar if language == "ar" else label_en)

            breakdown.append({
                "component": key,
                "label": label,
                "percentage": percentage * 100,
                "price": round(total_price * percentage, 2)
            })

        return breakdown

    async def execute(self, quotation: Quotation, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate construction costs using Qdrant knowledge + database pricing.

        Process:
        1. Query Qdrant to understand what materials/labor are needed
        2. Fetch actual pricing from PostgreSQL database
        3. Calculate costs based on project size and real prices
        """

        extracted_data = context.get("extracted_data", {})

        # Use bilingual mode for professional exports as requested
        language = "bilingual"

        # Get size - only sqm is used in Egypt
        size_sqm = extracted_data.get("size_sqm")
        project_type = extracted_data.get("project_type", "residential")

        logger.info(f"Calculating costs for {size_sqm} sqm {project_type} project (Bilingual Mode)")

        # Step 1: Query Qdrant to understand requirements
        requirements = await self._query_qdrant_for_requirements(extracted_data)
        material_queries = requirements.get("materials", [])
        labor_queries = requirements.get("labor", [])

        # Step 2: Fetch pricing from database
        # Pre-fetch fallback rates (async) before running sync DB methods in a thread.
        import asyncio
        _config = get_config_service()
        _fallback_rates = await _config.get_config("fallback_labor_rates") or {}

        materials = await asyncio.to_thread(self._fetch_materials_from_db, material_queries, "en")
        labor_rates = await asyncio.to_thread(self._fetch_labor_rates_from_db, labor_queries, "en", _fallback_rates)

        # Deduplicate materials based on project quality preference
        # Try to infer quality from requirements or extracted info
        quality_pref = extracted_data.get("finish_quality", "standard")
        if not quality_pref: 
             # heuristic: check description for keywords
             desc_lower = quotation.project_description.lower()
             if "lux" in desc_lower or "premium" in desc_lower or "high" in desc_lower:
                 quality_pref = "premium"
             elif "economy" in desc_lower or "budget" in desc_lower or "cheap" in desc_lower:
                 quality_pref = "economy"
             else:
                 quality_pref = "standard"
                 
        materials = await self._deduplicate_materials(materials, quality_pref, quotation.project_description or "")

        # Step 3: Calculate material costs (room-aware)
        material_items = []
        total_material_cost = 0

        from app.utils.quotation_descriptions import get_category_description, get_material_description, load_description_config
        from app.services.qdrant_service import get_qdrant_service

        # Pre-load description config (async → sync functions)
        desc_cfg = await load_description_config()

        # Get Qdrant service for knowledge retrieval
        qdrant_service = get_qdrant_service()

        # Get phase information (use Arabic for context internal)
        phase_info = await self._verify_and_enrich_phases(
            extracted_data.get("current_finish_level") or "plastered",
            extracted_data.get("target_finish_level") or "fully_finished",
            project_type,
            "ar"
        )

        # Build room breakdown for room-aware quantities
        room_breakdown = await self._distribute_areas_to_rooms(extracted_data)
        logger.info(
            f"Room breakdown: {len(room_breakdown)} spaces, "
            f"types: {[r['room_type'] for r in room_breakdown]}"
        )

        for material in materials:
            name = material.get("name") or "Material"
            if isinstance(name, dict):
                name = name.get("en", "Material")

            name = str(name)
            name_lower = name.lower()

            category = material.get("category") or "General"
            if isinstance(category, dict):
                category = category.get("en", "General")

            category = str(category)
            category_lower = category.lower()

            # Detect material type for room multiplier lookup
            mat_type = detect_material_type(name, category)

            # Accumulate quantity across all rooms using room-specific multipliers
            quantity = 0.0
            if mat_type == "door":
                quantity = size_sqm * 0.05
            elif mat_type == "ceiling":
                quantity = size_sqm * 1.0
            else:
                for room in room_breakdown:
                    rtype = room["room_type"]
                    rarea = room["area_sqm"]
                    mult = await self._get_room_material_multiplier(rtype, mat_type)
                    quantity += rarea * mult
            unit_price = material.get("price") or material.get("price_per_unit", 0)
            item_cost = quantity * unit_price
            unit = material.get("unit", "sqm")
            if isinstance(unit, dict):
                unit = unit.get("en", "sqm")

            # Generate dynamic professional description (BILINGUAL)
            try:
                description = get_material_description(
                    material=material,
                    quantity=quantity,
                    unit=unit,
                    phase_context=phase_info,
                    project_type=project_type,
                    language="bilingual",
                    qdrant_service=qdrant_service,
                    conversation_context=quotation.project_description,
                    cfg=desc_cfg,
                )
            except Exception as e:
                logger.warning(f"Error generating material description, using fallback: {e}")
                description = get_category_description(
                    category=category,
                    item_name=name,
                    quantity=quantity,
                    unit=unit,
                    language="bilingual",
                    conversation_context=quotation.project_description,
                    cfg=desc_cfg,
                )

            # Generate itemized price breakdown
            price_breakdown = await self._get_item_breakdown(name, category, unit_price, language="bilingual")

            material_items.append({
                "name": name,
                "description": description,
                "quantity": round(quantity, 2),
                "unit": unit,
                "unit_price": round(unit_price, 2),
                "total": round(item_cost, 2),
                "category": category,
                "price_breakdown": price_breakdown # Pass to export generators
            })

            total_material_cost += item_cost

        # Step 4: Calculate labor costs (room-aware)
        labor_trades = []
        total_labor_cost = 0

        # Load trade multipliers from config service
        config = get_config_service()
        project_type_lower = project_type.lower() if project_type else "residential"
        if any(kw in project_type_lower for kw in ["bank", "office", "commercial", "تجاري"]):
            trade_type = "commercial"
        elif any(kw in project_type_lower for kw in ["factory", "مصنع", "industrial"]):
            trade_type = "factory"
        else:
            trade_type = "residential"
        multipliers = await config.get_trade_multipliers(trade_type)

        # Finishing level adjustment from config
        finishing_adjustment = 1.0
        target_finish = (extracted_data.get("target_finish_level") or "").lower()
        luxury_kws = await config.get_config("finishing_keywords_luxury") or ["luxury", "فاخر"]
        premium_kws = await config.get_config("finishing_keywords_premium") or ["premium", "ممتاز"]
        economy_kws = await config.get_config("finishing_keywords_economy") or ["economy", "اقتصادي"]
        if any(kw in target_finish for kw in luxury_kws):
            finishing_adjustment = await config.get_config("finishing_adjustment_luxury") or 1.4
        elif any(kw in target_finish for kw in premium_kws):
            finishing_adjustment = await config.get_config("finishing_adjustment_premium") or 1.2
        elif any(kw in target_finish for kw in economy_kws):
            finishing_adjustment = await config.get_config("finishing_adjustment_economy") or 0.8

        if labor_rates:
            for labor in labor_rates:
                role = labor.get("role")
                if isinstance(role, dict):
                    role = role.get("en", "")

                role_lower = str(role).lower()

                # Find the matching trade key for base multiplier
                matched_trade_key = "default"
                trade_multiplier = multipliers.get("default", 1.0)
                for trade_key in multipliers.keys():
                    if trade_key != "default" and trade_key in role_lower:
                        trade_multiplier = multipliers[trade_key]
                        matched_trade_key = trade_key
                        break

                # Room-aware: accumulate hours across rooms
                role_hours = 0.0
                for room in room_breakdown:
                    rtype = room["room_type"]
                    rarea = room["area_sqm"]
                    room_labor_mult = await self._get_room_labor_multiplier(
                        rtype, matched_trade_key
                    )
                    role_hours += rarea * trade_multiplier * room_labor_mult

                role_hours *= finishing_adjustment

                hourly_rate = labor.get("hourly_rate", 0)
                if hourly_rate is None:
                    hourly_rate = 0
                role_cost = role_hours * hourly_rate

                # Bilingual labor description
                en_desc = f"Lump sum work for {role} at the site, including everything necessary to complete the work fully according to technical specifications."
                ar_desc = f"بالمقطوعية اعمال {role} للموقع تشمل كل ما يلزم لنهو العمل كاملاً طبقاً للمواصفات الفنية وأصول الصناعة."
                description = f"{en_desc}\n/ {ar_desc}"

                labor_trades.append({
                    "name": f"Labor: {role}",
                    "description": description,
                    "trade": role,
                    "quantity": round(role_hours, 1),
                    "unit": "hours",
                    "unit_price": round(hourly_rate, 2),
                    "total": round(role_cost, 2)
                })

                total_labor_cost += role_cost

        logger.info(f"Labor calculation: {len(labor_trades)} trades, total cost: {total_labor_cost:.2f} EGP")

        # Step 5: Calculate total using config-driven percentages
        contingency_pct = await config.get_config("contingency_percentage") or 0.10
        markup_pct = await config.get_config("markup_percentage") or 0.10
        overhead_split = await config.get_config("markup_overhead_split") or 0.5

        subtotal = total_material_cost + total_labor_cost
        contingency = subtotal * contingency_pct
        markup = subtotal * markup_pct
        total_cost = subtotal + contingency + markup

        cost_breakdown = {
            "materials": {
                "subtotal": round(total_material_cost, 2),
                "percentage": round((total_material_cost / total_cost) * 100, 1) if total_cost > 0 else 0,
                "items": material_items
            },
            "labor": {
                "subtotal": round(total_labor_cost, 2),
                "percentage": round((total_labor_cost / total_cost) * 100, 1) if total_cost > 0 else 0,
                "trades": labor_trades
            },
            "contingency": {
                "subtotal": round(contingency, 2),
                "percentage": round(contingency_pct * 100, 1),
                "rationale": "Standard contingency for construction projects"
            },
            "markup": {
                "subtotal": round(markup, 2),
                "percentage": round(markup_pct * 100, 1),
                "breakdown": {
                    "overhead": round(markup * overhead_split, 2),
                    "profit": round(markup * (1 - overhead_split), 2)
                }
            }
        }

        return {
            "cost_breakdown": cost_breakdown,
            "total_cost": round(total_cost, 2),
            "currency": self.currency_symbol,
            "size_sqm": round(size_sqm, 2),
            "materials_count": len(materials),
            "labor_roles_count": len(labor_rates),
            "confidence_interval": {
                "low": round(total_cost * 0.9, 2),
                "high": round(total_cost * 1.1, 2),
                "confidence_level": 0.85
            }
        }


