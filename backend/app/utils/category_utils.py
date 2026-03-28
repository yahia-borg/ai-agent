"""
Consolidated category detection and material type detection utilities.
Replaces duplicated implementations in:
  - quotation_descriptions.py
  - agent/tools.py
  - agents/cost_calculator.py
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ── Synchronous versions (for use in non-async contexts) ──────────
# These use fallback keyword lists. The async versions below load from DB.

_CATEGORY_KEYWORDS_FALLBACK = {
    "flooring": ["flooring", "tile", "ceramic", "porcelain", "marble", "parquet", "أرضيات", "سيراميك", "بورسلين", "رخام"],
    "painting": ["paint", "painting", "دهان", "دهانات", "طلاء"],
    "plastering": ["plaster", "plastering", "بياض", "محارة", "تخشين"],
    "plumbing": ["plumbing", "plumber", "sanitaryware", "toilet", "sink", "shower", "سباكة", "مواسير", "حمام"],
    "electrical": ["electrical", "electrician", "wiring", "كهرباء", "أسلاك", "مفاتيح"],
    "carpentry": ["carpentry", "carpenter", "door", "window", "نجارة", "أبواب", "شبابيك"],
    "demolition": ["demolition", "breaking", "هدم", "تكسير"],
}

_MAT_TYPE_KEYWORDS_FALLBACK = {
    "tile": ["tile", "ceramic", "porcelain", "marble", "flooring"],
    "paint": ["paint", "walls", "painting"],
    "plaster": ["plaster", "plastering"],
    "pipes": ["pipe", "plumb", "plumbing"],
    "electrical": ["cable", "wire", "switch", "electric", "electrical"],
    "wood": ["wood", "parquet", "cabinet", "carpentry"],
    "waterproofing": ["waterproof", "insulation"],
    "door": ["door", "window", "doors_windows"],
    "ceiling": ["ceiling", "ceilings"],
}

_MATERIAL_TYPE_KEYWORDS_FALLBACK = {
    "tiles": ["tile", "ceramic", "porcelain", "floor tile", "بلاط", "سيراميك", "بورسلين"],
    "stone": ["marble", "granite", "رخام", "جرانيت"],
    "paint": ["paint", "emulsion", "coating", "دهان", "طلاء"],
    "plaster": ["plaster", "skim", "محارة", "بياض"],
    "cement": ["cement", "أسمنت"],
    "steel": ["steel", "iron", "rebar", "حديد"],
    "wood": ["wood", "timber", "parquet", "خشب", "باركيه"],
    "pipes": ["pipe", "diameter", "مواسير", "قطر"],
    "electrical": ["cable", "wire", "switch", "كهرباء", "سلك"],
    "glass": ["glass", "زجاج"],
    "brick": ["brick", "block", "طوب", "بلوك"],
    "vinyl": ["vinyl", "فينيل"],
}


def detect_category(item_name: str, keywords: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Auto-detect category from item name using keyword matching.

    Args:
        item_name: Name of the item
        keywords: Optional category keyword dict (loaded from config service).
                  Falls back to hardcoded keywords if not provided.

    Returns:
        Category string (e.g. 'flooring', 'painting', 'General')
    """
    if not item_name:
        return "General"

    item_lower = str(item_name).lower()
    kw_map = keywords or _CATEGORY_KEYWORDS_FALLBACK

    for category, kws in kw_map.items():
        if any(kw in item_lower for kw in kws):
            return category

    return "General"


def detect_material_type(name: str, category: str = "", keywords: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Detect material type for room multiplier lookup.

    Replaces the inline mat_type detection in cost_calculator.py lines 1169-1187.

    Args:
        name: Material name
        category: Material category
        keywords: Optional mat_type keyword dict from config service.

    Returns:
        Material type key (e.g. 'tile', 'paint', 'default')
    """
    if not name:
        return "default"

    name_lower = str(name).lower()
    category_lower = str(category).lower() if category else ""
    kw_map = keywords or _MAT_TYPE_KEYWORDS_FALLBACK

    for mat_type, kws in kw_map.items():
        if any(kw in name_lower or kw == category_lower for kw in kws):
            return mat_type

    return "default"


def detect_material_group(name: str, keywords: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Detect material group for deduplication (TYPE_KEYWORDS replacement).

    Args:
        name: Material name (can be str or dict)
        keywords: Optional material type keyword dict from config service.

    Returns:
        Material group (e.g. 'tiles', 'stone', 'paint', 'other')
    """
    if isinstance(name, dict):
        name = f"{name.get('en', '')} {name.get('ar', '')}"

    name_lower = str(name).lower()
    kw_map = keywords or _MATERIAL_TYPE_KEYWORDS_FALLBACK

    for mat_type, kws in kw_map.items():
        if any(kw in name_lower for kw in kws):
            return mat_type

    return "other"


def extract_details_from_context(item_name: str, context: str, existing_details: Optional[Dict[str, Any]] = None,
                                  brand_keywords: Optional[List[str]] = None,
                                  color_keywords: Optional[List[str]] = None,
                                  finish_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Extract additional details (brand, color, finish, dimensions) from conversation context.
    Consolidated from tools.py and quotation_descriptions.py.

    Args:
        item_name: Name of the item
        context: Conversation context text
        existing_details: Existing details dict to avoid overwriting
        brand_keywords: Optional list from config service
        color_keywords: Optional list from config service
        finish_keywords: Optional list from config service
    """
    import re

    if not context or not item_name:
        return {}

    if existing_details is None:
        existing_details = {}

    context_lower = str(context).lower()
    extracted = {}

    # Brand
    brands = brand_keywords or ["knauf", "jotun", "sico", "italian", "carrara", "egyptian", "local"]
    brand_display = {"knauf": "White Knauf", "jotun": "Jotun", "sico": "Sico"}
    for brand in brands:
        if brand in context_lower:
            if brand == "italian" and "carrara" in context_lower:
                extracted["brand"] = "Italian Carrara"
            elif brand in brand_display:
                extracted["brand"] = brand_display[brand]
            elif not existing_details.get("brand"):
                extracted["brand"] = brand.capitalize()
            break

    # Color
    colors = color_keywords or ["white", "beige", "light beige", "medium beige", "dark", "black", "cream", "brown"]
    for color in colors:
        if color in context_lower:
            extracted["color"] = color.title()
            break

    # Finish
    finishes = finish_keywords or ["matt", "matte", "glossy", "semi-glossy", "semi glossy", "satin"]
    for finish in finishes:
        if finish in context_lower:
            extracted["finish"] = finish.title()
            break

    # Dimensions
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

    # Context/application area
    area_keywords = ['sales area', 'boh', 'back office', 'safe room', 'bathroom', 'kitchen', 'living room', 'bedroom']
    for area in area_keywords:
        if area in context_lower:
            extracted['context'] = f"for {area.title()}" if 'for' not in area else area.title()
            break

    # Specifications/features
    spec_keywords = ['suspended', 'access doors', 'shadow gap', 'premium', 'luxury', 'standard']
    specs = [spec.title() for spec in spec_keywords if spec in context_lower]
    if specs:
        extracted['specifications'] = ', '.join(specs)

    return extracted
