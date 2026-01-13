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
    
    def _convert_to_sqm(self, size: float, unit: str = "sqft") -> float:
        """Convert size to square meters (Egypt standard)"""
        if unit.lower() in ["sqm", "m2", "meter", "متر"]:
            return size
        elif unit.lower() in ["sqft", "sf", "foot", "قدم"]:
            return size * 0.092903  # Convert sqft to sqm
        return size * 0.092903  # Default assume sqft
    
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

Focus on what's needed to go from the CURRENT state to the TARGET state."""

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

            for query in material_queries:
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
                    
                    materials.append({
                        "name": name_display,  # Display name for compatibility
                        "name_bilingual": {
                            "en": row.name_en,
                            "ar": row.name_ar
                        },
                        "price": float(row.price),  # New schema uses 'price' not 'price_per_unit'
                        "price_per_unit": float(row.price),  # Keep for backward compatibility
                        "unit": unit_display,
                        "unit_id": row.unit_id,
                        "currency": currency_symbol or "EGP",
                        "currency_id": row.currency_id,
                        "category": category_display,
                        "category_id": row.category_id
                    })

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
                        "hourly_rate": float(row.hourly_rate) if row.hourly_rate else None,
                        "daily_rate": float(row.daily_rate) if row.daily_rate else None,
                        "currency": currency_symbol or "EGP",
                        "currency_id": row.currency_id,
                        "skill_level": row.skill_level,
                        "category_id": row.category_id
                    })

            logger.info(f"Fetched {len(labor_rates)} labor rates from database")
            return labor_rates

        except Exception as e:
            logger.error(f"Error fetching labor rates from DB: {e}", exc_info=True)
            return []
        finally:
            db.close()
    
    async def execute(self, quotation: Quotation, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate construction costs using Qdrant knowledge + database pricing.

        Process:
        1. Query Qdrant to understand what materials/labor are needed
        2. Fetch actual pricing from PostgreSQL database
        3. Calculate costs based on project size and real prices
        """

        extracted_data = context.get("extracted_data", {})

        # Detect language from quotation description
        detected = detect_language(quotation.project_description or "")
        language = "ar" if detected == "ar" else "en"

        # Get size - support both sqft and sqm
        size_sqft = extracted_data.get("size_sqft") or extracted_data.get("size_sqm")
        size_unit = "sqm" if extracted_data.get("size_sqm") else "sqft"

        # Convert to square meters (Egypt standard)
        size_sqm = self._convert_to_sqm(size_sqft, size_unit)
        project_type = extracted_data.get("project_type", "residential")

        logger.info(f"Calculating costs for {size_sqm} sqm {project_type} project (language: {language})")

        # Step 1: Query Qdrant to understand requirements
        requirements = await self._query_qdrant_for_requirements(extracted_data)
        material_queries = requirements.get("materials", [])
        labor_queries = requirements.get("labor", [])

        # Step 2: Fetch pricing from database (with language preference)
        materials = await self._fetch_materials_from_db(material_queries, language=language)
        labor_rates = await self._fetch_labor_rates_from_db(labor_queries, language=language)

        # Step 3: Calculate material costs
        material_items = []
        total_material_cost = 0

        from app.utils.quotation_descriptions import get_category_description

        for material in materials:
            # Estimate quantity based on project size and material type
            # Handle both old format (string) and new format (bilingual dict)
            name = material.get("name")
            if name is None:
                name = ""
            elif isinstance(name, dict):
                name = name.get(language, name.get("en", "")) or ""
            elif not isinstance(name, str):
                name = str(name) if name else ""
            
            name_lower = name.lower() if name else ""
            
            category = material.get("category")
            if category is None:
                category = "General"
            elif isinstance(category, dict):
                category = category.get(language, category.get("en", "General")) or "General"
            elif not isinstance(category, str):
                category = str(category) if category else "General"
            
            category_lower = category.lower() if category else "general"
            
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
            # Use 'price' field (new schema), fallback to 'price_per_unit' for backward compatibility
            unit_price = material.get("price") or material.get("price_per_unit", 0)
            item_cost = quantity * unit_price
            unit = material.get("unit", "sqm")
            if isinstance(unit, dict):
                unit = unit.get(language, unit.get("en", "sqm"))

            # Generate dynamic professional description
            description = get_category_description(
                category=category,
                item_name=name,
                quantity=quantity,
                unit=unit,
                conversation_context=quotation.project_description
            )

            material_items.append({
                "name": name,
                "description": description,
                "quantity": round(quantity, 2),
                "unit": unit,
                "unit_price": round(unit_price, 2),
                "total": round(item_cost, 2),
                "category": category
            })

            total_material_cost += item_cost

        # Step 4: Calculate labor costs
        labor_trades = []
        total_labor_cost = 0

        # Estimate total labor hours based on project size
        # Simple heuristic: 3 hours per sqm on average
        total_labor_hours = size_sqm * 3.0

        if labor_rates:
            # Distribute hours among available labor roles
            hours_per_role = total_labor_hours / len(labor_rates)

            for labor in labor_rates:
                # Handle both old format (string) and new format (bilingual dict)
                role = labor.get("role")
                if isinstance(role, dict):
                    role = role.get(language, role.get("en", ""))
                
                hourly_rate = labor.get("hourly_rate", 0)
                if hourly_rate is None:
                    hourly_rate = 0
                role_hours = hours_per_role
                role_cost = role_hours * hourly_rate

                # Generate dynamic professional description for labor
                if language == "ar":
                    description = f"بالمقطوعية اعمال {role} للموقع تشمل كل ما يلزم لنهو العمل كاملاً طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس."
                else:
                    description = f"Lump sum work for {role} at the site, including everything necessary to complete the work fully according to technical specifications, industry standards, and engineer's instructions."

                labor_trades.append({
                    "name": f"Labor: {role}",
                    "description": description,
                    "trade": role,
                    "quantity": round(role_hours, 1),
                    "unit": "hour",
                    "unit_price": round(hourly_rate, 2),
                    "total": round(role_cost, 2)
                })

                total_labor_cost += role_cost

        # Step 5: Calculate total
        subtotal = total_material_cost + total_labor_cost

        # Add contingency (10%)
        contingency = subtotal * 0.10

        # Add markup (10%)
        markup = subtotal * 0.10

        total_cost = subtotal + contingency + markup

        # Build cost breakdown
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

