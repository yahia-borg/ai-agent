from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.models.quotation import Quotation
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.agents.llm_client import get_llm_client
from app.models.project_data import ConstructionRequirements
from app.utils.language_detector import detect_language
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
    
    
    def _extract_keywords_from_list(self, items: List[str]) -> List[str]:
        """
        Extract simple keywords from verbose LLM responses.
        Aggressively strips modifiers, markdown, and extracts core material/role names.
        """
        import re
        keywords = []
        
        # Common modifiers to strip (both English and Arabic)
        material_modifiers = [
            'luxury', 'high-end', 'high end', 'premium', 'standard', 'basic',
            'commercial', 'residential', 'industrial', 'fireproof', 'fire proof',
            'smart', 'automatic', 'manual', 'semi', 'full', 'partial',
            'مميز', 'فاخر', 'عادي', 'تجاري', 'سكني'
        ]
        
        role_modifiers = [
            'luxury', 'high-end', 'premium', 'skilled', 'certified', 'licensed',
            'senior', 'junior', 'chief', 'head', 'assistant', 'apprentice',
            'فني', 'ماهر', 'مرخص', 'رئيسي'
        ]
        
        for item in items:
            if not item or not isinstance(item, str):
                continue
            
            # Remove markdown formatting
            text = re.sub(r'\*\*|__|\*|_|`|#', '', item)
            text = re.sub(r'^\d+\.\s*', '', text)
            text = re.sub(r'^[-•]\s*', '', text)
            text = re.sub(r'\([^)]*\)', '', text)  # Remove parentheses content (e.g., "(plasterer)")
            text = re.sub(r'\[.*?\]', '', text)
            text = re.sub(r'\{.*?\}', '', text)
            text = re.sub(r'/.*', '', text)  # Remove everything after slash (e.g., "marble/granite" → "marble")
            
            # Split by common separators
            parts = re.split(r'[:;,\n\-–—]', text)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                # Extract words (handle both English and Arabic)
                words = re.findall(r'[\u0600-\u06FF]+|[a-zA-Z]+', part)
                if not words:
                    continue
                
                # Remove modifiers
                filtered_words = []
                for word in words:
                    word_lower = word.lower()
                    if word_lower not in material_modifiers and word_lower not in role_modifiers:
                        filtered_words.append(word)
                
                if filtered_words:
                    # Take first 1-2 words (not 3) to keep keywords short
                    keyword = ' '.join(filtered_words[:2]).strip()
                    if len(keyword) > 2 and keyword not in keywords:
                        keywords.append(keyword)
                        if len(keywords) >= 25:  # Increased limit for better coverage
                            break
        
        # Deduplicate and return
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)
        
        return unique_keywords[:25]

    async def _verify_and_enrich_phases(
        self,
        current_finish: str,
        target_finish: str,
        project_type: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Query Qdrant to verify and enrich phase information.
        
        Args:
            current_finish: Current finish level (e.g., "plastered", "on_plaster")
            target_finish: Target finish level (e.g., "fully_finished", "turnkey")
            project_type: Type of project (e.g., "residential", "commercial")
            language: Language preference ('en' or 'ar')
        
        Returns:
            Dictionary with enriched phase information:
            {
                "current_phase": {
                    "name": "plastered",
                    "arabic_name": "على المحارة",
                    "description": "...",
                    "status": "...",
                    "completed_work": [],
                    "missing_work": []
                },
                "target_phase": {
                    "name": "fully_finished",
                    "arabic_name": "تشطيب كامل",
                    "description": "...",
                    "required_work": [],
                    "materials_needed": []
                }
            }
        """
        try:
            from app.services.qdrant_service import get_qdrant_service
            qdrant = get_qdrant_service()
            
            # Map finish levels to phase numbers for querying
            phase_mapping = {
                "bare_concrete": "1",
                "red_brick": "1",
                "half_finished": "2",
                "semi_finished": "2",
                "plastered": "2",
                "on_plaster": "3",
                "fully_finished": "4",
                "turnkey": "4"
            }
            
            current_phase_num = phase_mapping.get(current_finish, "2")
            target_phase_num = phase_mapping.get(target_finish, "4")
            
            # Query 1: Current phase information
            current_phase_query = f"Phase {current_phase_num} {current_finish} {project_type} status requirements"
            current_phase_results = qdrant.search_knowledge(current_phase_query, top_k=3)
            
            # Query 2: Target phase information
            target_phase_query = f"Phase {target_phase_num} {target_finish} {project_type} requirements materials"
            target_phase_results = qdrant.search_knowledge(target_phase_query, top_k=3)
            
            # Extract phase information from results
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
            
            # Extract from current phase results
            if current_phase_results:
                current_phase_info["description"] = "\n".join([r.get("content", "")[:200] for r in current_phase_results[:2]])
                # Try to extract Arabic name from topic
                for result in current_phase_results:
                    topic = result.get("topic", "")
                    arabic_match = re.search(r'\(([^)]+)\)', topic)
                    if arabic_match and any(ord(c) > 127 for c in arabic_match.group(1)):
                        current_phase_info["arabic_name"] = arabic_match.group(1)
                        break
            
            # Extract from target phase results
            if target_phase_results:
                target_phase_info["description"] = "\n".join([r.get("content", "")[:200] for r in target_phase_results[:2]])
                # Try to extract Arabic name from topic
                for result in target_phase_results:
                    topic = result.get("topic", "")
                    arabic_match = re.search(r'\(([^)]+)\)', topic)
                    if arabic_match and any(ord(c) > 127 for c in arabic_match.group(1)):
                        target_phase_info["arabic_name"] = arabic_match.group(1)
                        break
            
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

    async def _query_qdrant_for_requirements(self, extracted_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Query Qdrant knowledge base and use LLM to determine specific requirements.
        """
        try:
            from app.services.qdrant_service import get_qdrant_service

            current_finish = extracted_data.get("current_finish_level", "plastered")
            target_finish = extracted_data.get("target_finish_level", "fully_finished")
            project_type = extracted_data.get("project_type", "residential")

            # Phase 1: Knowledge Retrieval
            query = f"Detailed technical standards, phases, and specific material/labor lists for {project_type} "
            query += f"transition from {current_finish} to {target_finish}."

            logger.info(f"Retrieving standards for: {current_finish} -> {target_finish}")

            qdrant = get_qdrant_service()
            results = qdrant.search_knowledge(query, top_k=5)
            
            knowledge_context = "\n\n".join([
                f"Topic: {r.get('topic')}\nContent: {r.get('content')}" 
                for r in results
            ])

            # Phase 2: LLM Interpretation
            system_prompt = """You are a technical construction expert for the Egyptian market.
Based on the provided snippets from our knowledge base (Egyptian codes and standards), 
extract a structured list of specific materials and labor roles required for the given project transition.

CRITICAL: Return ONLY simple keywords/phrases (1-3 words each), NOT full descriptions or markdown formatting.
Examples of GOOD responses:
- Materials: ["cement", "steel bars", "gypsum board", "ceramic tiles", "paint"]
- Labor: ["mason", "electrician", "plumber", "tiler", "painter"]

Examples of BAD responses (DO NOT DO THIS):
- Materials: ["1. **Structural & Reinforcement Materials** (Compliance: ECP 203-2020): - B500DWR steel reinforcement bars"]
- Labor: ["**A. Technical Oversight Roles:** - Contract Supervising Engineer: Licensed from Engineers' Syndicate"]

Focus on what's needed to go from the CURRENT state to the TARGET state.
IF current state is 'plastered' or 'on_plaster', DO NOT include structural materials like 'steel', 'concrete', 'bricks', or 'cement' (unless for tiling mortar)."""

            prompt = f"""
PROJECT CONTEXT:
- Type: {project_type}
- Transition: {current_finish} TO {target_finish}

KNOWLEDGE BASE SNIPPETS:
\"\"\"
{knowledge_context}
\"\"\"

Extract ONLY simple keywords for materials and labor roles needed for THIS SPECIFIC transition.
Return each item as a short keyword (1-3 words), NOT full descriptions or markdown.
"""

            requirements = await self.llm.invoke_structured(
                prompt=prompt,
                schema=ConstructionRequirements,
                system_prompt=system_prompt
            )

            logger.info(f"LLM extracted requirements: {requirements.dict()}")

            # Extract keywords from verbose responses
            materials = self._extract_keywords_from_list(requirements.materials)
            labor = self._extract_keywords_from_list(requirements.labor)
            
            # Log extracted keywords for debugging
            logger.info(f"Extracted material keywords: {materials}")
            logger.info(f"Extracted labor keywords: {labor}")

            return {
                "materials": materials,
                "labor": labor
            }

        except Exception as e:
            logger.warning(f"Error in intelligent requirement extraction: {e}. Using basic fallback.")
            return {
                "materials": ["cement", "sand", "tile", "paint", "plaster", "wiring", "pipes"],
                "labor": ["mason", "electrician", "plumber", "painter", "tiler"]
            }
    
    async def _fetch_materials_from_db(self, material_queries: List[str], language: str = "en") -> List[Dict[str, Any]]:
        """
        Fetch materials from database based on queries from Qdrant.
        Uses PostgreSQL multilingual search function.

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
                        "category": category_display or _detect_category_from_query(query),
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
    
    async def _fetch_labor_rates_from_db(self, labor_queries: List[str], language: str = "en") -> List[Dict[str, Any]]:
        """
        Fetch labor rates from database based on queries from Qdrant.
        Uses PostgreSQL multilingual search function.

        Args:
            labor_queries: List of labor role search queries
            language: Language preference ('en' or 'ar')

        Returns list of labor rates.
        """
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
                    
                    labor_rates.append({
                        "role": role_display,  # Display name for compatibility
                        "role_bilingual": {
                            "en": row.role_en,
                            "ar": row.role_ar
                        },
                        "role_bilingual": {
                            "en": row.role_en,
                            "ar": row.role_ar
                        },
                        "hourly_rate": float(row.hourly_rate) if row.hourly_rate else self._get_default_labor_rate(row.role_en),
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
    
    
    def _get_default_labor_rate(self, role: str) -> float:
        """Provide fallback rates for common roles if DB is missing data."""
        role_lower = str(role).lower()
        if "engineer" in role_lower: return 150.0  # Supervising engineer
        if "electrician" in role_lower: return 60.0
        if "plumber" in role_lower: return 60.0
        if "tiler" in role_lower: return 70.0
        if "painter" in role_lower: return 55.0
        if "carpenter" in role_lower: return 65.0
        if "mason" in role_lower: return 60.0
        if "labor" in role_lower or "helper" in role_lower: return 40.0
        return 50.0  # Generic fallback

    def _deduplicate_materials(
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
        # Check if user explicitly requested marble/stone or ceramic/tiles
        user_wants_stone = any(kw in desc_lower for kw in ["رخام", "marble", "granite", "جرانيت", "عايز رخام", "want marble", "عايز جرانيت"])
        user_wants_tiles = any(kw in desc_lower for kw in ["سيراميك", "ceramic", "porcelain", "بلاط", "عايز سيراميك", "want ceramic", "want tile"])
        user_wants_wood = any(kw in desc_lower for kw in ["خشب", "wood", "parquet", "باركيه", "عايز خشب", "want wood"])

        # Step 3: Group by material type and limit similar items
        # Define material type keywords for grouping
        TYPE_KEYWORDS = {
            "tiles": ["tile", "ceramic", "porcelain", "floor tile", "بلاط", "سيراميك", "بورسلين"],
            "stone": ["marble", "granite", "رخام", "جرانيت"],  # Separate from tiles
            "paint": ["paint", "emulsion", "coating", "دهان", "طلاء"],
            "plaster": ["plaster", "skim", "محارة", "بياض"],
            "cement": ["cement", "أسمنت"],
            "steel": ["steel", "iron", "rebar", "حديد"],
            "wood": ["wood", "timber", "parquet", "خشب", "باركيه"],
            "pipes": ["pipe", "diameter", "مواسير", "قطر"],
            "electrical": ["cable", "wire", "switch", "كهرباء", "سلك"],
            "glass": ["glass", "زجاج"],
            "brick": ["brick", "block", "طوب", "بلوك"],
            "vinyl": ["vinyl", "فينيل"],
        }

        # Max items per type - flooring materials limited to 1 when user specifies
        MAX_PER_TYPE = {
            "tiles": 1,  # Only one ceramic type per quotation - select best match
            "stone": 1,  # Only one stone type per quotation - select best match
            "paint": 2,
            "plaster": 1,
            "cement": 1,
            "steel": 1,
            "wood": 1,  # Only one wood type per quotation
            "pipes": 2,
            "electrical": 2,
            "glass": 1,
            "brick": 1,
            "vinyl": 1,
            "default": 2
        }

        def get_material_type(material: Dict) -> str:
            """Detect material type from name."""
            name = material.get("name", "")
            if isinstance(name, dict):
                name = f"{name.get('en', '')} {name.get('ar', '')}"
            name_lower = str(name).lower()

            for mat_type, keywords in TYPE_KEYWORDS.items():
                if any(kw in name_lower for kw in keywords):
                    return mat_type
            return "other"

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

    def _get_item_breakdown(self, item_name: str, category: str, total_price: float, language: str = "en") -> List[Dict[str, Any]]:
        """
        Split a single unit price into standard construction components based on industry norms.
        """
        category = category or "General"
        cat_lower = str(category).lower()
        
        # Standard splits based on category
        splits = {
            "flooring": {"supply": 0.65, "installation": 0.15, "transport": 0.05, "misc": 0.15},
            "painting": {"supply": 0.45, "installation": 0.35, "transport": 0.05, "misc": 0.15},
            "plastering": {"supply": 0.30, "installation": 0.50, "transport": 0.05, "misc": 0.15},
            "electrical": {"supply": 0.70, "installation": 0.20, "transport": 0.02, "misc": 0.08},
            "plumbing": {"supply": 0.60, "installation": 0.25, "transport": 0.05, "misc": 0.10},
            "default": {"supply": 0.55, "installation": 0.25, "transport": 0.05, "misc": 0.15}
        }
        
        active_split = splits.get(next((k for k in splits if k in cat_lower), "default"))
        
        # Bilingual labels
        labels = {
            "supply": {"en": "Supply", "ar": "توريد"},
            "installation": {"en": "Installation", "ar": "تركيب"},
            "transport": {"en": "Transport & Site Logistics", "ar": "نقل وتشوينات"},
            "misc": {"en": "Sundries & Overheads", "ar": "مصروفات نثربة وهامش ربح"}
        }
        
        breakdown = []
        for key, percentage in active_split.items():
            label_en = labels[key]["en"]
            label_ar = labels[key]["ar"]
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
        materials = await self._fetch_materials_from_db(material_queries, language="en") # Fetch one, logic handles translation
        labor_rates = await self._fetch_labor_rates_from_db(labor_queries, language="en")

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
                 
        materials = self._deduplicate_materials(materials, quality_pref, quotation.project_description or "")

        # Step 3: Calculate material costs
        material_items = []
        total_material_cost = 0

        from app.utils.quotation_descriptions import get_category_description, get_material_description
        from app.services.qdrant_service import get_qdrant_service

        # Get Qdrant service for knowledge retrieval
        qdrant_service = get_qdrant_service()
        
        # Get phase information (use Arabic for context internal)
        phase_info = await self._verify_and_enrich_phases(
            extracted_data.get("current_finish_level", "plastered"),
            extracted_data.get("target_finish_level", "fully_finished"),
            project_type,
            "ar"
        )

        for material in materials:
            # Estimate quantity based on project size and material type
            # Handle both old format (string) and new format (bilingual dict)
            # Use 'en' as key but we'll generate bilingual descriptions
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
            
            # Default multiplier
            multiplier = 1.0
            
            # Refine multipliers based on construction norms
            if "wall" in name_lower or "paint" in name_lower or "plaster" in name_lower or category_lower in ["walls", "painting"]:
                multiplier = 2.8
            elif "ceiling" in name_lower or category_lower == "ceilings":
                multiplier = 1.0
            elif "floor" in name_lower or "tile" in name_lower or "ceramic" in name_lower or "porcelain" in name_lower or "marble" in name_lower or category_lower == "flooring":
                multiplier = 1.1
            elif "door" in name_lower or "window" in name_lower or category_lower == "doors_windows":
                multiplier = 0.05
            
            quantity = size_sqm * multiplier
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
                    conversation_context=quotation.project_description
                )
            except Exception as e:
                logger.warning(f"Error generating material description, using fallback: {e}")
                description = get_category_description(
                    category=category,
                    item_name=name,
                    quantity=quantity,
                    unit=unit,
                    language="bilingual",
                    conversation_context=quotation.project_description
                )

            # Generate itemized price breakdown (NEW)
            price_breakdown = self._get_item_breakdown(name, category, unit_price, language="bilingual")

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

        # Step 4: Calculate labor costs
        labor_trades = []
        total_labor_cost = 0

        # Trade-specific hour multipliers (hours per sqm)
        # Based on Egyptian construction industry standards
        TRADE_MULTIPLIERS = {
            # Residential multipliers
            "residential": {
                "electrician": 1.5,      # Wiring, outlets, switches, lighting
                "plumber": 1.2,          # Pipes, fixtures, sanitary
                "tiler": 2.0,            # Floor + wall tiles
                "painter": 1.8,          # Walls + ceilings (multiple coats)
                "carpenter": 0.8,        # Doors, windows, built-ins
                "mason": 1.0,            # General masonry work
                "plasterer": 1.5,        # Wall + ceiling plastering
                "welder": 0.3,           # Metal work
                "supervisor": 0.5,       # Site supervision
                "default": 1.0
            },
            # Commercial multipliers (banks, offices need more MEP work)
            "commercial": {
                "electrician": 2.5,      # More outlets, data points, security systems
                "plumber": 1.8,          # More fixtures, complex drainage
                "tiler": 2.2,            # Large floor areas
                "painter": 2.0,          # More wall area, premium finishes
                "carpenter": 1.2,        # Partitions, counters, doors
                "mason": 0.8,            # Less masonry in commercial
                "plasterer": 1.8,        # More ceiling work
                "welder": 0.5,           # Metal partitions, security
                "supervisor": 0.8,       # More supervision needed
                "default": 1.2
            },
            # Factory/Industrial
            "factory": {
                "electrician": 3.0,      # Heavy electrical, 3-phase
                "plumber": 1.5,          # Industrial plumbing
                "tiler": 1.0,            # Less tiling
                "painter": 1.2,          # Industrial paint
                "carpenter": 0.5,        # Minimal carpentry
                "mason": 1.5,            # More masonry
                "plasterer": 1.0,        # Basic plastering
                "welder": 2.0,           # Heavy metal work
                "supervisor": 1.0,       # Supervision
                "default": 1.0
            }
        }

        # Get project type multipliers (default to commercial if unknown)
        project_type_lower = project_type.lower() if project_type else "residential"
        if "bank" in project_type_lower or "office" in project_type_lower or "commercial" in project_type_lower or "تجاري" in project_type_lower:
            multipliers = TRADE_MULTIPLIERS["commercial"]
        elif "factory" in project_type_lower or "مصنع" in project_type_lower or "industrial" in project_type_lower:
            multipliers = TRADE_MULTIPLIERS["factory"]
        else:
            multipliers = TRADE_MULTIPLIERS["residential"]

        # Finishing level adjustment
        finishing_adjustment = 1.0
        target_finish = (extracted_data.get("target_finish_level") or "").lower()
        if "luxury" in target_finish or "فاخر" in target_finish:
            finishing_adjustment = 1.4  # Luxury needs more labor hours
        elif "premium" in target_finish or "ممتاز" in target_finish:
            finishing_adjustment = 1.2
        elif "economy" in target_finish or "اقتصادي" in target_finish:
            finishing_adjustment = 0.8

        if labor_rates:
            for labor in labor_rates:
                role = labor.get("role")
                if isinstance(role, dict):
                    role = role.get("en", "")

                role_lower = str(role).lower()

                # Find matching multiplier for this trade
                trade_multiplier = multipliers.get("default", 1.0)
                for trade_key in multipliers.keys():
                    if trade_key in role_lower:
                        trade_multiplier = multipliers[trade_key]
                        break

                # Calculate hours for this trade
                role_hours = size_sqm * trade_multiplier * finishing_adjustment

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

        # Step 5: Calculate total
        subtotal = total_material_cost + total_labor_cost
        contingency = subtotal * 0.10
        markup = subtotal * 0.10
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
                "percentage": 10.0,
                "rationale": "Standard contingency for construction projects"
            },
            "markup": {
                "subtotal": round(markup, 2),
                "percentage": 10.0,
                "breakdown": {
                    "overhead": round(markup * 0.5, 2),
                    "profit": round(markup * 0.5, 2)
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


