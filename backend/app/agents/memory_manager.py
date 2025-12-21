"""
Memory Manager for conversational agent
Handles both conversation memory (long-term) and agent session memory (short-term)
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.core.memory_store import MemoryStore
import logging

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages memory for conversational agent"""
    
    def __init__(self, db: Session):
        self.db = db
        self.memory_store = MemoryStore(db)
    
    def get_user_context(self, user_id: Optional[str] = None, quotation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user context including preferences and past quotations
        
        Args:
            user_id: Optional user ID
            quotation_id: Optional quotation ID for session context
            
        Returns:
            Dictionary with user context
        """
        context = {
            "preferences": {},
            "past_quotations": [],
            "session_data": {}
        }
        
        if user_id:
            context["preferences"] = self.memory_store.get_user_preferences(user_id)
            context["past_quotations"] = self.memory_store.get_past_quotations(user_id)
        
        if quotation_id:
            session_data = self.memory_store.get_agent_session(quotation_id)
            if session_data:
                context["session_data"] = session_data
        
        return context
    
    def save_user_preference(self, user_id: str, key: str, value: Any) -> None:
        """Save a user preference"""
        preferences = self.memory_store.get_user_preferences(user_id)
        preferences[key] = value
        self.memory_store.set_user_preferences(user_id, preferences)
    
    def get_conversation_history(self, quotation_id: str) -> List[Dict[str, str]]:
        """Get conversation history for a quotation session"""
        session_data = self.memory_store.get_agent_session(quotation_id)
        if session_data:
            return session_data.get("conversation_history", [])
        return []
    
    def save_conversation_history(self, quotation_id: str, history: List[Dict[str, str]]) -> None:
        """Save conversation history"""
        self.memory_store.update_agent_session(quotation_id, {
            "conversation_history": history
        })
    
    def get_extracted_data(self, quotation_id: str) -> Dict[str, Any]:
        """Get extracted data from agent session"""
        session_data = self.memory_store.get_agent_session(quotation_id)
        if session_data:
            return session_data.get("extracted_data", {})
        return {}
    
    def save_extracted_data(self, quotation_id: str, extracted_data: Dict[str, Any]) -> None:
        """Save extracted data"""
        self.memory_store.update_agent_session(quotation_id, {
            "extracted_data": extracted_data
        })
    
    def get_tool_results(self, quotation_id: str) -> Dict[str, Any]:
        """Get tool results from agent session"""
        session_data = self.memory_store.get_agent_session(quotation_id)
        if session_data:
            return session_data.get("tool_results", {})
        return {}
    
    def save_tool_results(self, quotation_id: str, tool_results: Dict[str, Any]) -> None:
        """Save tool results"""
        self.memory_store.update_agent_session(quotation_id, {
            "tool_results": tool_results
        })
    
    def initialize_session(self, quotation_id: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Initialize a new agent session"""
        session_data = initial_data or {
            "conversation_history": [],
            "extracted_data": {},
            "tool_results": {},
            "confidence_scores": {}
        }
        self.memory_store.set_agent_session(quotation_id, session_data)
    
    def update_session(self, quotation_id: str, updates: Dict[str, Any]) -> None:
        """Update agent session with partial data"""
        self.memory_store.update_agent_session(quotation_id, updates)
    
    def get_session_state(self, quotation_id: str) -> Dict[str, Any]:
        """Get full session state"""
        return self.memory_store.get_agent_session(quotation_id) or {}
    
    def save_quotation_to_history(self, user_id: str, quotation_data: Dict[str, Any]) -> None:
        """Save a completed quotation to user's history"""
        self.memory_store.add_past_quotation(user_id, quotation_data)
    
    def clear_session(self, quotation_id: str) -> None:
        """Clear agent session"""
        self.memory_store.clear_agent_session(quotation_id)
    
    def get_common_requirements(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get common requirements from past quotations"""
        if not user_id:
            return {}
        
        past_quotations = self.memory_store.get_past_quotations(user_id)
        if not past_quotations:
            return {}
        
        # Analyze past quotations to find common patterns
        common = {
            "project_types": [],
            "locations": [],
            "average_size": 0,
            "common_materials": []
        }
        
        project_types = {}
        locations = {}
        sizes = []
        materials = {}
        
        for quotation in past_quotations:
            # Count project types
            ptype = quotation.get("project_type")
            if ptype:
                project_types[ptype] = project_types.get(ptype, 0) + 1
            
            # Count locations
            location = quotation.get("location")
            if location:
                locations[location] = locations.get(location, 0) + 1
            
            # Collect sizes
            size = quotation.get("size_sqm") or quotation.get("size_sqft")
            if size:
                sizes.append(size)
            
            # Collect materials
            cost_breakdown = quotation.get("cost_breakdown", {})
            material_items = cost_breakdown.get("materials", {}).get("items", [])
            for item in material_items:
                name = item.get("name", "")
                if name:
                    materials[name] = materials.get(name, 0) + 1
        
        # Get most common
        if project_types:
            common["project_types"] = sorted(project_types.items(), key=lambda x: x[1], reverse=True)[:3]
        if locations:
            common["locations"] = sorted(locations.items(), key=lambda x: x[1], reverse=True)[:3]
        if sizes:
            common["average_size"] = sum(sizes) / len(sizes)
        if materials:
            common["common_materials"] = sorted(materials.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return common

