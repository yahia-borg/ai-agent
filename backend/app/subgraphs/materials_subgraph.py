"""
Materials Selection Subgraph for user material choices.

Flow with loop:
START → determine_needed → check_progress → [complete | present_options]
                                                            ↓
                                              parse_selection ← [user responds]
                                                            ↓
                                                    check_progress (loops back)

Returns Command to route back to supervisor.
"""
from typing import Literal
import logging

from langgraph.graph import StateGraph, END
from app.state.schemas import CostEstimationState
from app.subgraphs.nodes.materials_nodes import (
    determine_needed_node,
    check_progress_node,
    present_options_node,
    parse_selection_node,
    validate_complete_node,
    complete_materials_node
)

logger = logging.getLogger(__name__)


def should_continue_selection(state: CostEstimationState) -> Literal["complete", "continue"]:
    """
    Determine if material selection is complete or needs more input.

    Returns:
        "complete" if all selections done
        "continue" if more selections needed
    """
    validation = state.get("materials_validation", {})

    if validation.get("all_complete", False):
        return "complete"
    else:
        return "continue"


def build_materials_subgraph():
    """
    Build the materials selection subgraph.

    Internal structure:
    - determine_needed: Calculate required selections based on finishing status
    - check_progress: Check selection progress
    - validate_complete: Determine if all selections done
    - present_options: Show material choices to user (if not complete)
    - parse_selection: Extract user's choice from their message
    - complete: Mark material selection as complete

    Flow includes a loop: present_options → parse_selection → check_progress → [complete | present_options]

    Returns compiled subgraph that can be used as a node in the main graph.
    """
    logger.info("Building materials subgraph")

    builder = StateGraph(CostEstimationState)

    # Add nodes
    builder.add_node("determine_needed", determine_needed_node)
    builder.add_node("check_progress", check_progress_node)
    builder.add_node("validate_complete", validate_complete_node)
    builder.add_node("present_options", present_options_node)
    builder.add_node("parse_selection", parse_selection_node)
    builder.add_node("complete", complete_materials_node)

    # Set entry point
    builder.set_entry_point("determine_needed")

    # determine_needed → check_progress
    builder.add_edge("determine_needed", "check_progress")

    # check_progress → validate_complete
    builder.add_edge("check_progress", "validate_complete")

    # validate_complete → [complete | present_options]
    builder.add_conditional_edges(
        "validate_complete",
        should_continue_selection,
        {
            "complete": "complete",
            "continue": "present_options"
        }
    )

    # present_options → END (waits for user response)
    # When user responds, supervisor routes back to materials_subgraph
    # which re-enters at determine_needed, then:
    # - check_progress sees new user message
    # - routes to parse_selection
    builder.add_edge("present_options", END)

    # If we re-entered after user response, parse_selection → check_progress
    builder.add_edge("parse_selection", "check_progress")

    # complete → END
    builder.add_edge("complete", END)

    # Compile
    graph = builder.compile()

    logger.info("Materials subgraph built successfully")

    return graph
