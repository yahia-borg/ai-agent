import re
from typing import Literal


def detect_language(text: str) -> Literal["ar", "en", "mixed"]:
    """Detect if text is Arabic, English, or mixed"""
    if not text:
        return "en"
    
    # Arabic Unicode range: \u0600-\u06FF
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    
    arabic_chars = len(arabic_pattern.findall(text))
    total_chars = len(re.findall(r'\S', text))  # Non-whitespace characters
    
    if total_chars == 0:
        return "en"
    
    arabic_ratio = arabic_chars / total_chars
    
    if arabic_ratio > 0.3:
        # Check if there's also English
        english_pattern = re.compile(r'[a-zA-Z]')
        english_chars = len(english_pattern.findall(text))
        english_ratio = english_chars / total_chars
        
        if english_ratio > 0.2:
            return "mixed"
        return "ar"
    
    return "en"


def get_multilingual_prompt(language: str) -> dict:
    """Get multilingual prompts based on detected language"""
    prompts = {
        "ar": {
            "system": """أنت وكيل استخراج بيانات لمشاريع البناء في مصر.
استخرج المعلومات الرئيسية من أوصاف المشاريع وأعد بيانات JSON منظمة.
ركز على: نوع المشروع، المساحة بالمتر المربع، تفاصيل الموقع (المحافظة/المدينة)، الجدول الزمني، والمتطلبات الرئيسية.
يمكنك فهم النصوص بالعربية والإنجليزية.
الأسعار بالجنيه المصري (EGP).""",
            "extraction": """استخرج المعلومات المنظمة من وصف مشروع البناء هذا (مشروع في مصر):

"{description}"

الموقع: {location}
الرمز البريدي: {zip_code}
نوع المشروع: {project_type}
الجدول الزمني: {timeline}

أعد كائن JSON بالهيكل التالي:
{{
    "project_type": "residential|commercial|renovation|new_construction",
    "size_sqft": <رقم أو null>,
    "size_sqm": <رقم أو null>,
    "location_details": {{
        "city": "<اسم المدينة>",
        "governorate": "<اسم المحافظة>",
        "zip_code": "<الرمز البريدي>"
    }},
    "timeline_weeks": <رقم أو null>,
    "key_requirements": ["المتطلب1", "المتطلب2", ...],
    "confidence_score": <0.0 إلى 1.0>,
    "missing_information": ["ما هو مفقود"],
    "follow_up_questions": ["سؤال1", "سؤال2"],
    "detected_language": "ar|en|mixed"
}}

ملاحظة: استخرج المساحة بالمتر المربع (sqm).
الأسعار بالجنيه المصري (EGP).
كن دقيقاً ومحافظاً في تقدير درجات الثقة. أضف أسئلة متابعة فقط إذا كانت الثقة < 0.7."""
        },
        "en": {
            "system": """You are a construction project data extraction agent for Egypt.
Extract key information from project descriptions and return structured JSON data.
Focus on: project type, size (sqm or sq ft), location details (governorate/city), timeline, and key requirements.
You can understand texts in both Arabic and English.
Prices are in Egyptian Pounds (EGP).""",
            "extraction": """Extract structured information from this construction project description (project in Egypt):

"{description}"

Location: {location}
Zip Code: {zip_code}
Project Type: {project_type}
Timeline: {timeline}

Return a JSON object with the following structure:
{{
    "project_type": "residential|commercial|renovation|new_construction",
    "size_sqft": <number or null>,
    "size_sqm": <number or null>,
    "location_details": {{
        "city": "<city name>",
        "governorate": "<governorate name>",
        "zip_code": "<zip code>"
    }},
    "timeline_weeks": <number or null>,
    "key_requirements": ["requirement1", "requirement2", ...],
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"],
    "follow_up_questions": ["question1", "question2"],
    "detected_language": "ar|en|mixed"
}}

Note: Extract size in both sqft and sqm if mentioned. If only one is provided, calculate the other (1 sqm = 10.764 sqft).
Prices are in Egyptian Pounds (EGP).
Be accurate and conservative with confidence scores. Only include follow-up questions if confidence < 0.7."""
        },
        "mixed": {
            "system": """You are a construction project data extraction agent for Egypt that understands both Arabic and English.
Extract key information from project descriptions in any language and return structured JSON data.
Focus on: project type, size (sqm or sq ft), location details (governorate/city), timeline, and key requirements.
Respond in the same language(s) as the input when appropriate.
Prices are in Egyptian Pounds (EGP).""",
            "extraction": """Extract structured information from this construction project description (project in Egypt, may contain Arabic and/or English):

"{description}"

Location: {location}
Zip Code: {zip_code}
Project Type: {project_type}
Timeline: {timeline}

Return a JSON object with the following structure:
{{
    "project_type": "residential|commercial|renovation|new_construction",
    "size_sqft": <number or null>,
    "size_sqm": <number or null>,
    "location_details": {{
        "city": "<city name>",
        "governorate": "<governorate name>",
        "zip_code": "<zip code>"
    }},
    "timeline_weeks": <number or null>,
    "key_requirements": ["requirement1", "requirement2", ...],
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"],
    "follow_up_questions": ["question1", "question2"],
    "detected_language": "ar|en|mixed"
}}

Note: Extract size in both sqft and sqm if mentioned. If only one is provided, calculate the other (1 sqm = 10.764 sqft).
Prices are in Egyptian Pounds (EGP).
Be accurate and conservative with confidence scores. Only include follow-up questions if confidence < 0.7."""
        }
    }
    
    return prompts.get(language, prompts["en"])


def get_requirements_extraction_prompt(language: str) -> dict:
    """
    Get bilingual prompts for LLM-based requirements extraction.

    Used by requirements subgraph for intelligent extraction of project details
    from user messages with support for Arabic/English.

    Args:
        language: Language code ('ar', 'en', or 'mixed')

    Returns:
        Dict with 'system' and 'extraction' prompt templates
    """
    prompts = {
        "ar": {
            "system": """أنت مساعد لاستخراج متطلبات مشاريع البناء في مصر.
استخرج المعلومات من رسائل المستخدم وأعد JSON منظم.
ركز على: نوع المشروع، المساحة، عدد الغرف، حالة التشطيب الحالية، الستايل المطلوب، المستوى، والموقع.
يمكنك فهم العربية والإنجليزية.
الأسعار بالجنيه المصري (EGP).""",

            "extraction": """استخرج متطلبات المشروع من الرسالة التالية:

"{user_message}"

المتطلبات الحالية:
{current_requirements}

أعد JSON بالهيكل التالي (املأ فقط الحقول الموجودة في الرسالة):
{{
    "project_type": "residential|commercial|factory|null",
    "total_area_sqm": <رقم أو null>,
    "current_finishing_status": "bare_concrete|plastered|semi_finished|painted|null",
    "finishing_level": "basic|standard|premium|luxury|null",
    "bedrooms_count": <عدد أو null>,
    "bathrooms_count": <عدد أو null>,
    "living_rooms_count": <عدد أو null>,
    "kitchens_count": <عدد أو null>,
    "bedroom_size_sqm": <رقم أو null>,
    "bathroom_size_sqm": <رقم أو null>,
    "living_room_size_sqm": <رقم أو null>,
    "kitchen_size_sqm": <رقم أو null>,
    "desired_finishing_style": "modern|classic|minimal|luxury|null",
    "shops_count": <عدد أو null>,
    "offices_count": <عدد أو null>,
    "restrooms_count": <عدد أو null>,
    "commercial_type": "retail|office_building|mixed_use|null",
    "production_area_sqm": <رقم أو null>,
    "warehouse_area_sqm": <رقم أو null>,
    "office_area_sqm": <رقم أو null>,
    "factory_type": "light_manufacturing|heavy_industrial|warehouse|null",
    "confidence_score": <0.0 إلى 1.0>,
    "missing_information": ["ما هو مفقود"]
}}

ملاحظات مهمة:
- "residential" يشمل: شقة، فيلا، منزل، بيت، دوبلكس، تاون هاوس، بنتهاوس
- "commercial" يشمل: مكتب، محل، معرض، مول، متجر
- "factory" يشمل: مصنع، ورشة، مخزن
- "bare_concrete" = عظم، خرسانة | "plastered" = محارة | "semi_finished" = نصف تشطيب | "painted" = مدهون
- "basic" = بسيط، اقتصادي | "standard" = عادي، قياسي | "premium" = ممتاز | "luxury" = فاخر، لوكس
- استخرج عدد الغرف (bedrooms_count) ومساحاتها (bedroom_size_sqm) بشكل منفصل
- كن محافظاً في confidence_score"""
        },

        "en": {
            "system": """You are an assistant for extracting construction project requirements in Egypt.
Extract information from user messages and return structured JSON.
Focus on: project type, area, room count, current finishing status, desired style, level, and location.
You can understand both Arabic and English.
Prices are in Egyptian Pounds (EGP).""",

            "extraction": """Extract project requirements from this message:

"{user_message}"

Current requirements:
{current_requirements}

Return JSON with this structure (fill only fields mentioned in message):
{{
    "project_type": "residential|commercial|factory|null",
    "total_area_sqm": <number or null>,
    "current_finishing_status": "bare_concrete|plastered|semi_finished|painted|null",
    "finishing_level": "basic|standard|premium|luxury|null",
    "bedrooms_count": <number or null>,
    "bathrooms_count": <number or null>,
    "living_rooms_count": <number or null>,
    "kitchens_count": <number or null>,
    "bedroom_size_sqm": <number or null>,
    "bathroom_size_sqm": <number or null>,
    "living_room_size_sqm": <number or null>,
    "kitchen_size_sqm": <number or null>,
    "desired_finishing_style": "modern|classic|minimal|luxury|null",
    "shops_count": <number or null>,
    "offices_count": <number or null>,
    "restrooms_count": <number or null>,
    "commercial_type": "retail|office_building|mixed_use|null",
    "production_area_sqm": <number or null>,
    "warehouse_area_sqm": <number or null>,
    "office_area_sqm": <number or null>,
    "factory_type": "light_manufacturing|heavy_industrial|warehouse|null",
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"]
}}

Important notes:
- "residential" includes: apartment, villa, house, home, duplex, townhouse, penthouse
- "commercial" includes: office, shop, store, showroom, mall
- "factory" includes: factory, warehouse, plant, workshop
- Extract room counts (bedrooms_count) and sizes (bedroom_size_sqm) separately
- Be conservative with confidence_score"""
        },

        "mixed": {
            "system": """You are an assistant for extracting construction project requirements in Egypt.
You understand both Arabic and English and can extract information from mixed-language messages.
Focus on: project type, area, room count, current finishing status, desired style, level, and location.
Prices are in Egyptian Pounds (EGP).""",

            "extraction": """Extract project requirements from this message (may contain Arabic and/or English):

"{user_message}"

Current requirements:
{current_requirements}

Return JSON with this structure (fill only fields mentioned in message):
{{
    "project_type": "residential|commercial|factory|null",
    "total_area_sqm": <number or null>,
    "location": "<city name or null>",
    "rooms_breakdown": [
        {{"room_type": "bedroom|bathroom|living_room|kitchen", "area_sqm": <number>, "count": <count>}}
    ] or null,
    "current_finishing_status": "bare_concrete|plastered|semi_finished|painted|null",
    "desired_finishing_style": "<modern|classic|minimal or null>",
    "finishing_level": "basic|standard|premium|luxury|null",
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"]
}}

Important notes:
- "residential" includes: apartment, villa, house, home, duplex, townhouse, شقة، فيلا، منزل، بيت، دوبلكس
- "commercial" includes: office, shop, store, showroom, مكتب، محل، معرض
- "factory" includes: factory, warehouse, plant, مصنع، ورشة، مخزن
- Calculate total_area_sqm from room areas if possible
- If room count mentioned, add to rooms_breakdown
- Be conservative with confidence_score"""
        }
    }

    return prompts.get(language, prompts["en"])

