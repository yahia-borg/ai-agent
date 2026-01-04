from typing_extensions import TypedDict
from typing import Optional, Dict, Any, List, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from app.models.quotation import QuotationStatus


class QuotationAgentState(TypedDict):
    """
    State schema for the Supervisor ReAct graph.
    """
    # Messaging (Critical for ReAct)
    messages: Annotated[List[BaseMessage], add_messages]

    # Core Identity
    quotation_id: str
    session_id: Optional[str]  # Session ID for linking quotations
    status: str  # QuotationStatus
    
    # Phase & Finishing State (New)
    current_phase: str  # gathering|analyzing|quoting|complete
    finish_levels: Dict[str, str]  # {"current": "semi", "target": "full"}
    
    # Transient Processing Context (RAG, Missing Info, Loops)
    processing_context: Dict[str, Any]
    iteration_count: int
    
    # Legacy Fields (Kept for compatibility with other components or easy serialization)
    extracted_data: Optional[Dict[str, Any]]
    confidence_score: Optional[float]
    needs_followup: bool
    follow_up_questions: List[str]
    cost_breakdown: Optional[Dict[str, Any]]
    total_cost: Optional[float]
    error: Optional[str]
    results: Dict[str, Any]
