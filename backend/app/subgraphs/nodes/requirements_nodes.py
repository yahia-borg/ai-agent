"""
Requirements gathering nodes for the requirements subgraph.

Nodes:
- extract_node: Extract requirements from user message
- validate_node: Check completeness and determine next action
- generate_question_node: Generate follow-up question for missing fields
- complete_node: Mark requirements as complete
"""
from typing import Dict, Any
import logging

from langchain_core.messages import AIMessage, HumanMessage
from app.state.schemas import CostEstimationState
from app.agents.llm_client import get_llm_client
from app.utils.language_detector import detect_language
from app.tools.requirements_tools import detect_escape_intent

logger = logging.getLogger(__name__)

# ============= HELPER FUNCTIONS =============

# === GROUPED VALIDATION APPROACH ===
# Instead of asking 10+ questions individually, group related fields

# Group 1: Project Type (to determine what to ask next)
PROJECT_TYPE_FIELD = {
    "project_type": ["residential", "commercial", "factory"]
}

# Group 2: Project Basics (asked together in ONE composite question)
PROJECT_BASICS_GROUP = {
    "total_area_sqm": "number",
    "current_finishing_status": ["bare_concrete", "plastered", "semi_finished", "painted"],
    "finishing_level": ["basic", "standard", "premium", "luxury"]
}

# Group 3: Type-Specific Rooms/Spaces (asked together in ONE composite question)
RESIDENTIAL_ROOMS_GROUP = {
    "bedrooms_count": "number",
    "bathrooms_count": "number",
    "living_rooms_count": "number",
    "kitchens_count": "number"
}

COMMERCIAL_SPACES_GROUP = {
    "shops_count": "number",
    "offices_count": "number",
    "restrooms_count": "number",
    "commercial_type": ["retail", "office_building", "mixed_use"]
}

FACTORY_AREAS_GROUP = {
    "production_area_sqm": "number",
    "warehouse_area_sqm": "number",
    "office_area_sqm": "number",
    "factory_type": ["light_manufacturing", "heavy_industrial", "warehouse"]
}

# Group 4: Optional Details (can be skipped)
RESIDENTIAL_DETAILS_GROUP = {
    "desired_finishing_style": ["modern", "classic", "minimal", "luxury"]
}

# Mapping of project types to their room/space groups
PROJECT_TYPE_GROUPS = {
    "residential": RESIDENTIAL_ROOMS_GROUP,
    "commercial": COMMERCIAL_SPACES_GROUP,
    "factory": FACTORY_AREAS_GROUP
}


async def extract_requirements_llm(
    user_message: str,
    current_requirements: Dict[str, Any],
    language: str
) -> Dict[str, Any]:
    """
    Extract requirements using LLM with structured JSON output.

    Falls back to keyword extraction on error.

    Args:
        user_message: User's input message
        current_requirements: Existing requirements dict
        language: Detected language ('ar' or 'en')

    Returns:
        Updated requirements dict with extracted fields
    """
    try:
        from app.agents.llm_client import get_llm_client
        from app.utils.language_detector import get_requirements_extraction_prompt
        import re
        import json

        # Get LLM client
        llm_client = get_llm_client()

        # Get bilingual prompts
        prompts = get_requirements_extraction_prompt(language)
        system_prompt = prompts["system"]

        # Build extraction prompt with current state
        current_reqs_str = json.dumps(current_requirements, ensure_ascii=False, indent=2)
        extraction_prompt = prompts["extraction"].format(
            user_message=user_message,
            current_requirements=current_reqs_str
        )

        # Call LLM (async)
        response = await llm_client.invoke(extraction_prompt, system_prompt)

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            extracted_data = json.loads(json_match.group())
        else:
            extracted_data = json.loads(response)

        # Merge with current requirements (LLM output takes precedence for non-null values)
        updated_requirements = current_requirements.copy()

        for key, value in extracted_data.items():
            # Skip metadata fields
            if key in ["confidence_score", "missing_information"]:
                continue

            # Only update if LLM extracted a non-null value
            if value is not None:
                updated_requirements[key] = value

        logger.info(f"LLM extraction: {list(updated_requirements.keys())}, confidence={extracted_data.get('confidence_score', 0.0)}")

        return updated_requirements

    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}, falling back to keyword extraction")

        # Fallback to keyword-based extraction
        return _extract_requirements_keywords(user_message, current_requirements, language)


def _extract_requirements_keywords(
    user_message: str,
    current_requirements: Dict[str, Any],
    language: str
) -> Dict[str, Any]:
    """
    Fallback keyword-based extraction (original implementation).

    Used when LLM extraction fails. Simple keyword matching.
    """
    requirements = current_requirements.copy()
    message_lower = user_message.lower()

    # Extract project_type
    if not requirements.get("project_type"):
        if any(word in message_lower for word in ["residential", "apartment", "سكني", "شقة"]):
            requirements["project_type"] = "residential"
        elif any(word in message_lower for word in ["commercial", "office", "تجاري", "مكتب"]):
            requirements["project_type"] = "commercial"
        elif any(word in message_lower for word in ["factory", "industrial", "مصنع", "صناعي"]):
            requirements["project_type"] = "factory"

    # Extract total_area_sqm
    if not requirements.get("total_area_sqm"):
        import re
        area_patterns = [
            r'(\d+)\s*(?:m²|m2|sq\.?m|square\s*meters?|متر)',
            r'(\d+)\s*(?:meter|متر)',
        ]
        for pattern in area_patterns:
            match = re.search(pattern, message_lower)
            if match:
                requirements["total_area_sqm"] = float(match.group(1))
                break

    # Extract current_finishing_status
    if not requirements.get("current_finishing_status"):
        if any(word in message_lower for word in ["bare", "concrete", "عظم", "هيكل"]):
            requirements["current_finishing_status"] = "bare_concrete"
        elif any(word in message_lower for word in ["plaster", "محارة"]):
            requirements["current_finishing_status"] = "plastered"
        elif any(word in message_lower for word in ["semi", "نصف"]):
            requirements["current_finishing_status"] = "semi_finished"
        elif any(word in message_lower for word in ["painted", "مدهون"]):
            requirements["current_finishing_status"] = "painted"

    # Extract desired_finishing_style
    if not requirements.get("desired_finishing_style"):
        if any(word in message_lower for word in ["modern", "حديث"]):
            requirements["desired_finishing_style"] = "modern"
        elif any(word in message_lower for word in ["classic", "كلاسيك"]):
            requirements["desired_finishing_style"] = "classic"
        elif any(word in message_lower for word in ["minimal", "بسيط"]):
            requirements["desired_finishing_style"] = "minimal"

    # Extract finishing_level
    if not requirements.get("finishing_level"):
        if any(word in message_lower for word in ["luxury", "فاخر"]):
            requirements["finishing_level"] = "luxury"
        elif any(word in message_lower for word in ["premium", "ممتاز"]):
            requirements["finishing_level"] = "premium"
        elif any(word in message_lower for word in ["standard", "عادي"]):
            requirements["finishing_level"] = "standard"
        elif any(word in message_lower for word in ["basic", "بسيط"]):
            requirements["finishing_level"] = "basic"

    # Extract location
    if not requirements.get("location"):
        egyptian_cities = ["cairo", "القاهرة", "alexandria", "الإسكندرية", "giza", "الجيزة"]
        for city in egyptian_cities:
            if city in message_lower:
                requirements["location"] = city.title()
                break

    # Extract rooms_breakdown
    if not requirements.get("rooms_breakdown"):
        import re
        rooms = []
        bedroom_match = re.search(r'(\d+)\s*(?:bedroom|bedrooms|غرف نوم|غرفة نوم)', message_lower)
        if bedroom_match:
            count = int(bedroom_match.group(1))
            for i in range(count):
                rooms.append({"room_type": "bedroom", "area_sqm": 15.0, "count": 1})

        bathroom_match = re.search(r'(\d+)\s*(?:bathroom|bathrooms|حمام|حمامات)', message_lower)
        if bathroom_match:
            count = int(bathroom_match.group(1))
            rooms.append({"room_type": "bathroom", "area_sqm": 6.0, "count": count})

        if rooms:
            rooms.append({"room_type": "living_room", "area_sqm": 25.0, "count": 1})
            rooms.append({"room_type": "kitchen", "area_sqm": 12.0, "count": 1})
            requirements["rooms_breakdown"] = rooms

    return requirements


def check_completeness(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if requirements are complete using GROUPED validation.

    Validation Groups (3 questions max):
    1. Project type (if not in first message)
    2. Project basics (area + status + level) - ONE composite question
    3. Type-specific rooms/spaces - ONE composite question
    4. Optional details (style) - Can skip

    Returns dict with is_complete, missing_group, stage
    """

    # === Group 1: Project Type ===
    project_type = requirements.get("project_type")
    if not project_type or project_type not in ["residential", "commercial", "factory"]:
        return {
            "is_complete": False,
            "stage": "project_type",
            "missing_group": "project_type"
        }

    # === Group 2: Project Basics (asked together) ===
    missing_basics = []
    for field, expected in PROJECT_BASICS_GROUP.items():
        value = requirements.get(field)
        if not value:
            missing_basics.append(field)
        elif expected == "number" and not isinstance(value, (int, float)):
            missing_basics.append(field)
        elif isinstance(expected, list) and value not in expected:
            missing_basics.append(field)

    if missing_basics:
        return {
            "is_complete": False,
            "stage": "basics",
            "missing_group": "basics",
            "missing_fields": missing_basics
        }

    # === Group 3: Type-Specific Rooms/Spaces (asked together) ===
    type_specific_group = PROJECT_TYPE_GROUPS.get(project_type, {})
    missing_rooms = []

    for field, expected in type_specific_group.items():
        value = requirements.get(field)
        if not value:
            missing_rooms.append(field)
        elif expected == "number" and not isinstance(value, (int, float)):
            missing_rooms.append(field)
        elif isinstance(expected, list) and value not in expected:
            missing_rooms.append(field)

    if missing_rooms:
        return {
            "is_complete": False,
            "stage": "rooms",
            "missing_group": "rooms",
            "missing_fields": missing_rooms,
            "project_type": project_type
        }

    # === Group 4: Optional Details (can be skipped) ===
    # Style is optional - mark as complete even if missing

    # All required groups complete
    return {
        "is_complete": True,
        "stage": "complete",
        "missing_group": None
    }


async def generate_next_question_llm(
    validation_result: Dict[str, Any],
    current_requirements: Dict[str, Any],
    language: str
) -> str:
    """
    Generate contextual follow-up question using LLM.

    Uses conversational approach - asks ONLY for missing information
    based on what user already provided.
    """
    import json

    stage = validation_result.get("stage")
    missing_fields = validation_result.get("missing_fields", [])
    project_type = validation_result.get("project_type")

    # Build context for LLM
    already_provided = {k: v for k, v in current_requirements.items() if v}

    # Build prompt based on stage
    if stage == "project_type":
        context = "The user hasn't specified the project type yet."
        needed = "Project type (residential/commercial/factory)"
    elif stage == "basics":
        context = f"Already provided: {json.dumps(already_provided, ensure_ascii=False)}"
        needed = f"Missing: {', '.join(missing_fields)}"
    elif stage == "rooms":
        context = f"Project type: {project_type}. Already provided: {json.dumps(already_provided, ensure_ascii=False)}"
        needed = f"Missing room/space details: {', '.join(missing_fields)}"
    else:
        return "ممتاز! جاري حساب التكلفة..." if language == "ar" else "Perfect! Calculating your estimate..."

    # Build bilingual system prompt
    if language == "ar":
        system_prompt = """أنت مساعد لجمع متطلبات مشاريع البناء والتشطيب في مصر.
مهمتك: اسأل سؤال واحد قصير ومحدد فقط عن المعلومات الناقصة.

قواعد مهمة:
- لا تسأل عن معلومات تم تقديمها بالفعل
- لا تذكر أنواع مباني محددة (شقة، فيلا، منزل، إلخ) - اجعل الأسئلة عامة عن "المشروع" أو "المكان"
- كن محادثاً وودوداً
- اسأل سؤال واحد فقط في كل مرة
- استخدم أمثلة مصرية (متر مربع، جنيه مصري)
- كن مختصراً ومباشراً"""

        user_prompt = f"""{context}

المطلوب الآن: {needed}

اسأل سؤال واحد فقط بالعربية للحصول على المعلومات الناقصة. استخدم كلمات عامة ولا تذكر أنواع مباني محددة."""

    else:
        system_prompt = """You are an assistant for gathering construction and finishing project requirements in Egypt.
Your task: Ask ONE short, specific question about the missing information only.

Important rules:
- Do NOT ask about information already provided
- Do NOT mention specific building types (apartment, villa, house, etc.) - keep questions generic about "the project" or "your space"
- Be conversational and friendly
- Ask only ONE question at a time
- Use Egyptian context (square meters, EGP)
- Be concise and direct"""

        user_prompt = f"""{context}

Now needed: {needed}

Ask ONE question in English to get the missing information. Keep it generic - do not use specific building type names."""

    # Call LLM
    try:
        llm_client = get_llm_client()
        response = await llm_client.invoke(user_prompt, system_prompt)
        return response.strip()
    except Exception as e:
        logger.error(f"LLM question generation failed: {e}, using fallback")
        # Fallback to simple question
        if language == "ar":
            return f"من فضلك، أخبرني عن: {needed}"
        else:
            return f"Please tell me: {needed}"


def _get_project_type_question(language: str) -> str:
    """Get project type question (if not extracted from first message)."""
    if language == "ar":
        return """ما نوع المشروع؟
• سكني (شقة، فيلا، منزل، بنتهاوس)
• تجاري (محل، مكتب، معرض)
• مصنع

مثال: 'سكني' أو 'residential'"""
    else:
        return """What type of project?
• Residential (apartment, villa, house, penthouse)
• Commercial (shop, office, showroom)
• Factory

Example: 'residential' or 'apartment'"""


def _get_basics_composite_question(language: str) -> str:
    """Get composite question for project basics (area + status + level)."""
    if language == "ar":
        return """أخبرني عن تفاصيل المشروع:
• المساحة الإجمالية بالمتر المربع؟
• حالة التشطيب الحالية (عظم / محارة / نصف تشطيب / مدهون)؟
• مستوى التشطيب المطلوب (بسيط / عادي / ممتاز / فاخر)؟

مثال: '120 متر، عظم، عادي' أو '120m2, bare concrete, standard'"""
    else:
        return """Tell me about your project details:
• Total area in square meters?
• Current finishing status (bare concrete / plastered / semi-finished / painted)?
• Desired finishing level (basic / standard / premium / luxury)?

Example: '120m2, bare concrete, standard' or '120 square meters, bare, standard level'"""


def _get_rooms_composite_question(project_type: str, language: str) -> str:
    """Get composite question for rooms/spaces (asks ALL at once)."""

    if project_type == "residential":
        if language == "ar":
            return """أخبرني عن الغرف:
• كم عدد غرف النوم؟
• كم عدد الحمامات؟
• كم عدد غرف المعيشة؟ (عادة 1)
• كم عدد المطابخ؟ (عادة 1)

مثال: '3 غرف نوم، 2 حمام، 1 معيشة، 1 مطبخ' أو '3 bedrooms, 2 bathrooms, 1 living room, 1 kitchen'"""
        else:
            return """Tell me about the rooms:
• How many bedrooms?
• How many bathrooms?
• How many living rooms? (usually 1)
• How many kitchens? (usually 1)

Example: '3 bedrooms, 2 bathrooms, 1 living room, 1 kitchen' or simply '3 bed, 2 bath, 1 living, 1 kitchen'"""

    elif project_type == "commercial":
        if language == "ar":
            return """أخبرني عن المساحات:
• كم عدد المحلات؟
• كم عدد المكاتب؟
• كم عدد دورات المياه؟
• نوع المشروع (محلات / مباني مكاتب / استخدام مختلط)؟

مثال: '2 محلات، 1 مكتب، 2 دورات مياه، محلات' أو '2 shops, 1 office, 2 restrooms, retail'"""
        else:
            return """Tell me about the spaces:
• How many shops/stores?
• How many offices?
• How many restrooms?
• Type (retail / office building / mixed use)?

Example: '2 shops, 1 office, 2 restrooms, retail' or '2 stores, 1 office, 2 bathrooms, retail type'"""

    elif project_type == "factory":
        if language == "ar":
            return """أخبرني عن المساحات:
• مساحة منطقة الإنتاج بالمتر المربع؟
• مساحة المخزن بالمتر المربع؟
• مساحة المكاتب بالمتر المربع؟
• نوع المصنع (تصنيع خفيف / صناعي ثقيل / مخزن)؟

مثال: '500 متر إنتاج، 200 متر مخزن، 50 متر مكاتب، تصنيع خفيف' أو '500m2 production, 200m2 warehouse, 50m2 office, light manufacturing'"""
        else:
            return """Tell me about the areas:
• Production area in square meters?
• Warehouse area in square meters?
• Office area in square meters?
• Factory type (light manufacturing / heavy industrial / warehouse)?

Example: '500m2 production, 200m2 warehouse, 50m2 office, light manufacturing' or '500 production, 200 warehouse, 50 office, light'"""

    else:
        return "Please specify the room/space details."


# ============= NODE FUNCTIONS =============


async def extract_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Extract requirements from the last user message using LLM.

    Returns updated requirements dict.
    """
    messages = state.get("messages", [])
    current_requirements = state.get("requirements", {}) or {}

    # Get last user message
    last_user_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    if not last_user_message:
        logger.warning("No user message found for extraction")
        return {"requirements": current_requirements}

    # Check escape intent
    escape_result = detect_escape_intent.invoke({"message": last_user_message})
    if escape_result.get("wants_to_proceed", False):
        logger.info("User wants to proceed with defaults")
        return {
            "requirements": current_requirements,
            "user_confirmed_proceed": True
        }

    # Detect language
    language = detect_language(last_user_message)

    # Extract requirements using LLM (with keyword fallback)
    updated_requirements = await extract_requirements_llm(
        last_user_message,
        current_requirements,
        language
    )

    logger.info(f"Extracted requirements: {list(updated_requirements.keys())}")

    return {
        "requirements": updated_requirements,
        "current_agent": "requirements_subgraph"
    }


def validate_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Validate completeness of requirements.

    Returns validation results and routing decision.
    """
    requirements = state.get("requirements", {}) or {}

    # Check if user wants to proceed with defaults
    if state.get("user_confirmed_proceed", False):
        return {
            "requirements_validation": {
                "is_complete": False,
                "user_confirmed_proceed": True,
                "route": "complete"
            }
        }

    # Check completeness with GROUPED validation
    completeness = check_completeness(requirements)

    logger.info(
        f"Requirements validation: "
        f"stage={completeness['stage']}, "
        f"complete={completeness['is_complete']}, "
        f"missing_group={completeness.get('missing_group')}"
    )

    return {
        "requirements_validation": completeness
    }


async def generate_question_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Generate contextual follow-up question using LLM.

    Returns AI message with question that asks ONLY for missing information.
    """
    requirements = state.get("requirements", {}) or {}
    validation = state.get("requirements_validation", {})

    # Get last user message for language detection
    messages = state.get("messages", [])
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    language = detect_language(last_user_message) if last_user_message else "en"

    # Generate question using LLM (contextual, not hardcoded)
    question = await generate_next_question_llm(validation, requirements, language)

    return {
        "messages": [AIMessage(content=question)]
    }


def complete_node(state: CostEstimationState) -> Dict[str, Any]:
    """
    Mark requirements as complete and generate confirmation message.

    Returns completion flag and confirmation message.
    """
    requirements = state.get("requirements", {}) or {}

    # Get last user message for language detection
    messages = state.get("messages", [])
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    language = detect_language(last_user_message) if last_user_message else "en"

    # Generate confirmation
    if language == "ar":
        confirmation = "تمام! جاري حساب التكلفة..."
    else:
        confirmation = "Great! Calculating your estimate..."

    logger.info("Requirements gathering complete")

    return {
        "requirements_complete": True,
        "requirements": requirements,
        "messages": [AIMessage(content=confirmation)]
    }
