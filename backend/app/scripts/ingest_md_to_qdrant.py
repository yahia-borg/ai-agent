"""
Direct Markdown to Qdrant Ingestion Script

Parses specific markdown knowledge files and directly ingests them into Qdrant
vector store, bypassing PostgreSQL database.

Files processed:
- construction_finishing_knowledge_base_egypt.md
- egy-code.md
- egypt-construction-costs-2025.md
"""
import os
import sys
import argparse
import hashlib
from typing import List, Dict, Any
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.scripts.md_parser_enhanced import parse_knowledge_from_md
from app.services.qdrant_service import get_qdrant_service
from qdrant_client.models import PointStruct
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_file_hash(topic: str, source_document: str) -> int:
    """
    Generate deterministic hash-based ID from topic and source document.
    
    Args:
        topic: Knowledge item topic
        source_document: Source document filename
        
    Returns:
        Integer ID (positive, suitable for Qdrant)
    """
    combined = f"{topic}|{source_document}"
    hash_obj = hashlib.md5(combined.encode('utf-8'))
    # Convert to positive integer (use first 8 bytes to avoid overflow)
    return int(hash_obj.hexdigest()[:8], 16)


def validate_knowledge_item(item: Dict[str, Any]) -> bool:
    """
    Validate knowledge item before ingestion.
    
    Args:
        item: Knowledge item dict with topic, content, source_document, page_number
        
    Returns:
        True if valid, False otherwise
    """
    if not item.get("topic") or len(item.get("topic", "").strip()) < 3:
        return False
    
    content = item.get("content", "").strip()
    if not content or len(content) < 50:
        return False
    
    if len(content) > 10000:  # Too long, might cause issues
        logger.warning(f"Item '{item.get('topic')}' has very long content ({len(content)} chars), truncating...")
        item["content"] = content[:10000]
    
    return True


def process_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a markdown file and extract knowledge items.
    
    Args:
        file_path: Path to markdown file
        
    Returns:
        List of knowledge item dicts
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return []
    
    logger.info(f"Parsing {os.path.basename(file_path)}...")
    
    try:
        knowledge_items = parse_knowledge_from_md(file_path)
        
        # Validate and filter items
        valid_items = []
        for item in knowledge_items:
            if validate_knowledge_item(item):
                valid_items.append(item)
            else:
                logger.debug(f"Skipping invalid item: {item.get('topic', 'Unknown')}")
        
        logger.info(f"  - Extracted {len(valid_items)} valid knowledge items from {len(knowledge_items)} total")
        return valid_items
        
    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}", exc_info=True)
        return []


def ingest_to_qdrant(
    knowledge_items: List[Dict[str, Any]],
    qdrant_service,
    batch_size: int = 100,
    recreate: bool = False
) -> int:
    """
    Ingest knowledge items to Qdrant with batching and duplicate handling.
    
    Args:
        knowledge_items: List of knowledge item dicts
        qdrant_service: QdrantService instance
        batch_size: Batch size for embedding creation
        recreate: Whether to recreate collection before ingestion
        
    Returns:
        Number of items successfully added
    """
    if not knowledge_items:
        logger.warning("No knowledge items to ingest")
        return 0
    
    # Initialize/recreate collection if needed
    if recreate:
        logger.info("Recreating Qdrant collection...")
        qdrant_service.init_collection(recreate=True)
    else:
        # Just ensure collection exists
        qdrant_service.init_collection(recreate=False)
    
    # Generate IDs for items (hash-based to prevent duplicates)
    items_with_ids = []
    seen_ids = set()
    duplicates = 0
    
    for item in knowledge_items:
        item_id = get_file_hash(item.get("topic", ""), item.get("source_document", ""))
        
        # Check for hash collisions (very rare, but handle it)
        if item_id in seen_ids:
            # Add source_document hash to make unique
            item_id = get_file_hash(
                f"{item.get('topic', '')}{item.get('content', '')[:50]}",
                item.get("source_document", "")
            )
            if item_id in seen_ids:
                duplicates += 1
                logger.warning(f"Duplicate detected for: {item.get('topic', 'Unknown')}")
                continue
        
        seen_ids.add(item_id)
        item["id"] = item_id
        items_with_ids.append(item)
    
    if duplicates > 0:
        logger.info(f"Skipped {duplicates} duplicate items")
    
    total_items = len(items_with_ids)
    logger.info(f"Creating embeddings for {total_items} items (batch size: {batch_size})...")
    
    # Process in batches for embedding creation
    all_embeddings = []
    processed = 0
    
    for i in range(0, total_items, batch_size):
        batch = items_with_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_items + batch_size - 1) // batch_size
        
        logger.info(f"  - Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")
        
        try:
            # Prepare texts for embedding
            texts = []
            for item in batch:
                # Combine topic and content for better search
                text = f"{item.get('topic', '')} {item.get('content', '')}"
                texts.append(text)
            
            # Create embeddings
            embeddings = qdrant_service.create_embeddings(texts)
            all_embeddings.extend(embeddings)
            processed += len(batch)
            
        except Exception as e:
            logger.error(f"Error creating embeddings for batch {batch_num}: {e}")
            # Continue with next batch
            continue
    
    logger.info(f"Created embeddings for {processed}/{total_items} items")
    
    # Prepare points for Qdrant
    points = []
    for i, item in enumerate(items_with_ids):
        if i < len(all_embeddings):
            point = PointStruct(
                id=item["id"],
                vector=all_embeddings[i],
                payload={
                    "topic": item.get("topic", ""),
                    "content": item.get("content", ""),
                    "source_document": item.get("source_document", ""),
                    "page_number": item.get("page_number", 1),
                    "content_id": None  # No database ID for direct ingestion
                }
            )
            points.append(point)
    
    # Add to Qdrant
    if points:
        logger.info(f"Adding {len(points)} items to Qdrant...")
        try:
            qdrant_service.client.upsert(
                collection_name=qdrant_service.collection_name,
                points=points
            )
            logger.info(f"✓ Successfully added {len(points)} knowledge items to Qdrant")
            return len(points)
        except Exception as e:
            logger.error(f"Error adding items to Qdrant: {e}", exc_info=True)
            raise
    
    return 0


def main():
    """Main ingestion function"""
    parser = argparse.ArgumentParser(
        description="Ingest markdown knowledge files directly to Qdrant"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate Qdrant collection before ingestion (deletes existing data)"
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Custom file paths to process (default: 3 specific files)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for embedding creation (default: 100)"
    )
    
    args = parser.parse_args()
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = os.path.join(project_root, "data", "clean")
    
    # Default files to process
    default_files = [
        "construction_finishing_knowledge_base_egypt.md",
        "egy-code.md",
        "egypt-construction-costs-2025.md"
    ]
    
    # Determine files to process
    if args.files:
        # Use custom file paths
        file_paths = [os.path.abspath(f) for f in args.files]
    else:
        # Use default files from data/clean directory
        file_paths = [os.path.join(data_dir, f) for f in default_files]
    
    logger.info("=" * 60)
    logger.info("Direct MD to Qdrant Ingestion")
    logger.info("=" * 60)
    logger.info(f"Files to process: {len(file_paths)}")
    for fp in file_paths:
        logger.info(f"  - {os.path.basename(fp)}")
    logger.info("")
    
    # Parse all files
    all_knowledge_items = []
    file_stats = {}
    
    for file_path in file_paths:
        items = process_file(file_path)
        all_knowledge_items.extend(items)
        file_stats[os.path.basename(file_path)] = len(items)
    
    if not all_knowledge_items:
        logger.error("No knowledge items extracted from any file. Exiting.")
        return
    
    logger.info("")
    logger.info(f"Total knowledge items extracted: {len(all_knowledge_items)}")
    for filename, count in file_stats.items():
        logger.info(f"  - {filename}: {count} items")
    
    # Initialize Qdrant service
    logger.info("")
    logger.info("Initializing Qdrant service...")
    try:
        qdrant_service = get_qdrant_service()
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant service: {e}", exc_info=True)
        return
    
    # Ingest to Qdrant
    logger.info("")
    try:
        added_count = ingest_to_qdrant(
            all_knowledge_items,
            qdrant_service,
            batch_size=args.batch_size,
            recreate=args.recreate
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("Ingestion Complete!")
        logger.info("=" * 60)
        logger.info(f"Summary:")
        logger.info(f"  - Total items processed: {len(all_knowledge_items)}")
        logger.info(f"  - Items added to Qdrant: {added_count}")
        logger.info(f"  - Source documents: {len(file_stats)}")
        logger.info(f"  - Collection: {qdrant_service.collection_name}")
        logger.info("")
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

