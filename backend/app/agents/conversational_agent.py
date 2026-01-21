from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from typing_extensions import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
import logging

from app.agents.supervisor import SupervisorAgent
from app.agents.state import QuotationAgentState
from app.core.config import settings
from app.core.structured_logging import log_state_update, log_tool_execution
from app.graph.builder import build_supervisor_graph

logger = logging.getLogger(__name__)

class ConversationalAgent:
    """Conversational agent that uses the Supervisor architecture"""
    
    # Shared checkpointer for all instances to persist state across requests
    # LangGraph's MemorySaver handles conversation persistence automatically
    _checkpointer = MemorySaver()
    
    def __init__(self):
        self.supervisor = SupervisorAgent()
        self.graph = build_supervisor_graph(
            checkpointer=self._checkpointer,
            supervisor=self.supervisor,
            max_iterations=settings.MAX_ITERATIONS,
            use_start_edge=False  # ConversationalAgent uses set_entry_point
        )

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
                elif role == "assistant" and content.strip():
                    # Skip empty assistant messages (invalid for OpenAI API)
                    # Assistant messages must have either content OR tool_calls
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
                "processing_context": {
                    # Legacy fields moved here for backward compatibility
                    "extracted_data": {},
                    "confidence_score": 0.0,
                    "needs_followup": False,
                    "follow_up_questions": [],
                    "cost_breakdown": {},
                    "total_cost": 0.0,
                    "error": None
                },
                "iteration_count": 0,
                "results": {}
            }

            config = {
                "configurable": {
                    "thread_id": session_id,
                    "recursion_limit": settings.RECURSION_LIMIT
                }
            }
            
            # Stream processing state
            stream_state = {
                "full_content": "",
                "quotation_id": quotation_id or session_id,
                "session_id": session_id
            }

            # Use astream to get step-by-step updates (simpler and more reliable)
            async for state_update in self.graph.astream(initial_state, config, stream_mode="updates"):
                # Route to appropriate handler based on update type
                async for chunk in self._process_stream_update(state_update, stream_state):
                    yield chunk

            logger.info(f"Stream complete. Total content length: {len(stream_state['full_content'])}")

            # Conversation history is automatically persisted by LangGraph's MemorySaver
            # No need to manually save - it's stored in checkpoints via thread_id (session_id)

            # Get final quotation_id from session (might have been created during conversation)
            session = SessionService.get_or_create_session(db, session_id)
            final_quotation_id = session.quotation_id

            yield {"type": "done", "quotation_id": final_quotation_id, "session_id": session_id}

        finally:
            if should_close_db:
                db.close()

    async def _process_stream_update(
        self,
        state_update: Dict[str, Any],
        stream_state: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a single stream update and route to appropriate handler.
        Uses state machine pattern for clarity.
        """
        # Route based on update type
        if "supervisor" in state_update:
            async for chunk in self._stream_supervisor_update(state_update["supervisor"], stream_state):
                yield chunk
        elif "tools" in state_update:
            async for chunk in self._stream_tool_update(state_update["tools"], stream_state):
                yield chunk
        else:
            # Unknown update type - log for debugging
            logger.debug(f"Unknown stream update type: {list(state_update.keys())}")

    async def _stream_supervisor_update(
        self,
        supervisor_state: Dict[str, Any],
        stream_state: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle supervisor node updates - stream LLM tokens.
        """
        messages = supervisor_state.get("messages", [])
        if not messages:
            return

        last_message = messages[-1]
        logger.debug(f"Supervisor message type: {type(last_message).__name__}")

        # Only stream AI messages that DON'T have tool calls (final user-facing responses)
        if isinstance(last_message, AIMessage):
            has_tool_calls = hasattr(last_message, 'tool_calls') and last_message.tool_calls

            if not has_tool_calls:
                # This is a final response to the user - stream it
                content = last_message.content
                if content:
                    full_content = stream_state["full_content"]
                    if content not in full_content:
                        # Stream the new content
                        new_content = content[len(full_content):]
                        stream_state["full_content"] = content
                        if new_content:
                            logger.debug(f"Streaming content chunk: {len(new_content)} chars")
                            yield {"type": "content", "content": new_content}
            else:
                tool_count = len(last_message.tool_calls) if last_message.tool_calls else 0
                logger.debug(f"Skipping intermediate supervisor message (has {tool_count} tool calls)")

    async def _stream_tool_update(
        self,
        tool_state: Dict[str, Any],
        stream_state: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle tool node updates - log tool execution.
        """
        quotation_id = stream_state.get("quotation_id", "unknown")
        session_id = stream_state.get("session_id")
        
        # Log tool execution
        messages = tool_state.get("messages", [])
        if messages:
            # Tool execution completed - log it
            log_tool_execution(
                quotation_id=quotation_id,
                tool_name="tools",  # Generic name since we don't know which tool
                success=True,
                session_id=session_id
            )
        
        yield {"type": "status", "content": "Processing..."}

    async def _stream_state_updates(
        self,
        state: QuotationAgentState,
        stream_state: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Handle state transitions - log phase changes and state updates.
        """
        quotation_id = state.get("quotation_id", "unknown")
        session_id = state.get("session_id")
        current_phase = state.get("current_phase", "UNKNOWN")
        iteration_count = state.get("iteration_count", 0)
        
        # Log state update
        log_state_update(
            quotation_id=quotation_id,
            update_type="iteration",
            changes={"iteration_count": iteration_count},
            phase=current_phase,
            session_id=session_id
        )

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


