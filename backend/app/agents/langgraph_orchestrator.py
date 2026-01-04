from typing import Dict, Any, Literal
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from contextvars import ContextVar
import logging

from app.agents.state import QuotationAgentState
from app.agents.supervisor import SupervisorAgent, SUPERVISOR_TOOLS
from app.models.quotation import Quotation, QuotationStatus
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# Context variable for database session
db_session_context: ContextVar[Session] = ContextVar('db_session', default=None)

class LangGraphOrchestrator:
    """
    Supervisor-based Orchestrator.
    Uses a ReAct loop (Supervisor <-> Tools) to process quotations dynamically.
    """
    
    def __init__(self):
        self.checkpointer = MemorySaver()
        self.supervisor = SupervisorAgent()
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """Build the ReAct State Graph"""
        builder = StateGraph(QuotationAgentState)
        
        # Define Nodes
        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("tools", ToolNode(SUPERVISOR_TOOLS))
        
        # Define Edges
        builder.add_edge(START, "supervisor")
        
        # Conditional Edge: Check if supervisor wants to call tools or end
        builder.add_conditional_edges(
            "supervisor",
            self._should_continue,
            {
                "continue": "tools",
                "end": END
            }
        )
        
        # Edge: Tool output always goes back to supervisor
        builder.add_edge("tools", "supervisor")
        
        return builder.compile(checkpointer=self.checkpointer)

    async def _supervisor_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Run the Supervisor Agent (LLM)"""
        # Increment iteration count to prevent infinite loops
        current_iteration = state.get("iteration_count", 0) + 1
        
        # Call the supervisor agent
        result = await self.supervisor.invoke(state)
        
        return {
            "messages": result["messages"],
            "iteration_count": current_iteration
        }

    def _should_continue(self, state: QuotationAgentState) -> Literal["continue", "end"]:
        """Determine next step based on the last message"""
        messages = state.get("messages", [])
        if not messages:
            return "end"
            
        last_message = messages[-1]
        iteration = state.get("iteration_count", 0)
        
        # Safety Valve: Hard stop after 15 iterations
        if iteration >= 15:
            logger.warning(f"Quotation {state.get('quotation_id')} hit max iterations (15). Force stopping.")
            return "end"
            
        # Check if LLM made tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "continue"
            
        return "end"

    async def process_quotation(self, quotation_id: str, db: Session) -> Dict[str, Any]:
        """
        Process a quotation using the Supervisor Graph.
        
        Args:
            quotation_id: The ID of the quotation to process.
            db: Database session.
        """
        db_session_context.set(db)
        
        try:
            # Check/Update Status
            quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
            if not quotation:
                return {"success": False, "error": "Quotation not found"}
                
            if quotation.status == QuotationStatus.PENDING:
                quotation.status = QuotationStatus.PROCESSING
                db.commit()

            # Initialize State
            # Note: We don't load the full chat history from DB here because 
            # this orchestrator is often called for background tasks or initial API calls.
            # If "ConversationalAgent" is unified, we'd pass existing history.
            initial_state: QuotationAgentState = {
                "messages": [], # Start empty, let Supervisor fetch data via tools
                "quotation_id": quotation_id,
                "status": quotation.status.value,
                "processing_context": {},
                "iteration_count": 0,
                # Init legacy fields to None to satisfy TypedDict if needed (though Optional handles it)
                "extracted_data": None,
                "confidence_score": None,
                "needs_followup": False,
                "follow_up_questions": [],
                "cost_breakdown": None,
                "total_cost": None,
                "error": None,
                "results": {}
            }
            
            # Configure thread for checkpointer
            config = {"configurable": {"thread_id": quotation_id}}
            
            # Execute Graph
            final_state = await self.graph.ainvoke(initial_state, config)
            
            # Final Status Update
            # If no error, we mark as completed? 
            # In ReAct, "END" just means LLM stopped. We should check if costs were calculated.
            # We can check specific tool outputs or query the DB for QuotationData.
            
            db.refresh(quotation) # detailed data saved by tools
            
            # Simple heuristic: If we have a total cost, it's done. 
            # Otherwise, it might be waiting for user input (which this API doesn't handle directly interactively yet).
            # For this 'process_quotation' background task pattern, we mark COMPLETED if costs exist.
            
            if quotation.quotation_data and quotation.quotation_data.total_cost:
                 quotation.status = QuotationStatus.COMPLETED
                 db.commit()
            
            return {
                "success": True, 
                "quotation_id": quotation_id,
                "final_status": quotation.status.value
            }

        except Exception as e:
            logger.error(f"Orchestration Error: {e}")
            # Mark failed
            q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
            if q:
                q.status = QuotationStatus.FAILED
                db.commit()
            
            return {
                "success": False,
                "quotation_id": quotation_id,
                "error": str(e)
            }
        finally:
            db_session_context.set(None)
