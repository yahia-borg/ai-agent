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
        
        try:
            # Use structured output to ensure valid JSON and schema adherence
            extracted_data_model = await self.llm.invoke_structured(
                prompt=extraction_prompt,
                schema=ProjectData,
                system_prompt=system_prompt
            )
            
            # Convert Pydantic model to dictionary
            extracted_data = extracted_data_model.dict()
            
            # Validate and normalize (stays for defense in depth)
            extracted_data = self._normalize_data(extracted_data, quotation)
            
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
            # Log the parsing error with more details
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"JSON parsing error in DataCollectorAgent: {str(e)}")
            logger.error(f"LLM Response: {response[:500] if 'response' in locals() else 'No response'}")
            # Fallback to basic extraction
            return self._fallback_extraction(quotation)
        except Exception as e:
            # Log other errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in DataCollectorAgent.execute: {str(e)}", exc_info=True)
            # Fallback to basic extraction
            return self._fallback_extraction(quotation)
    
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
        
        # Extract square meters (primary for Egypt)
        sqm_match = re.search(r'(\d+)\s*(?:sqm|m2|m²|meter|متر|م²|م\s*مربع)', description, re.IGNORECASE)
        size_sqm = int(sqm_match.group(1)) if sqm_match else None
        
        # Extract square footage (support both English and Arabic patterns)
        sqft_match = re.search(r'(\d+)\s*(?:sq\s*ft|square\s*feet|sf|قدم|قدم\s*مربع)', description, re.IGNORECASE)
        size_sqft = int(sqft_match.group(1)) if sqft_match else None
        
        # Convert if only one is found
        if size_sqm and not size_sqft:
            size_sqft = int(size_sqm * 10.764)  # Convert sqm to sqft
        elif size_sqft and not size_sqm:
            size_sqm = int(size_sqft * 0.092903)  # Convert sqft to sqm
        
        # Determine project type from keywords (English and Arabic)
        project_type = None
        english_keywords = {
            "commercial": ["office", "commercial", "retail", "warehouse", "shop", "cafe", "coffee", "restaurant", "store", "showroom"],
            "residential": ["home", "house", "residential", "apartment", "villa", "unit"],
            "renovation": ["renovation", "remodel", "renovate", "finish"],
            "new_construction": ["new construction", "build", "construct", "foundation"]
        }
        
        arabic_keywords = {
            "commercial": ["مكتب", "تجاري", "محل", "مستودع", "كافيه", "قهوة", "مطعم", "معرض", "متجر"],
            "residential": ["منزل", "سكني", "شقة", "بيت", "فيلا", "وحدة"],
            "renovation": ["تجديد", "ترميم", "إعادة", "تشطيب"],
            "new_construction": ["بناء جديد", "بناء", "إنشاء", "تأسيس"]
        }
        
        keywords = english_keywords if detected_lang == "en" else (
            arabic_keywords if detected_lang == "ar" else {**english_keywords, **arabic_keywords}
        )
        
        for ptype, words in keywords.items():
            if any(word in description for word in words):
                project_type = ptype
                break
        
        # Extract timeline (support weeks/months in both languages)
        timeline_match = re.search(r'(\d+)\s*(?:week|month|أسبوع|شهر|أسابيع|أشهر)', description)
        timeline_weeks = int(timeline_match.group(1)) if timeline_match else None
        
        follow_up_question = (
            "What specific materials or finishes are you looking for?"
            if detected_lang == "en" else
            "ما هي المواد أو التشطيبات المحددة التي تبحث عنها؟"
        )
        
        return {
            "extracted_data": {
                "project_type": project_type or "residential",
                "size_sqft": size_sqft,
                "size_sqm": size_sqm,
                "location_details": {},
                "timeline_weeks": timeline_weeks,
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

