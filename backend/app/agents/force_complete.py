"""
Force Complete Node - Handles forced completion scenarios.

Triggered when max attempts reached but minimum requirements exist.
Applies defaults and routes to continue workflow.

This node uses Command since it needs dynamic routing.
"""
from typing import Dict, Any, Literal
from langgraph.types import Command

from app.state.schemas import CostEstimationState, RoutingDest, WorkflowStatus
from app.agents.supervisor import has_minimum_requirements
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


# ============= DEFAULT VALUES =============

DEFAULT_FINISHING_LEVEL = "standard"
DEFAULT_LOCATION = "Cairo"

RESIDENTIAL_ROOM_BREAKDOWN = [
    {"room": "Living Room", "percentage": 0.25},
    {"room": "Bedroom", "percentage": 0.20},
    {"room": "Kitchen", "percentage": 0.15},
    {"room": "Bathroom", "percentage": 0.10},
    {"room": "Other", "percentage": 0.30},
]

COMMERCIAL_ROOM_BREAKDOWN = [
    {"room": "Main Space", "percentage": 0.80},
    {"room": "Office", "percentage": 0.10},
    {"room": "Bathroom", "percentage": 0.10},
]

FACTORY_ROOM_BREAKDOWN = [
    {"room": "Workshop", "percentage": 0.90},
    {"room": "Office", "percentage": 0.10},
]


# ============= DEFAULT APPLICATION =============

def apply_defaults(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply default values for missing optional fields.
    
    Defaults:
    - finishing_level: "standard"
    - location: "Cairo"  
    - rooms: auto-calculated from total_area
    """
    updated = requirements.copy() if requirements else {}
    
    # Default finishing level
    if not updated.get("finishing_level"):
        updated["finishing_level"] = DEFAULT_FINISHING_LEVEL
        logger.debug(f"Applied default finishing_level: {DEFAULT_FINISHING_LEVEL}")
    
    # Default location
    if not updated.get("location"):
        updated["location"] = DEFAULT_LOCATION
        logger.debug(f"Applied default location: {DEFAULT_LOCATION}")
    
    # Auto-calculate rooms
    if not updated.get("rooms") and updated.get("total_area_sqm"):
        updated["rooms"] = _calculate_room_breakdown(
            updated["total_area_sqm"],
            updated.get("project_type", "residential")
        )
        logger.debug(f"Auto-calculated {len(updated['rooms'])} rooms")
    
    return updated


def _calculate_room_breakdown(total_area: float, project_type: str) -> list[Dict[str, Any]]:
    """Calculate room breakdown based on project type."""
    if project_type == "residential":
        breakdown = RESIDENTIAL_ROOM_BREAKDOWN
    elif project_type == "commercial":
        breakdown = COMMERCIAL_ROOM_BREAKDOWN
    else:  # factory
        breakdown = FACTORY_ROOM_BREAKDOWN
    
    return [
        {"room": item["room"], "area_sqm": round(total_area * item["percentage"], 2)}
        for item in breakdown
    ]


# ============= NODE =============

def force_complete_node(state: CostEstimationState) -> Command[RoutingDest]:
    """
    Force complete node that applies defaults and routes forward.
    
    Uses Command for dynamic routing:
    - If minimum requirements exist → calculation_agent or data_retrieval_agent
    - If minimum requirements missing → __end__ with error
    
    Flow:
    1. Apply defaults to requirements
    2. Validate minimum requirements
    3. Route to next stage or error
    """
    requirements = state.get("requirements", {}) or {}
    errors = state.get("errors", []).copy()
    
    logger.info("Force complete: applying defaults")
    
    # Apply defaults
    updated_requirements = apply_defaults(requirements)
    
    # Check minimum requirements
    if not has_minimum_requirements(updated_requirements):
        logger.error("Force complete failed: minimum requirements missing")
        return Command(
            update={
                "requirements": updated_requirements,
                "workflow_status": WorkflowStatus.ERROR.value,
                "errors": errors + ["Unable to proceed: missing minimum requirements (project_type and total_area_sqm)"]
            },
            goto="__end__"
        )
    
    # Mark requirements complete
    update: Dict[str, Any] = {
        "requirements": updated_requirements,
        "requirements_complete": True,
    }
    
    # Determine next stage
    postgres_complete = state.get("postgres_data_complete", False)
    qdrant_complete = state.get("qdrant_knowledge_complete", False)

    if not postgres_complete or not qdrant_complete:
        # Skip data retrieval, use estimates
        logger.info("Force complete: skipping data retrieval, using estimates")
        update["postgres_data_complete"] = True
        update["qdrant_knowledge_complete"] = True
        update["materials"] = state.get("materials", [])
        update["labor_rates"] = state.get("labor_rates", [])
        update["qdrant_knowledge"] = state.get("qdrant_knowledge", [])
        update["workflow_status"] = WorkflowStatus.CALCULATING.value
        return Command(update=update, goto="calculation_agent")
    
    if not state.get("calculation_complete", False):
        logger.info("Force complete: routing to calculation")
        update["workflow_status"] = WorkflowStatus.CALCULATING.value
        return Command(update=update, goto="calculation_agent")
    
    # All complete
    logger.info("Force complete: all stages done")
    update["workflow_status"] = WorkflowStatus.COMPLETE.value
    return Command(update=update, goto="__end__")