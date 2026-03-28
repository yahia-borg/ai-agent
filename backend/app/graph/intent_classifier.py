"""
LLM-based intent classifier using the response LLM (8061) with structured output.
Results are cached in Redis for repeated messages.
"""
import logging
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from app.agents.state import QuotationAgentState
from app.services.response_cache import get_response_cache

logger = logging.getLogger(__name__)


class IntentClassification(BaseModel):
    """Structured output schema for intent classification."""
    intent: str = Field(description="One of: chat, quotation, export, search")
    confidence: float = Field(description="0.0 to 1.0")
    language: str = Field(description="Detected language: ar or en")


CLASSIFIER_PROMPT = """Classify this user message for a construction quotation system.

Intents:
- "chat": Greetings, thanks, general questions, small talk, confirmations (ok/تمام/ماشي), farewells
- "quotation": Anything about construction, finishing, apartments, villas, offices,
  costs, prices, sizes, room details, project specifications, banks, hospitals, hotels
- "export": User wants PDF or Excel export of a quotation
- "search": User asks about specific material prices, labor rates, or standards

Respond with the intent, confidence (0-1), and detected language (ar/en).
"""

# Quick-check words for obvious chat during active quotation flow
_OBVIOUS_CHAT_WORDS = frozenset([
    "مرحبا", "اهلا", "سلام", "شكرا", "hello", "hi", "thanks",
    "ok", "تمام", "ماشي", "شكراً", "أهلاً", "bye", "مع السلامة",
])

# Quick-check words for obvious quotation/construction messages
_OBVIOUS_QUOTATION_WORDS = frozenset([
    # Arabic construction terms
    "تشطيب", "شقة", "فيلا", "متر", "محارة", "طوب", "بنك", "مكتب",
    "فاخر", "لوكس", "مقايسة", "تكلفة", "سعر", "غرفة", "حمام", "مطبخ",
    "دور", "دورين", "ارضي", "أرضي", "سيراميك", "رخام", "دهان",
    "مساحة", "اشطب", "عايز", "كهرباء", "سباكة", "نجارة",
    "مستشفى", "فندق", "مدرسة", "مول", "معرض",
    # English construction terms
    "finish", "apartment", "villa", "sqm", "plaster", "brick",
    "quotation", "cost", "price", "room", "bathroom", "kitchen",
    "floor", "ceramic", "marble", "paint", "luxury", "commercial",
    "office", "bank", "hospital", "hotel",
])


def _is_obvious_chat(msg: str) -> bool:
    """Quick keyword check for obvious chat during active quotation."""
    msg_lower = msg.lower().strip()
    return any(kw in msg_lower for kw in _OBVIOUS_CHAT_WORDS) and len(msg.split()) <= 3


def _is_obvious_quotation(msg: str) -> bool:
    """Quick keyword check for obvious construction/quotation messages."""
    msg_lower = msg.lower().strip()
    return any(kw in msg_lower for kw in _OBVIOUS_QUOTATION_WORDS)


def _route(intent: str, language: Optional[str] = None) -> Command:
    """Convert intent to graph Command."""
    updates = {}
    if language:
        updates["detected_language"] = language

    if intent == "chat":
        return Command(goto="response", update=updates if updates else None)
    else:  # quotation, export, search -> all need supervisor
        return Command(goto="supervisor", update=updates if updates else None)


async def classify_intent(state: QuotationAgentState) -> Command:
    """
    LLM-based intent classifier using 8061 with structured output.
    Results cached in Redis for repeated messages.
    """
    messages = state.get("messages", [])
    if not messages:
        return Command(goto="supervisor")

    last_msg = messages[-1].content.strip() if hasattr(messages[-1], "content") else ""
    if not last_msg:
        return Command(goto="supervisor")

    cache = get_response_cache()

    # 1. Check Redis cache first
    try:
        cached_intent = await cache.get_intent(last_msg)
        if cached_intent:
            logger.info(f"Intent cache HIT: '{last_msg[:40]}' -> {cached_intent}")
            return _route(cached_intent)
    except Exception:
        pass

    # 2. Check for active quotation context
    #    A quotation is "active" if:
    #    - Phase is beyond GATHERING (ANALYZING, QUOTING, COMPLETE), OR
    #    - We're in GATHERING but a real quotation_id exists (not just session-*)
    #      This ensures follow-up messages with project details go to supervisor
    current_phase = state.get("current_phase")
    quotation_id = state.get("quotation_id", "")
    has_real_quotation = quotation_id and not str(quotation_id).startswith("session-")
    has_active_quotation = current_phase not in (None, "", "GATHERING") or has_real_quotation

    if has_active_quotation:
        if _is_obvious_chat(last_msg):
            return Command(goto="response")
        return Command(goto="supervisor")

    # 3. Fast-path: if message contains obvious construction keywords, skip LLM
    if _is_obvious_quotation(last_msg):
        logger.info(f"Keyword fast-path: '{last_msg[:40]}' -> quotation (construction keywords detected)")
        try:
            await cache.set_intent(last_msg, "quotation")
        except Exception:
            pass
        return _route("quotation")

    # 4. LLM classification via 8061 structured output
    try:
        from app.agents.llm_client import LLMClient
        from app.core.config import settings
        # Use a dedicated small-max_tokens client for classification (~50 token output)
        classifier_client = LLMClient(
            base_url_override=settings.RESPONSE_LLM_BASE_URL or None,
            model_override=settings.RESPONSE_LLM_MODEL or None,
            max_tokens_override=256,
        )
        classifier = classifier_client.client.with_structured_output(IntentClassification)
        result = await classifier.ainvoke([
            SystemMessage(content=CLASSIFIER_PROMPT),
            HumanMessage(content=last_msg),
        ])

        logger.info(
            f"Intent classified: '{last_msg[:40]}' -> {result.intent} "
            f"(confidence={result.confidence:.2f}, lang={result.language})"
        )

        # 5. Cache the result
        try:
            await cache.set_intent(last_msg, result.intent)
        except Exception:
            pass

        # 6. Route based on intent
        return _route(result.intent, result.language)

    except Exception as e:
        logger.warning(f"Intent classification failed, defaulting to supervisor: {e}")
        return Command(goto="supervisor")
