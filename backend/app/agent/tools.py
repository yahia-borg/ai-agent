from app.models.quotation import Quotation, QuotationData
from app.core.database import SessionLocal
from app.core.db_context import get_or_create_async_db_session, db_session_context
from app.core.config import settings
from app.models.resources import Material, LaborRate
from app.models.knowledge import KnowledgeItem
from sqlalchemy import or_, text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import json
import re
import logging
from typing import List, Dict, Any, Optional
import uuid
# NOTE: Legacy export functions removed - use PDFGenerator and ExcelGenerator instead
from app.services.pdf_generator import PDFGenerator
from app.services.excel_generator import ExcelGenerator
from langchain_core.tools import tool
from app.utils.tool_cache import get_cached_result, set_cached_result
from app.utils.quotation_descriptions import get_category_description
from app.utils.language_detector import detect_language
import os
import datetime

logger = logging.getLogger(__name__)

# Helper function to detect category from item name
def _detect_category_from_name(item_name: str) -> str:
    """Auto-detect category from item name using keyword matching"""
    item_lower = item_name.lower()
    
    # Flooring
    if any(kw in item_lower for kw in ['flooring', 'tile', 'ceramic', 'porcelain', 'marble', 'parquet', 'أرضيات', 'سيراميك', 'بورسلين', 'رخام']):
        return "flooring"
    # Painting
    elif any(kw in item_lower for kw in ['paint', 'painting', 'دهان', 'دهانات', 'طلاء']):
        return "painting"
    # Plastering
    elif any(kw in item_lower for kw in ['plaster', 'plastering', 'بياض', 'محارة', 'تخشين']):
        return "plastering"
    # Plumbing
    elif any(kw in item_lower for kw in ['plumbing', 'plumber', 'sanitaryware', 'toilet', 'sink', 'shower', 'سباكة', 'مواسير', 'حمام']):
        return "plumbing"
    # Electrical
    elif any(kw in item_lower for kw in ['electrical', 'electrician', 'wiring', 'كهرباء', 'أسلاك', 'مفاتيح']):
        return "electrical"
    # Carpentry
    elif any(kw in item_lower for kw in ['carpentry', 'carpenter', 'door', 'window', 'نجارة', 'أبواب', 'شبابيك']):
        return "carpentry"
    # Demolition
    elif any(kw in item_lower for kw in ['demolition', 'breaking', 'هدم', 'تكسير']):
        return "demolition"
    
    return "General"

# Helper function to extract details from conversation context
def _extract_details_from_context(item_name: str, context: str, existing_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract additional details from conversation context to enrich item_details"""
    if not context:
        return {}
    
    if existing_details is None:
        existing_details = {}
    
    context_lower = context.lower()
    item_lower = item_name.lower()
    extracted = {}
    
    # Extract brand mentions
    brand_keywords = ['knauf', 'jotun', 'sico', 'italian', 'carrara', 'egyptian', 'local']
    for brand in brand_keywords:
        if brand in context_lower:
            if brand == 'italian' and 'carrara' in context_lower:
                extracted['brand'] = 'Italian Carrara'
            elif brand == 'knauf':
                extracted['brand'] = 'White Knauf'
            elif brand == 'jotun':
                extracted['brand'] = 'Jotun'
            elif brand == 'sico':
                extracted['brand'] = 'Sico'
            elif not existing_details.get('brand'):
                extracted['brand'] = brand.capitalize()
            break
    
    # Extract color mentions
    color_keywords = ['white', 'beige', 'light beige', 'medium beige', 'dark', 'black', 'cream', 'brown']
    for color in color_keywords:
        if color in context_lower:
            extracted['color'] = color.title()
            break
    
    # Extract finish mentions
    finish_keywords = ['matt', 'matte', 'glossy', 'semi-glossy', 'semi glossy', 'satin']
    for finish in finish_keywords:
        if finish in context_lower:
            extracted['finish'] = finish.title()
            break
    
    # Extract dimension mentions (basic pattern matching)
    dimension_patterns = [
        r'(\d+)\s*x\s*(\d+)\s*cm',
        r'(\d+)\s*cm\s*x\s*(\d+)\s*cm',
        r'(\d+)\s*mm',
        r'h\s*=\s*(\d+)\s*mm',
    ]
    for pattern in dimension_patterns:
        match = re.search(pattern, context_lower)
        if match:
            if 'x' in pattern:
                extracted['dimensions'] = f"{match.group(1)}X{match.group(2)} cm"
            elif 'h' in pattern:
                extracted['dimensions'] = f"H = {match.group(1)} mm"
            else:
                extracted['dimensions'] = f"{match.group(1)} mm"
            break
    
    # Extract context/application area
    area_keywords = ['sales area', 'boh', 'back office', 'safe room', 'bathroom', 'kitchen', 'living room', 'bedroom']
    for area in area_keywords:
        if area in context_lower:
            extracted['context'] = f"for {area.title()}" if 'for' not in area else area.title()
            break
    
    # Extract specifications/features
    spec_keywords = ['suspended', 'access doors', 'shadow gap', 'premium', 'luxury', 'standard']
    specs = []
    for spec in spec_keywords:
        if spec in context_lower:
            specs.append(spec.title())
    if specs:
        extracted['specifications'] = ', '.join(specs)
    
    return extracted

# Helper functions for query normalization and keyword extraction
def normalize_query(query: str) -> str:
    """Normalize query: lowercase, strip, handle Arabic/English"""
    return query.strip().lower()

def extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords, removing stop words"""
    stop_words = {'the', 'for', 'with', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'a', 'an'}
    words = query.lower().split()
    return [w for w in words if w not in stop_words and len(w) > 2]

def remove_special_chars(text: str) -> str:
    """Remove parentheses, special characters, normalize spacing"""
    text = re.sub(r'[()\[\]]', '', text)  # Remove parentheses and brackets
    text = re.sub(r'\s+', ' ', text)  # Normalize spaces
    return text.strip()

def extract_role_keyword(query: str) -> str:
    """Extract role keyword from phrases like 'mason worker' → 'mason'"""
    role_keywords = ['mason', 'electrician', 'plumber', 'carpenter', 'painter', 
                     'tiler', 'plasterer', 'foreman', 'supervisor', 'engineer']
    query_lower = query.lower()
    for role in role_keywords:
        if role in query_lower:
            return role
    # Fallback: return first meaningful word
    keywords = extract_keywords(query)
    return keywords[0] if keywords else query

@tool
async def search_materials(query: str) -> str:
    """
    Search for materials in the database using intelligent multilingual matching.
    
    DECISION CRITERIA:
    - Call when user asks about specific materials or prices
    - Call when you need material information for cost calculation
    - Use SIMPLE keywords (1-3 words) - avoid long descriptive phrases
    - Batch multiple material searches into fewer calls when possible
    - Do NOT call for general questions - only when specific materials are mentioned
    
    INPUT FORMAT:
    - query: Simple material name or keyword (1-3 words max)
      Examples: "cement", "أسمنت", "ceramic tile", "دهان", "marble"
      Avoid: "high quality Italian marble for flooring" → use "marble" instead
    
    OUTPUT FORMAT:
    - Returns: JSON array of materials with id, name (bilingual), price, unit, currency, category
    - If no results: Returns JSON with error message and suggestions
    - Format: [{"id": 1, "name": {"en": "...", "ar": "..."}, "price": 150.0, "unit": "bag", ...}, ...]
    
    STATE TRANSITIONS:
    - Does not modify state directly
    - Results used by calculate_costs for material pricing
    
    ERROR HANDLING:
    - If no results: Returns suggestions for similar materials
    - Automatically tries word splitting for compound queries
    - Always returns JSON (never crashes)
    
    EXAMPLES:
    - search_materials("cement") → Returns cement materials with prices in EGP
    - search_materials("أسمنت") → Returns Arabic-named cement materials
    - search_materials("ceramic tile") → Returns ceramic tile options
    """
    # Check cache first
    cache_key = query
    cached = get_cached_result("search_materials", cache_key)
    if cached is not None:
        return cached
    
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # Detect language from query
        detected = detect_language(query)
        language = "ar" if detected == "ar" else "en"
        
        # Use PostgreSQL multilingual search function
        result = await db.execute(
            text("""
                SELECT * FROM search_materials_multilingual(
                    :query,
                    :language,
                    NULL,  -- category_id (optional filter)
                    :limit
                )
            """),
            {"query": query, "language": language, "limit": settings.DEFAULT_SEARCH_LIMIT}
        )
        
        rows = result.fetchall()
        
        # If no results, try splitting compound queries into individual words
        if not rows and len(query.split()) > 1:
            logger.info(f"search_materials query='{query}' - no results, trying individual words")
            all_rows = []
            seen_ids = set()
            
            # Try each word separately
            words = query.split()
            for word in words:
                if len(word.strip()) < 2:  # Skip very short words
                    continue
                    
                word_result = await db.execute(
                    text("""
                        SELECT * FROM search_materials_multilingual(
                            :query,
                            :language,
                            NULL,
                            :limit
                        )
                    """),
                    {"query": word.strip(), "language": language, "limit": settings.WORD_SEARCH_LIMIT}
                )
                
                word_rows = word_result.fetchall()
                for row in word_rows:
                    if row.id not in seen_ids:
                        seen_ids.add(row.id)
                        all_rows.append(row)
            
            rows = all_rows[:settings.DEFAULT_SEARCH_LIMIT]  # Limit to default search limit
        
        if not rows:
            logger.warning(f"search_materials query='{query}' language='{language}' - no results found (tried full query and word splitting)")
            # Try to provide helpful suggestions based on common materials
            suggestions = []
            if language == "ar":
                suggestions = ["أسمنت", "بلاط", "دهان", "جص", "رخام", "سيراميك"]
            else:
                suggestions = ["cement", "tile", "paint", "plaster", "marble", "ceramic"]
            
            result_json = json.dumps({
                "error": "No materials found matching that query.",
                "suggestions": suggestions[:3],
                "query_used": query,
                "language": language
            }, ensure_ascii=False)
        else:
            materials_list = []
            # Eagerly load relationships to avoid lazy loading issues in async
            material_ids = [row.id for row in rows]
            materials_result = await db.execute(
                select(Material)
                .options(
                    selectinload(Material.category),
                    selectinload(Material.unit),
                    selectinload(Material.currency)
                )
                .filter(Material.id.in_(material_ids))
            )
            materials_dict = {m.id: m for m in materials_result.scalars().all()}
            
            for row in rows:
                material = materials_dict.get(row.id)
                if not material:
                    continue
                
                # Get category name (bilingual)
                category_name = None
                if material.category:
                    category_name = material.category.name
                
                # Get unit name (bilingual)
                unit_name = None
                if material.unit:
                    unit_name = material.unit.name
                
                # Get currency symbol
                currency_symbol = None
                if material.currency:
                    currency_symbol = material.currency.symbol
                
                materials_list.append({
                    "id": row.id,
                    "code": row.code,
                    "name": {
                        "en": row.name_en,
                        "ar": row.name_ar
                    },
                    "name_display": row.name_ar if language == "ar" else row.name_en,  # Display name based on language
                    "price": float(row.price),
                    "unit": unit_name,
                    "unit_id": row.unit_id,
                    "currency": currency_symbol or "EGP",
                    "currency_id": row.currency_id,
                    "category": category_name,
                    "category_id": row.category_id,
                    "relevance": float(row.relevance)
                })
            
            logger.info(f"search_materials query='{query}' language='{language}' found {len(materials_list)} items")
            result_json = json.dumps(materials_list, ensure_ascii=False)
        
        # Cache result
        set_cached_result("search_materials", result_json, cache_key)
        return result_json

    except Exception as e:
        logger.error(f"Error searching materials: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Error searching materials: {str(e)}"})
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()

@tool
async def search_labor_rates(query: str) -> str:
    """
    Search for labor rates by role name using intelligent multilingual matching.
    
    DECISION CRITERIA:
    - Call when user asks about labor costs or worker wages
    - Call when you need labor rate information for cost calculation
    - Use SIMPLE role names (1-2 words) - avoid long descriptions
    - Batch multiple role searches when possible
    - Do NOT call for general questions - only when specific roles are mentioned
    
    INPUT FORMAT:
    - query: Simple role name (1-2 words max)
      Examples: "mason", "بناء", "electrician", "كهربائي", "plumber", "سباك"
      Avoid: "skilled experienced mason worker" → use "mason" instead
    
    OUTPUT FORMAT:
    - Returns: JSON array of labor rates with role (bilingual), hourly_rate, daily_rate, currency
    - If no results: Returns JSON with error message and suggestions
    - Format: [{"id": 1, "role": {"en": "...", "ar": "..."}, "hourly_rate": 50.0, "daily_rate": 400.0, ...}, ...]
    
    STATE TRANSITIONS:
    - Does not modify state directly
    - Results used by calculate_costs for labor pricing
    
    ERROR HANDLING:
    - If no results: Returns suggestions for similar roles
    - Automatically tries word splitting for compound queries
    - Always returns JSON (never crashes)
    
    EXAMPLES:
    - search_labor_rates("mason") → Returns mason labor rates in EGP
    - search_labor_rates("بناء") → Returns Arabic-named mason rates
    - search_labor_rates("electrician") → Returns electrician hourly/daily rates
    """
    # Check cache first
    cache_key = query
    cached = get_cached_result("search_labor_rates", cache_key)
    if cached is not None:
        return cached
    
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # Detect language from query
        detected = detect_language(query)
        language = "ar" if detected == "ar" else "en"
        
        # Use PostgreSQL multilingual search function
        result = await db.execute(
            text("""
                SELECT * FROM search_labor_rates_multilingual(
                    :query,
                    :language,
                    NULL,  -- category_id (optional filter)
                    :limit
                )
            """),
            {"query": query, "language": language, "limit": settings.DEFAULT_SEARCH_LIMIT}
        )
        
        rows = result.fetchall()
        
        # If no results, try splitting compound queries into individual words
        if not rows and len(query.split()) > 1:
            logger.info(f"search_labor_rates query='{query}' - no results, trying individual words")
            all_rows = []
            seen_ids = set()
            
            # Try each word separately
            words = query.split()
            for word in words:
                if len(word.strip()) < 2:  # Skip very short words
                    continue
                    
                word_result = await db.execute(
                    text("""
                        SELECT * FROM search_labor_rates_multilingual(
                            :query,
                            :language,
                            NULL,
                            :limit
                        )
                    """),
                    {"query": word.strip(), "language": language, "limit": settings.WORD_SEARCH_LIMIT}
                )
                
                word_rows = word_result.fetchall()
                for row in word_rows:
                    if row.id not in seen_ids:
                        seen_ids.add(row.id)
                        all_rows.append(row)
            
            rows = all_rows[:settings.DEFAULT_SEARCH_LIMIT]  # Limit to default search limit
        
        if not rows:
            logger.warning(f"search_labor_rates query='{query}' language='{language}' - no results found (tried full query and word splitting)")
            # Try to provide helpful suggestions based on common labor roles
            suggestions = []
            if language == "ar":
                suggestions = ["بناء", "نجار", "كهربائي", "سباك", "دهان", "بلاط"]
            else:
                suggestions = ["mason", "carpenter", "electrician", "plumber", "painter", "tiler"]
            
            result_json = json.dumps({
                "error": "No labor rates found.",
                "suggestions": suggestions[:3],
                "query_used": query,
                "language": language
            }, ensure_ascii=False)
        else:
            labor_list = []
            # Eagerly load relationships to avoid lazy loading issues in async
            labor_ids = [row.id for row in rows]
            labor_result = await db.execute(
                select(LaborRate)
                .options(
                    selectinload(LaborRate.currency),
                    selectinload(LaborRate.category)
                )
                .filter(LaborRate.id.in_(labor_ids))
            )
            labor_dict = {l.id: l for l in labor_result.scalars().all()}
            
            for row in rows:
                labor = labor_dict.get(row.id)
                if not labor:
                    continue
                
                # Get currency symbol
                currency_symbol = None
                if labor.currency:
                    currency_symbol = labor.currency.symbol
                
                labor_list.append({
                    "id": row.id,
                    "code": row.code,
                    "role": {
                        "en": row.role_en,
                        "ar": row.role_ar
                    },
                    "role_display": row.role_ar if language == "ar" else row.role_en,  # Display name based on language
                    "hourly_rate": float(row.hourly_rate) if row.hourly_rate else None,
                    "daily_rate": float(row.daily_rate) if row.daily_rate else None,
                    "currency": currency_symbol or "EGP",
                    "currency_id": row.currency_id,
                    "skill_level": row.skill_level,
                    "category_id": row.category_id,
                    "relevance": float(row.relevance)
                })
            
            logger.info(f"search_labor_rates query='{query}' language='{language}' found {len(labor_list)} roles")
            result_json = json.dumps(labor_list, ensure_ascii=False)
        
        # Cache result
        set_cached_result("search_labor_rates", result_json, cache_key)
        return result_json

    except Exception as e:
        logger.error(f"Error searching labor rates: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Error searching labor rates: {str(e)}"})
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()

@tool
async def search_standards(query: str) -> str:
    """
    Search the Knowledge Base for construction standards, codes, or technical specifications.
    
    DECISION CRITERIA:
    - Call when user asks about building codes, standards, or technical requirements
    - Call when you need mix ratios, consumption rates, or finish level specifications
    - Use SHORT queries (1-5 words) - avoid long questions
    - Do NOT call for material/labor price questions (use search_materials/search_labor_rates)
    
    INPUT FORMAT:
    - query: Short technical query (1-5 words)
      Examples: "plaster mix ratio", "cement consumption", "finish level requirements", "building code"
      Avoid: "What is the proper mix ratio for plastering walls according to Egyptian standards?" → use "plaster mix ratio" instead
    
    OUTPUT FORMAT:
    - Returns: JSON array of knowledge items with topic, source, page, content_snippet
    - Format: [{"topic": "...", "source": "...", "page": 1, "content_snippet": "..."}, ...]
    
    STATE TRANSITIONS:
    - Does not modify state directly
    - Provides context for understanding requirements
    
    ERROR HANDLING:
    - If no results: Returns "No standards found in Knowledge Base."
    - Always returns formatted result (never crashes)
    
    EXAMPLES:
    - search_standards("plaster mix") → Returns plaster mix ratio standards
    - search_standards("finish level") → Returns finish level specifications
    """
    # Check cache first
    cached = get_cached_result("search_standards", query)
    if cached is not None:
        return cached
    
    try:
        from app.services.qdrant_service import get_qdrant_service
        qdrant = get_qdrant_service()
        
        # Use Qdrant for semantic search
        results = qdrant.search_knowledge(query, top_k=5)
        
        if not results:
            logger.info(f"search_standards query='{query}' - no results found")
            result = "No standards found in Knowledge Base."
        else:
            # Log retrieval results
            result_topics = [item.get("topic", "Unknown") for item in results]
            logger.info(f"search_standards query='{query}' found {len(results)} items: {result_topics}")

            # Format results
            items = []
            for item in results:
                # QdrantService.search_knowledge returns list of dicts or objects
                # Assuming it returns objects with 'payload' or similar, but let's check assumptions or use typical patterns
                # If QdrantService.search_knowledge returns what we expect (payloads):
                items.append({
                    "topic": item.get("topic", "Unknown"),
                    "source": item.get("source", "Unknown"),
                    "page": item.get("page", 0),
                    "content_snippet": item.get("content", "")[:500] + "..."
                })
            
            result = json.dumps(items, ensure_ascii=False)
            
        # Cache result
        set_cached_result("search_standards", result, query)
        return result

    except Exception as e:
        logger.error(f"Error searching standards in Qdrant: {str(e)}")
        # Fallback to empty if Qdrant fails, don't crash the agent
        return "Error searching knowledge base."

@tool
async def create_quotation(items_json: str, project_description: Optional[str] = None) -> str:
    """
    Creates a formal quotation record in the database.
    
    The argument `items_json` MUST be a valid JSON string representing a LIST of objects.
    Each object must have: "name" (str), "quantity" (float), "unit_price" (float), "unit" (str).
    
    RECOMMENDED fields for professional descriptions (inspired by real-world BOQ examples):
    - "category": Category of work (flooring, painting, plumbing, electrical, etc.)
    - "details": Comprehensive object with all mentioned attributes:
      * "brand": Manufacturer/brand name (e.g., "White Knauf", "Jotun", "Italian Carrara")
      * "color": Color specification (e.g., "Light Beige", "White", "Dark Color")
      * "finish": Finish type (e.g., "Matt", "semi-glossy", "glossy")
      * "dimensions": Size specifications (e.g., "60X60 cm", "12 mm", "H = 500 mm")
      * "specifications": Technical specs and features (e.g., "Suspended", "Access Doors", "Premium grade")
      * "context": Application area/context (e.g., "for Sales Area", "in BOH Area")
    
    Example with rich metadata:
    [
      {
        "name": "Marble Flooring",
        "quantity": 120,
        "unit_price": 1500,
        "unit": "m²",
        "category": "flooring",
        "details": {
          "brand": "Italian Carrara",
          "color": "Light Beige",
          "finish": "Matt",
          "dimensions": "60X60 cm",
          "specifications": "Premium grade, Suspended",
          "context": "for Sales Area"
        }
      }
    ]
    
    The `project_description` argument should contain a concise summary of the user's project requirements.
    If not provided, a default description will be used.
    
    Returns: JSON string with quotation_id and total_cost. PDF/Excel files are generated on-demand via download endpoints.
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        try:
            items = json.loads(items_json)
        except Exception as parse_err:
            return json.dumps({"error": "Invalid JSON format for items. Ensure it is a valid JSON string."})
        
        # Add detailed descriptions to items if not already present
        enriched_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            
            # If description already exists, keep it
            if "description" in item and item["description"]:
                enriched_items.append(item)
                continue
            
            # Generate description based on item name and category
            item_name = item.get("name", "")
            item_quantity = item.get("quantity", 0)
            item_unit = item.get("unit", "unit")
            item_category = item.get("category", "General")
            item_details = item.get("details")
            
            # Auto-detect category from item name if not provided
            if item_category == "General" or not item_category:
                item_category = _detect_category_from_name(item_name)
                item["category"] = item_category
            
            # Extract comprehensive details from conversation context if item_details is None or incomplete
            if not item_details or not isinstance(item_details, dict):
                item_details = {}
            
            # Enhance item_details with any additional context from project_description
            if project_description:
                enhanced_details = _extract_details_from_context(item_name, project_description, item_details)
                if enhanced_details:
                    item_details.update(enhanced_details)
                    item["details"] = item_details
            
            # Generate detailed Arabic description using all available data
            try:
                description = get_category_description(
                    category=item_category,
                    item_name=item_name,
                    quantity=item_quantity,
                    unit=item_unit,
                    is_arabic=True,
                    item_details=item_details if item_details else None,
                    conversation_context=project_description
                )
                item["description"] = description
            except Exception as desc_err:
                logger.warning(f"Description generation failed for {item_name}: {str(desc_err)}")
                # If description generation fails, use name as fallback
                item["description"] = item_name
            
            enriched_items.append(item)
        
        items = enriched_items
        total_amount = sum(item.get("quantity", 0) * item.get("unit_price", 0) for item in items)
        
        # Generate UUID for ID
        q_id = str(uuid.uuid4())
        
        # Use provided project description or fallback to default
        description = project_description if project_description and len(project_description.strip()) > 10 else "Agent Generated Quotation"
        
        # Create DB Record
        quotation = Quotation(
            id=q_id,
            project_description=description.strip(),
            status="completed"
        )
        db.add(quotation)
        await db.commit()
        
        # Create QuotationData (items live in JSON)
        q_data = QuotationData(
            quotation_id=q_id,
            cost_breakdown=items,
            total_cost=total_amount
        )
        db.add(q_data)
        await db.commit()
        
        # Return JSON with quotation info (files are generated on-demand via download endpoints)
        result = {
            "quotation_id": q_id,
            "total_cost": total_amount,
            "status": "completed",
            "message": f"Quotation #{q_id} created successfully. Total cost: {total_amount:.2f} EGP."
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return json.dumps({"error": f"Error creating quotation: {str(e)}"})
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()


@tool
async def export_quotation_pdf(quotation_id: str) -> str:
    """
    Export a quotation as a PDF file with detailed material breakdown.
    
    DECISION CRITERIA:
    - Call when user explicitly requests PDF export
    - Call only after calculate_costs has been executed (cost_breakdown must exist)
    - Do NOT call if quotation is not complete (no cost breakdown)
    
    INPUT FORMAT:
    - quotation_id: The quotation ID from current context (must have cost_breakdown)
    
    OUTPUT FORMAT:
    - Returns: JSON with success status, message, and quotation_id
    - Format: {"success": true, "message": "PDF generated successfully...", "quotation_id": "..."}
    - On error: Returns JSON with error message
    
    STATE TRANSITIONS:
    - Does not modify state
    - Generates PDF file in exports directory
    
    ERROR HANDLING:
    - If quotation not found: Returns error message
    - If no cost breakdown: Returns error asking to calculate costs first
    - Always returns JSON (never crashes)
    
    EXAMPLES:
    - export_quotation_pdf("quot-123") → Generates PDF with full BOQ breakdown
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # Fetch quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()
        if not quotation:
            return f"Error: Quotation {quotation_id} not found."

        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation_id)
        )
        q_data = q_data_result.scalar_one_or_none()
        if not q_data or not q_data.cost_breakdown:
            return "Error: No cost breakdown found. Please create a quotation first."

        # Generate PDF using professional service
        pdf_gen = PDFGenerator()
        pdf_buffer = pdf_gen.generate_quotation_pdf(quotation, q_data)
        
        # Save to exports directory for persistence
        filename = f"quotation_{quotation_id}_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(os.path.dirname(__file__), "../../../data/exports", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(pdf_buffer.getvalue())

        # Return success message (no download URL - user can download via UI buttons)
        return json.dumps({
            "success": True,
            "message": f"Professional PDF generated successfully. The quotation is ready for download.",
            "quotation_id": quotation_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return json.dumps({"error": f"Error generating PDF: {str(e)}"})
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()


@tool
async def export_quotation_excel(quotation_id: str) -> str:
    """
    Export a quotation as an Excel file with detailed material breakdown.
    
    DECISION CRITERIA:
    - Call when user explicitly requests Excel export
    - Call only after calculate_costs has been executed (cost_breakdown must exist)
    - Do NOT call if quotation is not complete (no cost breakdown)
    
    INPUT FORMAT:
    - quotation_id: The quotation ID from current context (must have cost_breakdown)
    
    OUTPUT FORMAT:
    - Returns: JSON with success status, message, and quotation_id
    - Format: {"success": true, "message": "Excel generated successfully...", "quotation_id": "..."}
    - On error: Returns JSON with error message
    
    STATE TRANSITIONS:
    - Does not modify state
    - Generates Excel file in exports directory
    
    ERROR HANDLING:
    - If quotation not found: Returns error message
    - If no cost breakdown: Returns error asking to calculate costs first
    - Always returns JSON (never crashes)
    
    EXAMPLES:
    - export_quotation_excel("quot-123") → Generates Excel with full BOQ breakdown
    """
    # Use context session if available, otherwise create new one
    db = await get_or_create_async_db_session()
    should_close = db_session_context.get() is None  # Only close if we created it
    
    try:
        # Fetch quotation
        result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
        quotation = result.scalar_one_or_none()
        if not quotation:
            return f"Error: Quotation {quotation_id} not found."

        q_data_result = await db.execute(
            select(QuotationData).filter(QuotationData.quotation_id == quotation_id)
        )
        q_data = q_data_result.scalar_one_or_none()
        if not q_data or not q_data.cost_breakdown:
            return "Error: No cost breakdown found. Please create a quotation first."

        # Generate Excel using professional service
        excel_gen = ExcelGenerator()
        excel_buffer = excel_gen.generate_quotation_excel(quotation, q_data)
        
        # Save to exports directory for persistence
        filename = f"quotation_{quotation_id}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
        filepath = os.path.join(os.path.dirname(__file__), "../../../data/exports", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(excel_buffer.getvalue())

        # Return success message (no download URL - user can download via UI buttons)
        return json.dumps({
            "success": True,
            "message": f"Professional Excel generated successfully. The quotation is ready for download.",
            "quotation_id": quotation_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error generating Excel: {str(e)}")
        return json.dumps({"error": f"Error generating Excel: {str(e)}"})
    finally:
        # Only close if we created the session (not from context)
        if should_close:
            await db.close()