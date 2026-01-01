"""
Materials selection nodes for the materials subgraph.

Simplified conversational flow for selecting materials per room/category.

Nodes:
- determine_needed_node: Calculate what needs to be selected based on finishing status
- present_options_node: Show material choices to user
- parse_selection_node: Extract user's choice
- validate_complete_node: Check if all selections are done
"""
from typing import Dict, Any
import logging

from langchain_core.messages import AIMessage, HumanMessage
from app.state.schemas import CostEstimationState
from app.utils.language_detector import detect_language

logger = logging.getLogger(__name__)

# ============= HELPER FUNCTIONS =============


def _group_rooms_by_type(rooms_breakdown: list, total_area: float) -> Dict[str, Any]:
    """Group rooms by type for easier material selection."""
    room_groups = {}

    for room in rooms_breakdown:
        room_type = room.get("room_type", "unknown")
        area = room.get("area_sqm", 0)
        count = room.get("count", 1)

        if room_type not in room_groups:
            room_groups[room_type] = {
                "total_area": 0,
                "count": 0,
                "rooms": []
            }

        room_groups[room_type]["total_area"] += area * count
        room_groups[room_type]["count"] += count
        room_groups[room_type]["rooms"].append(room)

    return room_groups


def _determine_needed_selections(current_finishing_status: str) -> list:
    """Determine what material selections are needed based on finishing status."""
    selection_map = {
        "bare_concrete": ["flooring", "wall_paint", "ceiling_paint", "bathroom_tiles", "kitchen_tiles", "doors"],
        "plastered": ["flooring", "wall_paint", "ceiling_paint", "bathroom_tiles", "kitchen_tiles"],
        "semi_finished": ["wall_paint", "ceiling_paint", "bathroom_tiles"],
        "painted": ["bathroom_tiles", "kitchen_tiles"]
    }

    return selection_map.get(current_finishing_status, selection_map["bare_concrete"])


def _check_selection_progress(
    material_selections: Dict[str, Any],
    needed_selections: list,
    room_groups: Dict[str, Any]
) -> Dict[str, Any]:
    """Check progress of material selections."""
    completed = []
    remaining = []

    for selection_type in needed_selections:
        if selection_type in material_selections:
            selection = material_selections[selection_type]
            if selection.get("material_id") or selection.get("material_name"):
                completed.append(selection_type)
                continue

        remaining.append(selection_type)

    next_needed = remaining[0] if remaining else None

    return {
        "completed": completed,
        "remaining": remaining,
        "next_needed": next_needed,
        "all_complete": len(remaining) == 0
    }


def _generate_material_question(
    selection_type: str,
    materials_db: list,
    room_groups: Dict[str, Any],
    language: str
) -> str:
    """Generate question presenting material options for a specific selection type."""
    # Map selection types to name keywords (bilingual)
    keyword_map = {
        "flooring": ["floor", "flooring", "أرضية", "أرضيات"],
        "wall_paint": ["paint", "emulsion", "دهان", "طلاء"],
        "ceiling_paint": ["paint", "emulsion", "ceiling", "دهان", "سقف"],
        "bathroom_tiles": ["tile", "ceramic", "porcelain", "سيراميك", "بلاط"],
        "kitchen_tiles": ["tile", "ceramic", "porcelain", "سيراميك", "بلاط"],
        "doors": ["door", "باب", "أبواب"]
    }

    keywords = keyword_map.get(selection_type, [selection_type])

    # Filter materials by name keywords (since categories are generic)
    matching_materials = []
    for material in materials_db:
        material_name = material.get("name", "").lower()
        # Check if any keyword matches
        if any(keyword.lower() in material_name for keyword in keywords):
            # Exclude labor items (they have "Labor" or "Skilled Worker" in name)
            if "labor" not in material_name and "skilled worker" not in material_name:
                matching_materials.append(material)

    # Take top 5 options
    options = matching_materials[:5]

    # Generate question
    if language == "ar":
        intro = f"اختر {selection_type}:\n\n"
    else:
        intro = f"Please select {selection_type.replace('_', ' ')}:\n\n"

    options_text = ""
    for i, material in enumerate(options, 1):
        name = material.get("name", "Unknown")
        price = material.get("price", 0)
        unit = material.get("unit", "unit")
        currency = material.get("currency", "EGP")

        if language == "ar":
            options_text += f"{i}. {name} - {price} {currency}/{unit}\n"
        else:
            options_text += f"{i}. {name} - {price} {currency}/{unit}\n"

    if language == "ar":
        footer = "\nأدخل الرقم أو اسم المادة."
    else:
        footer = "\nEnter the number or material name."

    return intro + options_text + footer


def _process_user_selection(
    user_message: str,
    selection_type: str,
    materials_db: list,
    room_groups: Dict[str, Any],
    current_selections: Dict[str, Any]
) -> Dict[str, Any]:
    """Process user's material selection from their message."""
    selections = current_selections.copy()
    message_lower = user_message.lower()

    # Map selection types to name keywords (must match _generate_material_question)
    keyword_map = {
        "flooring": ["floor", "flooring", "أرضية", "أرضيات"],
        "wall_paint": ["paint", "emulsion", "دهان", "طلاء"],
        "ceiling_paint": ["paint", "emulsion", "ceiling", "دهان", "سقف"],
        "bathroom_tiles": ["tile", "ceramic", "porcelain", "سيراميك", "بلاط"],
        "kitchen_tiles": ["tile", "ceramic", "porcelain", "سيراميك", "بلاط"],
        "doors": ["door", "باب", "أبواب"]
    }

    keywords = keyword_map.get(selection_type, [selection_type])

    # Filter materials by name keywords (same logic as _generate_material_question)
    matching_materials = []
    for material in materials_db:
        material_name = material.get("name", "").lower()
        if any(keyword.lower() in material_name for keyword in keywords):
            if "labor" not in material_name and "skilled worker" not in material_name:
                matching_materials.append(material)

    selected_material = None

    # Try to match by number (1, 2, 3, etc.)
    import re
    number_match = re.search(r'\b([1-5])\b', user_message)
    if number_match:
        idx = int(number_match.group(1)) - 1
        if 0 <= idx < len(matching_materials):
            selected_material = matching_materials[idx]

    # Try to match by name keyword
    if not selected_material:
        for material in matching_materials:
            material_name = material.get("name", "").lower()
            if any(word in message_lower for word in material_name.split()):
                selected_material = material
                break

    # Use first material as default if no match
    if not selected_material and matching_materials:
        selected_material = matching_materials[0]
        logger.info(f"No clear selection found, using first available: {selected_material.get('name')}")

    if selected_material:
        selections[selection_type] = {
            "material_id": selected_material.get("id"),
            "material_name": selected_material.get("name"),
            "price_per_unit": selected_material.get("price"),
            "unit": selected_material.get("unit"),
            "currency": selected_material.get("currency")
        }

    return selections


# ============= NODE FUNCTIONS =============


def determine_needed_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Determine what material selections are needed based on current finishing status.

    Returns: List of needed selection types and room groups
    """
    requirements = state.get("requirements", {})

    rooms_breakdown = requirements.get("rooms_breakdown", [])
    total_area = requirements.get("total_area_sqm", 100)
    current_status = requirements.get("current_finishing_status", "semi_finished")

    # Group rooms by type
    room_groups = _group_rooms_by_type(rooms_breakdown, total_area)

    # Determine needed selections
    needed_selections = _determine_needed_selections(current_status)

    logger.info(
        f"Materials needed: {needed_selections} for {len(room_groups)} room types"
    )

    return {
        "materials_room_groups": room_groups,
        "materials_needed_selections": needed_selections,
        "current_agent": "materials_subgraph"
    }


def check_progress_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Check selection progress and determine routing.

    Returns: Progress status and routing decision
    """
    material_selections = state.get("material_selections") or {}
    room_groups = state.get("materials_room_groups", {})
    needed_selections = state.get("materials_needed_selections", [])

    # Check progress using helper function
    progress = _check_selection_progress(
        material_selections,
        needed_selections,
        room_groups
    )

    logger.info(
        f"Selection progress: "
        f"{len(progress.get('completed', []))} / {len(needed_selections)} complete"
    )

    return {
        "materials_selection_progress": progress
    }


def present_options_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Present material options to user for the next needed selection.

    Returns: AI message with material choices
    """
    materials_db = state.get("materials", [])
    room_groups = state.get("materials_room_groups", {})
    progress = state.get("materials_selection_progress", {})

    # Get last user message for language detection
    messages = state.get("messages", [])
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    language = detect_language(last_user_message) if last_user_message else "en"

    # Get next selection needed
    next_selection = progress.get("next_needed")

    if not next_selection:
        logger.warning("No next selection found, completing")
        return {}

    # Generate question using helper
    question = _generate_material_question(
        next_selection,
        materials_db,
        room_groups,
        language
    )

    return {
        "messages": [AIMessage(content=question)]
    }


def parse_selection_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Parse user's material selection from their message.

    Returns: Updated material_selections dict
    """
    messages = state.get("messages", [])
    materials_db = state.get("materials", [])
    room_groups = state.get("materials_room_groups", {})
    material_selections = state.get("material_selections") or {}
    progress = state.get("materials_selection_progress", {})

    # Get last user message
    last_user_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    if not last_user_message:
        logger.warning("No user message to parse")
        return {}

    next_selection = progress.get("next_needed")

    # Process selection using helper
    updated_selections = _process_user_selection(
        last_user_message,
        next_selection,
        materials_db,
        room_groups,
        material_selections
    )

    if updated_selections != material_selections:
        logger.info(f"Material selection updated: {next_selection}")

    return {
        "material_selections": updated_selections
    }


def validate_complete_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Validate if all material selections are complete.

    Returns: Routing decision (complete or need_more)
    """
    progress = state.get("materials_selection_progress", {})

    all_complete = progress.get("all_complete", False)

    if all_complete:
        logger.info("All material selections complete")
        return {
            "materials_validation": {
                "all_complete": True,
                "route": "complete"
            }
        }
    else:
        logger.info("More material selections needed")
        return {
            "materials_validation": {
                "all_complete": False,
                "route": "continue"
            }
        }


def complete_materials_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Mark material selection as complete.

    Returns: Completion flag and confirmation message
    """
    material_selections = state.get("material_selections", {})

    # Get language for confirmation
    messages = state.get("messages", [])
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    language = detect_language(last_user_message) if last_user_message else "en"

    if language == "ar":
        confirmation = "تمام! اختياراتك مسجلة. جاري حساب التكاليف..."
    else:
        confirmation = "Material selections complete. Calculating costs..."

    logger.info(f"Material selection complete: {len(material_selections)} selections made")

    return {
        "material_selection_complete": True,
        "messages": [AIMessage(content=confirmation)]
    }
