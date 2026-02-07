#!/usr/bin/env python3
"""
Seed Qdrant Cloud with knowledge base data.

Usage:
    cd backend
    source venv/bin/activate
    python -m scripts.seed_qdrant_cloud
"""

import os
import sys
import re
import logging
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
QDRANT_URL = os.getenv('QDRANT_URL')
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
COLLECTION_NAME = "knowledge_items"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Knowledge files to ingest
KNOWLEDGE_FILES = [
    "construction_finishing_knowledge_base_egypt.md",
    "egy-code.md",
    "standards.md",
    "egypt-construction-costs-2025.md",
]


def parse_markdown_to_chunks(file_path: str, chunk_size: int = 1000) -> List[Dict[str, Any]]:
    """Parse markdown file into chunks for embedding."""
    chunks = []

    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return chunks

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(file_path)

    # Split by headers (## or ###)
    sections = re.split(r'\n(?=#{2,3}\s)', content)

    for i, section in enumerate(sections):
        section = section.strip()
        if not section or len(section) < 50:
            continue

        # Extract topic from header
        topic_match = re.match(r'^#{2,3}\s*(.+?)(?:\n|$)', section)
        topic = topic_match.group(1).strip() if topic_match else f"Section {i+1}"

        # Clean content
        content_text = re.sub(r'^#{2,3}\s*.+?\n', '', section).strip()

        # Skip if too short
        if len(content_text) < 50:
            continue

        # Split large sections into smaller chunks
        if len(content_text) > chunk_size:
            paragraphs = content_text.split('\n\n')
            current_chunk = ""
            chunk_num = 1

            for para in paragraphs:
                if len(current_chunk) + len(para) < chunk_size:
                    current_chunk += para + "\n\n"
                else:
                    if current_chunk.strip():
                        chunks.append({
                            "topic": f"{topic} (Part {chunk_num})",
                            "content": current_chunk.strip(),
                            "source_document": filename,
                            "page_number": i + 1
                        })
                        chunk_num += 1
                    current_chunk = para + "\n\n"

            if current_chunk.strip():
                chunks.append({
                    "topic": f"{topic} (Part {chunk_num})" if chunk_num > 1 else topic,
                    "content": current_chunk.strip(),
                    "source_document": filename,
                    "page_number": i + 1
                })
        else:
            chunks.append({
                "topic": topic,
                "content": content_text,
                "source_document": filename,
                "page_number": i + 1
            })

    return chunks


def main():
    logger.info("=" * 60)
    logger.info("SEEDING QDRANT CLOUD")
    logger.info("=" * 60)

    # Initialize Qdrant client
    logger.info(f"Connecting to Qdrant Cloud: {QDRANT_URL}")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Initialize embedding model
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    embedding_dim = model.get_sentence_embedding_dimension()
    logger.info(f"Embedding dimension: {embedding_dim}")

    # Create or recreate collection
    logger.info(f"Creating collection: {COLLECTION_NAME}")
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info(f"Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE
        )
    )
    logger.info(f"Collection {COLLECTION_NAME} created")

    # Parse knowledge files
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/clean'))
    logger.info(f"Data directory: {data_dir}")

    all_chunks = []
    for filename in KNOWLEDGE_FILES:
        file_path = os.path.join(data_dir, filename)
        logger.info(f"Processing: {filename}")
        chunks = parse_markdown_to_chunks(file_path)
        logger.info(f"  - Extracted {len(chunks)} chunks")
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.error("No knowledge chunks found!")
        return

    logger.info(f"\nTotal chunks to embed: {len(all_chunks)}")

    # Create embeddings
    logger.info("Creating embeddings...")
    texts = [f"{chunk['topic']} {chunk['content']}" for chunk in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=True)

    # Create points
    points = []
    for i, (chunk, embedding) in enumerate(zip(all_chunks, embeddings)):
        point = PointStruct(
            id=i,
            vector=embedding.tolist(),
            payload={
                "topic": chunk["topic"],
                "content": chunk["content"],
                "source_document": chunk["source_document"],
                "page_number": chunk["page_number"]
            }
        )
        points.append(point)

    # Upsert in batches
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        logger.info(f"Uploaded batch {i//batch_size + 1}/{(len(points) + batch_size - 1)//batch_size}")

    # Verify
    collection_info = client.get_collection(COLLECTION_NAME)
    logger.info(f"\n{'=' * 60}")
    logger.info("SEEDING COMPLETE")
    logger.info(f"{'=' * 60}")
    logger.info(f"Collection: {COLLECTION_NAME}")
    logger.info(f"Total vectors: {collection_info.points_count}")

    # Test search
    logger.info("\n--- Test Search: 'finishing stages' ---")
    query_embedding = model.encode(["finishing stages construction egypt"])[0].tolist()
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        limit=3
    )
    for r in results:
        logger.info(f"  Score: {r.score:.3f} | Topic: {r.payload.get('topic', '')[:50]}")


if __name__ == "__main__":
    main()
