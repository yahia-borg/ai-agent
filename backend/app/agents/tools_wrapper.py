from langchain_core.tools import tool
from typing import Optional, Dict, Any
import json
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.db_context import get_or_create_async_db_session, db_session_context
from app.core.config import settings
from app.models.quotation import Quotation, QuotationData
from app.agents.data_collector import DataCollectorAgent
from app.agents.cost_calculator import CostCalculatorAgent
from app.services.session_service import SessionService
from app.core.exceptions import ToolError, ErrorCodes

logger = logging.getLogger(__name__)


@tool
async def resolve_quotation(quotation_id: str, additional_info: Optional[str] = None) -> str:
    """
    Resolves quotation from database. Creates new quotation if not found.
    Handles session_id to quotation_id resolution.
    
    DECISION CRITERIA:
    - Call when you need to ensure a quotation exists before other operations
    - Call when quotation_id might be a session_id that needs resolution
    - Do NOT call if you already have a valid quotation_id from context
    
    INPUT FORMAT:
    - quotation_id: Quotation ID or session_id (pattern: "session-*")
    - additional_info: Optional description for new quotations
    
    OUTPUT FORMAT:
    - Returns: JSON string with quotation_id and status
    - Format: {"quotation_id": "...", "status": "...", "created": true/false}
    
    STATE TRANSITIONS:
    - Does not modify state directly
    - Quotation is created/updated in database
    
    ERROR HANDLING:
    - Always returns valid quotation_id (creates if missing)
    - Never crashes, returns error JSON on failure
    
    EXAMPLES:
    - resolve_quotation("quot-123") → Returns existing quotation
    - resolve_quotation("session-abc", "New project") → Creates and links quotation
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None
    
    try:
        # Try to find existing quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()
        
        # If not found, check if quotation_id is actually a session_id
        real_session_id = None
        if not quotation and quotation_id.startswith("session-"):
            real_session_id = quotation_id
            from app.models.memory import AgentSession
            session_result = await db.execute(
                select(AgentSession).filter(AgentSession.session_id == real_session_id)
            )
            session = session_result.scalar_one_or_none()
            if session and session.quotation_id:
                quote_result = await db.execute(
                    select(Quotation).filter(Quotation.id == session.quotation_id)
                )
                quotation = quote_result.scalar_one_or_none()
        
        # Auto-create quotation if still not found
        created = False
        if not quotation:
            logger.info(f"Quotation not found for '{quotation_id}'. Creating new quotation.")
            new_quotation_id = str(uuid.uuid4())
            quotation = Quotation(
                id=new_quotation_id,
                project_description=additional_info or "New construction project",
                status="pending"
            )
            db.add(quotation)
            await db.commit()
            await db.refresh(quotation)
            created = True
            
            # Link to session if we detected a session_id
            if real_session_id:
                try:
                    # Link session to quotation using async operations
                    from app.models.memory import AgentSession
                    session_result = await db.execute(
                        select(AgentSession).filter(AgentSession.session_id == real_session_id)
                    )
                    session = session_result.scalar_one_or_none()
                    if not session:
                        # Create session if it doesn't exist
                        session = AgentSession(
                            session_id=real_session_id,
                            quotation_id=None,
                            session_data={"conversation_history": []}
                        )
                        db.add(session)
                    session.quotation_id = new_quotation_id
                    await db.commit()
                    await db.refresh(session)
                    logger.info(f"Linked new quotation {new_quotation_id} to session {real_session_id}")
                except Exception as e:
                    logger.warning(f"Failed to link quotation to session: {e}")
        else:
            # Update project description if additional info is provided
            if additional_info:
                current_desc = quotation.project_description or ""
                quotation.project_description = f"{current_desc}\n\nClient Update: {additional_info}".strip()
                await db.commit()
        
        return json.dumps({
            "quotation_id": quotation.id,
            "status": quotation.status,
            "created": created
        })
        
    except Exception as e:
        logger.error(f"Error in resolve_quotation: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return json.dumps({"error": f"Error resolving quotation: {str(e)}"})
    finally:
        if should_close:
            await db.close()


@tool
async def extract_project_requirements(description: str) -> str:
    """
    Extracts project parameters from description. Pure function, no database operations.
    
    DECISION CRITERIA:
    - Call when you need to extract project data from text description
    - Call after resolve_quotation to get quotation description
    - Do NOT call if you already have extracted_data in state
    
    INPUT FORMAT:
    - description: Project description text (can be full quotation description)
    
    OUTPUT FORMAT:
    - Returns: JSON string with extracted_data, confidence_score, needs_followup, follow_up_questions
    - Format: {"extracted_data": {...}, "confidence_score": 0.8, ...}
    
    STATE TRANSITIONS:
    - Does not modify state or database
    - Returns data that should be saved via save_project_data
    
    ERROR HANDLING:
    - Always returns JSON (never crashes)
    - Returns empty extracted_data on failure
    
    EXAMPLES:
    - extract_project_requirements("150 sqm apartment in Cairo, fully finished") → Extracts size, type, location, finish level
    """
    try:
        # Create a temporary quotation object for the agent
        from app.models.quotation import Quotation
        temp_quotation = Quotation(
            id="temp",
            project_description=description,
            status="pending"
        )
        
        # Initialize agent
        agent = DataCollectorAgent()
        
        # Execute agent (pure extraction, no DB)
        context = {}
        result = await agent.execute(temp_quotation, context)
        
        # Return as JSON
        return json.dumps({
            "extracted_data": result.get("extracted_data", {}),
            "confidence_score": result.get("confidence_score", 0.0),
            "needs_followup": result.get("needs_followup", False),
            "follow_up_questions": result.get("follow_up_questions", [])
        })
        
    except Exception as e:
        logger.error(f"Error in extract_project_requirements: {e}")
        return json.dumps({
            "extracted_data": {},
            "confidence_score": 0.0,
            "needs_followup": False,
            "follow_up_questions": [],
            "error": str(e)
        })


@tool
async def save_project_data(quotation_id: str, extracted_data_json: str) -> str:
    """
    Saves extracted project data to QuotationData. Only persistence operations.
    
    DECISION CRITERIA:
    - Call after extract_project_requirements to persist data
    - Call when you need to update existing QuotationData
    - Do NOT call if data is already saved and unchanged
    
    INPUT FORMAT:
    - quotation_id: Valid quotation ID (must exist)
    - extracted_data_json: JSON string from extract_project_requirements output
    
    OUTPUT FORMAT:
    - Returns: Success message with saved data summary
    - Format: "Data saved: Type: [type], Size: [size] sqm, ..."
    
    STATE TRANSITIONS:
    - Updates QuotationData in database
    - Does not modify state directly
    
    ERROR HANDLING:
    - Returns error message if quotation not found
    - Always returns formatted message (never crashes)
    
    EXAMPLES:
    - save_project_data("quot-123", '{"extracted_data": {...}}') → Saves to QuotationData
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None
    
    try:
        # Parse extracted data
        try:
            data = json.loads(extracted_data_json)
            extracted_data = data.get("extracted_data", {})
            confidence = data.get("confidence_score", 0.0)
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for extracted_data_json"
        
        # Find quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()
        if not quotation:
            return f"Error: Quotation {quotation_id} not found. Run resolve_quotation first."
        
        # Save or Update QuotationData
        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation.id)
        )
        q_data = q_data_result.scalar_one_or_none()
        if not q_data:
            q_data = QuotationData(
                quotation_id=quotation.id,
                extracted_data=extracted_data,
                confidence_score=confidence
            )
            db.add(q_data)
        else:
            q_data.extracted_data = extracted_data
            q_data.confidence_score = confidence
        
        # Update quotation status
        quotation.status = "data_collection"
        
        await db.commit()
        
        # Format summary
        size = extracted_data.get("size_sqm")
        p_type = extracted_data.get("project_type", "Unknown")
        current_status = extracted_data.get("current_finish_level", "Not specified")
        target_status = extracted_data.get("target_finish_level", "Not specified")
        missing = extracted_data.get("missing_information", [])
        
        summary = f"Data saved:\n- Type: {p_type}\n- Size: {size if size else 'None'} sqm\n"
        summary += f"- Current Status: {current_status}\n- Target Status: {target_status}\n"
        
        if missing:
            summary += f"- Missing Info: {', '.join(missing)}\n"
        else:
            summary += "- All core data present.\n"
        
        return summary
        
    except Exception as e:
        logger.error(f"Error in save_project_data: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        raise ToolError(
            message=f"Error saving project data: {str(e)}",
            error_code=ErrorCodes.DB_TRANSACTION_ERROR,
            recoverable=True
        )
    finally:
        if should_close:
            await db.close()

@tool
async def collect_project_data(quotation_id: str, additional_info: Optional[str] = None) -> str:
    """
    Extracts project parameters (size, location, type, finish levels) from the quotation description.
    
    DECISION CRITERIA:
    - Call when user provides new project information (size, type, location, finish requirements)
    - Call when project data is missing or incomplete
    - Call when tool errors occur (as recovery mechanism)
    - Do NOT call if all required data is already extracted and user is asking about materials/prices
    
    INPUT FORMAT:
    - quotation_id: The quotation ID from current context (use exact ID, never make up new ones)
    - additional_info: SHORT summary (max {max_info_len} chars) of ONLY new information from user's latest message
      Examples: "150 sqm apartment", "fully finished", "Cairo location"
    
    OUTPUT FORMAT:
    - Returns: Concise summary string with extracted data and missing information
    - Format: "Data Extracted:\n- Type: [type]\n- Size: [size] sqm\n- Current Status: [status]\n- Target Status: [status]\n- Missing Info: [list]"
    
    STATE TRANSITIONS:
    - Updates: extracted_data (project_type, size_sqm, current_finish_level, target_finish_level)
    - Updates: confidence_score, missing_information, follow_up_questions
    
    ERROR HANDLING:
    - If quotation not found: Auto-creates new quotation
    - If session_id provided: Resolves to actual quotation_id
    - Always returns summary even on errors (never crashes)
    
    EXAMPLES:
    - collect_project_data("quot-123", "150 sqm apartment in Cairo") → Extracts size, type, location
    - collect_project_data("session-abc", "fully finished") → Updates finish level requirement
    """
    # Truncate additional_info to prevent tool call truncation issues
    from app.core.config import settings
    max_length = settings.MAX_ADDITIONAL_INFO_LENGTH
    if additional_info and len(additional_info) > max_length:
        logger.warning(f"Truncating additional_info from {len(additional_info)} to {max_length} characters")
        additional_info = additional_info[:max_length]
    
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # First, try to find existing quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()

        # If not found, check if quotation_id is actually a session_id (pattern: "session-*")
        real_session_id = None
        if not quotation and quotation_id.startswith("session-"):
            # This is a session_id, not quotation_id
            real_session_id = quotation_id
            # Try to get quotation linked to this session
            from app.models.memory import AgentSession
            session_result = await db.execute(
                select(AgentSession).filter(AgentSession.session_id == real_session_id)
            )
            session = session_result.scalar_one_or_none()
            if session and session.quotation_id:
                quote_result = await db.execute(
                    select(Quotation).filter(Quotation.id == session.quotation_id)
                )
                quotation = quote_result.scalar_one_or_none()

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
            await db.commit()
            await db.refresh(quotation)

            # Link to session if we detected a session_id
            if real_session_id:
                try:
                    # Link session to quotation using async operations
                    session_result = await db.execute(
                        select(AgentSession).filter(AgentSession.session_id == real_session_id)
                    )
                    session = session_result.scalar_one_or_none()
                    if not session:
                        # Create session if it doesn't exist
                        session = AgentSession(
                            session_id=real_session_id,
                            quotation_id=None,
                            session_data={"conversation_history": []}
                        )
                        db.add(session)
                    session.quotation_id = new_quotation_id
                    await db.commit()
                    await db.refresh(session)
                    logger.info(f"Linked new quotation {new_quotation_id} to session {real_session_id}")
                except Exception as e:
                    logger.warning(f"Failed to link quotation to session: {e}")
        else:
            # Update project description if additional info is provided
            if additional_info:
                current_desc = quotation.project_description or ""
                # Append new info clearly
                quotation.project_description = f"{current_desc}\n\nClient Update: {additional_info}".strip()
                await db.commit()
            
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
        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation.id)
        )
        q_data = q_data_result.scalar_one_or_none()
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
        
        # Update quotation status
        quotation.status = "data_collection"
        
        await db.commit()
        
        # Format output for Supervisor (LLM)
        # We need a concise summary, not the whole JSON
        size = extracted_data.get("size_sqm")
        unit = "sqm"

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
        logger.error(f"Error in collect_project_data: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        raise ToolError(
            message=f"Failed to extract project data: {str(e)}",
            error_code=ErrorCodes.EXTRACTION_FAILED,
            recoverable=True
        )
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()


@tool
async def calculate_costs(quotation_id: str) -> str:
    """
    Calculates detailed construction costs based on extracted project data.
    
    DECISION CRITERIA:
    - Call when you have sufficient project data (size_sqm and project_type are required minimum)
    - Call after collect_project_data has extracted core information
    - Call when user asks for cost estimate or quotation
    - Do NOT call if size_sqm or project_type is missing (call collect_project_data first)
    - This is the FINAL step before export - call once, then STOP tool calls
    
    INPUT FORMAT:
    - quotation_id: The quotation ID from current context (must exist in database)
    
    OUTPUT FORMAT:
    - Returns: Markdown-formatted summary with total cost and breakdown
    - Format: "### Cost Calculation Complete\n**Total: [amount] EGP**\n\n#### Material Breakdown:\n- [item]: [cost]\n..."
    
    STATE TRANSITIONS:
    - Updates: cost_breakdown (materials, labor with detailed items)
    - Updates: total_cost (final calculated amount)
    - Sets phase to "COMPLETE" when successful
    
    ERROR HANDLING:
    - If quotation not found: Returns error message asking to run collect_project_data first
    - If extracted_data missing: Returns error asking to extract data first
    - Always returns formatted message (never crashes)
    
    EXAMPLES:
    - calculate_costs("quot-123") → Generates full cost breakdown for 150 sqm residential project
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # Try to find quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()

        # If not found, check if quotation_id is actually a session_id
        if not quotation and quotation_id.startswith("session-"):
            from app.models.memory import AgentSession
            session_result = await db.execute(
                select(AgentSession).filter(AgentSession.session_id == quotation_id)
            )
            session = session_result.scalar_one_or_none()
            if session and session.quotation_id:
                quote_result = await db.execute(
                    select(Quotation).filter(Quotation.id == session.quotation_id)
                )
                quotation = quote_result.scalar_one_or_none()

        if not quotation:
            return f"Error: Quotation not found for '{quotation_id}'. Please run 'collect_project_data' first to create the quotation."

        # Use quotation.id (actual UUID) not quotation_id parameter
        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation.id)
        )
        q_data = q_data_result.scalar_one_or_none()
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
        
        # Update quotation status to allow downloads (CRITICAL FIX)
        quotation.status = "completed"
        
        await db.commit()
        
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
        logger.error(f"Error in calculate_costs: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        raise ToolError(
            message=f"Failed to calculate construction costs: {str(e)}",
            error_code=ErrorCodes.DB_QUERY_ERROR, # Or a more specific code if available
            recoverable=True
        )
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()
