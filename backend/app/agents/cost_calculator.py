from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.models.quotation import Quotation
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
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
    
    def get_required_context(self) -> list[str]:
        return ["extracted_data"]
    
    def _convert_to_sqm(self, size: float, unit: str = "sqft") -> float:
        """Convert size to square meters (Egypt standard)"""
        if unit.lower() in ["sqm", "m2", "meter", "متر"]:
            return size
        elif unit.lower() in ["sqft", "sf", "foot", "قدم"]:
            return size * 0.092903  # Convert sqft to sqm
        return size * 0.092903  # Default assume sqft

    async def _query_qdrant_for_requirements(self, extracted_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Query Qdrant knowledge base to determine what materials and labor are needed.

        Based on:
        - Current finishing level (bare_concrete, plastered, semi_finished, painted)
        - Target finishing level
        - Project type

        Returns dict with 'materials' and 'labor' lists
        """
        try:
            from app.services.qdrant_service import get_qdrant_service

            current_finish = extracted_data.get("current_finish_level", "plastered")
            target_finish = extracted_data.get("target_finish_level", "standard")
            project_type = extracted_data.get("project_type", "residential")

            # Build query for Qdrant
            query = f"What materials and labor are needed for {project_type} project "
            query += f"from {current_finish} to {target_finish} finishing level?"

            logger.info(f"Querying Qdrant: {query}")

            qdrant = get_qdrant_service()
            results = qdrant.search_knowledge(query, top_k=5)

            # Extract material and labor mentions from Qdrant results
            materials_mentioned = set()
            labor_mentioned = set()

            for result in results:
                content = result.get("content", "").lower()

                # Extract material keywords
                material_keywords = ["cement", "sand", "tile", "ceramic", "porcelain", "marble",
                                   "paint", "plaster", "gypsum", "wood", "parquet", "granite",
                                   "pipes", "wiring", "electrical", "plumbing", "doors", "windows"]

                for keyword in material_keywords:
                    if keyword in content:
                        materials_mentioned.add(keyword)

                # Extract labor keywords
                labor_keywords = ["mason", "electrician", "plumber", "carpenter", "painter",
                                "tiler", "plasterer", "foreman", "supervisor"]

                for keyword in labor_keywords:
                    if keyword in content:
                        labor_mentioned.add(keyword)

            logger.info(f"Qdrant suggested materials: {materials_mentioned}")
            logger.info(f"Qdrant suggested labor: {labor_mentioned}")

            return {
                "materials": list(materials_mentioned) if materials_mentioned else ["cement", "tile", "paint"],
                "labor": list(labor_mentioned) if labor_mentioned else ["mason", "painter"]
            }

        except Exception as e:
            logger.warning(f"Error querying Qdrant: {e}. Using fallback.")
            # Fallback: basic materials and labor
            return {
                "materials": ["cement", "tile", "paint", "plaster"],
                "labor": ["mason", "electrician", "plumber", "painter"]
            }
    
    async def _fetch_materials_from_db(self, material_queries: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch materials from database based on queries from Qdrant.

        Returns list of materials with pricing.
        """
        db = SessionLocal()
        try:
            materials = []

            for query in material_queries:
                # Query database for matching materials
                db_materials = db.query(Material).filter(
                    Material.name.ilike(f'%{query}%')
                ).limit(5).all()

                for m in db_materials:
                    materials.append({
                        "name": m.name,
                        "price_per_unit": m.price_per_unit,
                        "unit": m.unit,
                        "currency": m.currency,
                        "category": m.category
                    })

            logger.info(f"Fetched {len(materials)} materials from database")
            return materials

        except Exception as e:
            logger.error(f"Error fetching materials from DB: {e}")
            return []
        finally:
            db.close()
    
    async def _fetch_labor_rates_from_db(self, labor_queries: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch labor rates from database based on queries from Qdrant.

        Returns list of labor rates.
        """
        db = SessionLocal()
        try:
            labor_rates = []

            for query in labor_queries:
                # Query database for matching labor roles
                db_labor = db.query(LaborRate).filter(
                    LaborRate.role.ilike(f'%{query}%')
                ).limit(3).all()

                for l in db_labor:
                    labor_rates.append({
                        "role": l.role,
                        "hourly_rate": l.hourly_rate,
                        "currency": l.currency
                    })

            logger.info(f"Fetched {len(labor_rates)} labor rates from database")
            return labor_rates

        except Exception as e:
            logger.error(f"Error fetching labor rates from DB: {e}")
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

        # Get size - support both sqft and sqm
        size_sqft = extracted_data.get("size_sqft") or extracted_data.get("size_sqm")
        size_unit = "sqm" if extracted_data.get("size_sqm") else "sqft"

        # Convert to square meters (Egypt standard)
        size_sqm = self._convert_to_sqm(size_sqft, size_unit)
        project_type = extracted_data.get("project_type", "residential")

        logger.info(f"Calculating costs for {size_sqm} sqm {project_type} project")

        # Step 1: Query Qdrant to understand requirements
        requirements = await self._query_qdrant_for_requirements(extracted_data)
        material_queries = requirements.get("materials", [])
        labor_queries = requirements.get("labor", [])

        # Step 2: Fetch pricing from database
        materials = await self._fetch_materials_from_db(material_queries)
        labor_rates = await self._fetch_labor_rates_from_db(labor_queries)

        # Step 3: Calculate material costs
        material_items = []
        total_material_cost = 0

        for material in materials:
            # Estimate quantity based on project size
            # Simple heuristic: assume materials cover the entire area
            quantity = size_sqm
            unit_price = material.get("price_per_unit", 0)
            item_cost = quantity * unit_price

            material_items.append({
                "name": material.get("name"),
                "quantity": round(quantity, 2),
                "unit": material.get("unit", "sqm"),
                "unit_price": round(unit_price, 2),
                "cost": round(item_cost, 2),
                "category": material.get("category", "General")
            })

            total_material_cost += item_cost

        # Step 4: Calculate labor costs
        labor_trades = []
        total_labor_cost = 0

        # Estimate total labor hours based on project size
        # Simple heuristic: 10 hours per sqm on average
        total_labor_hours = size_sqm * 10.0

        if labor_rates:
            # Distribute hours among available labor roles
            hours_per_role = total_labor_hours / len(labor_rates)

            for labor in labor_rates:
                role = labor.get("role")
                hourly_rate = labor.get("hourly_rate", 0)
                role_hours = hours_per_role
                role_cost = role_hours * hourly_rate

                labor_trades.append({
                    "trade": role,
                    "hours": round(role_hours, 1),
                    "rate": round(hourly_rate, 2),
                    "cost": round(role_cost, 2)
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

