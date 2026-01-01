"""
Calculation Tools - Tools for cost calculations and quantity estimations.
"""
from typing import Dict, List, Any, Optional
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)

# Global cache for materials and labor rates (set by agent)
_materials_cache: List[Dict] = []
_labor_rates_cache: List[Dict] = []


def set_materials_cache(materials: List[Dict]):
    """Set materials cache for lookup tools."""
    global _materials_cache
    _materials_cache = materials


def set_labor_rates_cache(labor_rates: List[Dict]):
    """Set labor rates cache for lookup tools."""
    global _labor_rates_cache
    _labor_rates_cache = labor_rates


@tool
def calculate_material_quantity(
    material_type: str,
    area_sqm: float,
    work_type: str
) -> Dict[str, Any]:
    """
    Calculate material quantity needed based on area and work type.

    Material consumption rates per sqm:
    - Cement: 0.02 ton/sqm (for plastering)
    - Sand: 0.04 ton/sqm (for plastering)
    - Paint: 0.15 liter/sqm
    - Tiles: 1.1 sqm/sqm (includes 10% wastage)
    - Tile adhesive: 0.005 ton/sqm
    - Wiring: 0.5 meter/sqm
    - Pipes: 0.3 meter/sqm

    Args:
        material_type: Type of material (cement, sand, paint, tiles, adhesive, wiring, pipes)
        area_sqm: Area in square meters
        work_type: Type of work (plastering, painting, tiling, electrical, plumbing)

    Returns:
        Dict with 'quantity', 'unit', and 'material_type'
    """
    # Consumption rates mapping
    consumption_rates = {
        "plastering": {
            "cement": {"rate": 0.02, "unit": "ton"},
            "sand": {"rate": 0.04, "unit": "ton"}
        },
        "painting": {
            "paint": {"rate": 0.15, "unit": "liter"}
        },
        "tiling": {
            "tiles": {"rate": 1.1, "unit": "sqm"},
            "adhesive": {"rate": 0.005, "unit": "ton"}
        },
        "electrical": {
            "wiring": {"rate": 0.5, "unit": "meter"},
            "wire": {"rate": 0.5, "unit": "meter"}
        },
        "plumbing": {
            "pipes": {"rate": 0.3, "unit": "meter"},
            "pipe": {"rate": 0.3, "unit": "meter"}
        }
    }

    material_type_lower = material_type.lower()
    work_type_lower = work_type.lower()

    if work_type_lower in consumption_rates:
        if material_type_lower in consumption_rates[work_type_lower]:
            rate_info = consumption_rates[work_type_lower][material_type_lower]
            quantity = area_sqm * rate_info["rate"]

            logger.info(f"Calculated {quantity:.2f} {rate_info['unit']} of {material_type} for {area_sqm} sqm ({work_type})")

            return {
                "success": True,
                "quantity": round(quantity, 2),
                "unit": rate_info["unit"],
                "material_type": material_type,
                "work_type": work_type,
                "area_sqm": area_sqm
            }

    # Default fallback
    logger.warning(f"No consumption rate found for {material_type} in {work_type}")
    return {
        "success": False,
        "error": f"No consumption rate defined for {material_type} in {work_type}",
        "quantity": 0,
        "unit": "unknown"
    }


@tool
def calculate_labor_hours(
    work_type: str,
    area_sqm: float
) -> Dict[str, Any]:
    """
    Calculate labor hours needed based on work type and area.

    Labor hours per sqm for different work types:
    - Plastering: 1.5 hours/sqm
    - Painting: 0.8 hours/sqm
    - Tiling: 1.2 hours/sqm
    - Electrical installation: 0.6 hours/sqm
    - Plumbing installation: 0.5 hours/sqm
    - Doors/windows: 0.3 hours/sqm
    - Fixtures: 0.4 hours/sqm

    Args:
        work_type: Type of work (plastering, painting, tiling, electrical, plumbing, doors_windows, fixtures)
        area_sqm: Area in square meters

    Returns:
        Dict with 'hours', 'work_type', and 'recommended_role'
    """
    # Labor hours per sqm
    labor_rates = {
        "plastering": {"hours_per_sqm": 1.5, "role": "Mason"},
        "painting": {"hours_per_sqm": 0.8, "role": "Painter"},
        "tiling": {"hours_per_sqm": 1.2, "role": "Mason"},
        "electrical": {"hours_per_sqm": 0.6, "role": "Electrician"},
        "electrical_installation": {"hours_per_sqm": 0.6, "role": "Electrician"},
        "plumbing": {"hours_per_sqm": 0.5, "role": "Plumber"},
        "plumbing_installation": {"hours_per_sqm": 0.5, "role": "Plumber"},
        "doors_windows": {"hours_per_sqm": 0.3, "role": "Carpenter"},
        "fixtures": {"hours_per_sqm": 0.4, "role": "Semi-Skilled"}
    }

    work_type_lower = work_type.lower()

    if work_type_lower in labor_rates:
        rate_info = labor_rates[work_type_lower]
        hours = area_sqm * rate_info["hours_per_sqm"]

        logger.info(f"Calculated {hours:.2f} hours for {work_type} on {area_sqm} sqm")

        return {
            "success": True,
            "hours": round(hours, 2),
            "work_type": work_type,
            "area_sqm": area_sqm,
            "recommended_role": rate_info["role"]
        }

    # Default fallback
    logger.warning(f"No labor rate found for {work_type}")
    return {
        "success": False,
        "error": f"No labor rate defined for {work_type}",
        "hours": 0,
        "recommended_role": "Semi-Skilled"
    }


@tool
def calculate_material_cost(
    quantity: float,
    unit_price: float,
    unit: str = "unit"
) -> Dict[str, Any]:
    """
    Calculate total cost for a material based on quantity and unit price.

    Args:
        quantity: Quantity needed
        unit_price: Price per unit
        unit: Unit of measurement (optional, for reference)

    Returns:
        Dict with 'total_cost', 'quantity', 'unit_price'
    """
    total_cost = quantity * unit_price

    logger.info(f"Calculated cost: {quantity} {unit} × {unit_price} EGP = {total_cost} EGP")

    return {
        "success": True,
        "total_cost": round(total_cost, 2),
        "quantity": quantity,
        "unit_price": unit_price,
        "unit": unit
    }


@tool
def calculate_labor_cost(
    hours: float,
    hourly_rate: float,
    role: str = "labor"
) -> Dict[str, Any]:
    """
    Calculate total labor cost based on hours and hourly rate.

    Args:
        hours: Total hours needed
        hourly_rate: Hourly rate in EGP
        role: Labor role (optional, for reference)

    Returns:
        Dict with 'total_cost', 'hours', 'hourly_rate'
    """
    total_cost = hours * hourly_rate

    logger.info(f"Calculated labor cost for {role}: {hours} hours × {hourly_rate} EGP/hour = {total_cost} EGP")

    return {
        "success": True,
        "total_cost": round(total_cost, 2),
        "hours": hours,
        "hourly_rate": hourly_rate,
        "role": role
    }


@tool
def determine_work_scope(current_status: str) -> Dict[str, Any]:
    """
    Determine what work is needed based on current finishing status.

    Status options:
    - bare_concrete: Needs everything (plastering, electrical, plumbing, painting, tiling, fixtures)
    - plastered: Needs electrical, plumbing, painting, tiling, fixtures
    - semi_finished: Needs painting, tiling, fixtures
    - painted: Needs tiling, fixtures

    Args:
        current_status: Current finishing status (bare_concrete, plastered, semi_finished, painted)

    Returns:
        Dict with 'work_needed' (list of work types) and 'current_status'
    """
    work_map = {
        "bare_concrete": [
            "plastering", "electrical_installation", "plumbing_installation",
            "painting", "tiling", "doors_windows", "fixtures"
        ],
        "plastered": [
            "electrical_installation", "plumbing_installation",
            "painting", "tiling", "doors_windows", "fixtures"
        ],
        "semi_finished": [
            "painting", "tiling", "fixtures"
        ],
        "painted": [
            "tiling", "fixtures"
        ]
    }

    current_status_lower = current_status.lower()
    work_needed = work_map.get(current_status_lower, work_map["bare_concrete"])

    logger.info(f"Work scope for '{current_status}': {len(work_needed)} work types needed")

    return {
        "success": True,
        "work_needed": work_needed,
        "current_status": current_status,
        "work_count": len(work_needed)
    }


@tool
def lookup_material_price(material_name: str) -> Dict[str, Any]:
    """
    Look up the price of a material by name.

    Searches for material in the database by name (case-insensitive, partial match).

    Args:
        material_name: Name or keyword for the material (e.g., "cement", "paint", "tiles")

    Returns:
        Dict with 'price_per_unit', 'unit', 'name', or error
    """
    global _materials_cache

    if not _materials_cache:
        return {
            "success": False,
            "error": "No materials database available"
        }

    material_name_lower = material_name.lower()

    # Try exact match first
    for mat in _materials_cache:
        if material_name_lower == mat.get("name", "").lower():
            logger.info(f"Found exact match for '{material_name}': {mat['price_per_unit']} EGP/{mat['unit']}")
            return {
                "success": True,
                "price_per_unit": mat["price_per_unit"],
                "unit": mat["unit"],
                "name": mat["name"],
                "material_name": material_name
            }

    # Try partial match
    for mat in _materials_cache:
        if material_name_lower in mat.get("name", "").lower():
            logger.info(f"Found partial match for '{material_name}': {mat['name']} @ {mat['price_per_unit']} EGP/{mat['unit']}")
            return {
                "success": True,
                "price_per_unit": mat["price_per_unit"],
                "unit": mat["unit"],
                "name": mat["name"],
                "material_name": material_name
            }

    # Default price if not found
    logger.warning(f"Material '{material_name}' not found, using default price")
    return {
        "success": False,
        "error": f"Material '{material_name}' not found in database",
        "price_per_unit": 100.0,
        "unit": "unit"
    }


@tool
def lookup_labor_rate(role_keyword: str) -> Dict[str, Any]:
    """
    Look up hourly rate for a labor role.

    Searches for labor role in the database (case-insensitive, partial match).

    Args:
        role_keyword: Role keyword (e.g., "mason", "electrician", "painter", "plumber")

    Returns:
        Dict with 'hourly_rate', 'role', or error
    """
    global _labor_rates_cache

    if not _labor_rates_cache:
        return {
            "success": False,
            "error": "No labor rates database available"
        }

    role_lower = role_keyword.lower()

    # Try exact match first
    for labor in _labor_rates_cache:
        if role_lower == labor.get("role", "").lower():
            logger.info(f"Found exact match for '{role_keyword}': {labor['hourly_rate']} EGP/hour")
            return {
                "success": True,
                "hourly_rate": labor["hourly_rate"],
                "role": labor["role"],
                "role_keyword": role_keyword
            }

    # Try partial match
    for labor in _labor_rates_cache:
        if role_lower in labor.get("role", "").lower() or labor.get("role", "").lower() in role_lower:
            logger.info(f"Found partial match for '{role_keyword}': {labor['role']} @ {labor['hourly_rate']} EGP/hour")
            return {
                "success": True,
                "hourly_rate": labor["hourly_rate"],
                "role": labor["role"],
                "role_keyword": role_keyword
            }

    # Default rate if not found
    logger.warning(f"Labor role '{role_keyword}' not found, using default rate")
    return {
        "success": False,
        "error": f"Labor role '{role_keyword}' not found in database",
        "hourly_rate": 50.0,
        "role": role_keyword
    }


@tool
def add_contingency(subtotal: float, contingency_percent: float = 10.0) -> Dict[str, Any]:
    """
    Add contingency percentage to subtotal.

    Args:
        subtotal: Subtotal amount
        contingency_percent: Contingency percentage (default 10%)

    Returns:
        Dict with 'contingency_amount', 'total_with_contingency', 'percent'
    """
    contingency_amount = subtotal * (contingency_percent / 100.0)
    total_with_contingency = subtotal + contingency_amount

    logger.info(f"Added {contingency_percent}% contingency: {contingency_amount:.2f} EGP")

    return {
        "success": True,
        "contingency_amount": round(contingency_amount, 2),
        "total_with_contingency": round(total_with_contingency, 2),
        "contingency_percent": contingency_percent,
        "subtotal": subtotal
    }
