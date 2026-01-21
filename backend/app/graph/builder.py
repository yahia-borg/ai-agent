"""
Shared graph builder for Supervisor ReAct architecture.
Eliminates duplication between ConversationalAgent and LangGraphOrchestrator.
"""
from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage
import logging

from app.agents.state import QuotationAgentState
from app.agents.supervisor import SupervisorAgent, SUPERVISOR_TOOLS
from app.core.config import settings

logger = logging.getLogger(__name__)


def should_continue(state: QuotationAgentState, max_iterations: Optional[int] = None) -> Literal["continue", "end", "tools"]:
    """
    Determine next step based on the last message.
    
    Args:
        state: Current agent state
        max_iterations: Maximum iterations before force stop (defaults to config)
    
    Returns:
        "continue" or "tools" if should continue, "end" if should stop
    """
    max_iter = max_iterations or getattr(settings, 'MAX_ITERATIONS', 15)
    
    messages = state.get("messages", [])
    if not messages:
        return "end"
        
    last_message = messages[-1]
    iteration = state.get("iteration_count", 0)
    
    # Safety Valve: Hard stop after max iterations
    if iteration >= max_iter:
        quotation_id = state.get("quotation_id", "unknown")
        logger.warning(f"Quotation {quotation_id} hit max iterations ({max_iter}). Force stopping.")
        return "end"
        
    # Check if LLM made tool calls
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "continue"  # Will map to "tools" in conditional edges
    
    return "end"


async def supervisor_node(
    state: QuotationAgentState,
    supervisor: SupervisorAgent
) -> Dict[str, Any]:
    """
    Run the Supervisor Agent (LLM).
    
    Args:
        state: Current agent state
        supervisor: Supervisor agent instance
    
    Returns:
        Updated state with new messages and incremented iteration count
    """
    from app.core.structured_logging import log_tool_selection
    
    # Increment iteration count to prevent infinite loops
    current_iteration = state.get("iteration_count", 0) + 1
    quotation_id = state.get("quotation_id", "unknown")
    session_id = state.get("session_id")
    phase = state.get("current_phase", "UNKNOWN")
    
    # Call the supervisor agent
    result = await supervisor.invoke(state)
    
    # Log tool selection if LLM made tool calls
    messages = result.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get("name", "unknown")
                # Extract reasoning from message content if available
                reasoning = last_message.content if hasattr(last_message, 'content') and last_message.content else "Tool call from supervisor"
                log_tool_selection(
                    quotation_id=quotation_id,
                    tool_name=tool_name,
                    reasoning=reasoning[:200],  # Truncate for log size
                    phase=phase,
                    session_id=session_id,
                    iteration=current_iteration
                )
    
    return {
        "messages": result["messages"],
        "iteration_count": current_iteration
    }


def build_supervisor_graph(
    checkpointer: BaseCheckpointSaver,
    supervisor: Optional[SupervisorAgent] = None,
    max_iterations: Optional[int] = None,
    use_start_edge: bool = True
):
    """
    Build the shared supervisor ReAct graph.
    
    Args:
        checkpointer: Checkpoint saver for state persistence
        supervisor: Supervisor agent instance (creates new if not provided)
        max_iterations: Maximum iterations before force stop
        use_start_edge: If True, uses START edge (LangGraphOrchestrator style),
                       If False, uses set_entry_point (ConversationalAgent style)
    
    Returns:
        Compiled graph ready for execution
    """
    if supervisor is None:
        supervisor = SupervisorAgent()
    
    builder = StateGraph(QuotationAgentState)
    
    # Create supervisor node function bound to this supervisor instance
    async def call_supervisor(state: QuotationAgentState):
        return await supervisor_node(state, supervisor)
    
    # Create should_continue function with max_iterations bound
    def should_continue_bound(state: QuotationAgentState):
        return should_continue(state, max_iterations)
    
    # Define Nodes
    builder.add_node("supervisor", call_supervisor)
    builder.add_node("tools", ToolNode(SUPERVISOR_TOOLS))
    
    # Define Entry Point
    if use_start_edge:
        builder.add_edge(START, "supervisor")
    else:
        builder.set_entry_point("supervisor")
    
    # Conditional Edge: Check if supervisor wants to call tools or end
    # Map "continue" -> "tools" node, "end" -> END
    builder.add_conditional_edges(
        "supervisor",
        should_continue_bound,
        {
            "continue": "tools",
            "end": END
        }
    )
    
    # Edge: Tool output always goes back to supervisor
    builder.add_edge("tools", "supervisor")
    
    return builder.compile(checkpointer=checkpointer)
