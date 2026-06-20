"""
Optimized graph builder: LLM Intent Router + Redis Cache + Deterministic Workflow.

Graph structure:
  START -> cache_check -> (HIT) -> END
                       -> (MISS) -> intent_classifier (8061)
                                      -> "response" -> response_node (8061) -> END
                                      -> "workflow"  -> workflow_node (deterministic)
                                                           -> response_node (8061) -> END

The workflow_node replaces the old Mistral supervisor LLM for tool routing.
All tool selection is now pure Python logic (DB state + keyword checks).
Mistral (8021) is only called inside DataCollectorAgent for NLP extraction.
"""
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
import logging

from app.agents.state import QuotationAgentState
from app.graph.workflow_node import workflow_node

logger = logging.getLogger(__name__)


# ─── Response Prompt (for 8061) ────────────────────────────────────────

# Two slim prompts (≈150 tokens each). The old ~1000-token prompt drove the
# response model into degeneration loops (the bank-branch meltdown). Per the
# research finding, prompt length is the dominant factor — short + single-purpose.
# Numbers are rendered in Python (utils.cost_formatter), so the LLM never types money.

COLLECTION_PROMPT = """You are a construction finishing advisor for the Egyptian market. You handle everything yourself — never refer the user elsewhere.

Rules:
- Reply ONLY in Egyptian Arabic (اللهجة المصرية), even if the user writes English. Use Western digits 0-9 (never ٠١٢٣).
- Keep it to 2-3 sentences: acknowledge what the user gave, then ask for the NEXT missing item.
- If a "DATA SO FAR" section is shown below, ask only for the first thing under "Missing Info". For a commercial project you may also briefly ask about the layout (number of floors / offices / rooms) — it improves the quote.
- NEVER invent prices, costs, or material rates. NEVER tell the user to consult someone else. No download links.
- Don't ask about timelines, colors, or design style.

Phase: {current_phase}
"""

COST_INTRO_PROMPT = """You are a construction finishing advisor for the Egyptian market.
The full cost quotation table is shown to the user separately, right after your message — you do NOT write it.
Write ONLY a 1-2 sentence intro in Egyptian Arabic (Western digits 0-9) presenting the quotation and inviting the user to request a PDF/Excel export or any adjustment.
Do NOT list, restate, or invent any numbers, materials, or costs. No tables. No reasoning.

Phase: {current_phase}
"""



from app.core.config import settings

# ─── Node: cache_check ─────────────────────────────────────────────────

async def cache_check_node(state: QuotationAgentState) -> Command:
    """
    Redis lookup for cached responses.
    If hit: inject cached response as AIMessage and route to END.
    If miss: route to intent_classifier.
    """
    from app.services.response_cache import get_response_cache

    messages = state.get("messages", [])
    if not messages:
        return Command(goto="intent_classifier")

    last_msg = messages[-1].content.strip() if hasattr(messages[-1], "content") else ""
    if not last_msg:
        return Command(goto="intent_classifier")

    cache = get_response_cache()
    try:
        cached = await cache.get_response(last_msg)
        if cached:
            logger.info(f"Cache HIT for: '{last_msg[:40]}'")
            return Command(
                goto="__end__",
                update={"messages": [AIMessage(content=cached)]},
            )
    except Exception as e:
        logger.warning(f"Cache check failed: {e}")

    return Command(goto="intent_classifier")



# ─── Node: response ────────────────────────────────────────────────────

def _build_clean_messages(messages, system_prompt: str):
    """
    Build a clean user/assistant alternating message list from the full
    LangGraph history. The response LLM (vLLM) strictly requires:
    system, user, assistant, user, assistant, ...
    """
    # Step 1: Extract only user and assistant messages
    pairs = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            continue
        if isinstance(msg, HumanMessage):
            content = msg.content.strip() if msg.content else ""
            if content:
                pairs.append(("user", content))
        elif isinstance(msg, AIMessage):
            content = msg.content.strip() if msg.content else ""
            # Filter out supervisor "DONE" signal — not user-facing
            if content and content.upper() != "DONE":
                pairs.append(("assistant", content))

    # Step 2: Merge consecutive same-role messages
    merged = []
    for role, content in pairs:
        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + "\n" + content)
        else:
            merged.append((role, content))

    # Step 3: Ensure it starts with user
    while merged and merged[0][0] == "assistant":
        merged.pop(0)

    # Step 4: Ensure strict alternation
    alternating = []
    expected_role = "user"
    for role, content in merged:
        if role == expected_role:
            alternating.append((role, content))
            expected_role = "assistant" if role == "user" else "user"
        else:
            if alternating and alternating[-1][0] == role:
                alternating[-1] = (role, alternating[-1][1] + "\n" + content)

    # Step 5: Ensure last message is user
    while alternating and alternating[-1][0] == "assistant":
        alternating.pop()

    # Step 6: Build final message list
    clean = [SystemMessage(content=system_prompt)]
    for role, content in alternating:
        if role == "user":
            clean.append(HumanMessage(content=content))
        else:
            clean.append(AIMessage(content=content))

    if len(clean) == 1:
        clean.append(HumanMessage(content="Please provide a summary of the quotation."))

    logger.debug(
        f"_build_clean_messages: {len(messages)} raw -> {len(clean)} clean "
        f"(roles: {[type(m).__name__[0] for m in clean]})"
    )
    return clean


def _has_usable_response(msgs):
    """True if the last message is a real assistant reply (not DONE / tool calls)."""
    if not msgs:
        return False
    last = msgs[-1]
    if not isinstance(last, AIMessage):
        return False
    if hasattr(last, "tool_calls") and last.tool_calls:
        return False
    content = (last.content or "").strip()
    return bool(content) and content.upper() != "DONE"


def _engineering_questions_text(messages):
    """Return the engineering-questions message if this turn produced one, else None.
    The text is already grounded Egyptian Arabic (generated by engineering_node from
    KB context), so it's presented verbatim — no LLM re-phrasing (which could drift)."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return None
        if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "engineering_questions":
            content = (msg.content or "").strip()
            return content or None
    return None


def _is_cost_presentation_turn(messages) -> bool:
    """
    True when calculate_costs ran on THIS turn — i.e. a 'Cost Calculation Complete'
    ToolMessage sits after the most recent HumanMessage. On a later COMPLETE
    follow-up turn (no new tool) this is False, so we don't re-render the table.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return False
        if isinstance(msg, ToolMessage) and msg.content and "Cost Calculation Complete" in str(msg.content):
            return True
    return False


async def _fetch_cost_data(quotation_id: str):
    """Re-read the persisted cost_breakdown + total_cost so the table is rendered
    in code from the source of truth (never from LLM-typed numbers)."""
    from sqlalchemy import select
    from app.core.db_context import get_or_create_async_db_session, db_session_context
    from app.models.quotation import QuotationData
    from app.utils.session_utils import resolve_quotation_id

    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None
    try:
        quotation, _ = await resolve_quotation_id(quotation_id, db, create_if_missing=False)
        if not quotation:
            return None, None
        res = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation.id)
        )
        q = res.scalar_one_or_none()
        if not q:
            return None, None
        return q.cost_breakdown, q.total_cost
    finally:
        if should_close:
            await db.close()


async def _generate_cost_intro(client, messages, current_phase: str) -> str:
    """One short Arabic intro sentence. Bounded + fixed-fallback so a runaway
    generation can never reach the user (the table is rendered separately)."""
    fixed = "تمام، دي المقايسة التقديرية لمشروعك 👇 تقدر تطلب نسخة PDF أو Excel، أو تعدّل أي تفاصيل."
    try:
        clean = _build_clean_messages(messages, COST_INTRO_PROMPT.format(current_phase=current_phase))
        resp = await client.client.ainvoke(clean)
        text = (resp.content or "").strip()
        if not text or len(text) > 600:
            return fixed
        return text
    except Exception as e:
        logger.warning(f"Cost intro generation failed, using fixed intro: {e}")
        return fixed


async def response_node(state: QuotationAgentState) -> Dict[str, Any]:
    """
    Produce the user-facing reply.

    - Cost-presentation turn: render the BOQ table in Python from the persisted
      cost_breakdown and let the LLM write only a 1-2 sentence intro. The model
      never sees or re-types the figures (kills the degeneration meltdown).
    - Otherwise: a slim conversational/collection turn (no cost numbers in prompt).
    """
    from app.agents.llm_client import get_response_llm_client, get_llm_client
    from app.services.response_cache import get_response_cache
    from app.utils.cost_formatter import render_cost_table_markdown

    response_client = get_response_llm_client()
    tool_client = get_llm_client()

    messages = state.get("messages", [])
    quotation_id = state.get("quotation_id", "unknown")
    current_phase = state.get("current_phase", "GATHERING")
    lang = state.get("detected_language") or "ar"

    # ── Engineering-question turn: present the grounded questions verbatim ────
    eng_text = _engineering_questions_text(messages)
    if eng_text:
        return {"messages": [AIMessage(content=eng_text)]}

    # ── Cost-presentation turn: deterministic table + LLM intro ───────────────
    if _is_cost_presentation_turn(messages):
        cost_breakdown, total_cost = await _fetch_cost_data(quotation_id)
        table = render_cost_table_markdown(cost_breakdown, total_cost, lang)
        intro = await _generate_cost_intro(response_client, messages, current_phase)
        return {"messages": [AIMessage(content=f"{intro}\n\n{table}")]}

    # ── Conversational / collection turn ──────────────────────────────────────
    if response_client is tool_client and _has_usable_response(messages):
        return {"messages": []}

    try:
        # Inject only the data-collection summary (extracted fields / missing
        # info) — never cost figures — so the LLM asks the next question.
        data_summary = None
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.content:
                content = str(msg.content)
                if any(kw in content for kw in ("Data Extracted", "Missing Info", "Follow-up Needed")):
                    data_summary = content[:800]
                    break

        system_prompt = COLLECTION_PROMPT.format(current_phase=current_phase)
        if data_summary:
            system_prompt += "\n\n=== DATA SO FAR ===\n" + data_summary

        clean_messages = _build_clean_messages(messages, system_prompt)
        response = await response_client.client.ainvoke(clean_messages)

        # Cache only short, non-tool chat turns
        if messages:
            user_msg = None
            for m in reversed(messages):
                if isinstance(m, HumanMessage):
                    user_msg = m.content.strip()
                    break
            if user_msg and response.content:
                cache = get_response_cache()
                is_tool_flow = current_phase not in (None, "", "GATHERING")
                if not is_tool_flow and len(user_msg.split()) <= 10:
                    try:
                        await cache.set_response(user_msg, response.content)
                    except Exception:
                        pass

        return {"messages": [response]}

    except Exception as e:
        logger.warning(f"Response LLM failed, generating fallback: {e}")
        fallback = AIMessage(content="أنا هنا أساعدك في مقايسة التشطيب. إيه اللي تحتاجه؟")
        return {"messages": [fallback]}


# ─── Graph Builder ─────────────────────────────────────────────────────

def build_supervisor_graph(
    checkpointer: BaseCheckpointSaver,
    max_iterations: Optional[int] = None,
):
    """
    Build the deterministic workflow graph with intent routing and caching.

    Nodes: cache_check -> intent_classifier -> workflow -> response -> END

    The old Mistral-based supervisor loop is replaced by workflow_node, which
    uses pure Python logic to decide which tools to call.
    """
    builder = StateGraph(QuotationAgentState)

    # ── Bind closures ──

    async def call_cache_check(state: QuotationAgentState):
        return await cache_check_node(state)

    async def call_intent_classifier(state: QuotationAgentState):
        from app.graph.intent_classifier import classify_intent
        return await classify_intent(state)

    async def call_workflow(state: QuotationAgentState):
        return await workflow_node(state)

    async def call_response(state: QuotationAgentState):
        return await response_node(state)

    # ── Add Nodes ──

    builder.add_node("cache_check", call_cache_check)
    builder.add_node("intent_classifier", call_intent_classifier)
    builder.add_node("workflow", call_workflow)
    builder.add_node("response", call_response)

    # ── Edges ──

    builder.add_edge(START, "cache_check")
    # cache_check and intent_classifier use Command(goto=...) for routing
    # workflow always proceeds to response (no loop)
    builder.add_edge("workflow", "response")
    builder.add_edge("response", END)

    return builder.compile(checkpointer=checkpointer)
