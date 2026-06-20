"""
Deterministic workflow node — replaces the Mistral supervisor LLM for tool routing.

The Mistral model (8021) is no longer responsible for deciding which tool to call.
All routing is pure Python logic based on DB state and simple keyword checks.
The Mistral model is still used ONLY inside DataCollectorAgent.invoke_structured
(NLP extraction of ProjectData from Arabic/English text).

Decision tree per turn:
  1. PDF/Excel export keywords   → call export tool, done
  2. Search keywords             → call search tool, done
  3. Phase = COMPLETE            → no tools (response agent handles chat)
  4. Otherwise (quotation flow)  → collect_project_data
                                 → if all required fields present: calculate_costs
                                 → otherwise: return (response agent asks for missing info)
"""
import logging
import uuid
from typing import Any, Dict

from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select

from app.agents.state import QuotationAgentState
from app.agents.tools_wrapper import collect_project_data, calculate_costs
from app.agents.tools import (
    search_materials,
    search_labor_rates,
    search_standards,
    export_quotation_pdf,
    export_quotation_excel,
)
from app.core.db_context import get_or_create_async_db_session, db_session_context
from app.models.quotation import QuotationData
from app.utils.session_utils import resolve_quotation_id
from app.graph.engineering_node import run_engineering_step, _has_pending_round

logger = logging.getLogger(__name__)


# ── Keyword sets for intent detection ────────────────────────────────────

# Short confirmation/negation words that carry no construction info.
# When phase > GATHERING and message matches, skip collect_project_data.
_CONFIRMATION_WORDS = frozenset([
    "لا", "نعم", "أيوه", "ايوه", "تمام", "ماشي", "أوك", "اوك",
    "ok", "okay", "yes", "no", "sure", "fine", "yep", "nope",
])

_PDF_KEYWORDS = frozenset([
    "pdf", "بي دي اف", "طباعة", "اطبع", "تحميل", "حمل", "تنزيل", "نزل",
])
_EXCEL_KEYWORDS = frozenset([
    "excel", "xlsx", "اكسل", "اكسيل", "جدول اكسل",
])
_LABOR_KEYWORDS = frozenset([
    "عمالة", "عامل", "عمال", "نجار", "سباك", "كهربائي", "نقاش",
    "labor", "labour", "worker", "workforce",
])
_STANDARDS_KEYWORDS = frozenset([
    "كود", "مواصفات", "معيار", "معايير", "اشتراطات",
    "standard", "code", "spec", "specification",
])
_MATERIAL_KEYWORDS = frozenset([
    "سعر مواد", "أسعار مواد", "مواد بناء", "خامات", "سيراميك سعر",
    "رخام سعر", "دهان سعر", "طوب سعر", "أسمنت سعر",
    "material price", "cost of material",
])

# Phrases that mean "skip the engineering questions and quote now".
_QUOTE_NOW_KEYWORDS = frozenset([
    "اطلعلي السعر", "هات السعر", "عرض السعر", "احسبلي", "احسب السعر",
    "المقايسة", "كده كفاية", "خلاص اطلع", "اطلع السعر", "السعر دلوقتي",
    "quote now", "just quote", "calculate now", "price now", "skip",
])


def _contains(msg: str, keywords) -> bool:
    msg_lower = msg.lower()
    return any(kw in msg_lower for kw in keywords)


def _is_short_confirmation(msg: str, phase: str) -> bool:
    """
    Return True when the message is a short confirmation/negation with no new
    construction data and the quotation is already past GATHERING phase.
    In this case, collect_project_data would be called with a single word like
    "لا" or "تمام" — the LLM can't extract anything useful, and may wipe
    previously extracted fields.
    """
    if phase == "GATHERING":
        return False  # always collect in GATHERING — we need the initial data
    words = msg.strip().split()
    if len(words) > 4:
        return False  # long enough to potentially contain construction info
    msg_lower = msg.lower().strip()
    # Has no construction keywords and is a confirmation/negation word
    has_construction = _contains(msg_lower, _MATERIAL_KEYWORDS | _LABOR_KEYWORDS | _STANDARDS_KEYWORDS)
    is_confirmation = any(w in msg_lower for w in _CONFIRMATION_WORDS)
    return is_confirmation and not has_construction


# Sentinel strings the LLM emits for "I don't know" — these are NOT real values
# and must never satisfy a required-field gate (otherwise we quote on garbage).
_NULL_LIKE_VALUES = frozenset({"", "unknown", "null", "none", "not specified", "n/a"})


def _is_present(value) -> bool:
    """True only for a genuine value. A truthy sentinel like 'unknown' is absent."""
    if not value:
        return False
    if isinstance(value, str) and value.strip().lower() in _NULL_LIKE_VALUES:
        return False
    return True


def _has_sufficient_data(extracted: dict) -> bool:
    """
    Mirrors the validation guard in calculate_costs tool.
    All four fields must be present (and not a 'unknown'-style sentinel) before
    cost calculation is possible.
    """
    return all(
        _is_present(extracted.get(field))
        for field in ("size_sqm", "project_type", "current_finish_level", "target_finish_level")
    )


# Fields whose change should trigger a re-quote once a quotation is COMPLETE.
_MATERIAL_FIELDS = (
    "size_sqm", "project_type", "current_finish_level", "target_finish_level",
    "num_floors", "num_bathrooms", "num_kitchens",
)


def _room_signature(extracted: dict) -> list:
    """Normalised (room_type, count) multiset for comparing room layouts."""
    rooms = (extracted or {}).get("rooms") or []
    return sorted(
        (str(r.get("room_type", "")).lower(), int(r.get("count", 1) or 1))
        for r in rooms if isinstance(r, dict)
    )


def _data_changed(old: dict, new: dict) -> bool:
    """
    True if the user supplied materially new project data (size, type, finish
    levels, floors, room/bath/kitchen counts, or the room layout) vs the snapshot
    taken at the start of the turn. Used to decide whether a COMPLETE quotation
    must be recalculated. A bare confirmation leaves everything equal → no re-quote.
    """
    old = old or {}
    new = new or {}
    for field in _MATERIAL_FIELDS:
        if (old.get(field) or None) != (new.get(field) or None):
            return True
    return _room_signature(old) != _room_signature(new)


def _compute_phase(q_data) -> str:
    if q_data and q_data.total_cost is not None:
        return "COMPLETE"
    if q_data and q_data.cost_breakdown:
        return "QUOTING"
    if q_data and q_data.extracted_data:
        return "ANALYZING"
    return "GATHERING"


def _tid() -> str:
    """Generate a unique tool_call_id."""
    return str(uuid.uuid4())


# ── Main node ─────────────────────────────────────────────────────────────

async def workflow_node(state: QuotationAgentState) -> Dict[str, Any]:
    """
    Deterministic tool router. Reads DB state, decides which tools to call,
    executes them directly, returns ToolMessages for the response node.
    No LLM involved in routing decisions.
    """
    quotation_id = state.get("quotation_id")
    messages = state.get("messages", [])

    last_user_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = (msg.content or "").strip()
            break

    current_phase = state.get("current_phase", "GATHERING")
    tool_messages = []

    # ── Step 1: Resolve quotation and read current DB state ───────────────
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None
    actual_id = quotation_id

    try:
        quotation, _ = await resolve_quotation_id(
            quotation_id, db, create_if_missing=True
        )
        actual_id = quotation.id

        res = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == actual_id)
        )
        q_data = res.scalar_one_or_none()
        current_phase = _compute_phase(q_data)
        initial_extracted = (q_data.extracted_data or {}) if q_data else {}
    finally:
        if should_close:
            await db.close()

    logger.info(f"[workflow] quotation={actual_id} phase={current_phase} msg='{last_user_msg[:60]}'")

    # ── Step 2: Export requests (always handled regardless of phase) ───────
    if _contains(last_user_msg, _PDF_KEYWORDS):
        logger.info(f"[workflow] → export_quotation_pdf")
        res = await export_quotation_pdf.ainvoke({"quotation_id": actual_id})
        tool_messages.append(ToolMessage(
            content=res, name="export_quotation_pdf", tool_call_id=_tid()
        ))
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    if _contains(last_user_msg, _EXCEL_KEYWORDS):
        logger.info(f"[workflow] → export_quotation_excel")
        res = await export_quotation_excel.ainvoke({"quotation_id": actual_id})
        tool_messages.append(ToolMessage(
            content=res, name="export_quotation_excel", tool_call_id=_tid()
        ))
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    # ── Step 3: Search requests ────────────────────────────────────────────
    if _contains(last_user_msg, _LABOR_KEYWORDS):
        logger.info(f"[workflow] → search_labor_rates")
        res = await search_labor_rates.ainvoke({"query": last_user_msg})
        tool_messages.append(ToolMessage(
            content=res, name="search_labor_rates", tool_call_id=_tid()
        ))
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    if _contains(last_user_msg, _STANDARDS_KEYWORDS):
        logger.info(f"[workflow] → search_standards")
        res = await search_standards.ainvoke({"query": last_user_msg})
        tool_messages.append(ToolMessage(
            content=res, name="search_standards", tool_call_id=_tid()
        ))
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    if _contains(last_user_msg, _MATERIAL_KEYWORDS):
        logger.info(f"[workflow] → search_materials")
        res = await search_materials.ainvoke({"query": last_user_msg})
        tool_messages.append(ToolMessage(
            content=res, name="search_materials", tool_call_id=_tid()
        ))
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    # ── Step 3.5: Engineering Q&A in progress — route the answer here ──────
    # Once the agent has asked KB-grounded engineering questions, the user's reply
    # is the answer to them (and is often short, so this MUST run before the
    # short-confirmation skip and before collect). Record it, then either ask the
    # next batch or — if the engineer is satisfied / user said "quote now" — quote.
    if _has_pending_round(initial_extracted):
        quote_now = _contains(last_user_msg, _QUOTE_NOW_KEYWORDS)
        db_e = await get_or_create_async_db_session()
        should_close_e = db_session_context.get() is None
        try:
            eng_res = await run_engineering_step(actual_id, last_user_msg, db_e, quote_now=quote_now)
        finally:
            if should_close_e:
                await db_e.close()
        if not eng_res["complete"]:
            tool_messages.append(ToolMessage(
                content=eng_res["questions_text"], name="engineering_questions", tool_call_id=_tid()
            ))
            return {"messages": tool_messages, "current_phase": "ENGINEERING", "quotation_id": actual_id}
        logger.info("[workflow] engineering complete → calculate_costs")
        calc_res = await calculate_costs.ainvoke({"quotation_id": actual_id})
        tool_messages.append(ToolMessage(
            content=calc_res, name="calculate_costs", tool_call_id=_tid()
        ))
        db_p = await get_or_create_async_db_session()
        should_close_p = db_session_context.get() is None
        try:
            res_p = await db_p.execute(
                select(QuotationData).filter(QuotationData.quotation_id == actual_id)
            )
            current_phase = _compute_phase(res_p.scalar_one_or_none())
        finally:
            if should_close_p:
                await db_p.close()
        return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}

    # ── Step 4: Collect project data (LLM extraction via DataCollectorAgent) ──
    # Note: a COMPLETE quotation is NOT terminal — if the user adds new structural
    # info (floors, rooms, size, finish), we re-collect and re-quote below. Only a
    # bare confirmation/negation is skipped (handled by _is_short_confirmation).
    # Skip if message is just a confirmation/negation with no construction info —
    # calling the LLM with "لا" or "تمام" wastes a call and may wipe stored fields.
    if _is_short_confirmation(last_user_msg, current_phase):
        logger.info(f"[workflow] Skipping collect — short confirmation '{last_user_msg}' in phase {current_phase}")
        return {"messages": [], "current_phase": current_phase, "quotation_id": actual_id}

    logger.info(f"[workflow] → collect_project_data")
    collect_res = await collect_project_data.ainvoke({
        "quotation_id": actual_id,
        "additional_info": last_user_msg[:500],
    })
    tool_messages.append(ToolMessage(
        content=collect_res, name="collect_project_data", tool_call_id=_tid()
    ))

    # ── Step 6: Re-read DB and calculate costs if data is complete ─────────
    db2 = await get_or_create_async_db_session()
    should_close2 = db_session_context.get() is None
    try:
        res2 = await db2.execute(
            select(QuotationData).filter(QuotationData.quotation_id == actual_id)
        )
        q_data = res2.scalar_one_or_none()
        extracted = (q_data.extracted_data or {}) if q_data else {}

        if _has_sufficient_data(extracted):
            had_cost = bool(q_data and q_data.total_cost is not None)
            changed = _data_changed(initial_extracted, extracted)

            # Engineering gate: before the FIRST quote, run the KB-grounded
            # engineering Q&A so the BOQ reflects this specific project (unless the
            # user asked to quote now). Re-quotes after a later data change skip it.
            eng = extracted.get("engineering") or {}
            quote_now = _contains(last_user_msg, _QUOTE_NOW_KEYWORDS)
            if not had_cost and not eng.get("complete") and not quote_now:
                eng_res = await run_engineering_step(actual_id, last_user_msg, db2, quote_now=False)
                if not eng_res["complete"]:
                    logger.info("[workflow] → engineering questions (pre-quote)")
                    tool_messages.append(ToolMessage(
                        content=eng_res["questions_text"], name="engineering_questions", tool_call_id=_tid()
                    ))
                    return {"messages": tool_messages, "current_phase": "ENGINEERING", "quotation_id": actual_id}
                # Engineering immediately complete (e.g. no KB / LLM satisfied) → quote.

            if changed or not had_cost:
                logger.info(f"[workflow] → calculate_costs (changed={changed}, had_prior_cost={had_cost})")
                calc_res = await calculate_costs.ainvoke({"quotation_id": actual_id})
                tool_messages.append(ToolMessage(
                    content=calc_res, name="calculate_costs", tool_call_id=_tid()
                ))

                # Final phase from DB
                res3 = await db2.execute(
                    select(QuotationData).filter(QuotationData.quotation_id == actual_id)
                )
                q_data = res3.scalar_one_or_none()
                current_phase = _compute_phase(q_data)
            else:
                # Data unchanged and a quote already exists — keep it, no re-quote.
                current_phase = "COMPLETE"
                logger.info("[workflow] Sufficient data unchanged — keeping existing quote (no recalc)")
        else:
            current_phase = "GATHERING"
            logger.info(
                f"[workflow] Insufficient data — present: "
                f"size={_is_present(extracted.get('size_sqm'))}, "
                f"type='{extracted.get('project_type')}'({_is_present(extracted.get('project_type'))}), "
                f"current_finish={_is_present(extracted.get('current_finish_level'))}, "
                f"target_finish={_is_present(extracted.get('target_finish_level'))}"
            )
    finally:
        if should_close2:
            await db2.close()

    return {"messages": tool_messages, "current_phase": current_phase, "quotation_id": actual_id}
