from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.agents.llm_client import get_llm_client
from app.agents.tools_wrapper import collect_project_data, calculate_costs
from app.agent.tools import search_materials, search_labor_rates, search_standards, export_quotation_pdf, export_quotation_excel
from app.agents.state import QuotationAgentState
import logging

logger = logging.getLogger(__name__)


# List of tools available to the Supervisor
SUPERVISOR_TOOLS = [
    collect_project_data,
    calculate_costs,
    search_materials,
    search_labor_rates,
    search_standards,
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
        
    
    def get_system_prompt(self, quotation_id: str) -> str:
        """Generates the system prompt with context."""
        
        # Fetch dynamic state from DB
        current_phase = "GATHERING"
        current_status = "?"
        target_status = "?"
        
        db = SessionLocal()
        try:
            q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation_id).first()
            if q_data:
                # Read finish levels from extracted_data JSON
                extracted = q_data.extracted_data or {}
                current_status = extracted.get("current_finish_level") or "?"
                target_status = extracted.get("target_finish_level") or "?"

                # Determine phase
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
            
        base_prompt = """You are an expert Construction Supervisor for the Egyptian market.
Your goal is to help users get accurate construction quotations.

You have access to a team of tools:
1. 'collect_project_data': EXTRACTS project info (Size, Type, and optional Location) from the chat. ALWAYS run this after the user provides project details.
2. 'search_standards': Finds building codes and requirements (e.g., "mix ratio for plaster").
3. 'search_materials': Finds material prices in EGP (e.g., "Ceramic Cleopatra 60x60").
4. 'search_labor_rates': Finds worker wages in EGP (e.g., "Daily rate for Tiler").
5. 'calculate_costs': Generates the FINAL cost breakdown. Run this when you have sufficient data (Size and Type are required, Location and Materials are optional but improve accuracy).
6. 'export_quotation_pdf': Exports the quotation as a PDF file. Call this when the user asks for PDF export.
7. 'export_quotation_excel': Exports the quotation as an Excel file. Call this when the user asks for Excel export.

PROCESS FLOW:
1. Understand the Request: Read the user's latest message.
2. Gap Analysis: Do you have the Project Size? Type? If no, ask the user. Location is optional but helpful for accurate pricing.
3. Information Retrieval:
   - Run 'collect_project_data' to save what you know from the text to the DB.
   - If user asks for specific materials, use 'search_materials'.
   - If you need technical norms, use 'search_standards'.
4. Costing:
   - Once you have sufficient data (Size and Type are required), run 'calculate_costs'.
5. Export (if requested):
   - If user asks for PDF, use 'export_quotation_pdf'.
   - If user asks for Excel, use 'export_quotation_excel'.
6. Response:
   - Summarize the tool outputs clearly to the user.
   - If costing is done, present the final total and ask if they want to export (PDF/Excel).

RULES:
- Be professional but friendly.
- Quotes are in Egyptian Pounds (EGP).
- ALWAYS use the 'collect_project_data' tool when the user gives new project info. This tool will automatically create a new quotation if one doesn't exist.
- DO NOT hallucinate prices. Use the search tools.
- If a tool returns an error, ALWAYS call 'collect_project_data' first before trying other tools.
- DO NOT tell the user about technical errors like "quotation not found" or "issue with database". Instead, just call collect_project_data to fix it.
- **CRITICAL**: When calling 'collect_project_data', ALWAYS use the quotation_id from the current context (shown below as QUOTATION_ID). DO NOT make up new IDs like "default" or "new_quotation_001".
"""
        # Inject Dynamic Context
        phase_block = f"""
PHASE: {current_phase}
STATUS: {current_status} -> {target_status}
QUOTATION_ID: {quotation_id}

When calling collect_project_data, use this exact quotation_id: {quotation_id}
"""
        return base_prompt + phase_block

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
            
        # Invoke LLM
        try:
            response = await self.llm_with_tools.ainvoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Supervisor LLM Error: {e}")
            return {
                "messages": [
                    AIMessage(content="I encountered an error processing your request. Please try again.")
                ],
                "error": str(e)
            }
