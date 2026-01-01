"""
Cost Estimation Agent - Main agent class for the supervisor-based system.

This agent wraps the LangGraph and provides the interface for API integration,
replacing the ConversationalAgent.
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from app.graph.builder import build_cost_estimation_graph
from app.state.schemas import CostEstimationState, WorkflowStatus
from app.agents.memory_manager import MemoryManager
import logging
import json

logger = logging.getLogger(__name__)


class CostEstimationAgent:
    """Main cost estimation agent with supervisor-based routing"""
    
    def __init__(self, memory_manager: MemoryManager):
        """
        Initialize the cost estimation agent.
        
        Args:
            memory_manager: Memory manager for session persistence
        """
        self.memory_manager = memory_manager
        # Build graph once on initialization (not per request)
        self.graph = build_cost_estimation_graph()
    
    def _create_initial_state(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_id: str,
        quotation_id: Optional[str] = None
    ) -> CostEstimationState:
        """
        Create initial state for graph execution.
        
        Args:
            message: Current user message
            history: Conversation history
            session_id: Session identifier
            quotation_id: Optional quotation identifier
            
        Returns:
            Initial CostEstimationState
        """
        # Convert history to LangChain messages
        langchain_messages: List[BaseMessage] = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and content:
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant" and content:
                langchain_messages.append(AIMessage(content=content))
        
        # Add current message
        langchain_messages.append(HumanMessage(content=message))
        
        # Get existing state from memory if available
        session_state = self.memory_manager.get_session_state(session_id)
        existing_requirements = self.memory_manager.get_extracted_data(session_id) or {}

        # Create initial state
        initial_state: CostEstimationState = {
            "messages": langchain_messages,
            "current_agent": "supervisor",
            "requirements": existing_requirements.get("requirements") or {},
            "requirements_complete": existing_requirements.get("requirements_complete", False),
            "materials": existing_requirements.get("materials", []),
            "labor_rates": existing_requirements.get("labor_rates", []),
            "qdrant_knowledge": existing_requirements.get("qdrant_knowledge", []),
            "postgres_data_complete": existing_requirements.get("postgres_data_complete", False),
            "qdrant_knowledge_complete": existing_requirements.get("qdrant_knowledge_complete", False),
            "material_selections": existing_requirements.get("material_selections"),
            "material_selection_complete": existing_requirements.get("material_selection_complete", False),
            "quotation": existing_requirements.get("quotation"),
            "calculation_complete": existing_requirements.get("calculation_complete", False),
            "turn_count": existing_requirements.get("turn_count", 0),
            "agent_attempts": existing_requirements.get("agent_attempts", {}),
            "started_at": existing_requirements.get("started_at") or datetime.utcnow().isoformat(),
            "user_confirmed_proceed": existing_requirements.get("user_confirmed_proceed", False),
            "workflow_status": existing_requirements.get("workflow_status", WorkflowStatus.GATHERING_REQUIREMENTS),
            "errors": existing_requirements.get("errors", []),
        }
        
        return initial_state
    
    def _convert_state_to_response(
        self,
        state: CostEstimationState,
        session_id: str,
        quotation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert internal graph state to API response format.
        
        Args:
            state: Final graph state
            session_id: Session identifier
            quotation_id: Optional quotation identifier
            
        Returns:
            Response dict for API
        """
        # Extract response text from messages
        messages = state.get("messages", [])
        response_text = ""
        
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_text = msg.content
                break
        
        # If no response text, generate a default based on workflow status
        if not response_text:
            workflow_status = state.get("workflow_status", "")
            if workflow_status == WorkflowStatus.GATHERING_REQUIREMENTS:
                response_text = "I'm gathering information about your project. Could you please provide more details?"
            elif workflow_status == WorkflowStatus.RETRIEVING_DATA:
                response_text = "I'm searching for materials and pricing information..."
            elif workflow_status == WorkflowStatus.CALCULATING:
                response_text = "I'm calculating the cost estimate for your project..."
            elif workflow_status == WorkflowStatus.COMPLETE:
                response_text = "Your cost estimation is complete!"
            elif workflow_status == WorkflowStatus.ERROR:
                errors = state.get("errors", [])
                response_text = f"I encountered an error: {errors[-1] if errors else 'Unknown error'}"
            else:
                response_text = "Processing your request..."
        
        # Build history from messages
        history: List[Dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content or ""})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content or ""})
        
        # Extract quotation_id from quotation if available
        extracted_quotation_id = quotation_id
        quotation = state.get("quotation")
        if quotation and isinstance(quotation, dict):
            extracted_quotation_id = quotation.get("quotation_id", quotation_id)
        
        return {
            "response": response_text,
            "quotation_id": extracted_quotation_id,
            "history": history,
            "workflow_status": state.get("workflow_status"),
            "requirements_complete": state.get("requirements_complete", False),
            "quotation": quotation,
        }
    
    async def process_message(
        self,
        message: str,
        history: List[Dict[str, str]],
        session_id: str,
        quotation_id: Optional[str] = None,
        files: List[Dict[str, Any]] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Process a message and return response.
        
        Args:
            message: User message text
            history: Conversation history
            session_id: Session identifier
            quotation_id: Optional quotation identifier
            files: Optional list of uploaded files (not yet implemented)
            db: Database session
            
        Returns:
            Dictionary with response, quotation_id, history, and workflow status
        """
        # Initialize session if needed
        session_state = self.memory_manager.get_session_state(session_id)
        if not session_state:
            self.memory_manager.initialize_session(session_id)
        
        # Create initial state
        initial_state = self._create_initial_state(message, history, session_id, quotation_id)
        
        # Invoke graph with checkpoint (use session_id as thread_id)
        # Note: LangGraph will merge checkpointed state with initial_state
        # The messages in initial_state should override checkpointed messages
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }
        
        try:
            logger.info(f"Invoking graph with initial_state: messages={len(initial_state.get('messages', []))}, requirements_complete={initial_state.get('requirements_complete', False)}")
            # Log initial messages
            msg_info = []
            for m in initial_state.get('messages', []):
                msg_type = type(m).__name__
                msg_content = m.content[:50] if hasattr(m, 'content') and m.content else 'no content'
                msg_info.append(f"{msg_type}: {msg_content}")
            logger.info(f"Initial state messages: {msg_info}")
            
            # Execute graph step by step to see what's happening
            result = await self.graph.ainvoke(initial_state, config)
            
            logger.info(f"Graph execution completed. Final state: workflow_status={result.get('workflow_status')}, messages={len(result.get('messages', []))}, requirements_complete={result.get('requirements_complete', False)}")
            # Log final messages
            final_msg_info = []
            for m in result.get('messages', []):
                msg_type = type(m).__name__
                msg_content = m.content[:50] if hasattr(m, 'content') and m.content else 'no content'
                final_msg_info.append(f"{msg_type}: {msg_content}")
            logger.info(f"Final state messages: {final_msg_info}")
            
            # Convert state to response
            response = self._convert_state_to_response(result, session_id, quotation_id)
            logger.info(f"Converted response: response_text length={len(response.get('response', ''))}, workflow_status={response.get('workflow_status')}")
            
            # Save state to memory for next iteration
            self.memory_manager.save_extracted_data(session_id, {
                "requirements": result.get("requirements", {}),
                "requirements_complete": result.get("requirements_complete", False),
                "materials": result.get("materials", []),
                "labor_rates": result.get("labor_rates", []),
                "qdrant_knowledge": result.get("qdrant_knowledge", []),
                "postgres_data_complete": result.get("postgres_data_complete", False),
                "qdrant_knowledge_complete": result.get("qdrant_knowledge_complete", False),
                "material_selections": result.get("material_selections"),
                "material_selection_complete": result.get("material_selection_complete", False),
                "quotation": result.get("quotation"),
                "calculation_complete": result.get("calculation_complete", False),
                "turn_count": result.get("turn_count", 0),
                "agent_attempts": result.get("agent_attempts", {}),
                "started_at": result.get("started_at"),
                "user_confirmed_proceed": result.get("user_confirmed_proceed", False),
                "workflow_status": result.get("workflow_status"),
                "errors": result.get("errors", []),
            })
            
            # Save conversation history
            self.memory_manager.save_conversation_history(session_id, response["history"])
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            # Return error response
            error_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"I encountered an error: {str(e)}"}
            ]
            return {
                "response": f"I encountered an error processing your message: {str(e)}",
                "quotation_id": quotation_id,
                "history": error_history,
                "workflow_status": WorkflowStatus.ERROR,
                "requirements_complete": False,
                "quotation": None,
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
        """
        Process message with streaming response.
        
        For now, this processes normally and streams chunks.
        In the future, can use LLM streaming for real-time responses.
        
        Args:
            message: User message text
            history: Conversation history
            session_id: Session identifier
            quotation_id: Optional quotation identifier
            files: Optional list of uploaded files
            db: Database session
            
        Yields:
            Dictionary chunks with type and content
        """
        # Process message normally
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
        
        # Send final message with workflow status
        yield {
            "type": "done",
            "quotation_id": result["quotation_id"],
            "workflow_status": result.get("workflow_status"),
        }

