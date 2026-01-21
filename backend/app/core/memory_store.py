"""
Memory store for conversation and agent memory
Supports both PostgreSQL (primary) and Redis (optional cache)
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import and_
from app.models.memory import ConversationMemory, AgentSession
import json
import logging

logger = logging.getLogger(__name__)


class MemoryStore:
    """Memory store implementation using PostgreSQL"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # Conversation Memory Methods
    
    def get_conversation_memory(
        self, 
        user_id: Optional[str] = None, 
        quotation_id: Optional[str] = None,
        key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get conversation memory by user_id, quotation_id, or key"""
        query = self.db.query(ConversationMemory)
        
        conditions = []
        if user_id:
            conditions.append(ConversationMemory.user_id == user_id)
        if quotation_id:
            conditions.append(ConversationMemory.quotation_id == quotation_id)
        if key:
            conditions.append(ConversationMemory.key == key)
        
        if not conditions:
            return None
        
        memory = query.filter(and_(*conditions)).first()
        return memory.value if memory else None
    
    def set_conversation_memory(
        self,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None,
        quotation_id: Optional[str] = None
    ) -> None:
        """Set conversation memory"""
        # Check if exists
        query = self.db.query(ConversationMemory)
        conditions = [ConversationMemory.key == key]
        if user_id:
            conditions.append(ConversationMemory.user_id == user_id)
        if quotation_id:
            conditions.append(ConversationMemory.quotation_id == quotation_id)

        existing = query.filter(and_(*conditions)).first()

        if existing:
            existing.value = value
            # Explicitly mark JSON field as modified for SQLAlchemy change detection
            flag_modified(existing, "value")
        else:
            memory = ConversationMemory(
                key=key,
                value=value,
                user_id=user_id,
                quotation_id=quotation_id
            )
            self.db.add(memory)

        self.db.commit()
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences"""
        return self.get_conversation_memory(user_id=user_id, key="preferences") or {}
    
    def set_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> None:
        """Set user preferences"""
        self.set_conversation_memory(
            key="preferences",
            value=preferences,
            user_id=user_id
        )
    
    def get_past_quotations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get past quotations for a user"""
        return self.get_conversation_memory(user_id=user_id, key="past_quotations") or []
    
    def add_past_quotation(self, user_id: str, quotation: Dict[str, Any]) -> None:
        """Add a quotation to user's history"""
        past_quotations = self.get_past_quotations(user_id)
        past_quotations.append(quotation)
        self.set_conversation_memory(
            key="past_quotations",
            value=past_quotations,
            user_id=user_id
        )
    
    # Agent Session Memory Methods

    def get_agent_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get agent session data by session_id"""
        session = self.db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()
        return session.session_data if session else None

    def set_agent_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Set agent session data by session_id"""
        session = self.db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if session:
            session.session_data = session_data
            # Explicitly mark JSON field as modified for SQLAlchemy change detection
            flag_modified(session, "session_data")
        else:
            session = AgentSession(
                session_id=session_id,
                quotation_id=None,  # Will be set separately via SessionService
                session_data=session_data
            )
            self.db.add(session)

        self.db.commit()

    def update_agent_session(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Update agent session data with partial updates"""
        session_data = self.get_agent_session(session_id) or {}
        # Create new dict object to ensure SQLAlchemy detects change (defense-in-depth)
        new_session_data = {**session_data, **updates}
        self.set_agent_session(session_id, new_session_data)

    def clear_agent_session(self, session_id: str) -> None:
        """Clear agent session data"""
        session = self.db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()
        if session:
            self.db.delete(session)
            self.db.commit()

