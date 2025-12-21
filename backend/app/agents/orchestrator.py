import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.quotation import Quotation, QuotationStatus, QuotationData
from app.agents.data_collector import DataCollectorAgent
from app.agents.cost_calculator import CostCalculatorAgent
from app.agents.langgraph_orchestrator import LangGraphOrchestrator


class AgentOrchestrator:
    """Orchestrates the execution of multiple AI agents"""
    
    def __init__(self, use_langgraph: bool = True):
        """Initialize orchestrator
        
        Args:
            use_langgraph: If True, use LangGraph-based orchestrator (default: True)
        """
        if use_langgraph:
            self.langgraph_orchestrator = LangGraphOrchestrator()
        else:
            # Fallback to simple orchestrator
            self.data_collector = DataCollectorAgent()
            self.cost_calculator = CostCalculatorAgent()
        self.use_langgraph = use_langgraph
        self.agents = [self.data_collector, self.cost_calculator] if not use_langgraph else []
    
    async def process_quotation(self, quotation_id: str, db: Session) -> Dict[str, Any]:
        """Process a quotation through all agents"""
        
        if self.use_langgraph:
            # Use LangGraph orchestrator
            return await self.langgraph_orchestrator.process_quotation(quotation_id, db)
        
        # Fallback to simple orchestrator (original implementation)
        return await self._process_quotation_simple(quotation_id, db)
    
    async def _process_quotation_simple(self, quotation_id: str, db: Session) -> Dict[str, Any]:
        """Process a quotation through all agents"""
        
        # Get quotation from database
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            raise ValueError(f"Quotation {quotation_id} not found")
        
        context: Dict[str, Any] = {}
        results: Dict[str, Any] = {}
        
        try:
            # Update status to processing
            quotation.status = QuotationStatus.PROCESSING
            db.commit()
            
            # Agent 1: Data Collector
            quotation.status = QuotationStatus.DATA_COLLECTION
            db.commit()
            
            data_collector_result = await self.data_collector.execute(quotation, context)
            context["extracted_data"] = data_collector_result.get("extracted_data", {})
            results["data_collector"] = data_collector_result
            
            # Save extracted data to database
            quotation_data = db.query(QuotationData).filter(
                QuotationData.quotation_id == quotation_id
            ).first()
            
            if not quotation_data:
                quotation_data = QuotationData(
                    quotation_id=quotation_id,
                    extracted_data=context["extracted_data"],
                    confidence_score=data_collector_result.get("confidence_score", 0.5)
                )
                db.add(quotation_data)
            else:
                quotation_data.extracted_data = context["extracted_data"]
                quotation_data.confidence_score = data_collector_result.get("confidence_score", 0.5)
            
            db.commit()
            
            # Check if follow-up questions are needed
            if data_collector_result.get("needs_followup", False):
                # For MVP, we'll proceed with available data
                # In full version, we'd wait for user answers here
                pass
            
            # Agent 2: Cost Calculator
            quotation.status = QuotationStatus.COST_CALCULATION
            db.commit()
            
            cost_calculator_result = await self.cost_calculator.execute(quotation, context)
            results["cost_calculator"] = cost_calculator_result
            
            # Save cost breakdown to database
            quotation_data.cost_breakdown = cost_calculator_result.get("cost_breakdown", {})
            quotation_data.total_cost = cost_calculator_result.get("total_cost", 0.0)
            db.commit()
            
            # Mark as completed
            quotation.status = QuotationStatus.COMPLETED
            db.commit()
            
            return {
                "success": True,
                "quotation_id": quotation_id,
                "results": results
            }
            
        except Exception as e:
            # Mark as failed
            quotation.status = QuotationStatus.FAILED
            db.commit()
            
            return {
                "success": False,
                "quotation_id": quotation_id,
                "error": str(e)
            }
    
    async def process_quotation_async(self, quotation_id: str, db: Session):
        """Process quotation asynchronously (for background tasks)"""
        # This will be used with Celery in future phases
        return await self.process_quotation(quotation_id, db)

