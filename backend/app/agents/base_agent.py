from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.models.quotation import Quotation


class BaseAgent(ABC):
    """Base class for all AI agents"""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def execute(self, quotation: Quotation, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's main task
        
        Args:
            quotation: The quotation object
            context: Additional context from previous agents
            
        Returns:
            Dictionary with agent results
        """
        pass
    
    @abstractmethod
    def get_required_context(self) -> list[str]:
        """Return list of context keys required from previous agents"""
        pass

