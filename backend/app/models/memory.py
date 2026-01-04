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
    """
    Stores agent session memory (conversation history, extracted data, tool results).
    Sessions are independent of quotations and linked via foreign key.
    """
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)  # Unique session identifier
    quotation_id = Column(String(255), ForeignKey('quotations.id', ondelete='CASCADE'), nullable=True, index=True)  # Optional link to quotation
    session_data = Column(JSON, nullable=True)  # Stores full session state
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    quotation = relationship("Quotation", back_populates="sessions")

