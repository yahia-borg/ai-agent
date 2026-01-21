"""
Database session context for dependency injection across tools.
Allows tools to access a shared database session instead of creating new ones.
"""
from contextvars import ContextVar
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal, SessionLocal

# Context variable for database session (supports both sync and async)
db_session_context: ContextVar[Optional[Union[Session, AsyncSession]]] = ContextVar(
    'db_session', 
    default=None
)


def get_db_session() -> Optional[Union[Session, AsyncSession]]:
    """
    Get database session from context.
    Returns None if no session is set in context.
    """
    return db_session_context.get()


def get_or_create_db_session() -> Session:
    """
    Get database session from context, or create a new sync session if not available.
    Use this for synchronous operations.
    """
    session = db_session_context.get()
    if session is not None and isinstance(session, Session):
        return session
    return SessionLocal()


async def get_or_create_async_db_session() -> AsyncSession:
    """
    Get database session from context, or create a new async session if not available.
    Use this for asynchronous operations.
    
    Returns:
        AsyncSession from context or a new async session
    """
    session = db_session_context.get()
    if session is not None and isinstance(session, AsyncSession):
        return session
    # Create new async session - caller is responsible for closing if not from context
    return AsyncSessionLocal()
