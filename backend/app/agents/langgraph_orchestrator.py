from typing import Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import HumanMessage
import logging

from app.agents.state import QuotationAgentState
from app.models.quotation import Quotation, QuotationStatus
from app.core.db_context import db_session_context, get_or_create_async_db_session
from app.core.config import settings
from app.graph.builder import build_supervisor_graph
from app.graph.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)

class LangGraphOrchestrator:
    """
    Deterministic Workflow Orchestrator.
    Uses the workflow_node (pure Python routing) to process quotations.
    """

    def __init__(self):
        self.graph = build_supervisor_graph(
            checkpointer=get_checkpointer(),
        )

    async def process_quotation(self, quotation_id: str, db: Union[Session, AsyncSession]) -> Dict[str, Any]:
        """
        Process a quotation using the Supervisor Graph.
        
        Args:
            quotation_id: The ID of the quotation to process.
            db: Database session (sync or async - will convert to async if needed).
        """
        # Convert to async session if needed, or use existing async session
        if isinstance(db, AsyncSession):
            async_db = db
            should_close = False
        else:
            # Create async session for tools (they expect async)
            async_db = await get_or_create_async_db_session()
            should_close = db_session_context.get() is None
        
        db_session_context.set(async_db)
        
        try:
            # Check/Update Status
            result = await async_db.execute(select(Quotation).filter(Quotation.id == quotation_id))
            quotation = result.scalar_one_or_none()
            if not quotation:
                return {"success": False, "error": "Quotation not found"}
                
            if quotation.status == QuotationStatus.PENDING:
                quotation.status = QuotationStatus.PROCESSING
                await async_db.commit()

            # Initialize State — seed with the project description so the Supervisor
            # has user context and knows to call collect_project_data immediately.
            seed_messages = []
            if quotation.project_description:
                seed_messages = [HumanMessage(content=quotation.project_description)]

            initial_state: QuotationAgentState = {
                "messages": seed_messages,
                "quotation_id": quotation_id,
                "status": quotation.status.value,
                "current_phase": "GATHERING",
                "finish_levels": {},
                "processing_context": {
                    # Legacy fields moved here
                    "extracted_data": None,
                    "confidence_score": None,
                    "needs_followup": False,
                    "follow_up_questions": [],
                    "cost_breakdown": None,
                    "total_cost": None,
                    "error": None
                },
                "iteration_count": 0,
                "detected_language": None,
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
            
            await async_db.refresh(quotation) # detailed data saved by tools
            
            # Simple heuristic: If we have a total cost, it's done. 
            # Otherwise, it might be waiting for user input (which this API doesn't handle directly interactively yet).
            # For this 'process_quotation' background task pattern, we mark COMPLETED if costs exist.
            
            if quotation.quotation_data and quotation.quotation_data.total_cost:
                 quotation.status = QuotationStatus.COMPLETED
                 await async_db.commit()
            
            return {
                "success": True, 
                "quotation_id": quotation_id,
                "final_status": quotation.status.value
            }

        except Exception as e:
            logger.error(f"Orchestration Error: {e}")
            try:
                # Mark failed
                q_result = await async_db.execute(select(Quotation).filter(Quotation.id == quotation_id))
                q = q_result.scalar_one_or_none()
                if q:
                    q.status = QuotationStatus.FAILED
                    await async_db.commit()
            except Exception:
                pass
            
            return {
                "success": False,
                "quotation_id": quotation_id,
                "error": str(e)
            }
        finally:
            db_session_context.set(None)
            if should_close:
                await async_db.close()