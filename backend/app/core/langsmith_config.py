"""
LangSmith configuration for tracing and debugging.

This module sets up LangSmith integration for LangGraph execution tracing
and debugging capabilities.
"""
from typing import Optional, List
from langsmith import Client as LangSmithClient
from langchain_core.tracers import LangChainTracer
from app.core.config import settings
import logging
import os

logger = logging.getLogger(__name__)

# Global LangSmith client instance
_langsmith_client: Optional[LangSmithClient] = None


def get_langsmith_client() -> Optional[LangSmithClient]:
    """Get or create LangSmith client instance"""
    global _langsmith_client
    
    if not settings.LANGSMITH_API_KEY:
        logger.debug("LangSmith API key not configured, tracing disabled")
        return None
    
    if _langsmith_client is None:
        try:
            _langsmith_client = LangSmithClient(
                api_key=settings.LANGSMITH_API_KEY,
                api_url=settings.LANGSMITH_ENDPOINT,
            )
            logger.info(f"LangSmith client initialized for project: {settings.LANGSMITH_PROJECT}")
        except Exception as e:
            logger.error(f"Failed to initialize LangSmith client: {e}")
            return None
    
    return _langsmith_client


def get_langsmith_callbacks(tags: Optional[List[str]] = None) -> List:
    """
    Get LangSmith callbacks for LangGraph tracing.
    
    Args:
        tags: Optional list of tags to add to traces
        
    Returns:
        List of callback handlers (empty if LangSmith not configured)
    """
    if not settings.LANGSMITH_TRACING:
        return []
    
    if not settings.LANGSMITH_API_KEY:
        return []
    
    try:
        # Set environment variables for LangSmith (alternative approach)
        # This is automatically picked up by LangChain/LangGraph
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
        
        # Use LangChainTracer from langchain_core.tracers
        # This works with LangGraph
        tracer = LangChainTracer(
            project_name=settings.LANGSMITH_PROJECT,
            tags=tags or [],
        )
        logger.debug("LangSmith tracer created for LangGraph")
        return [tracer]
    except Exception as e:
        logger.error(f"Failed to create LangSmith tracer: {e}")
        logger.debug(f"Error details: {e}", exc_info=True)
        # If tracer creation fails, continue without tracing
        return []


def get_debug_callbacks() -> List:
    """
    Get debugging callbacks for step-by-step debugging.
    
    Returns:
        List of debugging callback handlers
    """
    # For now, we use the same tracing callbacks
    # LangSmith UI provides debugging capabilities
    # In the future, we can add additional debugging tools here
    return get_langsmith_callbacks(tags=["debug"])
