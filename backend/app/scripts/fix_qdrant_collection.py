"""
Fix Qdrant collection: Recreate collection with correct API format.

This script fixes the 'MaxSim is not a valid SimilarityFunction' error
by recreating the collection with the correct Distance.COSINE format.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.qdrant_service import get_qdrant_service
from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeItem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_qdrant_collection():
    """Recreate Qdrant collection and re-sync data from database"""
    
    logger.info("=" * 60)
    logger.info("Fixing Qdrant Collection")
    logger.info("=" * 60)
    
    try:
        # Get Qdrant service
        qdrant_service = get_qdrant_service()
        
        # Recreate collection with correct format
        logger.info("Recreating collection with correct API format...")
        qdrant_service.init_collection(recreate=True)
        logger.info("✓ Collection recreated successfully")
        
        # Re-sync data from database
        logger.info("\nRe-syncing data from database...")
        db = SessionLocal()
        try:
            knowledge_items = db.query(KnowledgeItem).all()
            
            if not knowledge_items:
                logger.warning("No knowledge items found in database. Collection is empty.")
                return
            
            # Convert to dict format
            items = []
            for item in knowledge_items:
                items.append({
                    "id": item.id,
                    "topic": item.topic or "",
                    "content": item.content,
                    "source_document": item.source_document or "",
                    "page_number": item.page_number or 1
                })
            
            # Add to Qdrant
            logger.info(f"Adding {len(items)} knowledge items to Qdrant...")
            qdrant_service.add_knowledge_items(items)
            logger.info(f"✓ Successfully synced {len(items)} items to Qdrant")
            
        finally:
            db.close()
        
        logger.info("\n" + "=" * 60)
        logger.info("Qdrant collection fixed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error fixing Qdrant collection: {e}")
        raise


if __name__ == "__main__":
    fix_qdrant_collection()

