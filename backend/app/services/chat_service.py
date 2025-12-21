"""
Chat service for orchestrating conversational agent interactions
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from app.agents.conversational_agent import ConversationalAgent
from app.agents.memory_manager import MemoryManager


class ChatService:
    """Service for handling chat interactions with the agent"""
    
    def __init__(self, db: Session):
        self.db = db
        self.memory_manager = MemoryManager(db)
        self.agent = ConversationalAgent(self.memory_manager)
    
    async def process_message(
        self,
        message: str,
        history: List[Dict[str, str]],
        quotation_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Process a chat message and return response
        
        Args:
            message: User message text
            history: Conversation history
            quotation_id: Optional quotation ID for session continuity
            files: Optional list of uploaded files
            
        Returns:
            Dictionary with response, quotation_id, and updated history
        """
        return await self.agent.process_message(
            message=message,
            history=history,
            quotation_id=quotation_id,
            files=files or [],
            db=self.db
        )
    
    async def process_message_stream(
        self,
        message: str,
        history: List[Dict[str, str]],
        quotation_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a chat message with streaming response
        
        Args:
            message: User message text
            history: Conversation history
            quotation_id: Optional quotation ID for session continuity
            files: Optional list of uploaded files
            
        Yields:
            Dictionary chunks with type and content
        """
        async for chunk in self.agent.process_message_stream(
            message=message,
            history=history,
            quotation_id=quotation_id,
            files=files or [],
            db=self.db
        ):
            yield chunk

