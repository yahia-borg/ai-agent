"""
Graph Builder - Constructs the LangGraph state machine.

Uses Command pattern for routing - no conditional edges needed.
Supervisor handles all routing decisions via Command.goto.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.state.schemas import CostEstimationState
from app.agents.supervisor import supervisor_node
from app.agents.force_complete import force_complete_node
from app.agents.simple_calculation_agent import simple_calculation_agent_node
from app.subgraphs import (
    build_requirements_subgraph,
    build_postgres_data_subgraph,
    build_qdrant_knowledge_subgraph,
    build_materials_subgraph
)
from app.core.langsmith_config import get_langsmith_callbacks
import logging

logger = logging.getLogger(__name__)


def build_cost_estimation_graph():
    """
    Build and compile the cost estimation LangGraph with subgraphs.

    Graph Structure:
    ```
    START → supervisor → [routes via Command]
                       ├→ requirements_subgraph → supervisor (via Command)
                       ├→ postgres_data_subgraph → supervisor (via Command)
                       ├→ qdrant_knowledge_subgraph → supervisor (via Command)
                       ├→ materials_subgraph → supervisor (via Command)
                       ├→ calculation_agent (simple) → supervisor (via Command)
                       ├→ force_complete → [calculation_agent | __end__] (via Command)
                       └→ END
    ```

    Workflow (5 stages):
    1. Requirements gathering (subgraph with internal validation)
    2. Postgres data retrieval (materials + labor rates - CRITICAL)
    3. Qdrant knowledge retrieval (building codes + standards - non-critical)
    4. Material selection (subgraph with conversational flow)
    5. Calculation (direct arithmetic, no LLM)
    6. Complete

    Routing:
    - Main graph uses Command pattern for type-safe routing
    - Subgraphs use conditional edges internally
    - Supervisor routes to subgraphs/agents or END
    - Subgraphs route back to supervisor when complete

    Returns:
        Compiled LangGraph with checkpointer
    """
    logger.info("Building cost estimation graph with subgraphs")

    # === Build Subgraphs ===
    logger.info("Building subgraphs...")
    requirements_graph = build_requirements_subgraph()
    postgres_data_graph = build_postgres_data_subgraph()
    qdrant_knowledge_graph = build_qdrant_knowledge_subgraph()
    materials_graph = build_materials_subgraph()
    logger.info("All subgraphs built successfully")

    # === Create Main Graph ===
    builder = StateGraph(CostEstimationState)

    # === Add Nodes ===
    # Supervisor and control nodes use Command pattern
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("force_complete", force_complete_node)

    # Subgraphs as nodes (use conditional edges internally)
    builder.add_node("requirements_subgraph", requirements_graph)
    builder.add_node("postgres_data_subgraph", postgres_data_graph)
    builder.add_node("qdrant_knowledge_subgraph", qdrant_knowledge_graph)
    builder.add_node("materials_subgraph", materials_graph)

    # Simple calculation agent (no subgraph needed)
    builder.add_node("calculation_agent", simple_calculation_agent_node)

    # === Set Entry Point ===
    builder.add_edge(START, "supervisor")

    # === Subgraph Return Edges ===
    # Subgraphs use END internally, so we need edges back to supervisor
    # When a subgraph completes, control returns to supervisor for next routing decision
    builder.add_edge("requirements_subgraph", "supervisor")
    builder.add_edge("postgres_data_subgraph", "supervisor")
    builder.add_edge("qdrant_knowledge_subgraph", "supervisor")
    builder.add_edge("materials_subgraph", "supervisor")

    # Simple agents and supervisor use Command pattern (no edges needed)
    # - supervisor returns Command[RoutingDest]
    # - calculation_agent returns Command[Literal["supervisor"]]
    # - force_complete returns Command[RoutingDest]

    # === Compile ===
    checkpointer = MemorySaver()

    callbacks = get_langsmith_callbacks(tags=["cost-estimation"])
    if callbacks:
        logger.info("Compiling graph with LangSmith tracing")

    graph = builder.compile(checkpointer=checkpointer)

    logger.info("Graph built successfully")
    return graph


def build_graph_with_postgres(connection_string: str):
    """
    Build graph with PostgreSQL checkpointer for production.

    Args:
        connection_string: PostgreSQL connection string

    Returns:
        Compiled LangGraph with PostgreSQL checkpointer
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    logger.info("Building graph with PostgreSQL checkpointer and subgraphs")

    # Build subgraphs
    requirements_graph = build_requirements_subgraph()
    postgres_data_graph = build_postgres_data_subgraph()
    qdrant_knowledge_graph = build_qdrant_knowledge_subgraph()
    materials_graph = build_materials_subgraph()

    builder = StateGraph(CostEstimationState)

    # Add nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("force_complete", force_complete_node)
    builder.add_node("requirements_subgraph", requirements_graph)
    builder.add_node("postgres_data_subgraph", postgres_data_graph)
    builder.add_node("qdrant_knowledge_subgraph", qdrant_knowledge_graph)
    builder.add_node("materials_subgraph", materials_graph)
    builder.add_node("calculation_agent", simple_calculation_agent_node)

    # Entry point
    builder.add_edge(START, "supervisor")

    # Subgraph return edges (same as memory version)
    builder.add_edge("requirements_subgraph", "supervisor")
    builder.add_edge("postgres_data_subgraph", "supervisor")
    builder.add_edge("qdrant_knowledge_subgraph", "supervisor")
    builder.add_edge("materials_subgraph", "supervisor")

    # Compile with PostgreSQL
    checkpointer = PostgresSaver.from_conn_string(connection_string)
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("Graph built with PostgreSQL and subgraphs")
    return graph