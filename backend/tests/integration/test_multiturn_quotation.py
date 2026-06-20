"""Integration test for the multi-turn quotation_id persistence bug.

Reproduces the previously-reported defect: a new quotation was created on every
turn because ``session.quotation_id`` was never persisted/reused, so a multi-turn
conversation never accumulated the 4 required fields and never calculated a cost.

Only the LLM touchpoints are mocked:
  * ``DataCollectorAgent.execute`` -> returns incremental ProjectData per turn
    (simulates the vLLM NLP extraction, which is unreachable from the dev host).
  * ``get_response_llm_client`` -> canned text (the response endpoint is unreachable).

Everything else runs for real against Postgres: intent routing (keyword fast-path),
quotation_id resolution + session linking, DB persistence/merge, and cost calc.
"""
import uuid

import pytest
import pytest_asyncio

from app.agents import data_collector as dc_module
from app.agents import llm_client as llm_module
from app.agents.conversational_agent import ConversationalAgent
from app.core.db_context import get_or_create_async_db_session
from app.models.quotation import QuotationData
from sqlalchemy import select


# ── Fakes ────────────────────────────────────────────────────────────────────

async def _fake_extract(self, quotation, context):
    """Return only the NEW field(s) implied by the latest message.

    Relies on the real merge logic in collect_project_data to accumulate fields
    across turns — which is exactly what the bug broke.
    """
    info = (context or {}).get("additional_info", "").lower()
    extracted = {}
    if "apartment" in info:
        extracted = {"size_sqm": 200, "project_type": "residential"}
    elif "plaster" in info:
        extracted = {"current_finish_level": "on_plaster"}
    elif "turnkey" in info or "luxury" in info:
        extracted = {"target_finish_level": "turnkey"}
    return {
        "extracted_data": extracted,
        "confidence_score": 0.9,
        "needs_followup": False,
        "follow_up_questions": [],
    }


from langchain_core.messages import AIMessage


class _FakeChatClient:
    async def ainvoke(self, messages):
        return AIMessage(content="تمام.")


class _FakeLLMClient:
    def __init__(self):
        self.client = _FakeChatClient()


@pytest.fixture(autouse=True)
def _mock_llms(monkeypatch):
    monkeypatch.setattr(dc_module.DataCollectorAgent, "execute", _fake_extract)
    monkeypatch.setattr(llm_module, "get_response_llm_client", lambda: _FakeLLMClient())


@pytest_asyncio.fixture(autouse=True)
async def _flush_cache():
    """Isolate from Redis: the cache_check node and intent cache are keyed by raw
    message text and persist across runs, which would otherwise serve a stale
    response and skip the workflow entirely."""
    import redis.asyncio as redis
    from app.core.config import settings

    r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield


# ── Test ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiturn_quotation_id_persists_and_accumulates():
    agent = ConversationalAgent()
    session_id = f"session-{uuid.uuid4().hex[:12]}"

    turns = [
        "I want to finish a 200 sqm apartment",
        "it is currently on plaster",
        "I want a luxury turnkey finish",
    ]

    quotation_ids = []
    for msg in turns:
        result = await agent.process_message(
            message=msg,
            history=[],
            session_id=session_id,
        )
        quotation_ids.append(result["quotation_id"])

    # 1. A real quotation was created (not left as the raw session id) ...
    assert all(qid for qid in quotation_ids), f"null quotation_id in {quotation_ids}"
    assert all(not str(qid).startswith("session-") for qid in quotation_ids), quotation_ids

    # 2. ... and the SAME quotation is reused every turn (the core bug).
    assert len(set(quotation_ids)) == 1, (
        f"expected one quotation across turns, got {set(quotation_ids)}"
    )

    final_id = quotation_ids[-1]

    # 3. Fields accumulated across turns into that single quotation.
    db = await get_or_create_async_db_session()
    try:
        res = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == final_id)
        )
        q_data = res.scalar_one_or_none()
    finally:
        await db.close()

    assert q_data is not None, "no QuotationData row persisted"
    extracted = q_data.extracted_data or {}
    assert extracted.get("size_sqm") == 200
    assert extracted.get("project_type") == "residential"
    assert extracted.get("current_finish_level") == "on_plaster"
    assert extracted.get("target_finish_level") == "turnkey"

    # 4. With all 4 fields present, a cost was calculated (0.0 is valid when the
    #    pricing DB is empty — COMPLETE is gated on total_cost IS NOT NULL).
    assert q_data.total_cost is not None, "cost was never calculated despite full data"
