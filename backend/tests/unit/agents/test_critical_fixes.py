"""
Unit tests for the critical agent flow fixes.

C-5: ConversationalAgent is a singleton on app.state
C-2: response_node returns only the new AIMessage (delta), not the full list
C-1: process_message_stream seeds initial_state with only the new HumanMessage
C-3: collect_project_data forwards additional_info to DataCollectorAgent.execute()

Note: the former C-4 (SupervisorAgent.get_system_prompt async session) was dropped
when the LLM ReAct supervisor was replaced by the deterministic workflow_node. The
phase/sufficiency regressions it guarded are now covered against workflow_node below.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_quotation():
    q = MagicMock()
    q.id = "quot-test-123"
    q.project_description = "Apartment renovation"
    q.location = "Cairo"
    q.project_type = None
    q.zip_code = None
    q.timeline = None
    q.status = "pending"
    return q


@pytest.fixture
def mock_quotation_data():
    qd = MagicMock()
    qd.quotation_id = "quot-test-123"
    qd.extracted_data = {
        "size_sqm": None,
        "project_type": "residential",
        "current_finish_level": None,
        "target_finish_level": None,
        "rooms": [],
        "confidence_score": 0.5,
    }
    qd.total_cost = None
    qd.cost_breakdown = None
    return qd


@pytest.fixture
def mock_async_db():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.fixture
def sample_state_5_messages():
    """A QuotationAgentState-like dict with 5 messages (2 turns + 1 new)."""
    return {
        "messages": [
            HumanMessage(content="I want a quotation"),
            AIMessage(content="Sure, what size?"),
            HumanMessage(content="150 sqm"),
            AIMessage(content="Got it, any finish level?"),
            HumanMessage(content="Fully finished please"),
        ],
        "quotation_id": "quot-test-123",
        "session_id": "session-abc",
        "current_phase": "GATHERING",
        "iteration_count": 2,
        "detected_language": "en",
        "status": "processing",
        "finish_levels": {},
        "processing_context": {},
        "results": {},
    }


# ── C-5: ConversationalAgent Singleton ──────────────────────────────────────

def test_agent_singleton_in_app_state():
    """app.state.agent must be a ConversationalAgent set during lifespan."""
    from app.agents.conversational_agent import ConversationalAgent

    app_state = MagicMock()

    with patch("app.agents.conversational_agent.build_supervisor_graph", return_value=MagicMock()):
        agent = ConversationalAgent()
        app_state.agent = agent

    assert isinstance(app_state.agent, ConversationalAgent)


# ── Workflow phase logic (ported from the deleted supervisor regressions) ────

def test_compute_phase_zero_cost_reaches_complete():
    """
    Regression: a completed quotation whose total_cost is 0.0 (empty pricing DB)
    must still resolve to COMPLETE. `if q_data.total_cost:` was False for 0.0 and
    caused the old supervisor to loop; _compute_phase uses `is not None`.
    """
    from app.graph.workflow_node import _compute_phase

    q = MagicMock()
    q.total_cost = 0.0
    q.cost_breakdown = {"materials": []}
    q.extracted_data = {"size_sqm": 150}
    assert _compute_phase(q) == "COMPLETE"


def test_compute_phase_progression():
    """_compute_phase derives the phase purely from DB state, not the LLM."""
    from app.graph.workflow_node import _compute_phase

    assert _compute_phase(None) == "GATHERING"

    gathering = MagicMock(total_cost=None, cost_breakdown=None, extracted_data=None)
    assert _compute_phase(gathering) == "GATHERING"

    analyzing = MagicMock(total_cost=None, cost_breakdown=None, extracted_data={"size_sqm": 150})
    assert _compute_phase(analyzing) == "ANALYZING"

    quoting = MagicMock(total_cost=None, cost_breakdown={"materials": []}, extracted_data={"size_sqm": 150})
    assert _compute_phase(quoting) == "QUOTING"


def test_has_sufficient_data_gating():
    """calculate_costs must only run once all four required fields are present."""
    from app.graph.workflow_node import _has_sufficient_data

    complete = {
        "size_sqm": 150,
        "project_type": "residential",
        "current_finish_level": "core_shell",
        "target_finish_level": "fully_finished",
    }
    assert _has_sufficient_data(complete) is True

    # Missing target_finish_level
    assert _has_sufficient_data({**complete, "target_finish_level": None}) is False
    # project_type sentinel "Unknown" is treated as missing
    assert _has_sufficient_data({**complete, "project_type": "Unknown"}) is False
    assert _has_sufficient_data({}) is False

    # Regression: a truthy 'unknown'-style sentinel on a finish level must NOT
    # satisfy the gate (this is what caused a premature quote before the target
    # finish was ever asked — "Determining requirements for: unknown -> unknown").
    for sentinel in ("unknown", "Unknown", "", "null", "none", "not specified", "N/A"):
        assert _has_sufficient_data({**complete, "current_finish_level": sentinel}) is False
        assert _has_sufficient_data({**complete, "target_finish_level": sentinel}) is False


def test_allowance_split_from_llm_boq_scope():
    """The allowance is split from the LLM-synthesised BOQ scope (any-language,
    no hardcoded keywords). We only normalise its relative weights to the anchored
    allowance, so line totals sum exactly to the allowance."""
    from app.agents.cost_calculator import CostCalculatorAgent
    agent = CostCalculatorAgent.__new__(CostCalculatorAgent)  # skip __init__ (no DB/LLM)

    remainder = 1_000_000.0
    extracted = {
        "size_sqm": 400.0,
        "engineering": {"complete": True, "boq_scope": {
            "summary_en": "Scope: porcelain flooring, central A/C, fire-fighting",
            "summary_ar": "نطاق العمل: أرضيات بورسلين، تكييف مركزي، إطفاء حريق",
            "line_items": [
                {"name_en": "Flooring (porcelain)", "name_ar": "أرضيات بورسلين", "weight": 2.0},
                {"name_en": "HVAC / central A/C", "name_ar": "تكييف مركزي", "weight": 1.0},
                {"name_en": "Fire-fighting & alarm", "name_ar": "إطفاء وإنذار", "weight": 1.0},
            ],
        }},
    }
    lines, scope = agent._build_allowance_lines(remainder, 400.0, extracted, "Luxury Finishing - Commercial Buildings")

    assert round(sum(l["total"] for l in lines), 2) == round(remainder, 2)
    assert len(lines) == 3
    names = " ".join(l["name"] for l in lines)
    assert "porcelain" in names.lower() and "Fire-fighting" in names
    # Weight 2:1:1 → flooring gets half the allowance.
    flooring = next(l for l in lines if "porcelain" in l["name"].lower())
    assert abs(flooring["total"] - 500_000.0) < 1.0
    assert scope and "porcelain" in scope["en"]

    # No boq_scope → generic fallback split, no scope summary, still sums exactly.
    base_lines, base_scope = agent._build_allowance_lines(1000.0, 100.0, {"size_sqm": 100.0}, "Standard Finishing - Residential Apartments")
    assert base_scope is None
    assert round(sum(l["total"] for l in base_lines), 2) == 1000.0


def test_topdown_anchor_mapping():
    """Finish level → market tier and project type → building group mapping that
    drives the top-down anchor row name '<Tier> Finishing - <Group>'."""
    from app.agents.cost_calculator import CostCalculatorAgent

    tier = CostCalculatorAgent._ANCHOR_TIER_BY_FINISH
    assert tier["turnkey"] == "Luxury"
    assert tier["fully_finished"] == "Standard"
    assert tier["semi_finished"] == "Economic"
    assert tier.get("super_lux") == "Super Deluxe"

    grp = CostCalculatorAgent._anchor_group_for_project
    assert grp("commercial") == "Commercial Buildings"
    assert grp("office") == "Commercial Buildings"
    assert grp("residential") == "Residential Apartments"
    assert grp("residential villa") == "Residential Villas"
    # The composed anchor name must match the seeded rows exactly.
    target, ptype = "turnkey", "commercial"
    name = f"{tier.get(target,'Standard')} Finishing - {grp(ptype)}"
    assert name == "Luxury Finishing - Commercial Buildings"


def test_franco_arabic_finish_extraction():
    """
    Franco-Arabic (Arabizi) finish terms must be recovered by the pattern fallback
    when the local model misses them — otherwise the bot re-asks an already-answered
    question (e.g. user typed "3ala el ma7ara" / "tashteeb kamel fa5er").
    """
    from app.agents.data_collector import DataCollectorAgent

    fill = DataCollectorAgent._fill_missing_with_patterns

    out = fill(None, {"current_finish_level": None}, "hyper market 400 meter 3ala el ma7ara")
    assert out["current_finish_level"] == "on_plaster"

    out = fill(None, {"target_finish_level": None}, "3ayez tashteeb kamel fa5er")
    assert out["target_finish_level"] == "turnkey"  # luxury wins over 'kamel'

    out = fill(None, {"current_finish_level": None}, "el wahda 3al tob el a7mar")
    assert out["current_finish_level"] == "core_shell"


def test_short_confirmation_skips_collection():
    """
    A bare confirmation/negation past GATHERING must skip collect_project_data so a
    single word like 'لا' or 'تمام' can't wipe previously extracted fields.
    """
    from app.graph.workflow_node import _is_short_confirmation

    assert _is_short_confirmation("تمام", "ANALYZING") is True
    assert _is_short_confirmation("ok", "QUOTING") is True
    # In GATHERING we always collect — we still need the initial data
    assert _is_short_confirmation("تمام", "GATHERING") is False
    # Real construction info must NOT be skipped
    assert _is_short_confirmation("شقة 150 متر", "ANALYZING") is False


# ── C-2: response_node Returns Delta Only ───────────────────────────────────

@pytest.mark.asyncio
async def test_response_node_returns_delta(sample_state_5_messages):
    """response_node must return only the new AIMessage, not the full list."""
    from app.graph.builder import response_node

    new_response = AIMessage(content="Here is your cost estimate.")

    with patch("app.agents.llm_client.get_response_llm_client") as mock_get_resp, \
         patch("app.agents.llm_client.get_llm_client") as mock_get_tool, \
         patch("app.services.response_cache.get_response_cache", return_value=AsyncMock()):

        resp_client = MagicMock()
        tool_client = MagicMock()
        resp_client.client.ainvoke = AsyncMock(return_value=new_response)
        mock_get_resp.return_value = resp_client
        mock_get_tool.return_value = tool_client  # different objects → will not early-exit

        result = await response_node(sample_state_5_messages)

    assert "messages" in result
    msgs = result["messages"]
    assert len(msgs) == 1, f"Expected 1 message delta, got {len(msgs)}"
    assert msgs[0].content == "Here is your cost estimate."


@pytest.mark.asyncio
async def test_response_node_early_exit_returns_empty(sample_state_5_messages):
    """When same LLM and valid response already in state, return empty delta."""
    from app.graph.builder import response_node

    # Make last message a valid AI response (no tool_calls)
    sample_state_5_messages["messages"][-1] = AIMessage(content="Valid response already here.")

    with patch("app.agents.llm_client.get_response_llm_client") as mock_get_resp, \
         patch("app.agents.llm_client.get_llm_client") as mock_get_tool:

        # Same object → early-exit path triggers
        shared_client = MagicMock()
        mock_get_resp.return_value = shared_client
        mock_get_tool.return_value = shared_client

        result = await response_node(sample_state_5_messages)

    assert result["messages"] == [], \
        "Early-exit path must return empty list, not full messages"


@pytest.mark.asyncio
async def test_response_node_fallback_returns_single_message(sample_state_5_messages):
    """On LLM error, fallback must be a single AIMessage in Egyptian Arabic."""
    from app.graph.builder import response_node

    with patch("app.agents.llm_client.get_response_llm_client") as mock_get_resp, \
         patch("app.agents.llm_client.get_llm_client") as mock_get_tool, \
         patch("app.services.response_cache.get_response_cache", return_value=AsyncMock()):

        resp_client = MagicMock()
        tool_client = MagicMock()
        resp_client.client.ainvoke = AsyncMock(side_effect=Exception("LLM timeout"))
        mock_get_resp.return_value = resp_client
        mock_get_tool.return_value = tool_client

        result = await response_node(sample_state_5_messages)

    msgs = result["messages"]
    assert len(msgs) == 1, f"Fallback must return exactly 1 message, got {len(msgs)}"
    assert isinstance(msgs[0], AIMessage)
    # Must be Egyptian Arabic, not English
    assert "I'm here" not in msgs[0].content, \
        "Fallback must be Egyptian Arabic, not English"


# ── C-1: No Message History Duplication ─────────────────────────────────────

@pytest.mark.asyncio
async def test_initial_state_contains_only_new_message():
    """process_message_stream must seed initial_state with only the new HumanMessage."""
    from app.agents.conversational_agent import ConversationalAgent

    captured_states = []

    async def mock_astream(initial_state, config, stream_mode=None):
        captured_states.append(initial_state)
        return
        yield  # make it an async generator

    with patch("app.agents.conversational_agent.build_supervisor_graph", return_value=MagicMock()), \
         patch("app.core.database.SessionLocal", return_value=MagicMock()), \
         patch("app.services.session_service.SessionService") as mock_ss:

        mock_session = MagicMock()
        mock_session.quotation_id = None
        mock_ss.get_or_create_session.return_value = mock_session

        agent = ConversationalAgent.__new__(ConversationalAgent)
        agent.graph = MagicMock()
        agent.graph.astream = mock_astream

        history = [
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": "old reply"},
        ]

        chunks = []
        async for chunk in agent.process_message_stream(
            message="new message",
            history=history,
            session_id="session-test",
        ):
            chunks.append(chunk)

    assert len(captured_states) == 1
    initial_messages = captured_states[0]["messages"]
    assert len(initial_messages) == 1, \
        f"initial_state.messages must have exactly 1 message (new HumanMessage), got {len(initial_messages)}"
    assert isinstance(initial_messages[0], HumanMessage)
    assert initial_messages[0].content == "new message"


# ── C-3: Forward additional_info to DataCollectorAgent ──────────────────────

@pytest.mark.asyncio
async def test_collect_project_data_forwards_additional_info(mock_quotation):
    """collect_project_data tool must pass additional_info in context to agent.execute()."""
    from app.agents.tools_wrapper import collect_project_data

    captured_contexts = []

    async def mock_execute(quotation, context):
        captured_contexts.append(context)
        return {
            "extracted_data": {"size_sqm": 150, "project_type": "residential",
                               "confidence_score": 0.8, "rooms": [], "missing_information": [],
                               "follow_up_questions": [], "current_finish_level": None,
                               "target_finish_level": None},
            "confidence_score": 0.8,
            "needs_followup": False,
            "follow_up_questions": [],
        }

    with patch("app.agents.tools_wrapper.get_or_create_async_db_session") as mock_db, \
         patch("app.agents.tools_wrapper.db_session_context") as mock_ctx, \
         patch("app.agents.tools_wrapper.resolve_quotation_id",
               return_value=(mock_quotation, False)), \
         patch("app.agents.tools_wrapper.DataCollectorAgent") as MockAgent, \
         patch("app.agents.tools_wrapper.select", return_value=MagicMock()):

        db = AsyncMock()
        qd_result = MagicMock()
        qd_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=qd_result)
        mock_db.return_value = db
        mock_ctx.get.return_value = db  # session in context

        mock_agent_instance = MagicMock()
        mock_agent_instance.execute = mock_execute
        MockAgent.return_value = mock_agent_instance

        await collect_project_data.ainvoke(
            {"quotation_id": "quot-test-123", "additional_info": "150 sqm apartment"}
        )

    assert len(captured_contexts) == 1
    assert captured_contexts[0].get("additional_info") == "150 sqm apartment", \
        "additional_info must be forwarded in context dict to DataCollectorAgent.execute()"


@pytest.mark.asyncio
async def test_data_collector_uses_additional_info_in_prompt(mock_quotation):
    """DataCollectorAgent must incorporate additional_info into the LLM extraction prompt."""
    from app.agents.data_collector import DataCollectorAgent
    from app.models.project_data import ProjectData

    captured_prompts = []

    async def mock_invoke_structured(prompt, schema, system_prompt=None):
        captured_prompts.append(prompt)
        return ProjectData(
            project_type="residential",
            size_sqm=150,
            confidence_score=0.8,
            rooms=[],
            key_requirements=[],
            missing_information=[],
            follow_up_questions=[],
        )

    with patch("app.agents.data_collector.get_llm_client") as mock_llm:
        llm = MagicMock()
        llm.invoke_structured = mock_invoke_structured
        mock_llm.return_value = llm

        agent = DataCollectorAgent()
        await agent.execute(mock_quotation, context={"additional_info": "3 bedrooms"})

    assert len(captured_prompts) == 1
    assert "3 bedrooms" in captured_prompts[0], \
        "additional_info must appear in the extraction prompt sent to the LLM"


@pytest.mark.asyncio
async def test_data_collector_handles_empty_additional_info(mock_quotation):
    """execute() with no additional_info must not crash and use project_description only."""
    from app.agents.data_collector import DataCollectorAgent
    from app.models.project_data import ProjectData

    async def mock_invoke_structured(prompt, schema, system_prompt=None):
        return ProjectData(
            project_type="residential",
            size_sqm=None,
            confidence_score=0.5,
            rooms=[],
            key_requirements=[],
            missing_information=[],
            follow_up_questions=[],
        )

    with patch("app.agents.data_collector.get_llm_client") as mock_llm:
        llm = MagicMock()
        llm.invoke_structured = mock_invoke_structured
        mock_llm.return_value = llm

        agent = DataCollectorAgent()
        result = await agent.execute(mock_quotation, context={})

    assert "extracted_data" in result
    assert result["extracted_data"]["project_type"] == "residential"
