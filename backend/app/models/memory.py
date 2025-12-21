from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class ConversationMemory(Base):
    """Stores long-term conversation memory (user preferences, past quotations)"""
    __tablename__ = "conversation_memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), index=True, nullable=True)  # Optional for anonymous users
    quotation_id = Column(String(255), index=True, nullable=True)  # Link to quotation if exists
    key = Column(String(255), index=True, nullable=False)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AgentSession(Base):
    """Stores agent session memory (conversation history, extracted data, tool results)"""
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(String(255), unique=True, index=True, nullable=False)
    session_data = Column(JSON, nullable=False)  # Stores full session state
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

