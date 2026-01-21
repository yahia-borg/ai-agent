"""
Structured logging utilities for agent decisions and state transitions.
Uses JSON format for better analysis and observability.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


def log_agent_decision(
    event_type: str,
    quotation_id: str,
    session_id: Optional[str] = None,
    phase: Optional[str] = None,
    tool_selected: Optional[str] = None,
    reasoning: Optional[str] = None,
    alternatives_considered: Optional[List[str]] = None,
    state_before: Optional[Dict[str, Any]] = None,
    state_after: Optional[Dict[str, Any]] = None,
    **kwargs
) -> None:
    """
    Log agent decision with structured JSON format.
    
    Args:
        event_type: Type of event (tool_selected, phase_transition, state_update, etc.)
        quotation_id: Quotation ID
        session_id: Optional session ID
        phase: Current phase
        tool_selected: Tool that was selected
        reasoning: Reasoning for the decision
        alternatives_considered: List of alternative tools/actions considered
        state_before: State before the decision
        state_after: State after the decision
        **kwargs: Additional context fields
    """
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "quotation_id": quotation_id,
        "session_id": session_id,
        "phase": phase,
        "tool_selected": tool_selected,
        "reasoning": reasoning,
        "alternatives_considered": alternatives_considered,
        **kwargs
    }
    
    # Remove None values for cleaner logs
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    # Log as JSON string for structured logging
    logger.info(f"AGENT_DECISION: {json.dumps(log_data, ensure_ascii=False)}")


def log_tool_selection(
    quotation_id: str,
    tool_name: str,
    reasoning: str,
    alternatives: Optional[List[str]] = None,
    phase: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """Log tool selection decision."""
    log_agent_decision(
        event_type="tool_selected",
        quotation_id=quotation_id,
        session_id=session_id,
        phase=phase,
        tool_selected=tool_name,
        reasoning=reasoning,
        alternatives_considered=alternatives,
        **kwargs
    )


def log_phase_transition(
    quotation_id: str,
    from_phase: str,
    to_phase: str,
    trigger: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """Log phase transition."""
    log_agent_decision(
        event_type="phase_transition",
        quotation_id=quotation_id,
        session_id=session_id,
        phase=to_phase,
        reasoning=f"Transitioned from {from_phase} to {to_phase}",
        transition_from=from_phase,
        transition_to=to_phase,
        trigger=trigger,
        **kwargs
    )


def log_state_update(
    quotation_id: str,
    update_type: str,
    changes: Dict[str, Any],
    phase: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """Log state update."""
    log_agent_decision(
        event_type="state_update",
        quotation_id=quotation_id,
        session_id=session_id,
        phase=phase,
        update_type=update_type,
        changes=changes,
        **kwargs
    )


def log_tool_execution(
    quotation_id: str,
    tool_name: str,
    success: bool,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    phase: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """Log tool execution result."""
    log_agent_decision(
        event_type="tool_execution",
        quotation_id=quotation_id,
        session_id=session_id,
        phase=phase,
        tool_selected=tool_name,
        execution_success=success,
        duration_ms=duration_ms,
        error=error,
        **kwargs
    )
