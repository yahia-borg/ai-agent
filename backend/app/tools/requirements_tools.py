"""
Requirements Tools - Helper tools for requirements gathering.

Simplified to only include escape intent detection.
All data collection is now done conversationally by the requirements agent.
"""
from typing import Dict
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)


# ============= ESCAPE INTENT DETECTION =============

ESCAPE_PHRASES_EN = [
    "just proceed", "proceed anyway", "that's enough", "thats enough",
    "go ahead", "just estimate", "skip", "use defaults", "that's all",
    "thats all", "enough questions", "just calculate", "proceed",
    "continue", "let's go", "lets go"
]

ESCAPE_PHRASES_AR = [
    # Proceed/Continue
    "كمل", "كمّل", "استمر", "امشي", "يلا", "يللا", "روح",
    # That's enough
    "كفاية", "كفايه", "خلاص", "بس كده", "بس كدا", "كده تمام", "كدا تمام",
    # OK/Fine
    "تمام", "ماشي", "ماشى", "حاضر", "اوك", "اوكي", "ok",
]


@tool
def detect_escape_intent(message: str) -> Dict[str, bool]:
    """
    Detect if user wants to proceed with defaults.

    Checks for skip/proceed phrases in English and Arabic.

    Args:
        message: User message text

    Returns:
        Dict with 'wants_to_proceed' (bool)
    """
    if not message:
        return {"wants_to_proceed": False}

    message_lower = message.lower().strip()

    all_phrases = ESCAPE_PHRASES_EN + ESCAPE_PHRASES_AR

    for phrase in all_phrases:
        if phrase in message_lower:
            return {"wants_to_proceed": True}

    return {"wants_to_proceed": False}
