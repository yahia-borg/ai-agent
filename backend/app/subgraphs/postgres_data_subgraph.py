"""
Postgres Data Subgraph for fetching materials and labor rates.

CRITICAL SUBGRAPH: Must succeed for quotation generation.
No fallbacks, no hardcoded prices, no location filtering.

Flow:
START → fetch_materials → fetch_labor_rates → validate → [complete | failed] → END

Returns Command to route back to supervisor.
"""
from typing import Literal
import logging

from langgraph.graph import StateGraph, END
from app.state.schemas import CostEstimationState
from app.subgraphs.nodes.postgres_data_nodes import (
    fetch_materials_node,
    fetch_labor_rates_node,
    validate_coverage_node,
    complete_postgres_node,
    failed_postgres_node
)

logger = logging.getLogger(__name__)


def should_complete(state: CostEstimationState) -> Literal["complete", "failed"]:
    """
    Determine if validation passed or failed.

    Returns:
        "complete" if validation passed
        "failed" if validation failed (stops workflow)
    """
    validation = state.get("postgres_validation", {})
    is_valid = validation.get("is_valid", False)

    logger.info(f"Postgres routing decision: validation={validation}, is_valid={is_valid}")

    if is_valid:
        logger.info("Routing to: complete")
        return "complete"
    else:
        logger.warning("Routing to: failed")
        return "failed"


def build_postgres_data_subgraph():
    """
    Build the Postgres data retrieval subgraph.

    Internal structure:
    - fetch_materials: Query ALL materials from PostgreSQL
    - fetch_labor_rates: Query ALL labor rates from PostgreSQL
    - validate: Check data coverage (≥30 materials, ≥5 labor categories)
    - complete: Mark as complete (validation passed)
    - failed: Stop workflow with error (validation failed)

    Returns compiled subgraph that can be used as a node in the main graph.
    """
    logger.info("Building postgres data subgraph")

    builder = StateGraph(CostEstimationState)

    # Add nodes
    builder.add_node("fetch_materials", fetch_materials_node)
    builder.add_node("fetch_labor_rates", fetch_labor_rates_node)
    builder.add_node("validate", validate_coverage_node)
    builder.add_node("complete", complete_postgres_node)
    builder.add_node("failed", failed_postgres_node)

    # Set entry point
    builder.set_entry_point("fetch_materials")

    # fetch_materials → fetch_labor_rates
    builder.add_edge("fetch_materials", "fetch_labor_rates")

    # fetch_labor_rates → validate
    builder.add_edge("fetch_labor_rates", "validate")

    # validate → [complete | failed]
    builder.add_conditional_edges(
        "validate",
        should_complete,
        {
            "complete": "complete",
            "failed": "failed"
        }
    )

    # complete → END
    builder.add_edge("complete", END)

    # failed → END (workflow will stop with error)
    builder.add_edge("failed", END)

    # Compile
    graph = builder.compile()

    logger.info("Postgres data subgraph built successfully")

    return graph
