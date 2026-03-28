from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.agents.llm_client import get_llm_client
from app.agents.tools_wrapper import (
    collect_project_data,
    calculate_costs,
    resolve_quotation,
)
from app.agent.tools import search_materials, search_labor_rates, search_standards, export_quotation_pdf, export_quotation_excel
from app.agents.state import QuotationAgentState
from app.core.structured_logging import log_phase_transition, log_state_update
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


# Tools available to the Supervisor (8 tools, down from 11)
SUPERVISOR_TOOLS = [
    collect_project_data,
    resolve_quotation,
    calculate_costs,
    search_materials,
    search_labor_rates,
    search_standards,
    export_quotation_pdf,
    export_quotation_excel,
]

from app.core.database import SessionLocal
from app.models.quotation import QuotationData

class SupervisorAgent:
    """
    The 'Brain' of the operation. A ReAct agent that decides which tool to call 
    based on the current state of the quotation and user history.
    """
    def __init__(self):
        self.llm_client = get_llm_client()
        # Bind tools to the LLM
        self.llm_with_tools = self.llm_client.client.bind_tools(SUPERVISOR_TOOLS)
        
    
    def _build_state_checklist(self, q_data: Optional[QuotationData]) -> str:
        """Build dynamic state checklist for prompt."""
        if not q_data or not q_data.extracted_data:
            return "❌ Size: Missing | ❌ Type: Missing | ❌ Finish Levels: Missing | ❌ Rooms: Missing"

        extracted = q_data.extracted_data or {}
        size = extracted.get("size_sqm")
        p_type = extracted.get("project_type")
        current = extracted.get("current_finish_level", "?")
        target = extracted.get("target_finish_level", "?")
        rooms = extracted.get("rooms", [])
        num_bathrooms = extracted.get("num_bathrooms")
        num_kitchens = extracted.get("num_kitchens")

        checklist = []
        checklist.append("✅" if size else "❌")
        checklist.append(f"Size: {size} sqm" if size else "Size: Missing")
        checklist.append("✅" if p_type and p_type != "Unknown" else "❌")
        checklist.append(f"Type: {p_type}" if p_type and p_type != "Unknown" else "Type: Missing")
        checklist.append("✅" if current and current != "?" and target and target != "?" else "❌")
        checklist.append(f"Finish: {current}→{target}" if current and current != "?" and target and target != "?" else "Finish: Missing")

        # Room breakdown check
        has_rooms = bool(rooms) or (num_bathrooms is not None and num_kitchens is not None)
        if has_rooms:
            room_summary_parts = []
            if rooms:
                room_summary_parts.append(f"{len(rooms)} spaces")
            if num_bathrooms is not None:
                room_summary_parts.append(f"{num_bathrooms} bath")
            if num_kitchens is not None:
                room_summary_parts.append(f"{num_kitchens} kitchen")
            checklist.append(f"✅ Rooms: {', '.join(room_summary_parts)}")
        else:
            checklist.append("❌ Rooms: Missing breakdown")

        if q_data.total_cost:
            checklist.append("✅ Cost: Calculated")
        elif q_data.cost_breakdown:
            checklist.append("⏳ Cost: In Progress")
        else:
            checklist.append("❌ Cost: Not Started")

        return " | ".join(checklist)
    
    def get_system_prompt(self, quotation_id: str) -> str:
        """Generates optimized system prompt with ReAct structure."""
        
        # Fetch dynamic state from DB
        current_phase = "GATHERING"
        current_status = "?"
        target_status = "?"
        state_checklist = "❌ All data missing"
        
        db = SessionLocal()
        try:
            q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation_id).first()
            
            if not q_data and quotation_id.startswith("session-"):
                from app.models.memory import AgentSession
                session = db.query(AgentSession).filter(AgentSession.session_id == quotation_id).first()
                if session and session.quotation_id:
                    real_quotation_id = session.quotation_id
                    q_data = db.query(QuotationData).filter(QuotationData.quotation_id == real_quotation_id).first()
                    quotation_id = real_quotation_id

            if q_data:
                extracted = q_data.extracted_data or {}
                current_status = extracted.get("current_finish_level") or "?"
                target_status = extracted.get("target_finish_level") or "?"
                state_checklist = self._build_state_checklist(q_data)

                if current_status != "?" and target_status != "?":
                    if q_data.total_cost:
                        current_phase = "COMPLETE"
                    elif q_data.cost_breakdown:
                        current_phase = "QUOTING"
                    else:
                        current_phase = "ANALYZING"
        except Exception as e:
            logger.error(f"Error fetching state for prompt: {e}")
        finally:
            db.close()
        
        max_info_len = settings.MAX_ADDITIONAL_INFO_LENGTH

        # Tool-routing prompt — NO user-facing text generation
        complete_override = ""
        if current_phase == "COMPLETE":
            complete_override = f"""
⚠️ PHASE = COMPLETE — READ THIS FIRST ⚠️
The quotation is ALREADY FINISHED with calculated costs.
- Do NOT call collect_project_data
- Do NOT call calculate_costs
- ONLY call export_quotation_pdf if the user explicitly asks to download or export a PDF
- ONLY call export_quotation_excel if the user explicitly asks to download or export Excel
- For ALL other messages (questions, thanks, clarifications): output exactly "DONE"
"""

        prompt = f"""You are a Construction Quotation Tool Router.
Your ONLY job is to call tools to gather project data and calculate costs.
You do NOT write user-facing responses. A separate response agent handles that.
{complete_override}
=== IMPORTANT: WHEN TO CALL TOOLS ===

Look at the STATE CHECKLIST below. If ANY field shows ❌, you MUST call a tool.

1. If user mentions ANY construction/finishing details (size, type, rooms, finish level):
   → ALWAYS call collect_project_data(quotation_id="{quotation_id}", additional_info="<summary of what user said>")
   This is your PRIMARY action. When in doubt, call collect_project_data.

2. If checklist shows ✅ for Size AND Type AND Finish AND Rooms:
   → Call calculate_costs(quotation_id="{quotation_id}")

3. If user asks about material prices → call search_materials
4. If user asks about labor rates → call search_labor_rates
5. If user asks about standards → call search_standards
6. If user asks for PDF/Excel export → call export_quotation_pdf or export_quotation_excel

=== WHEN TO OUTPUT "DONE" ===

Output exactly "DONE" (no other text) ONLY when:
- ✅ Cost: Calculated (quotation is complete)
- The last ToolMessage contains "Cost Calculation Complete" → STOP, output DONE immediately
- All fields are ✅ EXCEPT Rooms (response agent will ask the user)
- Tool output contains "Follow-up Needed" (response agent will ask the user)
- Tool output says "Missing Info" and you already called collect_project_data this turn
- User is just chatting (no construction data to extract)

=== LOOP PREVENTION ===
- NEVER call calculate_costs more than once per turn
- After calculate_costs returns success ("Cost Calculation Complete"), output DONE
- After calculate_costs returns an error, call collect_project_data ONCE then try calculate_costs again
- If you have called both collect_project_data AND calculate_costs already, output DONE

=== RULES ===

- Keep additional_info SHORT ({max_info_len} chars max) — just the key facts
- Use quotation_id: {quotation_id}
- For bank/hospital/hotel/school → project_type is ALWAYS "commercial"
- Never generate user-facing text, only tool calls or "DONE"
- Never hallucinate prices — only use data from tools
- Batch: 2-3 tool calls max per turn

=== CURRENT STATE (CHECK THIS FIRST) ===

Phase: {current_phase}
State Checklist: {state_checklist}
Quotation ID: {quotation_id}"""
        
        return prompt

    async def invoke(self, state: QuotationAgentState) -> Dict[str, Any]:
        """
        Run the Supervisor LLM against the current state messages.
        """
        messages = state.get("messages", [])
        quotation_id = state.get("quotation_id")
        
        # Ensure we have a system prompt
        # We check if the first message is a SystemMessage, if not (or if it needs updating), we insert/replace it.
        system_prompt = self.get_system_prompt(quotation_id)
        
        if not messages:
            messages = [SystemMessage(content=system_prompt)]
        elif not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=system_prompt))
        else:
            # Update existing system prompt (in case context changed, though ID usually static)
            messages[0] = SystemMessage(content=system_prompt)

        # Validate messages: Remove invalid assistant messages (empty content without tool_calls)
        # This prevents OpenAI API 400 errors
        validated_messages = []
        for msg in messages:
            if isinstance(msg, AIMessage):
                # Assistant messages must have either content OR tool_calls
                has_content = msg.content and msg.content.strip()
                has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
                if not (has_content or has_tool_calls):
                    logger.warning(f"Skipping invalid assistant message (empty content, no tool_calls)")
                    continue
            validated_messages.append(msg)

        # Invoke LLM
        try:
            response = await self.llm_with_tools.ainvoke(validated_messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Supervisor LLM Error: {e}")
            return {
                "messages": [
                    AIMessage(content="I encountered an error processing your request. Please try again.")
                ],
                "error": str(e)
            }
