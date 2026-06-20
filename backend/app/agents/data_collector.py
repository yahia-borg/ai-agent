import json
import re
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from app.agents.llm_client import get_llm_client
from app.models.quotation import Quotation, ProjectType
from app.models.project_data import ProjectData
from app.utils.language_detector import detect_language, get_multilingual_prompt


class DataCollectorAgent(BaseAgent):
    """Agent responsible for extracting project parameters from natural language (Arabic/English)"""
    
    def __init__(self):
        super().__init__("data_collector")
        self.llm = get_llm_client()
    
    def get_required_context(self) -> list[str]:
        return []
    
    async def execute(self, quotation: Quotation, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract project parameters from description (supports Arabic and English)"""

        # Detect language
        detected_lang = detect_language(quotation.project_description)

        # Get multilingual prompts
        prompts = get_multilingual_prompt(detected_lang)
        system_prompt = prompts["system"]

        # Format extraction prompt
        extraction_prompt = prompts["extraction"].format(
            description=quotation.project_description,
            location=quotation.location or 'Not specified' if detected_lang == "en" else 'غير محدد',
            project_type=quotation.project_type or 'Not specified' if detected_lang == "en" else 'غير محدد',
            timeline=quotation.timeline or 'Not specified' if detected_lang == "en" else 'غير محدد'
        )

        # Prepend the latest user message when provided by the supervisor tool call.
        # This ensures follow-up messages (e.g. "3 bedrooms", "fully finished") are
        # incorporated into extraction, not only the original project_description.
        additional_info = context.get("additional_info", "")
        if additional_info:
            label = "User's latest message" if detected_lang == "en" else "آخر رسالة من المستخدم"
            extraction_prompt = f"{label}: {additional_info}\n\n{extraction_prompt}"

        try:
            # Use structured output to ensure valid JSON and schema adherence
            extracted_data_model = await self.llm.invoke_structured(
                prompt=extraction_prompt,
                schema=ProjectData,
                system_prompt=system_prompt
            )

            # Convert Pydantic model to dictionary (model_dump() is the Pydantic v2 API)
            extracted_data = extracted_data_model.model_dump()

            # Validate and normalize (stays for defense in depth)
            extracted_data = self._normalize_data(extracted_data, quotation)

            # Pattern fallback: fill any null finish/size fields the LLM missed.
            # Local models (Mistral) often miss colloquial Arabic terms like "عالمحارة".
            # We scan both the original description AND the latest user message.
            full_text = " ".join(filter(None, [
                quotation.project_description or "",
                additional_info or "",
            ]))
            extracted_data = self._fill_missing_with_patterns(extracted_data, full_text)

            # Add detected language to extracted data
            extracted_data["detected_language"] = detected_lang
            
            # Determine if follow-up questions are needed
            # We use the confidence score from the model
            needs_followup = extracted_data.get("confidence_score", 0.0) < 0.7
            
            return {
                "extracted_data": extracted_data,
                "confidence_score": extracted_data.get("confidence_score", 0.5),
                "needs_followup": needs_followup,
                "follow_up_questions": (extracted_data.get("follow_up_questions") or [])[:2],
                "detected_language": detected_lang
            }
            
        except json.JSONDecodeError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"JSON parsing error in DataCollectorAgent: {str(e)}")
            return self._fallback_extraction(quotation)
        except Exception as e:
            # Log other errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in DataCollectorAgent.execute: {str(e)}", exc_info=True)
            # Fallback to basic extraction
            return self._fallback_extraction(quotation)
    
    def _fill_missing_with_patterns(self, data: Dict[str, Any], text: str) -> Dict[str, Any]:
        """
        Fill null extracted fields using regex/keyword patterns.
        Called after LLM extraction to recover fields the model missed,
        especially colloquial Arabic terms (e.g. "عالمحارة" → on_plaster).
        Only fills fields that are currently None/empty — never overwrites.

        A truthy 'unknown'-style sentinel from the LLM (e.g. current_finish_level
        = "unknown") counts as MISSING here, otherwise it would block the pattern
        fallback and then get normalised to None downstream — losing a value the
        user actually gave (e.g. Franco-Arabic "3ala el ma7ara").
        """
        text_lower = text.lower()

        # Demote sentinel strings to None so the `if not data.get(...)` guards below
        # fire and the regex/keyword fallback can recover the real value.
        _null_like = {"", "unknown", "null", "none", "not specified", "n/a", "na"}
        for _f in ("current_finish_level", "target_finish_level"):
            _v = data.get(_f)
            if isinstance(_v, str) and _v.strip().lower() in _null_like:
                data[_f] = None

        # current_finish_level — Arabic script, English, AND Franco-Arabic/Arabizi
        # (Latin-letter Egyptian Arabic, e.g. "3ala el ma7ara", "3al tob"). The
        # local model frequently fails to extract Franco-Arabic, so these patterns
        # are the safety net that keeps us from re-asking an already-answered question.
        if not data.get("current_finish_level"):
            if any(k in text_lower for k in [
                "عالمحارة", "على المحارة", "محارة", "on plaster", "on_plaster", "بياض", "متمحر",
                "ma7ara", "ma7arah", "mahara", "maharah", "mehara", "ma7ra", "el ma7ara", "3al ma7ara",
            ]):
                data["current_finish_level"] = "on_plaster"
            elif any(k in text_lower for k in [
                "عالطوب", "على الطوب", "طوب", "core shell", "core_shell", "هيكل", "عظم", "خرسانة",
                "tob", "toob", "el tob", "3al tob", "haykal", "3adm", "3azm", "kharsana",
            ]):
                data["current_finish_level"] = "core_shell"
            elif any(k in text_lower for k in [
                "نص تشطيب", "نصف تشطيب", "semi finished", "semi_finished", "شبه متشطب",
                "nos tashteeb", "nos tashtib", "nص tashteeb", "half finished",
            ]):
                data["current_finish_level"] = "semi_finished"
            elif any(k in text_lower for k in ["متشطب", "مشطوب", "fully finished", "fully_finished"]) and \
                 not any(k in text_lower for k in ["عايز", "عاوز", "محتاج", "want", "need", "3ayez", "3awez", "3aiz", "me7tag"]):
                # Only if describing current state, not desired target
                data["current_finish_level"] = "fully_finished"

        # target_finish_level — Arabic, English, AND Franco-Arabic
        if not data.get("target_finish_level"):
            if any(k in text_lower for k in [
                "سوبر لوكس", "super lux", "super luxury", "فاخر جداً", "ultra",
                "soper lux", "super loks", "soper loks",
            ]):
                data["target_finish_level"] = "turnkey"
            elif any(k in text_lower for k in [
                "لوكس", "luxury", "turnkey", "مفتاح", "فاخر",
                "lux", "loks", "fakher", "fa5er", "fakhir", "fa5ir",
            ]):
                data["target_finish_level"] = "turnkey"
            elif any(k in text_lower for k in [
                "تشطيب كامل", "fully finished", "fully_finished", "متشطبة كامل",
                "tashteeb kamel", "tashtib kamel", "kamel", "kaamel",
            ]):
                data["target_finish_level"] = "fully_finished"

        # size_sqm — only if truly missing
        if not data.get("size_sqm"):
            sqm = re.search(r'(\d+(?:\.\d+)?)\s*(?:sqm|m2|m²|متر مربع|متر\b|م²|م\s*مربع)', text_lower)
            if sqm:
                try:
                    data["size_sqm"] = float(sqm.group(1))
                except ValueError:
                    pass

        # num_floors — colloquial Arabic / franco-Arabic / English (e.g. "دورين",
        # "3ala doreen", "2 floors"). Only fill when the model missed it.
        if not data.get("num_floors"):
            m = re.search(
                r'(\d+)\s*(?:دور|أدوار|ادوار|طابق|طوابق|floors?|stor(?:e?y|ies)|adwar|dwar)',
                text_lower,
            )
            if m:
                try:
                    data["num_floors"] = max(1, int(m.group(1)))
                except ValueError:
                    pass
            elif any(k in text_lower for k in [
                "دورين", "دوريين", "طابقين", "دوبلكس", "duplex",
                "two floor", "two-floor", "two floors", "doreen", "dorein", "dawrein",
            ]):
                data["num_floors"] = 2
            elif any(k in text_lower for k in [
                "تلات ادوار", "تلات أدوار", "ثلاث ادوار", "ثلاثة طوابق",
                "three floor", "three floors", "talat adwar",
            ]):
                data["num_floors"] = 3

        return data

    def _normalize_data(self, data: Dict[str, Any], quotation: Quotation) -> Dict[str, Any]:
        """Normalize and validate extracted data"""
        # Use provided project_type if available
        if quotation.project_type:
            data["project_type"] = quotation.project_type.value
        
        # Ensure location_details exists and is properly formatted
        if "location_details" not in data or not isinstance(data["location_details"], dict):
            data["location_details"] = {}
        
        # Use provided zip_code if available
        if quotation.zip_code:
            data["location_details"]["zip_code"] = quotation.zip_code
        
        # Ensure status fields are strings or None
        if "current_finish_level" not in data:
            data["current_finish_level"] = None
        if "target_finish_level" not in data:
            data["target_finish_level"] = None
        
        # Ensure confidence score is between 0 and 1
        if "confidence_score" in data:
            data["confidence_score"] = max(0.0, min(1.0, float(data["confidence_score"])))
        else:
            data["confidence_score"] = 0.5
        
        return data
    
    def _fallback_extraction(self, quotation: Quotation) -> Dict[str, Any]:
        """Fallback extraction using simple pattern matching (supports Arabic and English)"""
        description = quotation.project_description.lower()
        detected_lang = detect_language(quotation.project_description)
        
        # Extract square meters (primary for Egypt - only unit used)
        sqm_match = re.search(r'(\d+)\s*(?:sqm|m2|m²|meter|متر|م²|م\s*مربع)', description, re.IGNORECASE)
        size_sqm = int(sqm_match.group(1)) if sqm_match else None
        
        # Determine project type from keywords (English and Arabic)
        project_type = None
        english_keywords = {
            "commercial": ["office", "commercial", "retail", "warehouse", "shop", "cafe", "coffee", "restaurant", "store", "showroom", "bank", "hotel", "hospital", "clinic", "school", "gym", "mall", "بنك", "فندق", "مستشفى", "عيادة", "مدرسة", "جيم", "مول", "كافيه", "قهوة", "مطعم", "معرض", "متجر", "محل", "صيدلية", "مكتب", "تجاري"],
            "residential": ["home", "house", "residential", "apartment", "villa", "unit", "منزل", "سكني", "شقة", "بيت", "فيلا", "وحدة", "دوبلكس", "بنتهاوس"],
            "new_construction": ["new construction", "build", "construct", "foundation", "بناء جديد", "بناء", "إنشاء", "تأسيس"]
        }
        
        for ptype, words in english_keywords.items():
            if any(word in description for word in words):
                project_type = ptype
                break
        
        # Extract finish levels (Fallback)
        current_finish = None
        target_finish = None
        
        finish_keywords = {
            "core_shell": ["core", "shell", "brick", "concrete", "طوب", "خرسانة", "عالطوب", "هيكل", "عظم"],
            "on_plaster": ["plaster", "محارة", "عالمحارة", "المحارة", "بياض", "متمحر"],
            "semi_finished": ["semi", "نص", "نصف", "شبه"],
            "fully_finished": ["fully", "finished", "كامل", "متشطب", "تشطيب كامل"],
            "turnkey": ["turnkey", "lux", "لوكس", "مفتاح", "فاخر", "سوبر لوكس", "luxury"]
        }
        
        # Simple extraction logic: check for "semi" or "finished" or "fully"
        if "semi" in description or "نص" in description:
            current_finish = "semi_finished"
        elif "plaster" in description or "محارة" in description:
            current_finish = "on_plaster"
        elif "brick" in description or "طوب" in description:
            current_finish = "core_shell"
            
        if "fully" in description or "كامل" in description or "turnkey" in description or "مفتاح" in description or "فاخر" in description or "lux" in description:
            target_finish = "fully_finished"
            if "lux" in description or "لوكس" in description or "turnkey" in description or "مفتاح" in description or "فاخر" in description or "سوبر" in description:
                target_finish = "turnkey"

        follow_up_question = (
            "What specific materials or finishes are you looking for?"
            if detected_lang == "en" else
            "ما هي المواد أو التشطيبات المحددة التي تبحث عنها؟"
        )
        
        return {
            "extracted_data": {
                "project_type": project_type or "residential",
                "size_sqm": size_sqm,
                "current_finish_level": current_finish,
                "target_finish_level": target_finish,
                "location_details": {},
                "key_requirements": [],
                "confidence_score": 0.5,
                "missing_information": ["Detailed requirements"] if detected_lang == "en" else ["المتطلبات التفصيلية"],
                "follow_up_questions": [],
                "detected_language": detected_lang
            },
            "confidence_score": 0.5,
            "needs_followup": True,
            "follow_up_questions": [follow_up_question],
            "detected_language": detected_lang
        }
