"""
Qdrant Vector Store Service
Uses Hugging Face sentence-transformers for embeddings
"""
import os
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QdrantService:
    """Service for managing Qdrant vector store"""
    
    def __init__(self):
        self.qdrant_url = getattr(settings, 'QDRANT_URL', 'http://localhost:6333')
        self.qdrant_api_key = getattr(settings, 'QDRANT_API_KEY', None)
        self.embedding_model_name = getattr(settings, 'EMBEDDING_MODEL',
                                           'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        self.embedding_model_path = getattr(settings, 'EMBEDDING_MODEL_PATH', '')

        # Initialize Qdrant client
        if self.qdrant_api_key:
            self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        else:
            self.client = QdrantClient(url=self.qdrant_url)

        # Initialize embedding model - prioritize local path if available
        if self.embedding_model_path and os.path.exists(self.embedding_model_path):
            logger.info(f"Loading embedding model from local path: {self.embedding_model_path}")
            self.embedding_model = SentenceTransformer(self.embedding_model_path)
        else:
            logger.info(f"Loading embedding model from HuggingFace: {self.embedding_model_name}")
            if self.embedding_model_path:
                logger.warning(f"Local model path not found: {self.embedding_model_path}")
            self.embedding_model = SentenceTransformer(self.embedding_model_name)

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
            
            # Search
            if hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    limit=top_k
                )
            elif hasattr(self.client, "query_points"):
                # Fallback for newer clients that might favor query_points or if search is behaving oddly
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    limit=top_k
                )
                results = response.points
            else:
                # Last resort or error
                raise AttributeError("QdrantClient has neither 'search' nor 'query_points' methods.")
            
            # Format results
            formatted_results = []
            for result in results:
                payload = result.payload or {}
                formatted_results.append({
                    "score": result.score,
                    "topic": payload.get("topic", ""),
                    "content": payload.get("content", ""),
                    "source_document": payload.get("source_document", ""),
                    "page_number": payload.get("page_number", 1),
                    "content_id": payload.get("content_id")
                })
            
            return formatted_results
            
        except Exception as e:
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
    """Get or create Qdrant service instance"""
    global _qdrant_service
    if _qdrant_service is None:
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

