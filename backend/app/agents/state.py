from typing_extensions import TypedDict
from typing import Optional, Dict, Any, List, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from app.models.quotation import QuotationStatus


class QuotationAgentState(TypedDict):
    """
    State schema for the Supervisor ReAct graph.
    Simplified to reduce cognitive overhead - legacy fields moved to processing_context.
    """
    # Messaging (Critical for ReAct)
    messages: Annotated[List[BaseMessage], add_messages]

    # Core Identity
    quotation_id: str
    session_id: Optional[str]  # Session ID for linking quotations
    status: str  # QuotationStatus
    
    # Phase & Finishing State
    current_phase: str  # gathering|analyzing|quoting|complete
    finish_levels: Dict[str, str]  # {"current": "semi", "target": "full"}
    
    # Processing Context (contains: extracted_data, cost_breakdown, total_cost, confidence_score, etc.)
    processing_context: Dict[str, Any]
    iteration_count: int
    
    # Results (for final outputs)
    results: Dict[str, Any]
