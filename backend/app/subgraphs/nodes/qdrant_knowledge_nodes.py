"""
Qdrant knowledge retrieval nodes for building codes and finishing standards.

NON-CRITICAL: Can continue with empty data if Qdrant fails.

Nodes:
- search_finishing_standards_node: Query finishing standards from Qdrant
- search_building_codes_node: Query Egypt building codes from Qdrant
- validate_knowledge_node: Ensure adequate knowledge (≥5 standards, ≥3 codes)
"""
from typing import Dict, Any
import logging

from app.state.schemas import CostEstimationState
from app.services.qdrant_service import get_qdrant_service

logger = logging.getLogger(__name__)


def search_finishing_standards_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Search Qdrant for finishing standards based on requirements.

    Query based on: current_finishing_status + desired_finishing_style

    Returns: List of relevant finishing standards
    """
    requirements = state.get("requirements", {}) or {}

    # Build search query
    finishing_status = requirements.get("current_finishing_status", "")
    finishing_style = requirements.get("desired_finishing_style", "modern")

    query = f"{finishing_status} {finishing_style} finishing standards Egypt construction"

    logger.info(f"Searching Qdrant for finishing standards: {query}")

    try:
        qdrant_service = get_qdrant_service()

        # Search with top_k=10 for better coverage
        results = qdrant_service.search_knowledge(query, top_k=10)

        # Filter by score (≥0.7 for relevance)
        filtered_results = [r for r in results if r.get("score", 0) >= 0.7]

        logger.info(
            f"Found {len(filtered_results)} finishing standards "
            f"(score ≥ 0.7) from {len(results)} total"
        )

        return {
            "qdrant_knowledge": filtered_results,
            "current_agent": "qdrant_knowledge_subgraph"
        }

    except Exception as e:
        logger.warning(f"Qdrant finishing standards search failed: {e}")
        # Non-critical - return empty list
        return {
            "qdrant_knowledge": [],
            "errors": [f"Qdrant finishing standards search failed: {e}"]
        }


def search_building_codes_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Search Qdrant for Egypt building codes based on project type.

    Query based on: project_type + location

    Returns: Accumulated list of building codes + finishing standards
    """
    requirements = state.get("requirements", {}) or {}
    existing_knowledge = state.get("qdrant_knowledge", [])

    # Build search query
    project_type = requirements.get("project_type", "residential")
    location = requirements.get("location", "Egypt")

    query = f"Egypt building codes regulations {project_type} {location} construction standards"

    logger.info(f"Searching Qdrant for building codes: {query}")

    try:
        qdrant_service = get_qdrant_service()

        # Search with top_k=7 for building codes
        results = qdrant_service.search_knowledge(query, top_k=7)

        # Filter by score (≥0.6 for codes, slightly lower threshold)
        filtered_results = [r for r in results if r.get("score", 0) >= 0.6]

        # Combine with existing knowledge
        combined_knowledge = existing_knowledge + filtered_results

        logger.info(
            f"Found {len(filtered_results)} building codes "
            f"(score ≥ 0.6). Total knowledge items: {len(combined_knowledge)}"
        )

        return {
            "qdrant_knowledge": combined_knowledge
        }

    except Exception as e:
        logger.warning(f"Qdrant building codes search failed: {e}")
        # Non-critical - return existing knowledge
        return {
            "qdrant_knowledge": existing_knowledge,
            "errors": [f"Qdrant building codes search failed: {e}"]
        }


def validate_knowledge_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Validate that we have adequate knowledge from Qdrant.

    Validation criteria:
    - ≥5 total knowledge items
    - Average score ≥0.7

    NON-CRITICAL: Can proceed with empty knowledge if validation fails.

    Returns: Validation results and routing decision
    """
    knowledge = state.get("qdrant_knowledge", [])

    # Calculate metrics
    total_items = len(knowledge)

    if total_items == 0:
        logger.warning("No knowledge items retrieved from Qdrant")
        return {
            "qdrant_validation": {
                "is_valid": False,
                "total_items": 0,
                "route": "complete_with_empty"  # Continue anyway
            }
        }

    # Calculate average score
    scores = [item.get("score", 0) for item in knowledge]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Check if adequate
    is_adequate = total_items >= 5 and avg_score >= 0.7

    if is_adequate:
        logger.info(
            f"Qdrant knowledge validation passed: "
            f"{total_items} items, avg score {avg_score:.2f}"
        )
        return {
            "qdrant_validation": {
                "is_valid": True,
                "total_items": total_items,
                "avg_score": avg_score,
                "route": "complete"
            }
        }
    else:
        logger.warning(
            f"Qdrant knowledge below ideal threshold: "
            f"{total_items} items (want ≥5), avg score {avg_score:.2f} (want ≥0.7)"
        )
        return {
            "qdrant_validation": {
                "is_valid": False,
                "total_items": total_items,
                "avg_score": avg_score,
                "route": "complete_with_empty"  # Continue anyway (non-critical)
            }
        }


def complete_qdrant_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Mark qdrant knowledge retrieval as complete.

    Returns: Completion flag
    """
    knowledge = state.get("qdrant_knowledge", [])

    logger.info(f"Qdrant knowledge retrieval complete: {len(knowledge)} items")

    return {
        "qdrant_knowledge_complete": True
    }
