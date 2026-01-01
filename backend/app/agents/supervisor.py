"""
Supervisor Router - State-based routing for cost estimation workflow.

This is a ROUTER, not an LLM orchestrator.
It reads completion flags and routes to the appropriate agent.
All routing uses Command pattern for type safety.
"""
from typing import Dict, Any
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from app.state.schemas import CostEstimationState, RoutingDest, WorkflowStatus
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


# ============= VALIDATION HELPERS =============

def has_minimum_requirements(requirements: Dict[str, Any] | None) -> bool:
    """
    Check if minimum required fields exist.
    
    Minimum requirements:
    - project_type: must be residential/commercial/factory
    - total_area_sqm: must be > 0
    """
    if not requirements:
        return False
    
    project_type = requirements.get("project_type")
    total_area = requirements.get("total_area_sqm")
    
    valid_type = project_type in ("residential", "commercial", "factory")
    valid_area = isinstance(total_area, (int, float)) and total_area > 0
    
    return valid_type and valid_area


def has_new_user_message(messages: list) -> bool:
    """Check if user sent a new message after last AI response."""
    if not messages:
        return False
    
    last_ai_idx = -1
    last_human_idx = -1
    
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage) and last_ai_idx == -1:
            last_ai_idx = i
        if isinstance(messages[i], HumanMessage) and last_human_idx == -1:
            last_human_idx = i
        if last_ai_idx >= 0 and last_human_idx >= 0:
            break
    
    return last_human_idx > last_ai_idx


def is_session_timed_out(started_at: str | None) -> bool:
    """Check if session exceeded timeout."""
    if not started_at:
        return False
    
    try:
        start_time = datetime.fromisoformat(started_at)
        timeout = timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)
        return datetime.utcnow() - start_time > timeout
    except (ValueError, TypeError):
        logger.warning(f"Invalid started_at: {started_at}")
        return False


# ============= ROUTING HELPERS =============

def _make_update(
    turn_count: int,
    agent_attempts: Dict[str, int],
    errors: list[str],
    **extra
) -> Dict[str, Any]:
    """Create base update dict."""
    return {
        "turn_count": turn_count,
        "current_agent": "supervisor",
        "agent_attempts": agent_attempts,
        "errors": errors,
        **extra
    }


def _route_end(
    turn_count: int,
    agent_attempts: Dict[str, int],
    errors: list[str],
    status: WorkflowStatus,
    error_msg: str | None = None
) -> Command[RoutingDest]:
    """Route to __end__ with status."""
    err_list = errors + [error_msg] if error_msg else errors
    update = _make_update(turn_count, agent_attempts, err_list, workflow_status=status.value)
    return Command(update=update, goto="__end__")


def _route_force_complete(
    turn_count: int,
    agent_attempts: Dict[str, int],
    errors: list[str],
    error_msg: str | None = None
) -> Command[RoutingDest]:
    """Route to force_complete."""
    err_list = errors + [error_msg] if error_msg else errors
    update = _make_update(
        turn_count, agent_attempts, err_list,
        workflow_status=WorkflowStatus.FORCED_COMPLETION.value
    )
    return Command(update=update, goto="force_complete")


def _route_to_agent(
    turn_count: int,
    agent_attempts: Dict[str, int],
    errors: list[str],
    agent_name: RoutingDest,
    status: WorkflowStatus,
    **extra_updates
) -> Command[RoutingDest]:
    """Route to an agent with incremented attempts."""
    # Increment attempts for this agent
    updated_attempts = agent_attempts.copy()
    updated_attempts[agent_name] = updated_attempts.get(agent_name, 0) + 1
    
    update = _make_update(
        turn_count, updated_attempts, errors,
        workflow_status=status.value,
        **extra_updates
    )
    return Command(update=update, goto=agent_name)


# ============= MAIN ROUTER =============

def supervisor_node(state: CostEstimationState) -> Command[RoutingDest]:
    """
    State-based router for cost estimation workflow.
    
    NOT an LLM - pure control flow logic based on completion flags.
    
    Routing Priority:
    1. Turn limit → force_complete
    2. Session timeout → __end__ (error)
    3. User confirmed proceed → force_complete
    4. Requirements stage (with max attempts check)
    5. Data retrieval stage (with max attempts check)
    6. Calculation stage (with max attempts check)
    7. New user message after completion → requirements_agent
    8. All complete → __end__
    
    Args:
        state: Current workflow state
        
    Returns:
        Command with routing destination and state updates
    """
    # === Extract state values ===
    turn_count = state.get("turn_count", 0) + 1
    agent_attempts = state.get("agent_attempts", {}).copy()
    errors = state.get("errors", []).copy()
    
    logger.info(
        f"Router: turn={turn_count}, "
        f"req_complete={state.get('requirements_complete', False)}, "
        f"postgres_complete={state.get('postgres_data_complete', False)}, "
        f"qdrant_complete={state.get('qdrant_knowledge_complete', False)}, "
        f"mat_sel_complete={state.get('material_selection_complete', False)}, "
        f"calc_complete={state.get('calculation_complete', False)}"
    )
    
    # === 1. Turn Limit ===
    if turn_count >= settings.MAX_TOTAL_TURNS:
        logger.warning(f"Turn limit reached: {turn_count}")
        return _route_force_complete(
            turn_count, agent_attempts, errors,
            "Maximum turn limit reached"
        )
    
    # === 2. Session Timeout ===
    if is_session_timed_out(state.get("started_at")):
        logger.warning("Session timeout")
        return _route_end(
            turn_count, agent_attempts, errors,
            WorkflowStatus.TIMEOUT,
            "Session timeout exceeded"
        )
    
    # === 3. User Confirmed Proceed ===
    if state.get("user_confirmed_proceed", False):
        logger.info("User confirmed proceed")
        return _route_force_complete(turn_count, agent_attempts, errors)
    
    # === 4. Requirements Stage ===
    if not state.get("requirements_complete", False):
        req_attempts = agent_attempts.get("requirements_subgraph", 0)

        # Check if we just asked a question (no new user message)
        # If so, end the graph and wait for user response
        if req_attempts > 0 and not has_new_user_message(state.get("messages", [])):
            logger.info("Requirements incomplete, waiting for user response")
            return _route_end(
                turn_count, agent_attempts, errors,
                WorkflowStatus.GATHERING_REQUIREMENTS,
                None  # No error - just waiting for user input
            )

        if req_attempts >= settings.MAX_REQUIREMENTS_ATTEMPTS:
            requirements = state.get("requirements", {})

            if has_minimum_requirements(requirements):
                logger.info("Max requirements attempts with minimum - forcing completion")
                return _route_force_complete(
                    turn_count, agent_attempts, errors,
                    "Max attempts reached, using minimum requirements"
                )
            else:
                logger.error("Max requirements attempts without minimum")
                return _route_end(
                    turn_count, agent_attempts, errors,
                    WorkflowStatus.ERROR,
                    "Unable to gather minimum requirements (project_type and total_area_sqm)"
                )

        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "requirements_subgraph",
            WorkflowStatus.GATHERING_REQUIREMENTS
        )

    # === 5. Postgres Data Stage (NEW - Split from data_retrieval) ===
    if not state.get("postgres_data_complete", False):
        postgres_attempts = agent_attempts.get("postgres_data_subgraph", 0)

        if postgres_attempts >= settings.MAX_DATA_RETRIEVAL_ATTEMPTS:
            logger.error("Max Postgres data retrieval attempts - CRITICAL FAILURE")
            return _route_end(
                turn_count, agent_attempts, errors,
                WorkflowStatus.ERROR,
                "CRITICAL: Unable to retrieve materials/labor rates from database"
            )

        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "postgres_data_subgraph",
            WorkflowStatus.RETRIEVING_DATA
        )

    # === 6. Qdrant Knowledge Stage (NEW - Split from data_retrieval) ===
    if not state.get("qdrant_knowledge_complete", False):
        qdrant_attempts = agent_attempts.get("qdrant_knowledge_subgraph", 0)

        if qdrant_attempts >= settings.MAX_DATA_RETRIEVAL_ATTEMPTS:
            logger.warning("Max Qdrant knowledge retrieval attempts - proceeding without knowledge (non-critical)")
            # Non-critical: continue without knowledge
            return Command(
                update={
                    "turn_count": turn_count,
                    "current_agent": "supervisor",
                    "agent_attempts": agent_attempts,
                    "qdrant_knowledge_complete": True,  # Mark as complete to continue
                    "qdrant_knowledge": [],  # Empty knowledge
                    "errors": errors + ["Qdrant knowledge retrieval max attempts - continuing without building codes"]
                },
                goto="supervisor"
            )

        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "qdrant_knowledge_subgraph",
            WorkflowStatus.RETRIEVING_DATA
        )

    # === 7. Material Selection Stage ===
    if not state.get("material_selection_complete", False):
        mat_sel_attempts = agent_attempts.get("materials_subgraph", 0)

        # Check if waiting for user response
        if mat_sel_attempts > 0 and not has_new_user_message(state.get("messages", [])):
            logger.info("Material selection incomplete, waiting for user response")
            return _route_end(
                turn_count, agent_attempts, errors,
                WorkflowStatus.SELECTING_MATERIALS,
                None  # No error - just waiting for user input
            )

        if mat_sel_attempts >= settings.MAX_REQUIREMENTS_ATTEMPTS:  # Reuse max requirements attempts
            logger.warning("Max material selection attempts - proceeding with defaults")
            return _route_to_agent(
                turn_count, agent_attempts, errors,
                "calculation_agent",
                WorkflowStatus.CALCULATING,
                material_selection_complete=True  # Force complete
            )

        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "materials_subgraph",
            WorkflowStatus.SELECTING_MATERIALS
        )

    # === 8. Calculation Stage ===
    if not state.get("calculation_complete", False):
        calc_attempts = agent_attempts.get("calculation_agent", 0)

        if calc_attempts >= settings.MAX_CALCULATION_ATTEMPTS:
            logger.error("Max calculation attempts")
            return _route_end(
                turn_count, agent_attempts, errors,
                WorkflowStatus.ERROR,
                "Max calculation attempts reached"
            )

        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "calculation_agent",
            WorkflowStatus.CALCULATING
        )

    # === 9. New User Message After Completion ===
    if has_new_user_message(state.get("messages", [])):
        logger.info("New user message after completion - re-entering workflow")
        return _route_to_agent(
            turn_count, agent_attempts, errors,
            "requirements_subgraph",
            WorkflowStatus.GATHERING_REQUIREMENTS,
            postgres_data_complete=False,
            qdrant_knowledge_complete=False,
            material_selection_complete=False,
            calculation_complete=False
        )

    # === 10. All Complete ===
    logger.info("Workflow complete")
    return _route_end(
        turn_count, agent_attempts, errors,
        WorkflowStatus.COMPLETE
    )