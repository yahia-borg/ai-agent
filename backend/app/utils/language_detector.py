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
ركز على: نوع المشروع، المساحة (بالمتر المربع أو القدم المربع)، تفاصيل الموقع (المحافظة/المدينة)، الجدول الزمني، والمتطلبات الرئيسية.
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

ملاحظة: استخرج المساحة بالمتر المربع (sqm) والقدم المربع (sqft) إن وُجدت. إذا وُجدت واحدة فقط، احسب الأخرى (1 متر مربع = 10.764 قدم مربع).
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

