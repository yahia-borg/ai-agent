from typing import Dict, Any, Literal, Optional
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from contextvars import ContextVar

from app.agents.state import QuotationAgentState
from app.agents.data_collector import DataCollectorAgent
from app.agents.cost_calculator import CostCalculatorAgent
from app.models.quotation import Quotation, QuotationStatus, QuotationData
from app.core.database import SessionLocal

# Context variable for database session (thread-safe)
db_session_context: ContextVar[Optional[Session]] = ContextVar('db_session', default=None)


class LangGraphOrchestrator:
    """LangGraph-based orchestrator for AI agents with state management"""
    
    def __init__(self):
        self.data_collector = DataCollectorAgent()
        self.cost_calculator = CostCalculatorAgent()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph"""
        builder = StateGraph(QuotationAgentState)
        
        # Add nodes
        builder.add_node("initialize", self._initialize_node)
        builder.add_node("data_collection", self._data_collection_node)
        builder.add_node("check_followup", self._check_followup_node)
        builder.add_node("cost_calculation", self._cost_calculation_node)
        builder.add_node("save_results", self._save_results_node)
        builder.add_node("handle_error", self._handle_error_node)
        
        # Define edges
        builder.add_edge(START, "initialize")
        builder.add_edge("initialize", "data_collection")
        
        # Conditional edge: check if follow-up is needed
        builder.add_conditional_edges(
            "data_collection",
            self._should_ask_followup,
            {
                "needs_followup": "check_followup",
                "continue": "cost_calculation"
            }
        )
        
        # After follow-up check, proceed to cost calculation
        builder.add_edge("check_followup", "cost_calculation")
        builder.add_edge("cost_calculation", "save_results")
        builder.add_edge("save_results", END)
        
        # Error handling
        builder.add_edge("handle_error", END)
        
        # Compile with checkpointer for state persistence
        return builder.compile(checkpointer=self.checkpointer)
    
    def _get_db(self) -> Session:
        """Get database session from context"""
        db = db_session_context.get()
        if db is None:
            # Fallback: create new session (shouldn't happen in normal flow)
            db = SessionLocal()
        return db
    
    async def _initialize_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Initialize the quotation processing"""
        db = self._get_db()
        quotation_id = state["quotation_id"]
        
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return {
                "error": f"Quotation {quotation_id} not found",
                "status": QuotationStatus.FAILED.value
            }
        
        quotation.status = QuotationStatus.PROCESSING
        db.commit()
        
        return {
            "status": QuotationStatus.PROCESSING.value,
            "results": {}
        }
    
    async def _data_collection_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Execute data collection agent"""
        db = self._get_db()
        quotation_id = state["quotation_id"]
        
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return {"error": "Quotation not found"}
        
        try:
            # Update status
            quotation.status = QuotationStatus.DATA_COLLECTION
            db.commit()
            
            # Execute data collector
            result = await self.data_collector.execute(quotation, {})
            
            # Save extracted data to database
            quotation_data = db.query(QuotationData).filter(
                QuotationData.quotation_id == quotation_id
            ).first()
            
            if not quotation_data:
                quotation_data = QuotationData(
                    quotation_id=quotation_id,
                    extracted_data=result.get("extracted_data", {}),
                    confidence_score=result.get("confidence_score", 0.5)
                )
                db.add(quotation_data)
            else:
                quotation_data.extracted_data = result.get("extracted_data", {})
                quotation_data.confidence_score = result.get("confidence_score", 0.5)
            
            db.commit()
            
            return {
                "extracted_data": result.get("extracted_data", {}),
                "confidence_score": result.get("confidence_score", 0.5),
                "needs_followup": result.get("needs_followup", False),
                "follow_up_questions": result.get("follow_up_questions", []),
                "status": QuotationStatus.DATA_COLLECTION.value,
                "results": {**state.get("results", {}), "data_collector": result}
            }
        except Exception as e:
            return {
                "error": str(e),
                "status": QuotationStatus.FAILED.value
            }
    
    def _should_ask_followup(self, state: QuotationAgentState) -> Literal["needs_followup", "continue"]:
        """Conditional routing: check if follow-up questions are needed"""
        needs_followup = state.get("needs_followup", False)
        confidence = state.get("confidence_score", 0.0)
        
        # For MVP, we'll proceed even if follow-up is needed
        # In full version, we'd route to follow-up handling
        if needs_followup and confidence < 0.5:
            return "needs_followup"
        return "continue"
    
    async def _check_followup_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Handle follow-up questions (for future enhancement)"""
        # For MVP, we proceed with available data
        # In full version, this would wait for user input
        return {
            "status": QuotationStatus.DATA_COLLECTION.value,
            "needs_followup": False  # Proceed anyway for MVP
        }
    
    async def _cost_calculation_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Execute cost calculation agent"""
        db = self._get_db()
        quotation_id = state["quotation_id"]
        extracted_data = state.get("extracted_data", {})
        
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return {"error": "Quotation not found"}
        
        try:
            # Update status
            quotation.status = QuotationStatus.COST_CALCULATION
            db.commit()
            
            # Prepare context for cost calculator
            context = {
                "extracted_data": extracted_data
            }
            
            # Execute cost calculator
            result = await self.cost_calculator.execute(quotation, context)
            
            return {
                "cost_breakdown": result.get("cost_breakdown", {}),
                "total_cost": result.get("total_cost", 0.0),
                "status": QuotationStatus.COST_CALCULATION.value,
                "results": {**state.get("results", {}), "cost_calculator": result}
            }
        except Exception as e:
            return {
                "error": str(e),
                "status": QuotationStatus.FAILED.value
            }
    
    async def _save_results_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Save final results to database"""
        db = self._get_db()
        quotation_id = state["quotation_id"]
        
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return {"error": f"Quotation {quotation_id} not found"}
        
        # Save cost breakdown to database
        quotation_data = db.query(QuotationData).filter(
            QuotationData.quotation_id == quotation_id
        ).first()
        
        if quotation_data:
            quotation_data.cost_breakdown = state.get("cost_breakdown")
            quotation_data.total_cost = state.get("total_cost")
            db.commit()
        
        # Mark as completed
        quotation.status = QuotationStatus.COMPLETED
        db.commit()
        
        return {
            "status": QuotationStatus.COMPLETED.value
        }
    
    async def _handle_error_node(self, state: QuotationAgentState) -> Dict[str, Any]:
        """Handle errors and mark quotation as failed"""
        db = self._get_db()
        quotation_id = state["quotation_id"]
        
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if quotation:
            quotation.status = QuotationStatus.FAILED
            db.commit()
        
        return {
            "status": QuotationStatus.FAILED.value,
            "error": state.get("error", "Unknown error")
        }
    
    async def process_quotation(self, quotation_id: str, db: Session) -> Dict[str, Any]:
        """Process a quotation through the LangGraph workflow"""
        # Set database session in context for nodes to access
        db_session_context.set(db)
        
        try:
            # Create initial state
            initial_state: QuotationAgentState = {
                "quotation_id": quotation_id,
                "status": QuotationStatus.PENDING.value,
                "extracted_data": None,
                "confidence_score": None,
                "needs_followup": False,
                "follow_up_questions": [],
                "cost_breakdown": None,
                "total_cost": None,
                "error": None,
                "results": {}
            }
            
            # Execute the graph with checkpointing
            config = {
                "configurable": {
                    "thread_id": quotation_id
                }
            }
            
            final_state = await self.graph.ainvoke(initial_state, config)
            
            return {
                "success": final_state.get("status") == QuotationStatus.COMPLETED.value,
                "quotation_id": quotation_id,
                "results": final_state.get("results", {}),
                "error": final_state.get("error")
            }
        except Exception as e:
            # Mark as failed
            quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
            if quotation:
                quotation.status = QuotationStatus.FAILED
                db.commit()
            
            return {
                "success": False,
                "quotation_id": quotation_id,
                "error": str(e)
            }
        finally:
            # Clean up context
            db_session_context.set(None)

