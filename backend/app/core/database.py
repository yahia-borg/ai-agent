from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator
from app.core.config import settings

# Synchronous database (kept for backward compatibility)
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async database
async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("postgresql+psycopg2://", "postgresql+asyncpg://")
async_engine = create_async_engine(
    async_database_url,
    pool_size=10,
    max_overflow=20,
    echo=False
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


def get_db():
    """Dependency for getting synchronous database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session"""
    async with AsyncSessionLocal() as session:
        yield session

