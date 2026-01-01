"""
Data Retrieval Tools - Tools for querying knowledge base, materials, and labor rates.
"""
from typing import Dict, List, Any
from langchain_core.tools import tool
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.services.qdrant_service import get_qdrant_service
from sqlalchemy import or_, func
import logging

logger = logging.getLogger(__name__)


@tool
def search_knowledge_base(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Search the knowledge base (Qdrant) for construction information.

    Use this to find:
    - Finishing standards and regulations
    - Building codes for Egypt
    - Construction best practices
    - Material recommendations
    - Style-specific requirements

    Args:
        query: Search query (e.g., "modern finishing requirements", "building regulations Egypt residential")
        top_k: Number of results to return (default 5)

    Returns:
        Dict with 'results' (list of relevant knowledge items) and 'count'
    """
    try:
        qdrant_service = get_qdrant_service()
        results = qdrant_service.search_knowledge(query, top_k=top_k)

        logger.info(f"Knowledge search for '{query}': found {len(results)} results")

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query
        }
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "count": 0
        }


@tool
def search_materials_by_name(material_name: str, limit: int = 20) -> Dict[str, Any]:
    """
    Search for materials by name using fuzzy matching.

    This tool searches material names for matches. Use keywords like:
    - "cement", "sand", "paint", "tiles", "ceramic"
    - "doors", "windows", "pipes", "wires"
    - Arabic terms are also supported

    The search uses ILIKE for partial matching and returns the best matches.

    Args:
        material_name: Name or keyword to search for (e.g., "cement", "paint white", "tiles")
        limit: Maximum number of results (default 20)

    Returns:
        Dict with 'materials' list containing: id, name, category, unit, price_per_unit, currency
    """
    db = SessionLocal()
    try:
        # Split search term into keywords for better matching
        keywords = material_name.lower().strip().split()

        # Build query with OR conditions for each keyword
        conditions = []
        for keyword in keywords:
            conditions.append(Material.name.ilike(f"%{keyword}%"))

        # Execute query with OR condition
        query = db.query(Material)
        if conditions:
            query = query.filter(or_(*conditions))

        materials = query.limit(limit).all()

        result = []
        for mat in materials:
            result.append({
                "id": mat.id,
                "name": mat.name,
                "category": mat.category,
                "unit": mat.unit,
                "price_per_unit": mat.price_per_unit,
                "currency": mat.currency
            })

        logger.info(f"Material search for '{material_name}': found {len(result)} results")

        return {
            "success": True,
            "materials": result,
            "count": len(result),
            "search_term": material_name
        }
    except Exception as e:
        logger.error(f"Error searching materials: {e}")
        return {
            "success": False,
            "error": str(e),
            "materials": [],
            "count": 0
        }
    finally:
        db.close()


@tool
def get_all_materials(limit: int = 500) -> Dict[str, Any]:
    """
    Get all available materials from the database.

    Use this to see what materials are available in the system.
    Returns up to 500 materials by default.

    Args:
        limit: Maximum number of materials to return (default 500)

    Returns:
        Dict with 'materials' list containing: id, name, category, unit, price_per_unit, currency
    """
    db = SessionLocal()
    try:
        materials = db.query(Material).limit(limit).all()

        result = []
        for mat in materials:
            result.append({
                "id": mat.id,
                "name": mat.name,
                "category": mat.category,
                "unit": mat.unit,
                "price_per_unit": mat.price_per_unit,
                "currency": mat.currency
            })

        logger.info(f"Retrieved {len(result)} materials")

        return {
            "success": True,
            "materials": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Error getting materials: {e}")
        return {
            "success": False,
            "error": str(e),
            "materials": [],
            "count": 0
        }
    finally:
        db.close()


@tool
def search_labor_rates_by_role(role_keyword: str) -> Dict[str, Any]:
    """
    Search for labor rates by role/job title.

    Common roles: Mason, Electrician, Plumber, Carpenter, Painter, Semi-Skilled, etc.

    Args:
        role_keyword: Role keyword to search for (e.g., "mason", "electrician", "painter")

    Returns:
        Dict with 'labor_rates' list containing: id, role, hourly_rate, currency
    """
    db = SessionLocal()
    try:
        labor_rates = db.query(LaborRate).filter(
            LaborRate.role.ilike(f"%{role_keyword}%")
        ).all()

        result = []
        for labor in labor_rates:
            result.append({
                "id": labor.id,
                "role": labor.role,
                "hourly_rate": labor.hourly_rate,
                "currency": labor.currency
            })

        logger.info(f"Labor rate search for '{role_keyword}': found {len(result)} results")

        return {
            "success": True,
            "labor_rates": result,
            "count": len(result),
            "search_term": role_keyword
        }
    except Exception as e:
        logger.error(f"Error searching labor rates: {e}")
        return {
            "success": False,
            "error": str(e),
            "labor_rates": [],
            "count": 0
        }
    finally:
        db.close()


@tool
def get_all_labor_rates() -> Dict[str, Any]:
    """
    Get all available labor rates from the database.

    Returns:
        Dict with 'labor_rates' list containing: id, role, hourly_rate, currency
    """
    db = SessionLocal()
    try:
        labor_rates = db.query(LaborRate).all()

        result = []
        for labor in labor_rates:
            result.append({
                "id": labor.id,
                "role": labor.role,
                "hourly_rate": labor.hourly_rate,
                "currency": labor.currency
            })

        logger.info(f"Retrieved {len(result)} labor rates")

        return {
            "success": True,
            "labor_rates": result,
            "count": len(result)
        }
    except Exception as e:
        logger.error(f"Error getting labor rates: {e}")
        return {
            "success": False,
            "error": str(e),
            "labor_rates": [],
            "count": 0
        }
    finally:
        db.close()
