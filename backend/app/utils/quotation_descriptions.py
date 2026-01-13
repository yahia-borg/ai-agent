"""
Quotation Description Templates
Provides detailed Arabic descriptions for quotation items based on Egyptian construction standards
"""
import re
from typing import Optional, Dict, Any


# Standard compliance phrase used in all descriptions
STANDARD_COMPLIANCE_PHRASE = "طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف"

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
def _extract_details_from_context(item_name: str, context: str) -> Dict[str, Any]:
    """Extract additional details from conversation context to enrich item_details"""
    if not context:
        return {}
    
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


def get_category_description(
    category: str,
    item_name: str,
    quantity: float,
    unit: str,
    is_arabic: bool = True,
    item_details: Optional[Dict[str, Any]] = None,
    conversation_context: Optional[str] = None
) -> str:
    """
    Generate detailed Arabic description for a quotation item based on category.
    
    Args:
        category: Category of work (flooring, painting, plumbing, electrical, carpentry, plastering, etc.)
        item_name: Name of the item
        quantity: Quantity of the item
        unit: Unit of measurement
        is_arabic: Whether to return Arabic description (default True)
        item_details: Optional dictionary with additional details (dimensions, brand, color, finish, etc.)
        conversation_context: Optional conversation context to extract missing details
    
    Returns:
        Detailed Arabic description following Egyptian market standards
    """
    if not is_arabic:
        # Return English fallback (for testing/debugging)
        return f"{item_name} - {quantity} {unit}"
    
    # Auto-detect category from item name if category is "General"
    if category.lower() == "general" or not category:
        category = _detect_category_from_name(item_name)
    
    # Extract details from conversation context if item_details is None or incomplete
    if conversation_context and (not item_details or not isinstance(item_details, dict)):
        if not item_details:
            item_details = {}
        # Extract additional details from context
        context_details = _extract_details_from_context(item_name, conversation_context)
        if context_details:
            item_details.update(context_details)
    
    category_lower = category.lower()
    item_lower = item_name.lower()
    
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
        if unit in ['m²', 'm2', 'م²']:
            unit_prefix = "بالمتر المسطح"
        elif unit in ['m', 'م']:
            unit_prefix = "بالمتر الطولي"
        elif unit in ['sack', 'bag', 'كيس', 'شيكارة']:
            unit_prefix = "بالشيكارة"
        elif 'unit' in unit.lower() or 'عدد' in unit or 'مقطوعية' in unit:
            unit_prefix = "بالمقطوعية" if 'lump' in unit.lower() or 'مقطوعية' in unit else "بالعدد"
        else:
            unit_prefix = "بالعدد"
        
        return f"{unit_prefix} توريد وتركيب {item_name} {STANDARD_COMPLIANCE_PHRASE}"


def get_flooring_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate comprehensive flooring description matching real-world BOQ quality"""
    item_lower = item_name.lower()
    
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
    item_lower = item_name.lower()
    
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


def get_demolition_description(item_name: str, quantity: float, unit: str, item_details: Optional[Dict[str, Any]] = None) -> str:
    """Generate demolition/breaking work description"""
    
    description = (
        f"بالمقطوعية تكسير وفك {item_name} مع نقل المخلفات إلى المقالب العمومية "
        f"{STANDARD_COMPLIANCE_PHRASE}"
    )
    
    return description
