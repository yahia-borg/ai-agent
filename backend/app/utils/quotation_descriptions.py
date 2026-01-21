"""
Quotation Description Templates
Provides detailed Arabic descriptions for quotation items based on Egyptian construction standards
"""
import re
from typing import Optional, Dict, Any, List


# Standard compliance phrase used in all descriptions
STANDARD_COMPLIANCE_PHRASE = "طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف"

# Helper function to detect category from item name
def _detect_category_from_name(item_name: str) -> str:
    """Auto-detect category from item name using keyword matching"""
    if not item_name:
        return "General"
    item_lower = str(item_name).lower()
    
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
def _extract_details_from_context(item_name: str, context: str) -> Dict[str, Any]:
    """Extract additional details from conversation context to enrich item_details"""
    if not context or not item_name:
        return {}
    
    context_lower = str(context).lower()
    item_lower = str(item_name).lower()
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
            else:
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


def get_material_description(
    material: Dict[str, Any],
    quantity: float,
    unit: str,
    phase_context: Optional[Dict[str, Any]] = None,
    project_type: str = "residential",
    language: str = "ar",
    qdrant_service: Optional[Any] = None,
    conversation_context: Optional[str] = None
) -> str:
    """
    Generate dynamic description based on actual material data and Qdrant knowledge.
    
    Args:
        material: Full material object from database with all properties
        quantity: Quantity needed
        unit: Unit of measurement
        phase_context: Enriched phase information from Qdrant (optional)
        project_type: Type of project (e.g., "residential", "commercial")
        language: Language preference ('ar' or 'en')
        qdrant_service: Qdrant service instance for knowledge retrieval (optional)
        conversation_context: Optional conversation context
    
    Returns:
        Dynamic Arabic/English description based on material data and standards
    """
    if language == "bilingual":
        ar_desc = _get_description_internal(material, quantity, unit, phase_context, project_type, "ar", qdrant_service)
        en_desc = _get_description_internal(material, quantity, unit, phase_context, project_type, "en", qdrant_service)
        return f"{en_desc}\n/ {ar_desc}"
    
    return _get_description_internal(material, quantity, unit, phase_context, project_type, language, qdrant_service)


def _get_description_internal(
    material: Dict[str, Any],
    quantity: float,
    unit: str,
    phase_context: Optional[Dict[str, Any]],
    project_type: str,
    language: str,
    qdrant_service: Optional[Any]
) -> str:
    """Internal helper to avoid recursion for bilingual mode"""
    # Extract material properties from database
    material_name = material.get("name") or ""
    if isinstance(material_name, dict):
        material_name = material_name.get(language, material_name.get("en", "")) or ""
    
    material_code = material.get("code", "")
    category = material.get("category") or "General"
    if isinstance(category, dict):
        category = category.get(language, category.get("en", "General")) or "General"
    
    # Query Qdrant for material-specific finishing standards (if service provided)
    # OPTIMIZATION: Disable per-material Qdrant queries to avoid excessive API calls
    # Each material was triggering 2 queries, causing 20+ queries for 10+ materials
    # Instead, use category-based descriptions which are faster and sufficient
    qdrant_knowledge = None
    # Disabled for performance - uncomment if needed for specific materials only
    # if qdrant_service and str(category).lower() in ["special", "luxury", "custom"]:
    #     try:
    #         # Query 1: Material-specific standards (only for special materials)
    #         material_query = f"{material_name} finishing requirements {category} {project_type}"
    #         material_standards = qdrant_service.search_knowledge(material_query, top_k=2)
    #         
    #         # Query 2: Material installation requirements
    #         installation_query = f"{material_name} installation requirements {project_type}"
    #         installation_results = qdrant_service.search_knowledge(installation_query, top_k=1)
    #         
    #         # Combine knowledge
    #         qdrant_knowledge = {
    #             "material_standards": material_standards,
    #             "installation_requirements": installation_results
    #         }
    #     except Exception as e:
    #         import logging
    #         logger = logging.getLogger(__name__)
    #         logger.warning(f"Error querying Qdrant for material description: {e}")
    
    # PRIORITIZE: Use DB description if available (it's the most accurate)
    db_description = material.get("db_description")
    if db_description and isinstance(db_description, dict):
        db_desc_text = db_description.get(language, db_description.get("en"))
        if db_desc_text:
            # Wrap DB description with standard BOQ phrases
            if language == "ar":
                return f"{_get_unit_prefix(unit)} توريد وتركيب {material_name} {db_desc_text} {_format_specs_ar(material)} {STANDARD_COMPLIANCE_PHRASE}"
            else:
                return f"Supply and install {material_name} {db_desc_text} {_format_specs_en(material)} According to technical specifications."

    # Extract material specifications from Qdrant knowledge
    specifications = _extract_specifications_from_qdrant(qdrant_knowledge, material_name, category)
    
    # Merge DB specifications with Qdrant specifications
    db_specs = material.get("specifications")
    if db_specs and isinstance(db_specs, dict):
        specifications.update(db_specs)
        
    # Generate description based on material type and category
    if language == "ar":
        return _generate_arabic_description(
            material=material,
            material_name=material_name,
            material_code=material_code,
            category=category,
            quantity=quantity,
            unit=unit,
            specifications=specifications,
            phase_context=phase_context,
            project_type=project_type
        )
    else:
        return _generate_english_description(
            material=material,
            material_name=material_name,
            material_code=material_code,
            category=category,
            quantity=quantity,
            unit=unit,
            specifications=specifications,
            phase_context=phase_context,
            project_type=project_type
        )

def _format_specs_ar(material: Dict[str, Any]) -> str:
    """Format extra specs for Arabic description"""
    parts = []
    brand = material.get("brand")
    code = material.get("code")
    if brand: parts.append(f"ماركة {brand}")
    if code: parts.append(f"(كود: {code})")
    return " ".join(parts)

def _format_specs_en(material: Dict[str, Any]) -> str:
    """Format extra specs for English description"""
    parts = []
    brand = material.get("brand")
    code = material.get("code")
    if brand: parts.append(f"Brand: {brand}")
    if code: parts.append(f"(Code: {code})")
    return " ".join(parts)


def _extract_specifications_from_qdrant(
    qdrant_knowledge: Optional[Dict[str, Any]],
    material_name: str,
    category: str
) -> Dict[str, Any]:
    """
    Extract material specifications from Qdrant knowledge.
    
    Returns:
        Dictionary with specifications: dimensions, brand, color, finish, standards, etc.
    """
    specs = {
        "dimensions": None,
        "brand": None,
        "color": None,
        "finish": None,
        "standards": [],
        "application": None,
        "installation_notes": []
    }
    
    if not qdrant_knowledge:
        return specs
    
    # Extract from material standards
    for result in qdrant_knowledge.get("material_standards", []):
        content = result.get("content", "").lower()
        
        # Extract dimensions
        # Fixed: escape * in regex pattern (was causing "nothing to repeat" error)
        dim_match = re.search(r'(\d+)\s*(?:x|×|\*)\s*(\d+)\s*(?:cm|سم)', content)
        if dim_match:
            specs["dimensions"] = f"{dim_match.group(1)} سم × {dim_match.group(2)} سم"
        
        # Extract standards
        if "ecp" in content or "es" in content or "iso" in content:
            std_match = re.findall(r'(ECP \d+-\d+|ES \d+[/-]\d+|ISO \d+)', content)
            if std_match:
                specs["standards"].extend(std_match)
        
        # Extract installation notes
        if "installation" in content or "تركيب" in content:
            specs["installation_notes"].append(result.get("content", ""))
    
    # Extract from installation requirements
    for result in qdrant_knowledge.get("installation_requirements", []):
        content = result.get("content", "")
        
        # Extract application area
        if "sales area" in content.lower() or "منطقة تجارية" in content:
            specs["application"] = "للمنطقة التجارية"
        elif "bathroom" in content.lower() or "حمام" in content:
            specs["application"] = "للحمام"
        elif "kitchen" in content.lower() or "مطبخ" in content:
            specs["application"] = "للمطبخ"
    
    return specs


def _generate_arabic_description(
    material: Dict[str, Any],
    material_name: str,
    material_code: str,
    category: str,
    quantity: float,
    unit: str,
    specifications: Dict[str, Any],
    phase_context: Optional[Dict[str, Any]],
    project_type: str
) -> str:
    """
    Generate Arabic description based on material data and specifications.
    """
    category_lower = (category or "").lower()
    material_lower = (material_name or "").lower()
    
    # Determine unit prefix
    unit_prefix = _get_unit_prefix(unit)
    
    # Base description structure
    description_parts = []
    
    # 1. Unit and material name
    description_parts.append(f"{unit_prefix} توريد وتركيب {material_name}")
    
    # 2. Material specifications from database
    if material_code:
        description_parts.append(f"(كود: {material_code})")
    
    # 3. Dimensions (from Qdrant or database)
    if specifications.get("dimensions"):
        description_parts.append(f"أبعاد {specifications['dimensions']}")
    
    # 4. Category-specific details
    if "paint" in material_lower or "دهان" in material_name:
        # Painting-specific
        description_parts.append(_get_painting_details(specifications, quantity, unit))
    elif "tile" in material_lower or "بلاط" in material_name or "سيراميك" in material_name:
        # Tile-specific
        description_parts.append(_get_tiling_details(specifications, material_name))
    elif "plaster" in material_lower or "محارة" in material_name:
        # Plastering-specific
        description_parts.append(_get_plastering_details(specifications))
    
    # 5. Standards compliance (from Qdrant)
    if specifications.get("standards"):
        stds = ", ".join(specifications["standards"][:3])  # Limit to 3 standards
        description_parts.append(f"طبقاً للمواصفات: {stds}")
    
    # 6. Application area (from Qdrant)
    if specifications.get("application"):
        description_parts.append(specifications["application"])
    
    # 7. Installation notes (from Qdrant)
    if specifications.get("installation_notes"):
        # Add first installation note
        note = specifications["installation_notes"][0][:100]  # Limit length
        description_parts.append(f"ملاحظات التركيب: {note}")
    
    # 8. Standard compliance phrase
    description_parts.append("طبقاً للأصول الصناعة والمواصفات الفنية وتعليمات المهندس المشرف")
    
    return " ".join([p for p in description_parts if p])


def _generate_english_description(
    material: Dict[str, Any],
    material_name: str,
    material_code: str,
    category: str,
    quantity: float,
    unit: str,
    specifications: Dict[str, Any],
    phase_context: Optional[Dict[str, Any]],
    project_type: str
) -> str:
    """
    Generate professional English description based on material data and specifications.
    """
    category_lower = (category or "").lower()
    material_lower = (material_name or "").lower()
    
    # Base description structure
    description_parts = []
    
    # 1. Action and material name
    description_parts.append(f"Supply and install {material_name}")
    
    # 2. Material code
    if material_code:
        description_parts.append(f"(Code: {material_code})")
    
    # 3. Dimensions
    if specifications.get("dimensions"):
        # Convert Arabic numbers/symbols if present
        dims = str(specifications["dimensions"]).replace("سم", "cm").replace("×", "x")
        description_parts.append(f"Dimensions: {dims}")
    
    # 4. Category-specific details
    if "paint" in material_lower or "دهان" in material_name:
        details = ["Washable type"]
        if specifications.get("finish"):
            details.append(specifications["finish"].lower())
        if quantity > 0 and unit in ['m²', 'm2']:
            details.append(f"for an area of {quantity:.0f} sqm")
        description_parts.append(", ".join(details))
        
    elif "tile" in material_lower or "بلاط" in material_name or "سيراميك" in material_name:
        details = []
        if "porcelain" in material_lower: details.append("Porcelain type")
        elif "ceramic" in material_lower: details.append("Ceramic type")
        elif "marble" in material_lower: details.append("Marble type")
        
        details.append("Including sand and mortar leveling layer")
        details.append("Samples to be approved prior to installation")
        details.append("Including matching 10cm height skirting")
        description_parts.append(". ".join(details))
        
    elif "plaster" in material_lower or "محارة" in material_name:
        description_parts.append("Cement and sand mortar (300kg cement per 3m³ sand)")
    
    # 5. Standards and compliance
    if specifications.get("standards"):
        stds = ", ".join(specifications["standards"][:3])
        description_parts.append(f"According to standards: {stds}")
    
    # 6. Standard closing
    description_parts.append("According to technical specifications, industry standards, and supervising engineer instructions.")
    
    return " ".join([p for p in description_parts if p])


def _get_unit_prefix(unit: str) -> str:
    """Get Arabic unit prefix based on unit"""
    if not unit:
        return "بالعدد"
    unit_lower = unit.lower()
    if unit_lower in ['m²', 'm2', 'م²', 'sqm']:
        return "بالمتر المسطح"
    elif unit_lower in ['m', 'م', 'meter']:
        return "بالمتر الطولي"
    elif unit_lower in ['sack', 'bag', 'كيس', 'شيكارة']:
        return "بالشيكارة"
    elif unit_lower in ['liter', 'l', 'لتر']:
        return "باللتر"
    else:
        return "بالعدد"


def _get_painting_details(specifications: Dict[str, Any], quantity: float, unit: str) -> str:
    """Get painting-specific details"""
    details = ["من النوع القابل للغسيل"]
    
    if specifications.get("finish"):
        finish = specifications["finish"]
        if "matt" in finish.lower():
            details.append("مات")
        elif "glossy" in finish.lower():
            details.append("لامع")
    
    if quantity > 0 and unit in ['m²', 'm2']:
        details.append(f"بمساحة {quantity:.0f} متر مربع")
    
    return " ".join(details)


def _get_tiling_details(specifications: Dict[str, Any], material_name: str) -> str:
    """Get tiling-specific details"""
    details = []
    
    # Material type
    if "porcelain" in material_name.lower() or "بورسلين" in material_name:
        details.append("من نوع بورسلين")
    elif "ceramic" in material_name.lower() or "سيراميك" in material_name:
        details.append("من نوع سيراميك")
    elif "marble" in material_name.lower() or "رخام" in material_name:
        details.append("من نوع رخام")
    
    # Installation details
    details.append("مع عمل طبقة التسوية من الرمل والمونة")
    details.append("تعتمد العينة قبل التركيب")
    details.append("تركيب وزرة من نفس النوع بارتفاع 10 سم")
    
    return " ".join(details)


def _get_plastering_details(specifications: Dict[str, Any]) -> str:
    """Get plastering-specific details"""
    return "من مونة الاسمنت والرمل بنسبة 300 كجم اسمنت لكل 3 م³ رمل"


def get_category_description(
    category: str,
    item_name: str,
    quantity: float,
    unit: str,
    language: str = "ar",
    is_arabic: bool = True,
    item_details: Optional[Dict[str, Any]] = None,
    conversation_context: Optional[str] = None
) -> str:
    """
    Generate detailed description for a quotation item based on category.
    
    Args:
        category: Category of work
        item_name: Name of the item
        quantity: Quantity of the item
        unit: Unit of measurement
        language: Language preference ('ar', 'en', or 'bilingual')
        is_arabic: Legacy support (mapped to 'ar' if True)
        item_details: Optional dictionary with additional details
        conversation_context: Optional conversation context
    """
    # Map legacy is_arabic to language if language is default
    if language == "ar" and not is_arabic:
        language = "en"
        
    if language == "bilingual":
        ar_desc = _get_category_description_internal(category, item_name, quantity, unit, True, item_details, conversation_context)
        en_desc = _get_category_description_internal(category, item_name, quantity, unit, False, item_details, conversation_context)
        return f"{en_desc}\n/ {ar_desc}"
    
    return _get_category_description_internal(category, item_name, quantity, unit, (language == "ar"), item_details, conversation_context)


def _get_category_description_internal(
    category: str,
    item_name: str,
    quantity: float,
    unit: str,
    is_arabic: bool,
    item_details: Optional[Dict[str, Any]],
    conversation_context: Optional[str]
) -> str:
    """Internal helper to avoid recursion for bilingual mode"""
    if not is_arabic:
        # Generate professional English description based on category
        return _generate_english_category_description(category, item_name, quantity, unit, item_details)
    
    category = category or "General"
    item_name = item_name or "Item"
    
    # Auto-detect category from item name if category is "General"
    if str(category).lower() == "general":
        category = _detect_category_from_name(item_name)
    
    # Extract details from conversation context if item_details is None or incomplete
    if conversation_context and (not item_details or not isinstance(item_details, dict)):
        if not item_details:
            item_details = {}
        # Extract additional details from context
        context_details = _extract_details_from_context(item_name, conversation_context)
        if context_details:
            item_details.update(context_details)
    
    category_lower = str(category).lower()
    item_lower = str(item_name).lower()
    
    # Flooring descriptions
    if any(keyword in category_lower or keyword in item_lower for keyword in 
           ['flooring', 'tile', 'ceramic', 'porcelain', 'marble', 'parquet', 'أرضيات', 'سيراميك', 'بورسلين']):
        return get_flooring_description(item_name, quantity, unit, item_details)
    
    # Painting descriptions
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['paint', 'painting', 'دهان', 'دهانات', 'طلاء']):
        return get_painting_description(item_name, quantity, unit, item_details)
    
    # Plastering descriptions
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['plaster', 'plastering', 'بياض', 'محارة', 'تخشين']):
        return get_plastering_description(item_name, quantity, unit, item_details)
    
    # Plumbing descriptions
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['plumbing', 'plumber', 'sanitaryware', 'toilet', 'sink', 'shower', 'سباكة', 'مواسير', 'حمام']):
        return get_plumbing_description(item_name, quantity, unit, item_details)
    
    # Electrical descriptions
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['electrical', 'electrician', 'wiring', 'كهرباء', 'أسلاك', 'مفاتيح']):
        return get_electrical_description(item_name, quantity, unit, item_details)
    
    # Carpentry descriptions
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['carpentry', 'carpenter', 'door', 'window', 'نجارة', 'أبواب', 'شبابيك']):
        return get_carpentry_description(item_name, quantity, unit, item_details)
    
    # Demolition/breaking work
    elif any(keyword in category_lower or keyword in item_lower for keyword in 
             ['demolition', 'breaking', 'هدم', 'تكسير']):
        return get_demolition_description(item_name, quantity, unit, item_details)
    
    # Default fallback
    else:
        # Generate basic description with unit prefix
        # Handle None unit
        unit = unit or ""
        unit_lower = unit.lower() if unit else ""

        if unit in ['m²', 'm2', 'م²']:
            unit_prefix = "بالمتر المسطح"
        elif unit in ['m', 'م']:
            unit_prefix = "بالمتر الطولي"
        elif unit in ['sack', 'bag', 'كيس', 'شيكارة']:
            unit_prefix = "بالشيكارة"
        elif unit_lower and ('unit' in unit_lower or 'عدد' in unit or 'مقطوعية' in unit):
            unit_prefix = "بالمقطوعية" if 'lump' in unit_lower or 'مقطوعية' in unit else "بالعدد"
        else:
            unit_prefix = "بالعدد"
        
        return f"{unit_prefix} توريد وتركيب {item_name} {STANDARD_COMPLIANCE_PHRASE}"


def get_flooring_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate comprehensive flooring description matching real-world BOQ quality"""
    item_name = item_name or "Flooring"
    item_lower = str(item_name).lower()
    
    # Determine tile type from item name (more specific matching)
    tile_type = "بورسلين"
    tile_size = "60 سم * 60 سم"
    if 'ceramic' in item_lower or 'سيراميك' in item_name:
        tile_type = "سيراميك"
        tile_size = "40 سم * 40 سم"  # Default ceramic size
    elif 'marble' in item_lower or 'رخام' in item_name:
        tile_type = "رخام"
        tile_size = "كما هو متعارف عليه"
    elif 'parquet' in item_lower or 'باركيه' in item_name or 'hardwood' in item_lower or 'wpc' in item_lower:
        # Distinguish between hardwood and WPC
        if 'wpc' in item_lower:
            tile_type = "WPC (خشب بلاستيك)"
        elif 'hardwood' in item_lower or 'wood' in item_lower:
            tile_type = "خشب طبيعي"
        else:
            tile_type = "باركيه"
        tile_size = "كما هو متعارف عليه"
    
    # Extract size from item_details if available (prioritize item_details)
    if item_details:
        if 'dimensions' in item_details:
            tile_size = str(item_details['dimensions'])
        elif 'size' in item_details:
            tile_size = str(item_details['size'])
        elif 'width' in item_details and 'height' in item_details:
            tile_size = f"{item_details['width']} سم * {item_details['height']} سم"
    
    # Include quantity and area information to make description unique
    area_info = ""
    if quantity > 0:
        if unit in ['m²', 'm2', 'م²']:
            area_info = f"بمساحة {quantity:.0f} متر مربع "
        elif unit in ['m', 'م']:
            area_info = f"بمساحة {quantity:.0f} متر طولي "
    
    # Include brand if available
    brand_info = ""
    if item_details and 'brand' in item_details:
        brand = item_details['brand']
        if 'knauf' in brand.lower():
            brand_info = "من انتاج شركة كنوف "
        elif 'jotun' in brand.lower():
            brand_info = "من انتاج شركة جوتن "
        elif 'italian' in brand.lower():
            brand_info = f"من انتاج {brand} "
        else:
            brand_info = f"من انتاج {brand} "
    
    # Include color if available
    color_info = "باللون المطلوب"
    if item_details and 'color' in item_details:
        color = item_details['color']
        color_info = f"باللون {color}"
    
    # Include finish if available
    finish_info = ""
    if item_details and 'finish' in item_details:
        finish = item_details['finish']
        if 'matt' in finish.lower() or 'matte' in finish.lower():
            finish_info = "مات "
        elif 'glossy' in finish.lower():
            finish_info = "لامع "
        elif 'semi' in finish.lower():
            finish_info = "نصف لامع "
    
    # Include context/application area if available
    context_info = ""
    if item_details and 'context' in item_details:
        context = item_details['context']
        if 'sales area' in context.lower():
            context_info = "للمنطقة التجارية "
        elif 'boh' in context.lower() or 'back office' in context.lower():
            context_info = "لمنطقة الخلفية "
    
    # Include specifications if available
    spec_info = ""
    if item_details and 'specifications' in item_details:
        specs = item_details['specifications']
        if 'premium' in specs.lower() or 'luxury' in specs.lower():
            spec_info = "من النوع المميز "
        elif 'suspended' in specs.lower():
            spec_info = "معلق "
    
    description = (
        f"بالمتر المسطح توريد وتركيب ارضيات {tile_type} أبعاد {tile_size} {color_info} {finish_info}"
        f"{area_info}{brand_info}{context_info}{spec_info}"
        f"مع عمل طبقة التسوية من الرمل والمونة وتعتمد العينة قبل التركيب "
        f"ومحمل على البند تركيب وزرة من نفس نوع {tile_type} بارتفاع 10 سم "
        f"والعمل طبقاً للأصول الصناعة والمواصفات الفنية والتنفيذ طبقاً للأبعاد الموضحة "
        f"بالرسومات الهندسية المعتمدة والحساب الهندسي"
    )
    
    return description


def get_painting_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate comprehensive painting description matching real-world BOQ quality"""
    item_name = item_name or "Painting"
    item_lower = str(item_name).lower()
    
    # Determine paint type and surface from item name
    paint_type = "بلاستيك"
    surface_type = "للحوائط"
    
    if 'ceiling' in item_lower or 'سقف' in item_name:
        surface_type = "للأسقف"
    elif 'wall' in item_lower or 'حائط' in item_name:
        surface_type = "للحوائط"
    
    if 'emulsion' in item_lower or 'إيمولشن' in item_name:
        paint_type = "بلاستيك إيمولشن"
    elif 'acrylic' in item_lower or 'أكريليك' in item_name:
        paint_type = "أكريليك"
    elif 'oil' in item_lower or 'زيتي' in item_name:
        paint_type = "زيتي"
    
    # Brand from item_details if available, otherwise from item name
    brand = "من انتاج شركة جوتن"
    if item_details and 'brand' in item_details:
        brand_name = item_details['brand']
        if 'jotun' in brand_name.lower():
            brand = "من انتاج شركة جوتن"
        elif 'sico' in brand_name.lower():
            brand = "من انتاج شركة سيكو"
        else:
            brand = f"من انتاج شركة {brand_name}"
    elif 'jotun' in item_lower or 'جوتن' in item_name:
        brand = "من انتاج شركة جوتن"
    elif 'sico' in item_lower or 'سيكو' in item_name:
        brand = "من انتاج شركة سيكو"
    
    # Include quantity/area to make description unique
    area_info = ""
    if quantity > 0:
        if unit in ['m²', 'm2', 'م²']:
            area_info = f"بمساحة {quantity:.0f} متر مربع "
        elif unit in ['liter', 'لتر', 'L']:
            area_info = f"بكمية {quantity:.0f} لتر "
    
    # Include color if available
    color_info = "بالألوان المطلوب"
    if item_details and 'color' in item_details:
        color = item_details['color']
        color_info = f"باللون {color}"
    
    # Include finish if available
    finish_info = ""
    if item_details and 'finish' in item_details:
        finish = item_details['finish']
        if 'matt' in finish.lower() or 'matte' in finish.lower():
            finish_info = "مات "
        elif 'glossy' in finish.lower():
            finish_info = "لامع "
        elif 'semi' in finish.lower():
            finish_info = "نصف لمعة "
        else:
            finish_info = "نصف لمعة "  # Default
    else:
        finish_info = "نصف لمعة "  # Default
    
    # Include context/application area if available
    context_info = ""
    if item_details and 'context' in item_details:
        context = item_details['context']
        if 'sales area' in context.lower():
            context_info = "للمنطقة التجارية "
        elif 'boh' in context.lower() or 'back office' in context.lower():
            context_info = "لمنطقة الخلفية "
    
    # Include specifications if available
    spec_info = ""
    if item_details and 'specifications' in item_details:
        specs = item_details['specifications']
        if 'premium' in specs.lower() or 'luxury' in specs.lower():
            spec_info = "من النوع المميز "
    
    description = (
        f"بالمتر المسطح توريد وعمل دهان {paint_type} {surface_type} من النوع القابل للغسيل "
        f"{finish_info}{color_info} {area_info}{brand} {context_info}{spec_info}"
        f"طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف"
    )
    
    return description


def get_plastering_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate plastering description based on real Egyptian market examples"""
    
    description = (
        f"بالمتر المسطح توريد وتنفيذ بياض تخشين للحوائط الداخلية من مونة الاسمنت والرمل "
        f"بنسبة 300 كجم اسمنت بورتلاندي عادي لكل 3 م³ رمل ويشمل البند عمل الطرطشة قبل بياض التخشين "
        f"من مونة تتكون من 450 كجم اسمنت / م³ رمل وترش بالمياه ثم عمل البؤج والأوتار على الميزان "
        f"مع معالجة الرشح والرطوبة إن وجدت والسعر يشمل إزالة البياض القديم المطبل ونقل المخلفات "
        f"إلى المقالب العمومية ويتم نهو العمل {STANDARD_COMPLIANCE_PHRASE}"
    )
    
    return description


def get_plumbing_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate plumbing description based on real Egyptian market examples"""
    item_name = item_name or "Plumbing item"
    item_lower = item_name.lower()
    
    # Determine if it's materials or installation work
    if any(keyword in item_lower for keyword in ['pipe', 'valve', 'fixture', 'مواسير', 'محابس', 'خلاطات']):
        description = (
            f"بالمقطوعية توريد وتركيب {item_name} طبقاً للمواصفات الفنية وأصول الصناعة "
            f"وتعليمات المهندس المشرف"
        )
    elif any(keyword in item_lower for keyword in ['toilet', 'sink', 'shower', 'مرحاض', 'حوض', 'دش']):
        description = (
            f"بالعدد توريد وتركيب {item_name} من النوع المطابق للمواصفات المصرية "
            f"{STANDARD_COMPLIANCE_PHRASE}"
        )
    else:
        description = (
            f"بالمقطوعية توريد وتركيب {item_name} {STANDARD_COMPLIANCE_PHRASE}"
        )
    
    return description


def get_electrical_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate electrical description based on real Egyptian market examples"""
    item_name = item_name or "Electrical item"
    item_lower = item_name.lower()
    
    # Determine if it's materials or installation
    if any(keyword in item_lower for keyword in ['wire', 'cable', 'أسلاك', 'كابلات']):
        description = (
            f"بالمتر الطولي توريد وتركيب {item_name} طبقاً للمواصفات الفنية المصرية "
            f"وأصول الصناعة وتعليمات المهندس المشرف"
        )
    elif any(keyword in item_lower for keyword in ['switch', 'outlet', 'socket', 'مفاتيح', 'مآخذ', 'برايز']):
        description = (
            f"بالعدد توريد وتركيب {item_name} من النوع المطابق للمواصفات المصرية "
            f"{STANDARD_COMPLIANCE_PHRASE}"
        )
    else:
        description = (
            f"بالمقطوعية توريد وتركيب {item_name} {STANDARD_COMPLIANCE_PHRASE}"
        )
    
    return description


def get_carpentry_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate carpentry description based on real Egyptian market examples"""
    item_name = item_name or "Carpentry item"
    item_lower = item_name.lower()
    
    # Extract dimensions from item_details if available
    dimensions = ""
    if item_details and 'dimensions' in item_details:
        dimensions = f"أبعاد {item_details['dimensions']}"
    elif item_details and 'size' in item_details:
        dimensions = f"أبعاد {item_details['size']}"
    
    if 'door' in item_lower or 'باب' in item_name:
        door_type = "مفصلية"
        if 'sliding' in item_lower or 'جرار' in item_name:
            door_type = "جرار"
        elif 'hinged' in item_lower:
            door_type = "مفصلية"
        
        description = (
            f"بالعدد توريد وتركيب باب {door_type} {dimensions} من المصانع المتخصصة "
            f"من خشب مسكي مع كسوة بلوط شامل المقابض والمفصلات وقفل إيطالي كمبيوتر "
            f"والكادر والدهان {STANDARD_COMPLIANCE_PHRASE}"
        )
    elif 'window' in item_lower or 'شباك' in item_name or 'نافذة' in item_name:
        description = (
            f"بالعدد توريد وتركيب {item_name} {dimensions} من المصانع المتخصصة "
            f"طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف"
        )
    else:
        description = (
            f"بالعدد توريد وتركيب {item_name} {dimensions} من المصانع المتخصصة "
            f"{STANDARD_COMPLIANCE_PHRASE}"
        )
    
    return description


    return description


def _generate_english_category_description(
    category: str,
    item_name: str,
    quantity: float,
    unit: str,
    item_details: Optional[Dict[str, Any]] = None
) -> str:
    """Generate detailed English category description equivalent to the Arabic version"""
    # Safety checks
    safe_category = str(category or "").lower() or _detect_category_from_name(str(item_name or "")).lower()
    safe_item_name = str(item_name or "Project item")
    
    # Determine item details
    brand = item_details.get('brand', 'Standard approved brand') if item_details else 'Standard approved brand'
    color = item_details.get('color', 'as requested') if item_details else 'as requested'
    dims = item_details.get('dimensions', item_details.get('size', 'standard size')) if item_details else 'standard size'
    
    if 'flooring' in safe_category:
        return (
            f"Supply and installation of flooring ({safe_item_name}), {dims}, color {color}. "
            f"Including sand and mortar leveling layer. Samples must be approved before installation. "
            f"Including 10cm matching skirting. Work to follow technical specifications and engineering drawings."
        )
    elif 'painting' in safe_category:
        return (
            f"Supply and application of washable paint ({safe_item_name}), {brand}. "
            f"Color {color}, finish as requested. According to technical specifications and industry standards."
        )
    elif 'plastering' in safe_category:
        return (
            f"Supply and execution of internal wall plastering (300kg cement per 3m³ sand). "
            f"Including spatter dash (450kg cement/m³ sand), leveling, and verticality check using master line and level."
        )
    
    return f"Supply and installation of {safe_item_name}. According to technical specifications, industry standards, and supervising engineer instructions."
