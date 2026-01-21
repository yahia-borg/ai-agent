from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.agents.llm_client import get_llm_client
from app.agents.tools_wrapper import (
    collect_project_data,
    calculate_costs,
    resolve_quotation,
    extract_project_requirements,
    save_project_data
)
from app.agent.tools import search_materials, search_labor_rates, search_standards, export_quotation_pdf, export_quotation_excel
from app.agents.state import QuotationAgentState
from app.core.structured_logging import log_phase_transition, log_state_update
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


# List of tools available to the Supervisor
SUPERVISOR_TOOLS = [
    # Convenience wrapper (backward compatible)
    collect_project_data,
    # Focused tools (use for better control)
    resolve_quotation,
    extract_project_requirements,
    save_project_data,
    # Cost calculation
    calculate_costs,
    # Search tools
    search_materials,
    search_labor_rates,
    search_standards,
    # Export tools
    export_quotation_pdf,
    export_quotation_excel
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
            return "❌ Size: Missing | ❌ Type: Missing | ❌ Finish Levels: Missing"
        
        extracted = q_data.extracted_data or {}
        size = extracted.get("size_sqm")
        p_type = extracted.get("project_type")
        current = extracted.get("current_finish_level", "?")
        target = extracted.get("target_finish_level", "?")
        
        checklist = []
        checklist.append("✅" if size else "❌")
        checklist.append(f"Size: {size} sqm" if size else "Size: Missing")
        checklist.append("✅" if p_type and p_type != "Unknown" else "❌")
        checklist.append(f"Type: {p_type}" if p_type and p_type != "Unknown" else "Type: Missing")
        checklist.append("✅" if current and current != "?" and target and target != "?" else "❌")
        checklist.append(f"Finish: {current}→{target}" if current and current != "?" and target and target != "?" else "Finish: Missing")
        
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
        
        # ReAct prompt following LangGraph best practices
        prompt = f"""You are an expert Construction Finishing Supervisor for the Egyptian market. Your goal is to provide accurate quotations by systematically gathering data and calculating costs.

=== REACT REASONING CYCLE ===

1. THINK: 
   - Read the DYNAMIC STATE checklist below
   - Analyze what data is present (✅) vs missing (❌)
   - Determine what the user is asking for
   - Decide which tool(s) to use based on state, not assumptions

2. ACT:
   - Call the appropriate tool(s) based on your analysis
   - Use exact quotation_id: {quotation_id}
   - Keep tool arguments concise ({max_info_len} chars max)

3. OBSERVE:
   - Read tool outputs carefully
   - Update your understanding of the current state
   - Note any errors or missing data

4. REFLECT:
   - Check if you have enough data to proceed
   - If all required data is ✅, move to next phase
   - If data is ❌, gather it first
   - Stop when task is complete

=== DECISION TREE (CHECK STATE CHECKLIST FIRST) ===

STEP 1: Check DYNAMIC STATE checklist below:
- If checklist shows ✅ for Size AND ✅ for Type AND ✅ for Finish Levels:
  → PROCEED to calculate_costs (DO NOT ask for confirmation - data exists!)
- If checklist shows ❌ for Size OR ❌ for Type OR ❌ for Finish Levels:
  → Call collect_project_data to extract missing information
- If checklist shows ✅ Cost: Calculated:
  → You're done - provide summary or ask if user wants export

STEP 2: Handle user requests:
- User asks "what materials?" or "prices?" → search_materials/search_labor_rates
- User asks "what standards?" or "specifications?" → search_standards
- User asks "export PDF/Excel" → export_quotation_pdf/excel

STEP 3: After calculate_costs completes:
- Provide cost breakdown to user
- Ask if they want to export or adjust anything
- DO NOT call calculate_costs again if already calculated

=== CRITICAL RULES ===

1. TRUST THE STATE CHECKLIST: If checklist shows ✅, the data exists - proceed immediately
2. DO NOT ask for data that's already in the checklist (✅ means it's present)
3. Only ask questions if checklist shows ❌ for required fields
4. After calculate_costs completes, stop and present results
5. Never hallucinate prices - only use data from tools
6. Batch searches: 2-3 tool calls max per turn

=== AVAILABLE TOOLS ===

- collect_project_data: Extract project info from description
- calculate_costs: Calculate cost breakdown (requires Size + Type + Finish Levels)
- search_materials: Search material prices (keywords: 1-3 words)
- search_labor_rates: Search labor rates (keywords: 1-3 words)
- search_standards: Search technical standards (keywords: 1-5 words)
- export_quotation_pdf: Export quotation as PDF
- export_quotation_excel: Export quotation as Excel

=== OUTPUT FORMATTING ===

- Use Western numerals (0-9), never Eastern Arabic (٠١٢٣٤٥٦٧٨٩)
- Format prices: "125,000 EGP" (comma for thousands)
- Markdown tables: | Header | Header |\\n|--------|--------|\\n| Data | Data |
- No special Unicode characters
- Lists: Use "1." or "-" only
- Keep responses concise and structured

=== DYNAMIC STATE (CHECK THIS FIRST) ===

Phase: {current_phase}
State Checklist: {state_checklist}
Quotation ID: {quotation_id}

Remember: If the checklist shows ✅ for all required fields, proceed to calculate_costs immediately. Do not ask for confirmation."""
        
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
