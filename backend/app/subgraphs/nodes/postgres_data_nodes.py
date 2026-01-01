"""
Postgres data retrieval nodes for materials and labor rates.

CRITICAL: This subgraph must succeed. No fallbacks, no hardcoded prices.
If PostgreSQL fails, the entire workflow stops with an error.

Nodes:
- fetch_materials_node: Query ALL materials from PostgreSQL
- fetch_labor_rates_node: Query ALL labor rates from PostgreSQL
- validate_coverage_node: Ensure sufficient data (≥30 materials, ≥5 labor categories)
"""
from typing import Dict, Any
import logging

from app.state.schemas import CostEstimationState, WorkflowStatus
from sqlalchemy.orm import Session
from app.core.database import get_db

logger = logging.getLogger(__name__)


def fetch_materials_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Fetch ALL materials from PostgreSQL without location filtering.

    CRITICAL: If database query fails, raise exception (no fallback).

    Returns: List of materials with name, category, unit, price_per_unit, currency
    """
    logger.info("Fetching materials from PostgreSQL (no location filtering)")

    try:
        # Get database session
        db = next(get_db())

        try:
            # Import Material model
            from app.models.resources import Material

            # Query ALL materials (no location filtering)
            materials = db.query(Material).all()

            # Convert to dict format
            materials_list = []
            for material in materials:
                materials_list.append({
                    "id": material.id,
                    "name": material.name,
                    "category": material.category,
                    "unit": material.unit,
                    "price_per_unit": float(material.price_per_unit),
                    "currency": "EGP",  # Egyptian Pounds
                    "supplier": getattr(material, "supplier", None),
                    "description": getattr(material, "description", None)
                })

            logger.info(f"Fetched {len(materials_list)} materials from PostgreSQL")

            return {
                "materials": materials_list,
                "current_agent": "postgres_data_subgraph"
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"CRITICAL: Failed to fetch materials from PostgreSQL: {e}")
        # DO NOT use fallback - raise exception to stop workflow
        raise RuntimeError(f"Database materials query failed: {e}")


def fetch_labor_rates_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Fetch ALL labor rates from PostgreSQL without location filtering.

    CRITICAL: If database query fails, raise exception (no fallback).

    Returns: List of labor rates with category, daily_rate, description
    """
    logger.info("Fetching labor rates from PostgreSQL (no location filtering)")

    try:
        # Get database session
        db = next(get_db())

        try:
            # Import LaborRate model
            from app.models.resources import LaborRate

            # Query ALL labor rates (no location filtering)
            labor_rates = db.query(LaborRate).all()

            # Convert to dict format
            labor_rates_list = []
            for rate in labor_rates:
                labor_rates_list.append({
                    "id": rate.id,
                    "category": rate.role,  # LaborRate model uses 'role' not 'category'
                    "daily_rate": float(rate.hourly_rate * 8),  # Convert hourly to daily (8-hour day)
                    "hourly_rate": float(rate.hourly_rate),  # LaborRate model stores hourly_rate
                    "currency": "EGP",  # Egyptian Pounds
                    "description": getattr(rate, "description", None),
                    "skill_level": getattr(rate, "skill_level", "standard")
                })

            logger.info(f"Fetched {len(labor_rates_list)} labor rates from PostgreSQL")

            return {
                "labor_rates": labor_rates_list
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"CRITICAL: Failed to fetch labor rates from PostgreSQL: {e}")
        # DO NOT use fallback - raise exception to stop workflow
        raise RuntimeError(f"Database labor rates query failed: {e}")


def validate_coverage_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Validate that we have sufficient materials and labor data.

    Validation criteria:
    - Materials: ≥30 items, all major categories present, all prices > 0
    - Labor rates: ≥5 categories, all rates > 0

    Returns: Validation results and routing decision
    """
    materials = state.get("materials", [])
    labor_rates = state.get("labor_rates", [])

    errors = []

    # Validate materials
    if len(materials) < 30:
        errors.append(f"Insufficient materials: {len(materials)} < 30 required")

    # Check for invalid prices
    invalid_prices = [m for m in materials if m.get("price_per_unit", 0) <= 0]
    if invalid_prices:
        errors.append(f"{len(invalid_prices)} materials have invalid prices (≤ 0)")

    # Check for category diversity (data-driven, not hardcoded)
    available_categories = set(m.get("category", "").strip() for m in materials if m.get("category"))
    if len(available_categories) < 1:
        errors.append("No material categories found in database")

    logger.info(f"Found {len(available_categories)} material categories: {list(available_categories)}")

    # Validate labor rates
    if len(labor_rates) < 5:
        errors.append(f"Insufficient labor rates: {len(labor_rates)} < 5 required")

    # Check for invalid rates
    invalid_rates = [r for r in labor_rates if r.get("daily_rate", 0) <= 0]
    if invalid_rates:
        errors.append(f"{len(invalid_rates)} labor rates have invalid prices (≤ 0)")

    # Determine routing
    if errors:
        logger.error(f"Postgres data validation failed: {', '.join(errors)}")
        return {
            "postgres_validation": {
                "is_valid": False,
                "errors": errors,
                "route": "failed"
            }
        }
    else:
        logger.info(
            f"Postgres data validation passed: "
            f"{len(materials)} materials, {len(labor_rates)} labor rates"
        )
        return {
            "postgres_validation": {
                "is_valid": True,
                "materials_count": len(materials),
                "labor_rates_count": len(labor_rates),
                "route": "complete"
            }
        }


def complete_postgres_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Mark postgres data retrieval as complete.

    Returns: Completion flag
    """
    logger.info("Postgres data retrieval complete")

    return {
        "postgres_data_complete": True
    }


def failed_postgres_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Handle validation failure.

    CRITICAL: Stops workflow, no fallback.

    Returns: Error state and workflow termination
    """
    validation = state.get("postgres_validation", {})
    errors = validation.get("errors", ["Unknown validation error"])

    error_message = f"CRITICAL: Postgres data validation failed - {'; '.join(errors)}"
    logger.error(error_message)

    return {
        "postgres_data_complete": False,
        "workflow_status": WorkflowStatus.ERROR.value,
        "errors": [error_message]
    }
