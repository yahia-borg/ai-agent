"""
Qdrant Knowledge Subgraph for fetching building codes and finishing standards.

NON-CRITICAL SUBGRAPH: Can proceed with empty knowledge if Qdrant fails.

Flow:
START → search_finishing_standards → search_building_codes → validate → complete → END

Returns Command to route back to supervisor.
"""
import logging

from langgraph.graph import StateGraph, END
from app.state.schemas import CostEstimationState
from app.subgraphs.nodes.qdrant_knowledge_nodes import (
    search_finishing_standards_node,
    search_building_codes_node,
    validate_knowledge_node,
    complete_qdrant_node
)

logger = logging.getLogger(__name__)


def build_qdrant_knowledge_subgraph():
    """
    Build the Qdrant knowledge retrieval subgraph.

    Internal structure:
    - search_finishing_standards: Query finishing standards from Qdrant
    - search_building_codes: Query Egypt building codes from Qdrant
    - validate: Check knowledge adequacy (≥5 items, avg score ≥0.7)
    - complete: Mark as complete (always completes, even with empty data)

    Returns compiled subgraph that can be used as a node in the main graph.
    """
    logger.info("Building qdrant knowledge subgraph")

    builder = StateGraph(CostEstimationState)

    # Add nodes
    builder.add_node("search_finishing_standards", search_finishing_standards_node)
    builder.add_node("search_building_codes", search_building_codes_node)
    builder.add_node("validate", validate_knowledge_node)
    builder.add_node("complete", complete_qdrant_node)

    # Set entry point
    builder.set_entry_point("search_finishing_standards")

    # search_finishing_standards → search_building_codes
    builder.add_edge("search_finishing_standards", "search_building_codes")

    # search_building_codes → validate
    builder.add_edge("search_building_codes", "validate")

    # validate → complete (always, even if validation fails)
    # Non-critical: we can proceed without knowledge
    builder.add_edge("validate", "complete")

    # complete → END
    builder.add_edge("complete", END)

    # Compile
    graph = builder.compile()

    logger.info("Qdrant knowledge subgraph built successfully")

    return graph
