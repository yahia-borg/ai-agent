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
            "system": """أنت مساعد ذكي مصري بيتكلم عامية مصرية صرف، متخصص في استخراج بيانات مشاريع البناء.
هتستخرج المعلومات الرئيسية من أوصاف المشاريع وترجع بيانات JSON منظمة بس بالعامية المصرية في التعليقات أو الأسئلة المتابعة إذا لزم الأمر.
ركز على: نوع المشروع، المساحة (بالمتر المربع أو القدم)، الجدول الزمني، والمتطلبات الرئيسية.
بتفهم النصوص بالعامية المصرية أو الفصحى أو الإنجليزية.
الأسعار بالجنيه المصري (EGP).
**مهم جدًا**: كل رد منك لازم يكون بالعامية المصرية الفصيحة (مش فصحى، مش إنجليزي)، حتى لو الوصف بالإنجليزي. الـ JSON نفسه يفضل بالإنجليزي عشان الدقة، بس أي شرح أو أسئلة متابعة بالعامية.""",
            "extraction": """استخرج المعلومات المنظمة من وصف مشروع البناء ده بالعامية المصرية:
\"{description}\"
الموقع: {location}
نوع المشروع: {project_type}
الجدول الزمني: {timeline}

رجع كائن JSON بالهيكل ده، والحقول النصية زي key_requirements و missing_information و follow_up_questions لازم تكون بالعامية المصرية صرف:

{{
    "project_type": "تجاري|سكني|بناء_جديد|null",
    "size_sqm": <رقم أو null>,
    "current_finish_level": "على_الطوب|على_المحارة|نص_تشطيب|متشطب|تشطيب_قديم",
    "target_finish_level": "نص_تشطيب|تشطيب_كامل|تشطيب_فاخر|عالمفتاح|سوبر_لوكس",
    "key_requirements": ["...", "..."],
    "confidence_score": <0.0 - 1.0>,
    "missing_information": ["...", "..."],
    "follow_up_questions": ["...", "..."],
    "detected_language": "عربي|إنجليزي|مختلط"
}}

ملاحظة: المساحة بالمتر المربع (sqm).
الموقع لو موجود حطه في key_requirements.
كن دقيق في الثقة، وأضف أسئلة متابعة بس لو الثقة أقل من 0.7.
**الرد كله بالعامية المصرية إلا الـ JSON keys والقيم اللي هي options ثابتة.**"""
        },
        "en": {
            "system": """You are a construction project data extraction assistant.
Extract key information from project descriptions and return structured JSON data.
Focus on: project type, size (sqm), timeline, and key requirements.
You can understand texts in both Arabic and English.
Prices are in Egyptian Pounds (EGP).""",
            "extraction": """Extract structured information from this construction project description:

"{description}"

Location: {location}
Project Type: {project_type}
Timeline: {timeline}

Return a JSON object with the following structure:
{{
    "project_type": "commercial (office, shop, cafe, etc.)|residential (apartment, villa, etc.)|new_construction|null",
    "size_sqm": <number or null>,
    "current_finish_level": "core_shell|on_plaster|semi_finished|finished|old_finish",
    "target_finish_level": "semi_finished|fully_finished|luxury_finished|turnkey|super_lux",
    "key_requirements": ["requirement1", "requirement2", ...],
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"],
    "follow_up_questions": ["question1", "question2"],
    "detected_language": "ar|en|mixed"
}}

Note: Extract size in sqm.
Location is optional - if mentioned, add it to key_requirements.
Prices are in Egyptian Pounds (EGP).
Be accurate and conservative with confidence scores. Only include follow-up questions if confidence < 0.7."""
        },
        "mixed": {
            "system": """You are a construction project data extraction assistant that understands both Arabic and English.
Extract key information from project descriptions in any language and return structured JSON data.
Focus on: project type, size (sqm), location details (governorate/city), timeline, and key requirements.
Respond in the same language(s) as the input when appropriate.
Prices are in Egyptian Pounds (EGP).""",
            "extraction": """Extract structured information from this construction project description:

"{description}"

Location: {location}
Project Type: {project_type}
Timeline: {timeline}

Return a JSON object with the following structure:
{{
    "project_type": "commercial (office, shop, cafe, etc.)|residential (apartment, villa, etc.)|new_construction|null",
    "size_sqm": <number or null>,
    "current_finish_level": "core_shell|on_plaster|semi_finished|finished|old_finish",
    "target_finish_level": "semi_finished|fully_finished|luxury_finished|turnkey|super_lux",
    "key_requirements": ["requirement1", "requirement2", ...],
    "confidence_score": <0.0 to 1.0>,
    "missing_information": ["what's missing"],
    "follow_up_questions": ["question1", "question2"],
    "detected_language": "ar|en|mixed"
}}

Note: Extract size in sqm.
Location is optional - if mentioned, add it to key_requirements.
Prices are in Egyptian Pounds (EGP).
Be accurate and conservative with confidence scores. Only include follow-up questions if confidence < 0.7."""
        }
    }
    
    return prompts.get(language, prompts["en"])

