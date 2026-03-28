from langchain_core.tools import tool
from typing import Optional, Dict, Any
import json
import logging
from sqlalchemy import select

from app.core.db_context import get_or_create_async_db_session, db_session_context
from app.core.config import settings
from app.models.quotation import Quotation, QuotationData, QuotationStatus
from app.agents.data_collector import DataCollectorAgent
from app.agents.cost_calculator import CostCalculatorAgent
from app.services.session_service import SessionService
from app.core.exceptions import ToolError, ErrorCodes
from app.utils.session_utils import resolve_quotation_id

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
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None

    try:
        quotation, created = await resolve_quotation_id(
            quotation_id, db, create_if_missing=True, additional_info=additional_info
        )

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

    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None

    try:
        quotation, _ = await resolve_quotation_id(
            quotation_id, db, create_if_missing=True, additional_info=additional_info
        )

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
        
        # Update quotation status — never downgrade from completed/cost_calculation
        if quotation.status not in (QuotationStatus.COMPLETED, QuotationStatus.COST_CALCULATION):
            quotation.status = QuotationStatus.DATA_COLLECTION
        
        await db.commit()
        
        # Format output for Supervisor (LLM)
        # We need a concise summary, not the whole JSON
        size = extracted_data.get("size_sqm")
        unit = "sqm"

        p_type = extracted_data.get("project_type")
        current_status = extracted_data.get("current_finish_level", "Not specified")
        target_status = extracted_data.get("target_finish_level", "Not specified")
        key_reqs = extracted_data.get("key_requirements", [])
        rooms = extracted_data.get("rooms", [])
        num_bathrooms = extracted_data.get("num_bathrooms")
        num_kitchens = extracted_data.get("num_kitchens")

        # Correctly get missing info from extracted_data
        missing = extracted_data.get("missing_information", [])

        # Mandatory field validation for the summary
        if not size:
            if "Size (sqm)" not in missing:
                missing.append("Size (sqm)")
        if not p_type or p_type == "Unknown":
            if "Project Type" not in missing:
                missing.append("Project Type")

        # Room breakdown validation
        has_rooms = bool(rooms) or (num_bathrooms is not None and num_kitchens is not None)
        if not has_rooms:
            if "Room breakdown" not in missing:
                missing.append("Room breakdown")

        summary = f"Data Extracted:\n- Type: {p_type or 'Unknown'}\n- Size: {size if size else 'None'} {unit}\n"
        summary += f"- Current Status: {current_status}\n- Target Status: {target_status}\n"

        # Show room breakdown if available
        if rooms:
            room_parts = []
            for r in rooms:
                rtype = r.get("room_type", "?")
                rcount = r.get("count", 1)
                room_parts.append(f"{rcount}x {rtype}")
            summary += f"- Rooms: {', '.join(room_parts)}\n"
        if num_bathrooms is not None:
            summary += f"- Bathrooms: {num_bathrooms}\n"
        if num_kitchens is not None:
            summary += f"- Kitchens: {num_kitchens}\n"

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
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None

    try:
        quotation, _ = await resolve_quotation_id(
            quotation_id, db, create_if_missing=False
        )

        if not quotation:
            return f"Error: Quotation not found for '{quotation_id}'. Please run 'collect_project_data' first to create the quotation."

        # Use quotation.id (actual UUID) not quotation_id parameter
        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation.id)
        )
        q_data = q_data_result.scalar_one_or_none()
        if not q_data or q_data.extracted_data is None:
            return "Error: No extracted data found. Please run 'collect_project_data' first to extract project details."

        # Validate required fields before calculating
        extracted = q_data.extracted_data
        missing_fields = []
        if not extracted.get("size_sqm"):
            missing_fields.append("size (sqm)")
        if not extracted.get("project_type") or extracted.get("project_type") == "Unknown":
            missing_fields.append("project type")
        if not extracted.get("current_finish_level"):
            missing_fields.append("current finish level")
        if not extracted.get("target_finish_level"):
            missing_fields.append("target finish level")
        if missing_fields:
            return f"Error: Cannot calculate costs yet. Missing required data: {', '.join(missing_fields)}. Please call collect_project_data to gather this information first."

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
        
        # Update quotation status to allow downloads
        quotation.status = QuotationStatus.COMPLETED
        
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
