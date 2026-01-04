from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from typing_extensions import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
import logging

from app.agents.supervisor import SupervisorAgent, SUPERVISOR_TOOLS
from app.agents.memory_manager import MemoryManager
from app.agents.state import QuotationAgentState

logger = logging.getLogger(__name__)

class ConversationalAgent:
    """Conversational agent that uses the Supervisor architecture"""
    
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.supervisor = SupervisorAgent()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build a Supervisor-based ReAct graph for the chat"""
        builder = StateGraph(QuotationAgentState)
        
        # Node: Supervisor (The Brain)
        async def call_supervisor(state: QuotationAgentState):
            result = await self.supervisor.invoke(state)
            return result
        
        # Node: Tools (The Hands)
        tool_node = ToolNode(SUPERVISOR_TOOLS)
        
        async def tool_node_with_meta(state: QuotationAgentState):
            result = await tool_node.ainvoke(state)
            iteration = state.get("iteration_count", 0) or 0
            return {**result, "iteration_count": iteration + 1}
        
        # Build logic
        builder.add_node("supervisor", call_supervisor)
        builder.add_node("tools", tool_node_with_meta)
        
        builder.set_entry_point("supervisor")
        
        def should_continue(state: QuotationAgentState) -> str:
            messages = state.get("messages", [])
            last_msg = messages[-1]
            if state.get("iteration_count", 0) >= 15:
                return END
            if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                return "tools"
            return END
            
        builder.add_conditional_edges("supervisor", should_continue, {"tools": "tools", END: END})
        builder.add_edge("tools", "supervisor")
        
        return builder.compile(checkpointer=self.checkpointer)

    async def process_message_stream(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_id: str,
        quotation_id: Optional[str] = None,
        files: List[Dict[str, Any]] = None,
        db: Session = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process message with REAL streaming response via LangGraph astream_events"""

        # Get or create session and check for linked quotation
        from app.services.session_service import SessionService
        from app.core.database import SessionLocal

        if not db:
            db = SessionLocal()
            should_close_db = True
        else:
            should_close_db = False

        try:
            # Get session and associated quotation
            session = SessionService.get_or_create_session(db, session_id)

            # Use quotation_id from session if not provided
            if not quotation_id and session.quotation_id:
                quotation_id = session.quotation_id
                logger.info(f"Using quotation {quotation_id} from session {session_id}")

            # Convert history
            langchain_messages = []
            for msg in history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    langchain_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    langchain_messages.append(AIMessage(content=content))

            langchain_messages.append(HumanMessage(content=message))

            # Initial state (following QuotationAgentState)
            # Note: quotation_id might be None initially - tools will create it
            initial_state: QuotationAgentState = {
                "messages": langchain_messages,
                "quotation_id": quotation_id or session_id,  # Fallback to session_id for compatibility
                "session_id": session_id,  # Add session_id to state
                "status": "PROCESSING",
                "current_phase": "GATHERING",
                "finish_levels": {},
                "processing_context": {},
                "iteration_count": 0,
                "extracted_data": {},
                "confidence_score": 0.0,
                "needs_followup": False,
                "follow_up_questions": [],
                "cost_breakdown": {},
                "total_cost": 0.0,
                "results": {}
            }

            config = {"configurable": {"thread_id": session_id}}
            full_content = ""

            # Use astream to get step-by-step updates (simpler and more reliable)
            async for state_update in self.graph.astream(initial_state, config, stream_mode="updates"):
                logger.info(f"Stream update received: {list(state_update.keys())}")

                # Check for supervisor node updates
                if "supervisor" in state_update:
                    supervisor_state = state_update["supervisor"]
                    messages = supervisor_state.get("messages", [])

                    if messages:
                        last_message = messages[-1]
                        logger.info(f"Last message type: {type(last_message).__name__}")

                        # Only stream AI messages that DON'T have tool calls (final user-facing responses)
                        if isinstance(last_message, AIMessage):
                            # Check if this message has tool calls (means it's an intermediate "thinking" message)
                            has_tool_calls = hasattr(last_message, 'tool_calls') and last_message.tool_calls

                            if not has_tool_calls:
                                # This is a final response to the user - stream it
                                content = last_message.content
                                if content and content not in full_content:
                                    # Stream the new content
                                    new_content = content[len(full_content):]
                                    full_content = content
                                    if new_content:
                                        logger.info(f"Yielding final content: {new_content[:50]}...")
                                        yield {"type": "content", "content": new_content}
                            else:
                                logger.info(f"Skipping intermediate supervisor message (has {len(last_message.tool_calls)} tool calls)")

                # Check for tool node updates
                elif "tools" in state_update:
                    logger.info("Tool execution detected")
                    yield {"type": "status", "content": "Processing..."}

            logger.info(f"Stream complete. Total content length: {len(full_content)}")

            # Persist history for compatibility
            updated_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_content}
            ]
            self.memory_manager.save_conversation_history(session_id, updated_history)

            # Get final quotation_id from session (might have been created during conversation)
            session = SessionService.get_or_create_session(db, session_id)
            final_quotation_id = session.quotation_id

            yield {"type": "done", "quotation_id": final_quotation_id, "session_id": session_id}

        finally:
            if should_close_db:
                db.close()

    async def process_message(self, *args, **kwargs) -> Dict[str, Any]:
        """Process message synchronously by consuming the stream"""
        full_content = ""
        quotation_id = kwargs.get("quotation_id")
        session_id = kwargs.get("session_id")
        history = kwargs.get("history", [])
        
        async for chunk in self.process_message_stream(*args, **kwargs):
            if chunk["type"] == "content":
                full_content += chunk["content"]
            elif chunk["type"] == "done":
                quotation_id = chunk.get("quotation_id", quotation_id)
        
        updated_history = history + [
            {"role": "user", "content": kwargs.get("message")},
            {"role": "assistant", "content": full_content}
        ]
        
        return {
            "response": full_content,
            "quotation_id": quotation_id,
            "history": updated_history
        }


