"""
Requirements Subgraph for gathering and validating project requirements.

Flow:
START → extract → validate → [complete | generate_question] → END

Returns Command to route back to supervisor.
"""
from typing import Literal
import logging

from langgraph.graph import StateGraph, END
from langgraph.types import Command
from app.state.schemas import CostEstimationState
from app.subgraphs.nodes.requirements_nodes import (
    extract_node,
    validate_node,
    generate_question_node,
    complete_node
)

logger = logging.getLogger(__name__)


def should_ask_question(state: CostEstimationState) -> Literal["complete", "ask_question"]:
    """
    Determine if we should ask a follow-up question or complete.

    Returns:
        "complete" if requirements are complete or user confirmed proceed
        "ask_question" if missing required fields
    """
    validation = state.get("requirements_validation", {})

    # User confirmed proceed (escape intent)
    if validation.get("user_confirmed_proceed", False):
        return "complete"

    # Check if complete
    if validation.get("is_complete", False):
        return "complete"

    # Missing required fields
    return "ask_question"


def build_requirements_subgraph():
    """
    Build the requirements gathering subgraph.

    Internal structure:
    - extract: Extract requirements from user message
    - validate: Check completeness
    - generate_question: Create follow-up question (if incomplete)
    - complete: Mark requirements as complete

    Returns compiled subgraph that can be used as a node in the main graph.
    """
    logger.info("Building requirements subgraph")

    builder = StateGraph(CostEstimationState)

    # Add nodes
    builder.add_node("extract", extract_node)
    builder.add_node("validate", validate_node)
    builder.add_node("generate_question", generate_question_node)
    builder.add_node("complete", complete_node)

    # Set entry point
    builder.set_entry_point("extract")

    # extract → validate
    builder.add_edge("extract", "validate")

    # validate → [complete | generate_question]
    builder.add_conditional_edges(
        "validate",
        should_ask_question,
        {
            "complete": "complete",
            "ask_question": "generate_question"
        }
    )

    # complete → END
    builder.add_edge("complete", END)

    # generate_question → END (waits for user response)
    builder.add_edge("generate_question", END)

    # Compile (no checkpointer needed for subgraph)
    graph = builder.compile()

    logger.info("Requirements subgraph built successfully")

    return graph
