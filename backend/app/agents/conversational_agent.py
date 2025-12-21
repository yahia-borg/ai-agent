"""
Conversational Agent using LangGraph with memory integration
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from app.agents.llm_client import get_llm_client
from app.agents.memory_manager import MemoryManager
from app.agent.tools import search_materials, search_labor_rates, search_standards, create_quotation
from app.utils.language_detector import detect_language, get_multilingual_prompt
import json
import logging

logger = logging.getLogger(__name__)

# Define tools
TOOLS = [search_materials, search_labor_rates, search_standards, create_quotation]


from typing_extensions import TypedDict, Annotated

class ConversationalAgentState(TypedDict):
    """State for conversational agent with memory"""
    messages: Annotated[List[BaseMessage], add_messages]
    quotation_id: str
    extracted_data: Dict[str, Any]
    tool_results: Dict[str, Any]
    memory_context: Dict[str, Any]
    needs_followup: bool
    follow_up_questions: List[str]
    iteration_count: int


class ConversationalAgent:
    """Conversational agent with memory and tools"""
    
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.llm_client = get_llm_client()
        self.llm = self.llm_client.client
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
    
    def _extract_project_description(self, messages: List[BaseMessage]) -> Optional[str]:
        """
        Extract project description from conversation messages.
        Looks for the first substantial user message that describes the project.
        """
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                content = msg.content.strip()
                # Skip very short messages or tool-related messages
                if len(content) > 20 and not content.startswith(('search_', 'create_')):
                    # Use first substantial user message as project description
                    # Limit to first 500 characters for brevity
                    return content[:500] if len(content) > 500 else content
        return None
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph with memory checkpoints"""
        builder = StateGraph(ConversationalAgentState)
        
        # Bind tools to LLM
        llm_with_tools = self.llm.bind_tools(TOOLS)
        
        # System prompt
        system_prompt = """You are a helpful construction cost estimation assistant for Egypt. 
You help users by:
1. Asking questions to understand their project requirements
2. Using tools to search for materials, labor rates, and building standards
3. Providing accurate cost estimates based on the information gathered
4. Being conversational and friendly

When the user describes a project:
- FIRST: Use search_standards to find relevant building codes and requirements for the project type
- THEN: Use search_materials to find material prices based on what the user needs
- ALSO: Use search_labor_rates to find labor costs for different trades
- Ask follow-up questions if information is missing (project size, location, timeline, etc.)
- Be concise but thorough
- Remember previous conversation context to avoid asking the same questions

Database Search Guidelines:
- When searching for materials, try multiple query variations:
  * Extract material type from multi-attribute queries (e.g., "light beige marble flooring" → search "marble")
  * Use specific material names from user conversation
  * If first search fails, try alternative terms and keyword extraction
  * Example: If user says "Italian marble", try searching "marble" first
- When searching for labor, extract role keywords:
  * "mason worker" → search "mason"
  * "electrician" → search "electrician"
  * Try variations if first search doesn't work

Tool Usage Guidelines:
- search_standards: Use when user mentions project type, building codes, or requirements
- search_materials: Use when user mentions specific materials or you need to suggest materials
- search_labor_rates: Use when calculating labor costs or user asks about labor
- create_quotation: Only use when you have enough information and user explicitly asks for quotation
  * IMPORTANT: When calling create_quotation, always include the project_description parameter.
  * The project_description should be a concise summary (1-2 sentences) of the user's project requirements.
  * Extract it from the conversation - use the initial project description or a summary of what the user wants to build.
  * Example: "Finishing a 200 m² modern semi-finished apartment" or "تجهيز شقة 200 متر مربع نصف تشطيب على الطراز الحديث"

CRITICAL - create_quotation Item Structure (Inspired by real-world BOQ examples):
When calling create_quotation, each item MUST include comprehensive details for professional descriptions:

1. REQUIRED fields: "name", "quantity", "unit_price", "unit"
2. RECOMMENDED: "category" field (flooring, painting, plumbing, electrical, etc.)
3. RECOMMENDED: "details" object with ALL mentioned attributes from conversation:
   - "brand": Extract from conversation (e.g., "Knauf", "Jotun", "Italian Carrara", "White Knauf")
   - "color": Extract color names (e.g., "Light Beige", "White", "Dark Color", "Cream")
   - "finish": Extract finish type (e.g., "Matt", "semi-glossy", "glossy", "satin")
   - "dimensions": Extract sizes (e.g., "60X60 cm", "12 mm", "H = 500 mm", "3mm thickness")
   - "specifications": Extract features (e.g., "Suspended", "Access Doors", "Premium grade", "Shadow Gap")
   - "context": Extract application area (e.g., "for Sales Area", "in BOH Area", "for bathroom", "in living room")

Extract ALL these attributes from conversation context - be thorough and comprehensive.
If user mentions "Italian marble", include {"brand": "Italian", "type": "marble"} in details.
If user mentions "light beige matt finish", include {"color": "Light Beige", "finish": "Matt"}.
If user mentions "for sales area", include {"context": "for Sales Area"}.
Infer missing attributes from project description when possible.

Example item structure:
{
  "name": "Marble Flooring",
  "quantity": 120,
  "unit_price": 1500,
  "unit": "m²",
  "category": "flooring",
  "details": {
    "brand": "Italian Carrara",
    "color": "Light Beige",
    "finish": "Matt",
    "dimensions": "60X60 cm",
    "specifications": "Premium grade",
    "context": "for Sales Area"
  }
}

IMPORTANT - When create_quotation returns a quotation_id:
- Inform the user that their quotation has been created successfully
- Tell them they can download PDF and Excel files by visiting the quotation page
- DO NOT create fake download links or use placeholder URLs like "example.com"
- Simply inform them: "Your quotation has been created! You can download the PDF and Excel files from the quotation page, or use the download links in the interface."

Always respond in the same language as the user (Arabic or English).
Prices are in Egyptian Pounds (EGP)."""
        
        def call_model(state: ConversationalAgentState):
            """Call LLM with memory context"""
            messages = state.get("messages", [])
            
            # Extract project description from conversation for context
            project_desc = None
            if messages:
                # Get project description from first substantial user message
                for msg in messages:
                    if isinstance(msg, HumanMessage) and msg.content:
                        content = msg.content.strip()
                        if len(content) > 20 and not content.startswith(('search_', 'create_')):
                            project_desc = content[:500] if len(content) > 500 else content
                            break
            
            # Build system prompt with project description context if available
            enhanced_system_prompt = system_prompt
            if project_desc:
                enhanced_system_prompt += f"\n\nCurrent project context: {project_desc}"
                enhanced_system_prompt += "\nWhen calling create_quotation, use this as the project_description parameter."
            
            # Add system prompt if not present
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=enhanced_system_prompt)] + messages
            else:
                # Replace existing system message with enhanced one
                messages[0] = SystemMessage(content=enhanced_system_prompt)
            
            # Add memory context to the last message if available
            memory_context = state.get("memory_context", {})
            if memory_context:
                context_str = f"\n\nUser context: {json.dumps(memory_context, ensure_ascii=False)}"
                if messages and isinstance(messages[-1], HumanMessage):
                    messages[-1].content += context_str
            
            response = llm_with_tools.invoke(messages)
            
            # Ensure AIMessage has content
            if hasattr(response, 'tool_calls') and response.tool_calls and not response.content:
                response.content = "Processing your request..."
            
            return {"messages": [response]}
        
        tool_node = ToolNode(TOOLS)
        
        def tool_node_with_memory(state: ConversationalAgentState):
            """Tool node that saves results to memory"""
            result = tool_node.invoke(state)
            iteration = state.get("iteration_count", 0)
            
            # Extract tool results
            tool_results = state.get("tool_results", {})
            
            # Handle result - it might be a dict or just messages
            if isinstance(result, dict):
                messages = result.get("messages", [])
            else:
                messages = result if isinstance(result, list) else []
            
            # Save tool results to memory
            for msg in messages:
                if hasattr(msg, 'name') and hasattr(msg, 'content'):
                    tool_results[msg.name] = msg.content
            
            return {
                "messages": messages,
                "iteration_count": iteration + 1,
                "tool_results": tool_results
            }
        
        def should_continue(state: ConversationalAgentState) -> str:
            """Determine if should continue or end"""
            messages = state.get("messages", [])
            if not messages:
                return "end"
            
            last_message = messages[-1]
            iteration = state.get("iteration_count", 0)
            
            # Hard stop after 5 iterations
            if iteration >= 5:
                return "end"
            
            # If LLM wants to call tools, continue
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                return "tools"
            
            return "end"
        
        # Build graph
        builder.add_node("agent", call_model)
        builder.add_node("tools", tool_node_with_memory)
        
        builder.set_entry_point("agent")
        
        builder.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )
        
        builder.add_edge("tools", "agent")
        
        # Compile with checkpointer
        return builder.compile(checkpointer=self.checkpointer)
    
    async def process_message(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_id: str,
        quotation_id: Optional[str] = None,
        files: List[Dict[str, Any]] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """Process a message and return response"""
        # Initialize session if needed (use session_id for session management)
        session_state = self.memory_manager.get_session_state(session_id)
        if not session_state:
            self.memory_manager.initialize_session(session_id)
        
        # Get memory context (use session_id for session, quotation_id for quotation linking)
        memory_context = self.memory_manager.get_user_context(quotation_id=quotation_id)
        
        # Convert history to LangChain messages
        # Clean history to only extract role and content (ignore attachments and other fields)
        langchain_messages = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and content:
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant" and content:
                langchain_messages.append(AIMessage(content=content))
        
        # Add current message
        langchain_messages.append(HumanMessage(content=message))
        
        # Prepare initial state - ensure all required fields
        # Use session_id for session management, quotation_id for quotation linking
        initial_state: ConversationalAgentState = {
            "messages": langchain_messages,
            "quotation_id": quotation_id or session_id,  # Fallback to session_id if no quotation_id
            "extracted_data": self.memory_manager.get_extracted_data(session_id) or {},
            "tool_results": self.memory_manager.get_tool_results(session_id) or {},
            "memory_context": memory_context,
            "needs_followup": False,
            "follow_up_questions": [],
            "iteration_count": 0
        }
        
        # Invoke graph with checkpoint (use session_id as thread_id for conversation continuity)
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }
        
        result = await self.graph.ainvoke(initial_state, config)
        
        # Extract response
        final_messages = result.get("messages", [])
        response_text = ""
        
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_text = msg.content
                break
        
        # Extract quotation_id from tool results (if create_quotation was called)
        tool_results = result.get("tool_results", {})
        extracted_quotation_id = quotation_id  # Default to current quotation_id
        
        # Check if create_quotation tool was called and extract new quotation_id
        if "create_quotation" in tool_results:
            try:
                tool_result_str = tool_results["create_quotation"]
                if isinstance(tool_result_str, str):
                    tool_result_json = json.loads(tool_result_str)
                    if "quotation_id" in tool_result_json:
                        extracted_quotation_id = tool_result_json["quotation_id"]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # Keep using existing quotation_id
        
        # Use session_id for memory operations (session management)
        # quotation_id is only for linking quotations
        
        # If no response, synthesize from tool results
        if not response_text:
            if tool_results:
                response_text = self._synthesize_response_from_tools(tool_results)
            else:
                response_text = "I'm processing your request. Please provide more details about your project."
        
        # Update memory
        # Clean history to only include role and content (remove attachments and other fields)
        cleaned_history = []
        for msg in history:
            cleaned_msg = {
                "role": msg.get("role", ""),
                "content": msg.get("content", "")
            }
            cleaned_history.append(cleaned_msg)
        
        updated_history = cleaned_history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response_text}
        ]
        # Use session_id for session management (conversation history, tool results, extracted data)
        self.memory_manager.save_conversation_history(session_id, updated_history)
        self.memory_manager.save_tool_results(session_id, tool_results)
        self.memory_manager.save_extracted_data(session_id, result.get("extracted_data", {}))
        
        return {
            "response": response_text,
            "quotation_id": extracted_quotation_id,
            "history": updated_history
        }
    
    async def process_message_stream(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_id: str,
        quotation_id: Optional[str] = None,
        files: List[Dict[str, Any]] = None,
        db: Session = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process message with streaming response"""
        # For now, process normally and stream chunks
        # In future, can use LLM streaming
        result = await self.process_message(message, history, session_id, quotation_id, files, db)
        
        # Stream response in chunks
        response = result["response"]
        chunk_size = 20
        
        for i in range(0, len(response), chunk_size):
            chunk = response[i:i+chunk_size]
            yield {
                "type": "content",
                "content": chunk
            }
        
        yield {
            "type": "done",
            "quotation_id": result["quotation_id"]
        }
    
    def _synthesize_response_from_tools(self, tool_results: Dict[str, Any]) -> str:
        """Synthesize response from tool results"""
        response_parts = []
        
        if "search_materials" in tool_results:
            try:
                materials = json.loads(tool_results["search_materials"])
                if isinstance(materials, list) and materials:
                    response_parts.append("I found the following materials:\n")
                    for mat in materials[:5]:
                        name = mat.get("name", "Unknown")
                        price = mat.get("price", 0)
                        unit = mat.get("unit", "")
                        response_parts.append(f"- {name}: {price} EGP/{unit}")
            except:
                pass
        
        if "search_labor_rates" in tool_results:
            try:
                labor = json.loads(tool_results["search_labor_rates"])
                if isinstance(labor, list) and labor:
                    response_parts.append("\nLabor rates:\n")
                    for rate in labor[:3]:
                        role = rate.get("role", "Unknown")
                        hourly = rate.get("hourly_rate", 0)
                        response_parts.append(f"- {role}: {hourly} EGP/hour")
            except:
                pass
        
        if not response_parts:
            return "I've gathered some information. Let me help you with your project requirements."
        
        return "\n".join(response_parts)

