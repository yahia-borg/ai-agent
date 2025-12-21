"""
Admin endpoints for system management
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.qdrant_service import get_qdrant_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync-qdrant")
async def sync_qdrant(
    db: Session = Depends(get_db)
):
    """
    Sync Qdrant vector store with knowledge items from database.
    This endpoint populates the Qdrant collection with all knowledge items.
    """
    try:
        from app.core.config import settings
        
        # Check if Qdrant URL is configured
        qdrant_url = settings.QDRANT_URL
        logger.info(f"Attempting to sync Qdrant at {qdrant_url}")
        
        qdrant_service = get_qdrant_service()
        
        # Sync from database
        qdrant_service.sync_from_database(db)
        
        return {
            "status": "success",
            "message": "Qdrant collection synced successfully from database",
            "qdrant_url": qdrant_url
        }
    except ConnectionError as e:
        logger.error(f"Qdrant connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to Qdrant. Please ensure Qdrant service is running. Error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error syncing Qdrant: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync Qdrant: {str(e)}"
        )
