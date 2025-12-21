from typing import List, TypedDict, Literal, Annotated
import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from app.agents.llm_client import get_llm_client
from app.agent.tools import search_materials, search_labor_rates, search_standards, create_quotation

# Define the tools list
TOOLS = [search_materials, search_labor_rates, search_standards, create_quotation]

class AgentState(TypedDict):
    """The state of the agent includes messages and iteration tracking."""
    messages: Annotated[List[BaseMessage], add_messages]
    iteration_count: int  # Track number of agent-tool cycles

def get_runnable_agent():
    """
    Constructs and compiles the LangGraph agent.
    """
    # 1. Get the LLM (ensure it supports tool calling, e.g. OpenAI/Anthropic)
    llm_client = get_llm_client()
    llm = llm_client.client # This gives us the LangChain ChatModel object (OpenAI/Anthropic)
    
    # 2. Bind tools to the LLM
    llm_with_tools = llm.bind_tools(TOOLS)

    # 3. Define the System Prompt - Simplified for Qwen 3
    system_message = SystemMessage(content="""You are a construction cost estimator.

When user asks for apartment finishing:
1. Call search_materials("Cement") 
2. Call search_materials("Porcelain")
3. Call search_materials("Paint")
4. STOP and summarize the prices you found

Do NOT call create_quotation.
After finding 3 materials, respond with a summary like:
"Based on your 200m2 apartment, here are the materials:
- Cement: X EGP per bag (need 50 bags)
- Porcelain: Y EGP per m2 (need 220 m2)  
- Paint: Z EGP per liter (need 100 liters)"

Call tools ONLY 3 times, then STOP.""")


    # 4. Define Nodes
    def call_model(state: AgentState):
        messages = state['messages']
        
        # Ensure system prompt is first if not present
        if not isinstance(messages[0], SystemMessage):
            messages = [system_message] + messages
        
        response = llm_with_tools.invoke(messages)
        
        # FIX: Ensure AIMessage has content if it has tool calls.
        # Some providers/adapters drop empty-content messages, breaking the sequence (System -> Tool error).
        if hasattr(response, 'tool_calls') and response.tool_calls and not response.content:
            response.content = "Processing tool request..."
            
        return {"messages": [response]}

    tool_node = ToolNode(TOOLS)
    
    # Wrap tool node to increment counter AFTER tools execute
    def tool_node_with_counter(state: AgentState):
        result = tool_node.invoke(state)
        iteration = state.get('iteration_count', 0)
        # Ensure result is a mutable dictionary to add iteration_count
        if not isinstance(result, dict):
            result = {"messages": result} # Assuming tool_node returns messages directly if not a dict
        result['iteration_count'] = iteration + 1
        return result

    # 5. Define Conditional Logic with proper iteration tracking
    def should_continue(state: AgentState) -> Literal["tools", END]:
        messages = state['messages']
        last_message = messages[-1]
        iteration = state.get('iteration_count', 0)
        
        # Hard stop after 5 tool executions to prevent infinite loops
        if iteration >= 5:
            return END
            
        # If the LLM decided to call a tool, route to "tools"
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        # Otherwise, stop
        return END

    # 6. Build Graph
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node_with_counter)  # Use wrapped version

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
    )

    workflow.add_edge("tools", "agent") # Loop back to agent after tools

    # 7. Compile
    app = workflow.compile()
    return app

# Singleton accessor
_graph_app = None
def get_agent_graph():
    global _graph_app
    if _graph_app is None:
        _graph_app = get_runnable_agent()
    return _graph_app
# Legacy ReActAgent removed. Use get_agent_graph() for LangGraph agent.
