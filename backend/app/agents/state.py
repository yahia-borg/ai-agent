from typing_extensions import TypedDict
from typing import Optional, Dict, Any, List
from app.models.quotation import QuotationStatus


class QuotationAgentState(TypedDict):
    """State schema for the quotation processing graph
    
    Note: All values must be JSON-serializable for LangGraph checkpointing
    """
    quotation_id: str
    status: str  # QuotationStatus as string for serialization
    extracted_data: Optional[Dict[str, Any]]
    confidence_score: Optional[float]
    needs_followup: bool
    follow_up_questions: List[str]
    cost_breakdown: Optional[Dict[str, Any]]
    total_cost: Optional[float]
    error: Optional[str]
    results: Dict[str, Any]

