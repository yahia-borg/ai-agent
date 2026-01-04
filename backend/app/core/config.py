from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS - can be comma-separated string or list
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # LLM Configuration
    LLM_PROVIDER: str = "openai"
    
    # RunPod vLLM Configuration
    RUNPOD_ENDPOINT_ID: str = ""
    RUNPOD_API_KEY: str = ""
    RUNPOD_BASE_URL: str = ""
    
    # Anthropic Configuration (recommended alternative)
    ANTHROPIC_API_KEY: str = ""
    
    # Model name
    MODEL_NAME: str = ""
    
    # @property
    # def openai_base_url(self) -> str:
    #     """Construct RunPod vLLM endpoint URL"""
    #     # Use custom base URL if provided
    #     if self.RUNPOD_BASE_URL:
    #         return self.RUNPOD_BASE_URL
    #     # Otherwise construct RunPod Serverless endpoint
    #     if self.RUNPOD_ENDPOINT_ID:
    #         return f"https://ukmezus9easxmw-8000.proxy.runpod.net/v1/"
    #     return ""
    
    # Redis (for Celery)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Regional Configuration
    DEFAULT_COUNTRY: str = "EG"  # Egypt
    DEFAULT_CURRENCY: str = "EGP"  # Egyptian Pounds
    DEFAULT_LOCALE: str = "ar_EG"  # Arabic (Egypt)
    
    # Qdrant Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    
    # Embedding Model Configuration (Hugging Face)
    # Embedding Model Configuration (Hugging Face)
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_MODEL_PATH: str = ""

    # Agent Limits
    MAX_TOTAL_TURNS: int = 20
    MAX_REQUIREMENTS_ATTEMPTS: int = 8
    MAX_DATA_RETRIEVAL_ATTEMPTS: int = 3
    MAX_CALCULATION_ATTEMPTS: int = 3
    SESSION_TIMEOUT_MINUTES: int = 30

    # LangSmith Configuration
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "construction-agent"
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into list"""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return self.CORS_ORIGINS
    
    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        case_sensitive = True
        extra = "ignore"


settings = Settings()
