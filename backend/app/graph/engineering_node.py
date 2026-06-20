"""
KB-grounded engineering questioning sub-phase.

Once the four core fields (size, project_type, current/target finish) are known,
the agent stops behaving like a fixed checklist and starts behaving like an
engineer building a Bill of Quantities: it asks sharp, project-specific
engineering questions (flooring system, MEP scope, HVAC, ceilings, fire safety,
kitchens/cold rooms, façade, sanitary fit-out) — but ONLY the ones that matter
for THIS project type and finishing transition, and ONLY grounded in the seeded
knowledge base (Qdrant `knowledge_items`). No hallucinated requirements.

Routing stays deterministic (workflow_node decides WHEN this runs); the LLM only
generates the question CONTENT, constrained by retrieved KB context + a schema.

State lives in ``QuotationData.extracted_data["engineering"]``::

    {
      "complete": bool,
      "rounds": [ {"questions": [{"topic","question"}], "answer": str|None}, ... ]
    }

A "round" is one batch of questions; the user's next message is recorded as that
round's ``answer``. Adaptive + bounded: the LLM signals ``enough_info`` to stop,
and we hard-cap at MAX_ROUNDS so it can never interrogate forever.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.agents.llm_client import get_llm_client
from app.models.project_data import EngineeringAssessment, BOQScope
from app.models.quotation import QuotationData

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3  # bound the adaptive loop — at most 3 batches of questions

_ENGINEERING_SYSTEM_PROMPT = """You are a senior Egyptian finishing & construction engineer preparing a precise Bill of Quantities (BOQ) for a client.

You ask sharp, practical engineering questions that MATERIALLY change the BOQ — flooring system, electrical/plumbing (MEP) scope, HVAC, false/gypsum ceilings, fire safety, kitchens/cold rooms, façade/storefront, sanitary fit-out, lighting — but ONLY the ones relevant to THIS project type and finishing transition.

Hard rules:
- Ground EVERY question in the REFERENCE KNOWLEDGE provided. Never invent a requirement the reference does not support.
- Ask in simple Egyptian Arabic (اللهجة المصرية). Use Western digits 0-9.
- Ask at most 3 questions, and only the MOST important still-missing ones. Do not repeat anything already answered.
- When the reference + known facts are enough to build an accurate BOQ, set enough_info=true and return no questions.
- One concise question per item — no compound questions, no design/colour/timeline chit-chat."""

_BOQ_SCOPE_SYSTEM_PROMPT = """You are a senior Egyptian finishing & construction engineer writing the Bill of Quantities (BOQ) work breakdown for a finishing project.

Using the project facts, the engineering Q&A (the client may answer in Arabic, English, or Franco-Arabic/Arabizi — understand ALL of them), and the reference knowledge, produce:
1. line_items — the named finishing work-packages for THIS specific project (e.g. electrical & low-current, plumbing & sanitary, HVAC, false ceilings, flooring WITH the chosen material, partitions/joinery, painting, fire-fighting, kitchen/cold-room, façade — plus anything else the client confirmed, and omit what they don't need). Each item: name_en, name_ar (Egyptian Arabic), and a positive RELATIVE cost weight (rough proportion; it will be normalised).
2. summary_en / summary_ar — ONE short line listing the key scope the client confirmed.

Rules:
- Reflect what the client actually said (in any language). If they named a flooring material, put it in the flooring line.
- Ground packages in the reference knowledge; don't invent systems the project doesn't need.
- Western digits 0-9. Short names. NEVER output money amounts — only relative weights."""


async def synthesize_boq_scope(extracted: Dict[str, Any], eng: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ask the LLM (which natively understands Arabic/English/Franco-Arabic) to turn
    the engineering Q&A into a structured BOQ work breakdown + scope summary. Returns
    a dict (BOQScope) or None on failure. Weights are relative — never absolute money."""
    kb_context = _retrieve_kb_context(extracted)
    prompt = (
        f"PROJECT: type={extracted.get('project_type')}, area={extracted.get('size_sqm')} m², "
        f"current finish={extracted.get('current_finish_level')}, "
        f"target finish={extracted.get('target_finish_level')}.\n\n"
        f"ENGINEERING Q&A:\n{_format_prior_qa(eng)}\n\n"
        f"REFERENCE KNOWLEDGE:\n{kb_context or '(none retrieved)'}\n\n"
        "Produce the BOQ work breakdown (line_items with bilingual names + relative "
        "weights) and a one-line bilingual scope summary of what the client confirmed."
    )
    try:
        scope: BOQScope = await get_llm_client().invoke_structured(
            prompt=prompt, schema=BOQScope, system_prompt=_BOQ_SCOPE_SYSTEM_PROMPT,
        )
        data = scope.model_dump()
        if not data.get("line_items"):
            return None
        return data
    except Exception as e:
        logger.warning(f"[engineering] BOQ scope synthesis failed (non-fatal): {e}")
        return None


def _get_engineering_state(extracted: Dict[str, Any]) -> Dict[str, Any]:
    eng = extracted.get("engineering")
    if not isinstance(eng, dict):
        eng = {"complete": False, "rounds": []}
    eng.setdefault("complete", False)
    eng.setdefault("rounds", [])
    return eng


def _has_pending_round(extracted: Dict[str, Any]) -> bool:
    """True when the last engineering round is still awaiting the user's answer."""
    eng = extracted.get("engineering")
    if not isinstance(eng, dict) or eng.get("complete"):
        return False
    rounds = eng.get("rounds") or []
    return bool(rounds) and rounds[-1].get("answer") is None


def _retrieve_kb_context(extracted: Dict[str, Any], max_chars: int = 2500) -> str:
    """Pull grounding docs from Qdrant for this project's finishing transition."""
    project_type = extracted.get("project_type") or "residential"
    current = (extracted.get("current_finish_level") or "").replace("_", " ")
    target = (extracted.get("target_finish_level") or "").replace("_", " ")
    query = (
        f"{project_type} finishing from {current} to {target} "
        "BOQ engineering requirements materials systems MEP flooring ceilings finishing stages"
    )
    try:
        from app.services.qdrant_service import get_qdrant_service
        docs = get_qdrant_service().search_knowledge(query, top_k=5)
    except Exception as e:
        logger.warning(f"[engineering] KB retrieval failed (non-fatal): {e}")
        return ""
    parts: List[str] = []
    used = 0
    for d in docs:
        snippet = f"- {d.get('topic','')}: {str(d.get('content',''))[:500]}"
        if used + len(snippet) > max_chars:
            break
        parts.append(snippet)
        used += len(snippet)
    return "\n".join(parts)


def _format_prior_qa(eng: Dict[str, Any]) -> str:
    lines: List[str] = []
    for rnd in eng.get("rounds", []):
        for q in rnd.get("questions", []):
            lines.append(f"Q ({q.get('topic','')}): {q.get('question','')}")
        if rnd.get("answer"):
            lines.append(f"A: {rnd['answer']}")
    return "\n".join(lines) if lines else "none"


def _render_questions_message(questions: List[Dict[str, str]]) -> str:
    """The full user-facing Arabic message: intro + numbered questions + escape."""
    intro = "تمام 👍 عشان أطلعلك مقايسة دقيقة زي المهندس، محتاج أعرف كام تفصيلة فنية:"
    body = "\n".join(f"{i}. {q.get('question','').strip()}" for i, q in enumerate(questions, 1))
    escape = "ولو حابب أطلعلك السعر دلوقتي على المواصفات القياسية، قولي «اطلعلي السعر»."
    return f"{intro}\n{body}\n\n{escape}"


async def run_engineering_step(
    actual_id: str,
    last_user_msg: str,
    db,
    quote_now: bool = False,
) -> Dict[str, Any]:
    """
    Advance the engineering Q&A one step and persist state.

    - Records the user's latest message as the answer to any pending round.
    - Asks the LLM (grounded in KB) whether enough info exists; if not, generates
      the next batch of questions.
    - Marks complete when the LLM is satisfied, the round cap is hit, or the user
      asked to quote now.

    Returns ``{"complete": bool, "questions_text": Optional[str]}``. When not
    complete, ``questions_text`` is the full Arabic message to show the user.
    """
    res = await db.execute(
        select(QuotationData).filter(QuotationData.quotation_id == actual_id)
    )
    q_data = res.scalar_one_or_none()
    extracted = dict((q_data.extracted_data or {}) if q_data else {})
    eng = _get_engineering_state(extracted)

    # 1. Record the answer to the pending round (this turn's message answers it).
    if eng["rounds"] and eng["rounds"][-1].get("answer") is None and last_user_msg:
        eng["rounds"][-1]["answer"] = last_user_msg[:500]

    async def _complete(reason: str) -> Dict[str, Any]:
        """Mark engineering done, synthesise the BOQ scope (best-effort), persist."""
        eng["complete"] = True
        extracted["engineering"] = eng  # so synthesis sees the recorded answers
        scope = await synthesize_boq_scope(extracted, eng)
        if scope:
            eng["boq_scope"] = scope
        await _persist(db, q_data, extracted, eng)
        logger.info(f"[engineering] complete ({reason}); boq_scope={'yes' if scope else 'no'}")
        return {"complete": True, "questions_text": None}

    # 2. Escape hatch / hard cap.
    if quote_now or len(eng["rounds"]) >= MAX_ROUNDS:
        return await _complete(f"quote_now={quote_now}, rounds={len(eng['rounds'])}")

    # 3. Ask the LLM (grounded) for the next questions or a 'done' verdict.
    kb_context = _retrieve_kb_context(extracted)
    prompt = (
        f"PROJECT: type={extracted.get('project_type')}, area={extracted.get('size_sqm')} m², "
        f"current finish={extracted.get('current_finish_level')}, "
        f"target finish={extracted.get('target_finish_level')}.\n\n"
        f"PRIOR ENGINEERING Q&A:\n{_format_prior_qa(eng)}\n\n"
        f"REFERENCE KNOWLEDGE (ground questions ONLY in this):\n{kb_context or '(none retrieved)'}\n\n"
        "Decide if you have enough to build an accurate BOQ. If yes, set enough_info=true "
        "with no questions. If no, return the 1-3 most important still-missing engineering "
        "questions, each grounded in the reference above."
    )

    try:
        assessment: EngineeringAssessment = await get_llm_client().invoke_structured(
            prompt=prompt,
            schema=EngineeringAssessment,
            system_prompt=_ENGINEERING_SYSTEM_PROMPT,
        )
    except Exception as e:
        # On failure, don't block the user — proceed to quote with what we have.
        logger.warning(f"[engineering] assessment failed ({e}); marking complete")
        return await _complete("assessment failed")

    new_questions = [
        {"topic": q.topic, "question": q.question}
        for q in (assessment.questions or [])
        if q.question and q.question.strip()
    ]

    if assessment.enough_info or not new_questions:
        return await _complete("LLM enough_info")

    eng["rounds"].append({"questions": new_questions, "answer": None})
    await _persist(db, q_data, extracted, eng)
    logger.info(
        f"[engineering] round {len(eng['rounds'])}: asking {len(new_questions)} "
        f"question(s) [{', '.join(q['topic'] for q in new_questions)}]"
    )
    return {"complete": False, "questions_text": _render_questions_message(new_questions)}


async def _persist(db, q_data, extracted: Dict[str, Any], eng: Dict[str, Any]) -> None:
    extracted["engineering"] = eng
    if q_data is not None:
        q_data.extracted_data = extracted
        # Reassign so SQLAlchemy detects the JSON mutation.
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(q_data, "extracted_data")
        await db.commit()
