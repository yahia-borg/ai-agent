"""
Unit tests for the HIGH agent flow fixes.

H-4: Intent classifier uses a module-level LLMClient singleton (not per-message)
H-5: ConversationalAgent and LangGraphOrchestrator share one MemorySaver instance

Note: the former H-1 (ToolNode handle_tool_errors) was dropped when the LLM
supervisor + ToolNode were replaced by the deterministic workflow_node, which
invokes tools directly. Tool error handling now lives in the tools themselves.
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage


# ── H-4: Intent classifier singleton ────────────────────────────────────────

def test_classifier_singleton_reused():
    """
    _get_classifier() must return the same object on every call — LLMClient is
    constructed once, not once per classify_intent invocation.
    """
    # Reset module state so we start from None
    import app.graph.intent_classifier as ic_module
    ic_module._classifier = None  # reset for test isolation

    mock_chain = MagicMock()
    mock_client = MagicMock()
    mock_client.client.with_structured_output.return_value = mock_chain

    with patch("app.agents.llm_client.LLMClient", return_value=mock_client), \
         patch("app.core.config.settings") as mock_settings:
        mock_settings.RESPONSE_LLM_BASE_URL = "http://test:8061"
        mock_settings.RESPONSE_LLM_MODEL = "test-model"

        first = ic_module._get_classifier()
        second = ic_module._get_classifier()

    assert first is second, (
        "_get_classifier() must return the same object on every call; "
        "LLMClient should be constructed only once"
    )
    # LLMClient constructor called exactly once
    assert mock_client.client.with_structured_output.call_count == 1, (
        "with_structured_output should be called exactly once during singleton init"
    )

    # Clean up module state
    ic_module._classifier = None


def test_classifier_singleton_not_rebuilt_after_init():
    """
    After the singleton is initialized, calling _get_classifier() again must NOT
    create a new LLMClient.
    """
    import app.graph.intent_classifier as ic_module

    mock_chain = MagicMock()
    mock_client = MagicMock()
    mock_client.client.with_structured_output.return_value = mock_chain

    with patch("app.agents.llm_client.LLMClient", return_value=mock_client) as mock_llm_cls, \
         patch("app.core.config.settings") as mock_settings:
        mock_settings.RESPONSE_LLM_BASE_URL = None
        mock_settings.RESPONSE_LLM_MODEL = None

        ic_module._classifier = None  # ensure clean state
        ic_module._get_classifier()
        ic_module._get_classifier()
        ic_module._get_classifier()

        assert mock_llm_cls.call_count == 1, (
            f"LLMClient constructor called {mock_llm_cls.call_count} times; expected 1"
        )

    ic_module._classifier = None  # clean up


# ── H-5: Shared MemorySaver ──────────────────────────────────────────────────

def test_checkpointer_singleton():
    """
    get_checkpointer() must return the same MemorySaver instance on every call.
    """
    from app.graph.checkpointer import get_checkpointer

    first = get_checkpointer()
    second = get_checkpointer()
    third = get_checkpointer()

    assert first is second is third, (
        "get_checkpointer() must return the same MemorySaver object every time"
    )


def test_both_agents_share_checkpointer():
    """
    ConversationalAgent and LangGraphOrchestrator must both use the shared
    checkpointer from app.graph.checkpointer, not separate MemorySaver instances.
    """
    from app.graph.checkpointer import get_checkpointer, _checkpointer

    captured = {}

    def mock_build_graph(checkpointer, max_iterations=None):
        captured["checkpointer"] = checkpointer
        return MagicMock()

    with patch("app.agents.conversational_agent.build_supervisor_graph", side_effect=mock_build_graph):
        from app.agents.conversational_agent import ConversationalAgent
        agent = ConversationalAgent()

    assert captured["checkpointer"] is _checkpointer, (
        "ConversationalAgent must pass the shared _checkpointer to build_supervisor_graph"
    )

    captured.clear()

    with patch("app.agents.langgraph_orchestrator.build_supervisor_graph", side_effect=mock_build_graph):
        from app.agents.langgraph_orchestrator import LangGraphOrchestrator
        orch = LangGraphOrchestrator()

    assert captured["checkpointer"] is _checkpointer, (
        "LangGraphOrchestrator must pass the shared _checkpointer to build_supervisor_graph"
    )
