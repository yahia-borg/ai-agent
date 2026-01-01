"""
Qdrant Vector Store Service
Uses Hugging Face sentence-transformers for embeddings
"""
import os
import threading
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread lock for singleton
_qdrant_lock = threading.Lock()


class QdrantService:
    """Service for managing Qdrant vector store"""
    
    def __init__(self):
        self.qdrant_url = getattr(settings, 'QDRANT_URL', 'http://localhost:6333')
        self.qdrant_api_key = getattr(settings, 'QDRANT_API_KEY', None)
        # Model name for HuggingFace fallback
        # Using local embedding model path; fallback removed
        # Optional local path to a pre-downloaded model
        embedding_model_path = getattr(settings, 'EMBEDDING_MODEL_PATH', '')

        # Initialize Qdrant client
        if self.qdrant_api_key:
            self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        else:
            self.client = QdrantClient(url=self.qdrant_url)

        # Initialize embedding model
        # Priority: Local path > HuggingFace model name
        # Device selection (default: cpu to avoid CUDA compatibility issues)
        device = getattr(settings, 'EMBEDDING_DEVICE', 'cpu')

        # Resolve relative paths relative to backend directory (where .env is located)
        if embedding_model_path and not os.path.isabs(embedding_model_path):
            # Get the backend directory (where config.py and .env are located)
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            embedding_model_path = os.path.abspath(os.path.join(backend_dir, embedding_model_path))
            logger.info(f"Resolved relative path to: {embedding_model_path}")

        # Auto-detect model path if not explicitly set
        if not embedding_model_path:
            # Try Docker path first
            docker_path = "/app/ai_models/embedding_model"
            # Try local path (relative to project root)
            local_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "ai_models", "embedding_model"
            )

            if os.path.exists(docker_path):
                embedding_model_path = docker_path
                logger.info(f"Auto-detected Docker model path: {embedding_model_path}")
            elif os.path.exists(local_path):
                embedding_model_path = local_path
                logger.info(f"Auto-detected local model path: {embedding_model_path}")

        if embedding_model_path and os.path.exists(embedding_model_path):
            # Use local model from mounted volume or local filesystem
            logger.info(f"Loading embedding model from local path: {embedding_model_path} (device: {device})")
            try:
                # Force local-only mode to prevent ANY HuggingFace API calls
                self.embedding_model = SentenceTransformer(
                    embedding_model_path,
                    device=device,
                    local_files_only=True
                )
                logger.info("✓ Model loaded successfully from local files (HuggingFace access disabled)")
            except Exception as e:
                logger.error(f"Failed to load local model: {e}")
                raise RuntimeError(
                    f"Local model at '{embedding_model_path}' failed to load. "
                    "Ensure all model files are present. HuggingFace fallback is disabled."
                )
        else:
            # This should not happen in production - require local model
            error_msg = (
                f"Embedding model not found at '{embedding_model_path}'. "
                "Please download the model first. HuggingFace auto-download is disabled for offline operation."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        logger.info(f"Embedding dimension: {self.embedding_dim}")
        
        self.collection_name = "knowledge_items"
    
    def init_collection(self, collection_name: str = None, recreate: bool = False):
        """Initialize or recreate Qdrant collection"""
        if collection_name:
            self.collection_name = collection_name
        
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_exists = any(c.name == self.collection_name for c in collections.collections)
            
            if collection_exists and recreate:
                logger.info(f"Deleting existing collection: {self.collection_name}")
                self.client.delete_collection(self.collection_name)
                collection_exists = False
            
            if not collection_exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collection {self.collection_name} created successfully")
            else:
                logger.info(f"Collection {self.collection_name} already exists")
                
        except Exception as e:
            logger.error(f"Error initializing collection: {e}")
            raise
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings for a list of texts"""
        try:
            embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            raise
    
    def add_knowledge_items(self, knowledge_items: List[Dict[str, Any]]):
        """Add knowledge items to Qdrant vector store"""
        if not knowledge_items:
            logger.warning("No knowledge items to add")
            return
        
        logger.info(f"Adding {len(knowledge_items)} knowledge items to Qdrant")
        
        # Prepare texts for embedding
        texts = []
        for item in knowledge_items:
            # Combine topic and content for better search
            text = f"{item.get('topic', '')} {item.get('content', '')}"
            texts.append(text)
        
        # Create embeddings
        embeddings = self.create_embeddings(texts)
        
        # Prepare points
        points = []
        for i, item in enumerate(knowledge_items):
            point = PointStruct(
                id=i,  # Use index as ID, or use item ID if available
                vector=embeddings[i],
                payload={
                    "topic": item.get('topic', ''),
                    "content": item.get('content', ''),
                    "source_document": item.get('source_document', ''),
                    "page_number": item.get('page_number', 1),
                    "content_id": item.get('id', None)  # Reference to database ID
                }
            )
            points.append(point)
        
        # Upsert points
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Successfully added {len(points)} knowledge items to Qdrant")
        except Exception as e:
            logger.error(f"Error adding knowledge items: {e}")
            raise
    
    def search_knowledge(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search knowledge items by query"""
        try:
            # Create query embedding
            query_embedding = self.embedding_model.encode([query])[0].tolist()

            # Search using query_points (updated Qdrant API)
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=top_k
            ).points

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "score": result.score,
                    "topic": result.payload.get("topic", ""),
                    "content": result.payload.get("content", ""),
                    "source_document": result.payload.get("source_document", ""),
                    "page_number": result.payload.get("page_number", 1),
                    "content_id": result.payload.get("content_id")
                })

            return formatted_results

        except Exception as e:
            error_str = str(e)
            # Check if error is due to old collection format (MaxSim similarity function)
            if "MaxSim" in error_str or "SimilarityFunction" in error_str or "not a valid" in error_str:
                logger.warning(
                    f"Collection '{self.collection_name}' was created with old API format. "
                    f"Recreating collection with correct format..."
                )
                try:
                    # Recreate collection with correct format
                    self.init_collection(recreate=True)
                    logger.info(f"Collection '{self.collection_name}' recreated successfully")
                    # Retry search (will return empty since collection is now empty)
                    logger.warning("Collection recreated but is now empty. Please re-sync data.")
                    return []
                except Exception as recreate_error:
                    logger.error(f"Failed to recreate collection: {recreate_error}")
                    raise
            
            logger.error(f"Error searching knowledge: {e}")
            raise
    
    def sync_from_database(self, db_session):
        """Sync all knowledge items from database to Qdrant"""
        from app.models.knowledge import KnowledgeItem
        
        logger.info("Syncing knowledge items from database to Qdrant")
        
        # Fetch all knowledge items
        knowledge_items = db_session.query(KnowledgeItem).all()
        
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
        
        # Clear and recreate collection
        self.init_collection(recreate=True)
        
        # Add all items
        self.add_knowledge_items(items)
        
        logger.info(f"Synced {len(items)} knowledge items to Qdrant")


# Global instance
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Get or create Qdrant service instance (thread-safe singleton)"""
    global _qdrant_service

    # Double-check locking pattern for thread safety
    if _qdrant_service is None:
        with _qdrant_lock:
            if _qdrant_service is None:
                logger.info("Creating new QdrantService instance")
                _qdrant_service = QdrantService()

    return _qdrant_service


if __name__ == "__main__":
    # Test
    service = QdrantService()
    service.init_collection(recreate=True)
    
    # Test search
    test_items = [
        {
            "id": 1,
            "topic": "Building Materials",
            "content": "Cement is a key building material used in construction.",
            "source_document": "test.md",
            "page_number": 1
        }
    ]
    
    service.add_knowledge_items(test_items)
    
    results = service.search_knowledge("construction materials", top_k=3)
    print(f"Search results: {results}")

