"""
Shared LangGraph checkpointer singleton.

Both ConversationalAgent (chat endpoint) and LangGraphOrchestrator (background
processing) must use the same MemorySaver instance so they share conversation
state for the same thread_id (session_id / quotation_id).

Replace MemorySaver with AsyncSqliteSaver or RedisSaver for multi-instance
deployments (tracked as known debt in the constitution).
"""
from langgraph.checkpoint.memory import MemorySaver

_checkpointer = MemorySaver()


def get_checkpointer() -> MemorySaver:
    """Return the shared in-process checkpointer instance."""
    return _checkpointer
