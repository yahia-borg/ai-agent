from typing import Dict, Any
from app.agents.base_agent import BaseAgent
from app.models.quotation import Quotation
from app.core.config import settings
from app.agent.tools import search_materials, search_labor_rates
import json


class CostCalculatorAgent(BaseAgent):
    """Agent responsible for calculating construction costs (Egypt market)"""
    
    def __init__(self):
        super().__init__("cost_calculator")
        # Egypt market pricing data (EGP - Egyptian Pounds)
        # Prices per square meter (common unit in Egypt)
        self.material_costs = {
            "flooring": {
                "carpet": 150,  # EGP per sqm
                "hardwood": 400,  # EGP per sqm
                "luxury_vinyl": 250,  # EGP per sqm
                "tile": 200,  # EGP per sqm (ceramic/porcelain)
                "marble": 600  # EGP per sqm
            },
            "lighting": {
                "basic": 500,  # EGP per fixture
                "standard": 1500,  # EGP per fixture
                "premium": 3000  # EGP per fixture
            },
            "fixtures": {
                "basic": 2000,  # EGP
                "standard": 5000,  # EGP
                "premium": 10000  # EGP
            },
            "paint": {
                "basic": 80,  # EGP per sqm
                "standard": 120,  # EGP per sqm
                "premium": 200  # EGP per sqm
            }
        }
        
        # Egypt labor rates (EGP per hour)
        self.labor_rates = {
            "general_contractor": 150,  # EGP/hour
            "electrician": 120,  # EGP/hour
            "plumber": 100,  # EGP/hour
            "carpenter": 100,  # EGP/hour
            "painter": 80,  # EGP/hour
            "tiler": 120,  # EGP/hour
            "plasterer": 90  # EGP/hour
        }
        
        # Egypt regional cost multipliers by city/governorate
        self.regional_multipliers = {
            "cairo": 1.2,  # Cairo (higher costs)
            "alexandria": 1.15,  # Alexandria
            "giza": 1.1,  # Giza
            "new_cairo": 1.25,  # New Cairo (premium area)
            "6_october": 1.2,  # 6th October City
            "new_capital": 1.3,  # New Administrative Capital
            "default": 1.0  # Other areas
        }
        
        # Currency configuration
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
    
    def _detect_egypt_location(self, location: str, zip_code: str) -> str:
        """Detect Egypt location for regional pricing"""
        if not location:
            return "default"
        
        location_lower = location.lower()
        
        # Check for major Egyptian cities
        if any(city in location_lower for city in ["cairo", "القاهرة", "القاهره"]):
            if "new" in location_lower or "جديد" in location_lower:
                return "new_cairo"
            return "cairo"
        elif any(city in location_lower for city in ["alexandria", "الإسكندرية", "اسكندريه"]):
            return "alexandria"
        elif any(city in location_lower for city in ["giza", "الجيزة", "جيزه"]):
            return "giza"
        elif any(city in location_lower for city in ["6 october", "6th october", "أكتوبر", "السادس"]):
            return "6_october"
        elif any(city in location_lower for city in ["new capital", "العاصمة", "الادارية"]):
            return "new_capital"
        
        return "default"
    
    async def _get_material_cost_per_sqm(self, extracted_data: Dict[str, Any]) -> float:
        """Get material cost per sqm using tools or fallback to default"""
        try:
            # Try to get materials from extracted data or search
            key_requirements = extracted_data.get("key_requirements", [])
            project_type = extracted_data.get("project_type", "residential")
            
            # Search for common materials
            material_queries = ["cement", "tiles", "paint"]
            if project_type == "residential":
                material_queries.extend(["porcelain", "marble"])
            
            total_price = 0
            count = 0
            
            for query in material_queries[:3]:  # Limit to 3 queries
                try:
                    result = search_materials.invoke({"query": query})
                    if result and result != "No materials found matching that query.":
                        materials = json.loads(result)
                        if isinstance(materials, list) and materials:
                            # Get average price
                            prices = [m.get("price", 0) for m in materials if m.get("price")]
                            if prices:
                                total_price += sum(prices) / len(prices)
                                count += 1
                except Exception as e:
                    continue
            
            if count > 0:
                avg_material_price = total_price / count
                # Estimate cost per sqm (materials typically 30-50% of total, so multiply by 2-3)
                return avg_material_price * 2.5
        except Exception as e:
            pass
        
        # Fallback to default
        return 3000.0  # EGP per sqm (mid-range)
    
    async def _get_average_labor_rate(self) -> float:
        """Get average labor rate using tools or fallback to default"""
        try:
            # Search for common labor roles
            labor_queries = ["electrician", "plumber", "carpenter", "painter", "tiler"]
            
            total_rate = 0
            count = 0
            
            for query in labor_queries:
                try:
                    result = search_labor_rates.invoke({"query": query})
                    if result and result != "No labor rates found.":
                        labor_rates = json.loads(result)
                        if isinstance(labor_rates, list) and labor_rates:
                            rates = [l.get("hourly_rate", 0) for l in labor_rates if l.get("hourly_rate")]
                            if rates:
                                total_rate += sum(rates) / len(rates)
                                count += 1
                except Exception as e:
                    continue
            
            if count > 0:
                return total_rate / count
        except Exception as e:
            pass
        
        # Fallback to default
        return sum(self.labor_rates.values()) / len(self.labor_rates)
    
    async def _get_labor_rate(self, role: str) -> float:
        """Get labor rate for a specific role using tools or fallback"""
        try:
            result = search_labor_rates.invoke({"query": role})
            if result and result != "No labor rates found.":
                labor_rates = json.loads(result)
                if isinstance(labor_rates, list) and labor_rates:
                    # Find matching role
                    for lr in labor_rates:
                        if role.lower() in lr.get("role", "").lower():
                            return lr.get("hourly_rate", 0)
                    # Return first rate if no match
                    if labor_rates:
                        return labor_rates[0].get("hourly_rate", 0)
        except Exception as e:
            pass
        
        # Fallback to default
        return self.labor_rates.get(role, 100)
    
    async def execute(self, quotation: Quotation, context: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate construction costs based on extracted data (Egypt market)"""
        
        extracted_data = context.get("extracted_data", {})
        
        # Get size - support both sqft and sqm
        size_sqft = extracted_data.get("size_sqft") or extracted_data.get("size_sqm")
        size_unit = "sqm" if extracted_data.get("size_sqm") else "sqft"
        
        if not size_sqft:
            size_sqft = 100  # Default 100 sqm (approximately 1076 sqft)
            size_unit = "sqm"
        
        # Convert to square meters (Egypt standard)
        size_sqm = self._convert_to_sqm(size_sqft, size_unit)
        project_type = extracted_data.get("project_type", "residential")
        
        # Get regional multiplier for Egypt
        location_key = self._detect_egypt_location(quotation.location or "", quotation.zip_code or "")
        regional_multiplier = self.regional_multipliers.get(location_key, self.regional_multipliers["default"])
        
        # Calculate material costs using tools if available, otherwise use defaults
        material_cost_per_sqm = await self._get_material_cost_per_sqm(extracted_data)
        total_material_cost = size_sqm * material_cost_per_sqm * regional_multiplier
        
        # Calculate labor costs (Egypt market)
        # Estimate labor hours based on project size and type (per sqm)
        if project_type == "renovation":
            labor_hours_per_sqm = 8.0  # Hours per sqm
        elif project_type == "commercial":
            labor_hours_per_sqm = 12.0  # Hours per sqm
        else:
            labor_hours_per_sqm = 10.0  # Hours per sqm
        
        total_labor_hours = size_sqm * labor_hours_per_sqm
        avg_labor_rate = await self._get_average_labor_rate()
        total_labor_cost = total_labor_hours * avg_labor_rate * regional_multiplier
        
        # Permits and fees (Egypt - estimated in EGP)
        # Building permits in Egypt vary by project type and location
        if project_type == "commercial":
            permits_fees = 5000  # EGP
        elif project_type == "new_construction":
            permits_fees = 8000  # EGP
        else:
            permits_fees = 3000  # EGP
        
        # Contingency (10%)
        subtotal = total_material_cost + total_labor_cost + permits_fees
        contingency = subtotal * 0.10
        
        # Markup (10%)
        markup = subtotal * 0.10
        
        # Total cost
        total_cost = subtotal + contingency + markup
        
        cost_breakdown = {
            "materials": {
                "subtotal": round(total_material_cost, 2),
                "percentage": round((total_material_cost / total_cost) * 100, 1),
                "items": [
                    {
                        "category": "general_materials",
                        "cost": round(total_material_cost, 2),
                        "quantity": round(size_sqm, 2),
                        "unit": "sqm",
                        "unit_cost": round(material_cost_per_sqm * regional_multiplier, 2)
                    }
                ]
            },
            "labor": {
                "subtotal": round(total_labor_cost, 2),
                "percentage": round((total_labor_cost / total_cost) * 100, 1),
                "trades": [
                    {
                        "trade": "general_contractor",
                        "hours": round(total_labor_hours * 0.4, 1),
                        "rate": await self._get_labor_rate("general_contractor"),
                        "cost": round(total_labor_hours * 0.4 * await self._get_labor_rate("general_contractor") * regional_multiplier, 2)
                    },
                    {
                        "trade": "electrician",
                        "hours": round(total_labor_hours * 0.2, 1),
                        "rate": await self._get_labor_rate("electrician"),
                        "cost": round(total_labor_hours * 0.2 * await self._get_labor_rate("electrician") * regional_multiplier, 2)
                    },
                    {
                        "trade": "plumber",
                        "hours": round(total_labor_hours * 0.2, 1),
                        "rate": await self._get_labor_rate("plumber"),
                        "cost": round(total_labor_hours * 0.2 * await self._get_labor_rate("plumber") * regional_multiplier, 2)
                    },
                    {
                        "trade": "carpenter",
                        "hours": round(total_labor_hours * 0.2, 1),
                        "rate": await self._get_labor_rate("carpenter"),
                        "cost": round(total_labor_hours * 0.2 * await self._get_labor_rate("carpenter") * regional_multiplier, 2)
                    }
                ]
            },
            "permits_and_fees": {
                "subtotal": round(permits_fees, 2),
                "percentage": round((permits_fees / total_cost) * 100, 1)
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
            "region": "Egypt",
            "size_sqm": round(size_sqm, 2),
            "regional_multiplier": regional_multiplier,
            "confidence_interval": {
                "low": round(total_cost * 0.9, 2),
                "high": round(total_cost * 1.1, 2),
                "confidence_level": 0.85
            }
        }

