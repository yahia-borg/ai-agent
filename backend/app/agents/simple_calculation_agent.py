"""
Simple Calculation Agent - Direct cost calculation based on material selections.

Uses prices from egypt-construction-costs-2025.md which are per m² and include labor.
No ReAct, no LLM - just direct arithmetic.
"""
from typing import Literal, List, Dict, Any
from langchain_core.messages import AIMessage
from langgraph.types import Command
from app.state.schemas import CostEstimationState
import logging

logger = logging.getLogger(__name__)


def simple_calculation_agent_node(state: CostEstimationState) -> Command[Literal["supervisor"]]:
    """
    Simple calculation agent - direct cost calculation.

    Calculation based on egypt-construction-costs-2025.md:
    - Prices are per m² and INCLUDE material + labor
    - Paint prices include 2-3 coats
    - Just multiply: cost = area × price_per_m²

    Returns:
        Command to route back to supervisor
    """
    requirements = state.get("requirements", {})
    material_selections = state.get("material_selections") or {}
    qdrant_knowledge = state.get("qdrant_knowledge", [])

    total_area = requirements.get("total_area_sqm")
    project_type = requirements.get("project_type")
    current_status = requirements.get("current_finishing_status")
    finishing_level = requirements.get("finishing_level")
    location = requirements.get("location", "Cairo")
    rooms_breakdown = requirements.get("rooms_breakdown", [])

    logger.info(f"Simple calculation: {total_area}m², status={current_status}")

    try:
        # Calculate costs (prices include labor per egypt-construction-costs-2025.md)
        cost_breakdown = _calculate_all_costs(material_selections, total_area)

        # Totals
        subtotal = cost_breakdown["total"]
        contingency = subtotal * 0.10  # 10% contingency
        total_estimate = subtotal + contingency

        # Create quotation
        quotation = {
            "project_type": project_type,
            "total_area_sqm": total_area,
            "finishing_level": finishing_level,
            "current_finishing_status": current_status,
            "location": location,
            "rooms_count": len(rooms_breakdown),
            "cost_per_sqm": round(total_estimate / total_area, 2) if total_area else 0,
            "subtotal": round(subtotal, 2),
            "contingency": round(contingency, 2),
            "total_estimate": round(total_estimate, 2),
            "currency": "EGP",
            "breakdown": cost_breakdown["breakdown"],
            "work_scope": cost_breakdown["work_scope"],
            "notes": [
                f"Based on user material selections",
                "Prices include material + labor (per egypt-construction-costs-2025.md)",
                f"Used {len(qdrant_knowledge)} building references",
                "Costs may vary ±10-15%"
            ]
        }

        # Format response
        response = _format_quotation_response(quotation)

        logger.info(f"Calculation complete: Total = {total_estimate} EGP")

        return Command(
            update={
                "current_agent": "calculation_agent",
                "quotation": quotation,
                "calculation_complete": True,
                "messages": [AIMessage(content=response)],
            },
            goto="supervisor"
        )

    except Exception as e:
        logger.error(f"Error in calculation: {e}", exc_info=True)
        return Command(
            update={
                "current_agent": "calculation_agent",
                "calculation_complete": True,
                "errors": state.get("errors", []) + [str(e)],
                "messages": [AIMessage(content=f"Calculation error: {str(e)}")],
            },
            goto="supervisor"
        )


def _calculate_all_costs(material_selections: Dict, total_area: float) -> Dict[str, Any]:
    """
    Calculate all costs from material selections.

    Per egypt-construction-costs-2025.md:
    - Paint prices (line 161-174): per m², include material + labor for 2-3 coats
    - Tile prices (line 139-156): per m²
    - All prices are final installed prices
    """
    total = 0
    breakdown = {}
    work_scope = []

    # === 1. FLOORING ===
    flooring = material_selections.get("flooring", {})
    for room_type, selection in flooring.items():
        area = selection.get("area_sqm", 0)
        price_per_unit = selection.get("price_per_unit", 0)
        unit = selection.get("unit", "m²")

        # Direct calculation: area × price
        if unit == "m²" or unit == "sqm":
            cost = area * price_per_unit
        else:
            # If not per m², assume it's total price
            cost = price_per_unit

        total += cost
        breakdown[f"{room_type}_flooring"] = {
            "material": selection.get("material_name"),
            "area": round(area, 2),
            "unit_price": price_per_unit,
            "unit": unit,
            "total_cost": round(cost, 2)
        }
        work_scope.append(f"{room_type.replace('_', ' ').title()} flooring")

    # === 2. WALL PAINT ===
    wall_paint = material_selections.get("wall_paint")
    if wall_paint:
        # Wall area estimation: perimeter × height
        # For typical 3m ceiling: wall_area ≈ 2.5 × floor_area
        floor_area = sum(s.get("area_sqm", 0) for s in flooring.values()) if flooring else total_area
        wall_area = floor_area * 2.5

        price_per_m2 = wall_paint.get("price_per_unit", 0)

        # Price per m² already includes labor (per egypt-construction-costs-2025.md line 174)
        cost = wall_area * price_per_m2

        total += cost
        breakdown["wall_paint"] = {
            "material": wall_paint.get("material_name"),
            "area": round(wall_area, 2),
            "unit_price": price_per_m2,
            "unit": "m²",
            "total_cost": round(cost, 2),
            "note": "Includes material + labor for 2-3 coats"
        }
        work_scope.append("Wall painting")

    # === 3. CEILING PAINT ===
    ceiling_paint = material_selections.get("ceiling_paint")
    if ceiling_paint:
        # Ceiling area ≈ floor area
        ceiling_area = sum(s.get("area_sqm", 0) for s in flooring.values()) if flooring else total_area

        price_per_m2 = ceiling_paint.get("price_per_unit", 0)

        # Price per m² already includes labor
        cost = ceiling_area * price_per_m2

        total += cost
        breakdown["ceiling_paint"] = {
            "material": ceiling_paint.get("material_name"),
            "area": round(ceiling_area, 2),
            "unit_price": price_per_m2,
            "unit": "m²",
            "total_cost": round(cost, 2),
            "note": "Includes material + labor for 2-3 coats"
        }
        work_scope.append("Ceiling painting")

    # === 4. BATHROOM TILES ===
    bathroom_tiles = material_selections.get("bathroom_tiles")
    if bathroom_tiles:
        # Get bathroom area from flooring if available
        bathroom_area = 0
        for room_type, selection in flooring.items():
            if "bathroom" in room_type.lower():
                bathroom_area += selection.get("area_sqm", 0)

        if bathroom_area == 0:
            # Estimate: ~10% of total area for bathrooms
            bathroom_area = total_area * 0.10

        # Tiles area: floor + walls (walls ≈ 2× floor for bathrooms up to ceiling)
        tiles_area = bathroom_area * 3.0

        price_per_m2 = bathroom_tiles.get("price_per_unit", 0)

        # Add 10% wastage
        cost = tiles_area * price_per_m2 * 1.10

        total += cost
        breakdown["bathroom_tiles"] = {
            "material": bathroom_tiles.get("material_name"),
            "floor_area": round(bathroom_area, 2),
            "tiles_area": round(tiles_area, 2),
            "unit_price": price_per_m2,
            "unit": "m²",
            "total_cost": round(cost, 2),
            "note": "Includes floor + walls + 10% wastage"
        }
        work_scope.append("Bathroom tiling")

    # === 5. DOORS & WINDOWS ===
    doors_windows = material_selections.get("doors_windows")
    if doors_windows:
        # This is typically a per-unit price
        price = doors_windows.get("price_per_unit", 0)
        cost = price

        total += cost
        breakdown["doors_windows"] = {
            "material": doors_windows.get("material_name"),
            "unit_price": price,
            "total_cost": round(cost, 2)
        }
        work_scope.append("Doors & windows")

    return {
        "total": total,
        "breakdown": breakdown,
        "work_scope": work_scope
    }


def _format_quotation_response(quotation: Dict) -> str:
    """Format quotation as concise markdown."""
    work_scope = ", ".join(quotation.get("work_scope", []))

    # Handle None values safely
    project_type = (quotation.get('project_type') or 'Project').title()
    total_area = quotation.get('total_area_sqm', 0)
    finishing_level = (quotation.get('finishing_level') or 'Standard').title()
    location = quotation.get('location', 'Cairo')
    current_status = (quotation.get('current_finishing_status') or 'unknown').replace('_', ' ')

    response = f"""## Cost Estimate

**{project_type} | {total_area}m² | {finishing_level} | {location}**

| Item | Amount (EGP) |
|------|--------------|
| Subtotal (incl. materials + labor) | {quotation.get('subtotal', 0):,.0f} |
| Contingency (10%) | {quotation.get('contingency', 0):,.0f} |
| **Total** | **{quotation.get('total_estimate', 0):,.0f}** |
| **Per m²** | **{quotation.get('cost_per_sqm', 0):,.0f}** |

**Work:** {work_scope}

*Prices include material + labor. Based on {current_status} status. May vary ±10-15%*"""

    return response
