from app.models.quotation import Quotation, QuotationData
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.models.knowledge import KnowledgeItem
from sqlalchemy import or_
import json
import re
import logging
from typing import List, Dict, Any, Optional
import uuid
from app.agent.export import generate_pdf_quotation, generate_excel_quotation
from langchain_core.tools import tool
from app.utils.tool_cache import get_cached_result, set_cached_result
from app.utils.quotation_descriptions import get_category_description
import os

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
    Search for materials in the database using intelligent multi-strategy matching.
    
    This tool handles various query formats and database entry formats:
    - Database entries: "Marble (Local)", "Porcelain Tiles", "Hardwood Flooring"
    - User queries: "marble", "marble flooring", "wood floor tiles", "light beige marble"
    
    Search strategies (tried in order):
    1. Direct match: searches for exact query in name/category
    2. Keyword extraction: splits query into keywords and searches each
    3. Normalized search: removes parentheses and special characters
    4. Category fallback: searches category field if name search fails
    
    Examples of good queries:
    - "marble" → finds "Marble (Local)"
    - "porcelain tiles" → finds "Porcelain Tiles"
    - "hardwood" → finds "Hardwood Flooring"
    - "cement" → finds cement-related materials
    - "light beige marble" → extracts "marble" and finds "Marble (Local)"
    
    Returns JSON array of materials with: id, name, price, unit, currency, category.
    If no results, returns helpful message with suggestions.
    """
    # Check cache first
    cached = get_cached_result("search_materials", query)
    if cached is not None:
        return cached
    
    db = SessionLocal()
    try:
        # Normalize query
        normalized_query = normalize_query(query)
        keywords = extract_keywords(normalized_query)
        
        results = []
        search_strategies_tried = []
        
        # Strategy 1: Direct ILIKE match
        search_strategies_tried.append("direct_match")
        direct_results = db.query(Material).filter(
            or_(
                Material.name.ilike(f'%{normalized_query}%'),
                Material.category.ilike(f'%{normalized_query}%')
            )
        ).limit(10).all()
        results.extend(direct_results)
        
        # Strategy 2: Keyword matching (if no direct match or to get more results)
        if keywords:
            search_strategies_tried.append("keyword_extraction")
            for keyword in keywords:
                keyword_results = db.query(Material).filter(
                    or_(
                        Material.name.ilike(f'%{keyword}%'),
                        Material.category.ilike(f'%{keyword}%')
                    )
                ).limit(10).all()
                # Add only new results
                for r in keyword_results:
                    if r not in results:
                        results.append(r)
        
        # Strategy 3: Normalized search (remove parentheses, special chars)
        if not results:
            search_strategies_tried.append("normalized_search")
            clean_query = remove_special_chars(normalized_query)
            if clean_query != normalized_query:
                normalized_results = db.query(Material).filter(
                    or_(
                        Material.name.ilike(f'%{clean_query}%'),
                        Material.category.ilike(f'%{clean_query}%')
                    )
                ).limit(10).all()
                results.extend(normalized_results)
        
        # Remove duplicates while preserving order
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                unique_results.append(r)
        
        # Limit to 10 results
        results = unique_results[:10]
        
        # Log search results
        if results:
            result_names = [m.name for m in results]
            logger.info(f"search_materials query='{query}' found {len(results)} items: {result_names}")
        else:
            logger.info(f"search_materials query='{query}' - no results found")
        
        logger.debug(f"search_materials query='{query}' strategies={search_strategies_tried}")
        
        if not results:
            # Provide helpful error message with suggestions
            suggestions = []
            if keywords:
                suggestions.append(f"Try searching for: {', '.join(keywords[:3])}")
            result = json.dumps({
                "error": "No materials found matching that query.",
                "suggestions": suggestions,
                "query_used": query
            }, ensure_ascii=False)
        else:
            materials_list = []
            for m in results:
                materials_list.append({
                    "id": m.id,
                    "name": m.name,
                    "price": m.price_per_unit,
                    "unit": m.unit,
                    "currency": m.currency,
                    "category": m.category
                })
            
            result = json.dumps(materials_list, ensure_ascii=False)
        
        # Cache result
        set_cached_result("search_materials", result, query)
        return result

    except Exception as e:
        logger.error(f"Error searching materials: {str(e)}")
        return f"Error searching materials: {str(e)}"
    finally:
        db.close()

@tool
async def search_labor_rates(query: str) -> str:
    """
    Search for labor rates by role name using intelligent role extraction.
    
    This tool handles various query formats and database entry formats:
    - Database entries: "Skilled Worker (Mason)", "Unskilled Labor", "Foreman/Supervisor"
    - User queries: "mason", "mason worker", "electrician", "carpenter"
    
    Search strategies (tried in order):
    1. Direct match: searches for exact query in role field
    2. Role extraction: extracts role keyword from phrases (e.g., "mason worker" → "mason")
    3. Parentheses extraction: matches role inside parentheses (e.g., "mason" → "Skilled Worker (Mason)")
    4. Normalized search: handles special characters like "/" in "Foreman/Supervisor"
    
    Examples of good queries:
    - "mason" → finds "Skilled Worker (Mason)"
    - "electrician" → finds "Skilled Worker (Electrician)"
    - "unskilled" → finds "Unskilled Labor"
    - "foreman" → finds "Foreman/Supervisor"
    
    Returns JSON array of labor rates with: role, hourly_rate, currency.
    If no results, returns helpful message with suggestions.
    """
    # Check cache first
    cached = get_cached_result("search_labor_rates", query)
    if cached is not None:
        return cached
    
    db = SessionLocal()
    try:
        # Extract role keyword from query
        role_keyword = extract_role_keyword(query)  # "mason" from "mason worker"
        normalized_query = normalize_query(query)
        
        results = []
        search_strategies_tried = []
        
        # Strategy 1: Direct match
        search_strategies_tried.append("direct_match")
        direct_results = db.query(LaborRate).filter(
            LaborRate.role.ilike(f'%{normalized_query}%')
        ).limit(5).all()
        results.extend(direct_results)
        
        # Strategy 2: Role keyword match (extract from parentheses)
        if role_keyword and role_keyword != normalized_query:
            search_strategies_tried.append("role_extraction")
            role_results = db.query(LaborRate).filter(
                LaborRate.role.ilike(f'%{role_keyword}%')
            ).limit(5).all()
            # Add only new results
            for r in role_results:
                if r not in results:
                    results.append(r)
        
        # Strategy 3: Normalized search (handle "/" and special chars)
        if not results:
            search_strategies_tried.append("normalized_search")
            clean_query = remove_special_chars(normalized_query)
            if clean_query != normalized_query:
                normalized_results = db.query(LaborRate).filter(
                    LaborRate.role.ilike(f'%{clean_query}%')
                ).limit(5).all()
                results.extend(normalized_results)
        
        # Remove duplicates while preserving order
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                unique_results.append(r)
        
        # Limit to 5 results
        results = unique_results[:5]
        
        # Log search results
        if results:
            result_roles = [l.role for l in results]
            logger.info(f"search_labor_rates query='{query}' found {len(results)} roles: {result_roles}")
        else:
            logger.info(f"search_labor_rates query='{query}' - no results found")
            
        logger.debug(f"search_labor_rates query='{query}' role_keyword='{role_keyword}' strategies={search_strategies_tried}")
        
        if not results:
            # Provide helpful suggestions
            suggestions = []
            if role_keyword:
                suggestions.append(f"Try searching for: {role_keyword}")
            result = json.dumps({
                "error": "No labor rates found.",
                "suggestions": suggestions,
                "query_used": query
            }, ensure_ascii=False)
        else:
            labor_list = []
            for l in results:
                labor_list.append({
                    "role": l.role,
                    "hourly_rate": l.hourly_rate,
                    "currency": l.currency
                })
            
            result = json.dumps(labor_list, ensure_ascii=False)
        
        # Cache result
        set_cached_result("search_labor_rates", result, query)
        return result
    except Exception as e:
        logger.error(f"Error searching labor rates: {str(e)}")
        return f"Error searching labor rates: {str(e)}"
    finally:
        db.close()

@tool
async def search_standards(query: str) -> str:
    """
    Search the Knowledge Base for construction standards, codes, or technical specifications.
    Useful for finding mix ratios, consumption rates, or building code requirements.
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
    db = SessionLocal()
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
        db.commit()
        
        # Create QuotationData (items live in JSON)
        q_data = QuotationData(
            quotation_id=q_id,
            cost_breakdown=items,
            total_cost=total_amount
        )
        db.add(q_data)
        db.commit()
        
        # Return JSON with quotation info (files are generated on-demand via download endpoints)
        result = {
            "quotation_id": q_id,
            "total_cost": total_amount,
            "status": "completed",
            "message": f"Quotation #{q_id} created successfully. Total cost: {total_amount:.2f} EGP."
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        db.rollback()
        return json.dumps({"error": f"Error creating quotation: {str(e)}"})
    finally:
        db.close()


@tool
async def export_quotation_pdf(quotation_id: str) -> str:
    """
    Export a quotation as a PDF file.

    Args:
        quotation_id: The ID of the quotation to export.

    Returns:
        Success message with file path or error message.
    """
    db = SessionLocal()
    try:
        # Fetch quotation
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return f"Error: Quotation {quotation_id} not found."

        q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation_id).first()
        if not q_data or not q_data.cost_breakdown:
            return "Error: No cost breakdown found. Please create a quotation first."

        # Generate PDF
        items = q_data.cost_breakdown
        total_cost = q_data.total_cost or 0

        filepath = generate_pdf_quotation(quotation_id, items, total_cost)

        # Return success with file info
        filename = os.path.basename(filepath)
        return json.dumps({
            "success": True,
            "message": f"PDF generated successfully: {filename}",
            "filepath": filepath,
            "quotation_id": quotation_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return json.dumps({"error": f"Error generating PDF: {str(e)}"})
    finally:
        db.close()


@tool
async def export_quotation_excel(quotation_id: str) -> str:
    """
    Export a quotation as an Excel file.

    Args:
        quotation_id: The ID of the quotation to export.

    Returns:
        Success message with file path or error message.
    """
    db = SessionLocal()
    try:
        # Fetch quotation
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            return f"Error: Quotation {quotation_id} not found."

        q_data = db.query(QuotationData).filter(QuotationData.quotation_id == quotation_id).first()
        if not q_data or not q_data.cost_breakdown:
            return "Error: No cost breakdown found. Please create a quotation first."

        # Generate Excel
        items = q_data.cost_breakdown
        total_cost = q_data.total_cost or 0

        filepath = generate_excel_quotation(quotation_id, items, total_cost)

        # Return success with file info
        filename = os.path.basename(filepath)
        return json.dumps({
            "success": True,
            "message": f"Excel file generated successfully: {filename}",
            "filepath": filepath,
            "quotation_id": quotation_id
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error generating Excel: {str(e)}")
        return json.dumps({"error": f"Error generating Excel: {str(e)}"})
    finally:
        db.close()