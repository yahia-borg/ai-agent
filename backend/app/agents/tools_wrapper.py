from langchain_core.tools import tool
from typing import Optional, Dict, Any
import json
import logging
import uuid

from app.core.database import SessionLocal
from app.models.quotation import Quotation, QuotationData
from app.agents.data_collector import DataCollectorAgent
from app.agents.cost_calculator import CostCalculatorAgent
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)

@tool
async def collect_project_data(quotation_id: str, additional_info: Optional[str] = None) -> str:
    """
    Extracts project parameters (size, location, type) from the quotation description.

    Args:
        quotation_id: The ID of the quotation to process.
        additional_info: Optional additional details provided by the user to update the project description.

    Returns:
        A concise summary string of the extracted data and any missing information.
    """
    db = SessionLocal()
    try:
        # First, try to find existing quotation
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()

        # If not found, check if quotation_id is actually a session_id (pattern: "session-*")
        real_session_id = None
        if not quotation and quotation_id.startswith("session-"):
            # This is a session_id, not quotation_id
            real_session_id = quotation_id
            # Try to get quotation linked to this session
            from app.models.memory import AgentSession
            session = db.query(AgentSession).filter(AgentSession.session_id == real_session_id).first()
            if session and session.quotation_id:
                quotation = db.query(Quotation).filter(Quotation.id == session.quotation_id).first()

        # Auto-create quotation if still not found
        if not quotation:
            logger.info(f"Quotation not found for '{quotation_id}'. Creating new quotation.")

            # Create with proper UUID
            new_quotation_id = str(uuid.uuid4())
            quotation = Quotation(
                id=new_quotation_id,
                project_description=additional_info or "New construction project",
                status="pending"
            )
            db.add(quotation)
            db.commit()
            db.refresh(quotation)

            # Link to session if we detected a session_id
            if real_session_id:
                try:
                    SessionService.link_session_to_quotation(db, real_session_id, new_quotation_id)
                    logger.info(f"Linked new quotation {new_quotation_id} to session {real_session_id}")
                except Exception as e:
                    logger.warning(f"Failed to link quotation to session: {e}")
        else:
            # Update project description if additional info is provided
            if additional_info:
                current_desc = quotation.project_description or ""
                # Append new info clearly
                quotation.project_description = f"{current_desc}\n\nClient Update: {additional_info}".strip()
                db.commit()
            
        # Initialize agent
        agent = DataCollectorAgent()
        
        # Execute agent
        context = {} # Context can be expanded if needed
        result = await agent.execute(quotation, context)
        
        # Persist results to DB (Agent often does this, but we ensure QuotationData is updated)
        # Note: DataCollectorAgent.execute already updates the DB in the current implementation? 
        # Checking implementation: It returns a dict but DOES update DB inside execute if logic allows.
        # Actually, looking at previous analysis, DataCollectorAgent.execute returns a dict and 
        # the *Orchestrator* was responsible for saving it to QuotationData. 
        # So we MUST save it here to replicate Orchestrator behavior.
        
        extracted_data = result.get("extracted_data", {})
        confidence = result.get("confidence_score", 0.0)
        
        # Save or Update QuotationData
        # IMPORTANT: Use quotation.id (actual UUID) not quotation_id (LLM parameter)
        q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation.id).first()
        if not q_data:
            q_data = QuotationData(
                quotation_id=quotation.id,  # Use actual UUID from database
                extracted_data=extracted_data,  # Contains current_finish_level and target_finish_level
                confidence_score=confidence
            )
            db.add(q_data)
        else:
            q_data.extracted_data = extracted_data
            q_data.confidence_score = confidence
        
        db.commit()
        
        # Format output for Supervisor (LLM)
        # We need a concise summary, not the whole JSON
        size = extracted_data.get("size_sqm") or extracted_data.get("size_sqft")
        unit = "sqm" if extracted_data.get("size_sqm") else "sqft"

        p_type = extracted_data.get("project_type")
        current_status = extracted_data.get("current_finish_level", "Not specified")
        target_status = extracted_data.get("target_finish_level", "Not specified")
        key_reqs = extracted_data.get("key_requirements", [])
        
        # Correctly get missing info from extracted_data
        missing = extracted_data.get("missing_information", [])
        
        # Mandatory field validation for the summary
        if not size:
            if "Size (sqm)" not in missing:
                missing.append("Size (sqm)")
        if not p_type or p_type == "Unknown":
            if "Project Type" not in missing:
                missing.append("Project Type")

        summary = f"Data Extracted:\n- Type: {p_type or 'Unknown'}\n- Size: {size if size else 'None'} {unit}\n"
        summary += f"- Current Status: {current_status}\n- Target Status: {target_status}\n"

        # Show key requirements if any (includes location if mentioned)
        if key_reqs:
            summary += f"- Key Requirements: {', '.join(key_reqs)}\n"
        
        if missing:
             summary += f"- Missing Info: {', '.join(missing)}\n"
        else:
             summary += "- All core data appears present.\n"
             
        if result.get("needs_followup"):
             followups = result.get('follow_up_questions', [])
             if followups:
                summary += f"- Follow-up Needed: {', '.join(followups)}"
             
        return summary

    except Exception as e:
        logger.error(f"Error in collect_project_data: {e}")
        return f"Error collecting project data: {str(e)}"
    finally:
        db.close()


@tool
async def calculate_costs(quotation_id: str) -> str:
    """
    Calculates detailed construction costs based on extracted data.

    Args:
        quotation_id: The ID of the quotation to calculate costs for.

    Returns:
        A concise summary of the Total Cost and breakdown.
    """
    db = SessionLocal()
    try:
        # Try to find quotation
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()

        # If not found, check if quotation_id is actually a session_id
        if not quotation and quotation_id.startswith("session-"):
            from app.models.memory import AgentSession
            session = db.query(AgentSession).filter(AgentSession.session_id == quotation_id).first()
            if session and session.quotation_id:
                quotation = db.query(Quotation).filter(Quotation.id == session.quotation_id).first()

        if not quotation:
            return f"Error: Quotation not found for '{quotation_id}'. Please run 'collect_project_data' first to create the quotation."

        # Use quotation.id (actual UUID) not quotation_id parameter
        q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation.id).first()
        if not q_data or not q_data.extracted_data:
            return "Error: No extracted data found. Please run 'collect_project_data' first to extract project details."
            
        # Initialize Agent
        agent = CostCalculatorAgent()
        
        # Prepare context
        context = {
            "extracted_data": q_data.extracted_data
        }
        
        # Execute
        result = await agent.execute(quotation, context)
        
        # Save results (Orchestrator previously did this)
        q_data.cost_breakdown = result.get("cost_breakdown")
        q_data.total_cost = result.get("total_cost")
        db.commit()
        
        # Format Output
        total = result.get("total_cost", 0)
        currency = result.get("currency", "EGP")
        breakdown = result.get("cost_breakdown", {})
        
        summary = f"### 🏗️ Cost Calculation Complete\n**Total Estimated Cost: {total:,.2f} {currency}**\n\n"
        
        summary += "#### 📦 Material & BOQ Breakdown:\n"
        if "materials" in breakdown:
            for item in breakdown["materials"].get("items", []):
                name = item.get("name")
                cost = item.get("total", 0)
                summary += f"- **{name}**: {cost:,.2f} {currency}\n"
        
        if "labor" in breakdown:
             summary += "\n#### 👷 Labor & Trades:\n"
             for trade in breakdown["labor"].get("trades", []):
                 name = trade.get("trade")
                 cost = trade.get("total", 0)
                 summary += f"- **{name}**: {cost:,.2f} {currency}\n"
             
        summary += "\n> [!TIP]\n"
        summary += "> Full detailed professional breakdown (6-column BOQ with technical specs) has been saved. You can now export this as PDF or Excel."
        return summary

    except Exception as e:
        logger.error(f"Error in calculate_costs: {e}")
        return f"Error calculating costs: {str(e)}"
    finally:
        db.close()
