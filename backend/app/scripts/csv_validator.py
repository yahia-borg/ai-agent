"""
CSV Validator for Materials, Labor Rates, and Knowledge Items
Validates data quality before database ingestion
"""
import csv
import os
import re
from typing import List, Dict, Any, Tuple

# Exclusion patterns for invalid material entries (same as in md_parser_enhanced.py)
EXCLUDED_DEMOGRAPHIC_PATTERNS = [
    'arabs', 'foreigners', 'egyptians', 'العرب', 'الأجانب', 'المصريين',
    'arab', 'foreigner', 'egyptian'
]

EXCLUDED_ECONOMIC_PATTERNS = [
    'indicator', 'balance', 'sector', 'financial', 'monetary', 'capital market',
    'trade', 'payment', 'export', 'import', 'gdp', 'inflation', 'economy',
    'economic', 'stock', 'market', 'index', 'exchange'
]

EXCLUDED_CURRENCY_PATTERNS = [
    'dollar', 'euro', 'sterling', 'currency', 'pound sterling', 'us dollar',
    'exchange rate', 'forex', 'usd', 'eur', 'gbp'
]

EXCLUDED_STATISTICAL_PATTERNS = [
    'population', 'unemployment', 'births', 'deaths', 'marriage', 'divorce',
    'labor force', 'employment', 'statistics', 'statistical', 'census',
    'demographic', 'demography'
]

EXCLUDED_LOCATION_PATTERNS = [
    'cairo', 'alexandria', 'giza', 'delta', 'coast', 'hurghada', 'upper egypt',
    'sheikh zayed', 'heliopolis', 'downtown', '6th october', '5th settlement',
    'north coast', 'red sea', 'obour', 'badr', 'new cities'
]

EXCLUDED_SECTOR_PATTERNS = [
    'manufacturing industries', 'constructions', 'agriculture', 'fishing',
    'retail trade', 'wholesale', 'banking', 'insurance', 'telecommunications',
    'real estate', 'renting', 'public administration', 'defense', 'education',
    'health', 'tourism', 'hotels', 'restaurants', 'governmental', 'non governmental',
    'electricity', 'water', 'sewerage', 'storage', 'transportation', 'information',
    'communication', 'financing', 'services', 'industry', 'sector'
]

EXCLUDED_NON_CONSTRUCTION_PATTERNS = [
    'wheat', 'meat', 'poultry', 'buffalo', 'cow', 'oil', 'cotton', 'seed',
    'fertilizer', 'food', 'grain', 'agricultural product'
]

# Combined exclusion patterns for quick checking
ALL_EXCLUDED_PATTERNS = (
    EXCLUDED_DEMOGRAPHIC_PATTERNS + EXCLUDED_ECONOMIC_PATTERNS +
    EXCLUDED_CURRENCY_PATTERNS + EXCLUDED_STATISTICAL_PATTERNS +
    EXCLUDED_LOCATION_PATTERNS + EXCLUDED_SECTOR_PATTERNS +
    EXCLUDED_NON_CONSTRUCTION_PATTERNS
)


def validate_materials(csv_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate materials CSV.
    Returns (valid_materials, invalid_materials)
    """
    valid = []
    invalid = []
    
    if not os.path.exists(csv_path):
        return valid, invalid
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            errors = []
            
            # Validate name
            name = row.get('name', '').strip()
            if not name or len(name) < 3:
                errors.append("Name too short or empty")
            elif len(name) > 255:
                errors.append("Name too long")
            else:
                name_lower = name.lower()
                # Check for invalid patterns (basic patterns)
                invalid_patterns = [
                    'figure', 'table', 'issue date', 'www.', '@', 'http',
                    'صورة', 'جدول', 'تاريخ', 'شكل', 'page', 'صفحة'
                ]
                if any(pattern in name_lower for pattern in invalid_patterns):
                    errors.append(f"Invalid name pattern: {name}")
                
                # Check for excluded patterns (demographics, economics, currencies, locations, statistics, sectors)
                excluded_categories = []
                if any(pattern in name_lower for pattern in EXCLUDED_DEMOGRAPHIC_PATTERNS):
                    excluded_categories.append("demographics")
                if any(pattern in name_lower for pattern in EXCLUDED_ECONOMIC_PATTERNS):
                    excluded_categories.append("economics")
                if any(pattern in name_lower for pattern in EXCLUDED_CURRENCY_PATTERNS):
                    excluded_categories.append("currency")
                if any(pattern in name_lower for pattern in EXCLUDED_STATISTICAL_PATTERNS):
                    excluded_categories.append("statistics")
                if any(pattern in name_lower for pattern in EXCLUDED_LOCATION_PATTERNS):
                    excluded_categories.append("location")
                if any(pattern in name_lower for pattern in EXCLUDED_SECTOR_PATTERNS):
                    excluded_categories.append("sector")
                if any(pattern in name_lower for pattern in EXCLUDED_NON_CONSTRUCTION_PATTERNS):
                    excluded_categories.append("non-construction")
                
                if excluded_categories:
                    errors.append(f"Excluded pattern detected ({', '.join(excluded_categories)}): {name}")
                
                # Additional validation: skip if it looks like a location or economic indicator
                if any(name_lower.startswith(pattern) or f" {pattern} " in name_lower 
                       for pattern in EXCLUDED_LOCATION_PATTERNS):
                    errors.append(f"Location pattern detected: {name}")
                
                # Skip entries that are clearly economic/statistical indicators (unless they're actual materials)
                indicator_patterns = ['indicator', 'index', 'balance', 'total', 'average', 'rate', 'ratio']
                if any(pattern in name_lower for pattern in indicator_patterns) and not any(
                    material_keyword in name_lower for material_keyword in 
                    ['cement', 'steel', 'brick', 'concrete', 'wood', 'glass', 'paint', 'tile', 'marble', 'aggregate']
                ):
                    errors.append(f"Economic/statistical indicator pattern detected: {name}")
                
                # Skip dates/years (patterns like "February 2024", "2024", etc.)
                if re.search(r'\b(19|20)\d{2}\b', name) or re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}', name_lower):
                    errors.append(f"Date/year pattern detected: {name}")
                
                # Skip entries that are just numbers or look like codes
                if re.match(r'^[-]?\d+[.]?\d*$', name.strip()) or re.match(r'^[A-Z]-\s*\d+', name):
                    errors.append(f"Number/code pattern detected: {name}")
            
            # Validate price
            try:
                price = float(row.get('price_per_unit', 0))
                if price < 10 or price > 1000000:
                    errors.append(f"Price out of range: {price}")
            except (ValueError, TypeError):
                errors.append("Invalid price")
            
            # Validate unit
            unit = row.get('unit', '').strip()
            valid_units = ['m²', 'm³', 'ton', 'kg', 'unit', 'lot', 'bag', 'كيس', 'طن', 'كيلو', 'متر', 'وحدة']
            if unit and unit.lower() not in [u.lower() for u in valid_units]:
                # Allow custom units but log
                pass
            
            # Validate category
            category = row.get('category', 'General').strip()
            if len(category) > 100:
                errors.append("Category too long")
            
            if errors:
                invalid.append({
                    'row': row,
                    'errors': errors
                })
            else:
                valid.append(row)
    
    return valid, invalid


def validate_labor_rates(csv_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate labor rates CSV.
    Returns (valid_labor, invalid_labor)
    """
    valid = []
    invalid = []
    
    if not os.path.exists(csv_path):
        return valid, invalid
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            errors = []
            
            # Validate role
            role = row.get('role', '').strip()
            if not role or len(role) < 3:
                errors.append("Role name too short or empty")
            elif len(role) > 100:
                errors.append("Role name too long")
            
            # Validate hourly rate (updated range: 30-350 EGP/hour to accommodate daily wage conversions)
            try:
                rate = float(row.get('hourly_rate', 0))
                if rate < 30 or rate > 350:
                    errors.append(f"Hourly rate out of range: {rate}")
            except (ValueError, TypeError):
                errors.append("Invalid hourly rate")
            
            if errors:
                invalid.append({
                    'row': row,
                    'errors': errors
                })
            else:
                valid.append(row)
    
    return valid, invalid


def validate_knowledge_items(csv_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate knowledge items CSV.
    Returns (valid_knowledge, invalid_knowledge)
    """
    valid = []
    invalid = []
    
    if not os.path.exists(csv_path):
        return valid, invalid
    
    unwanted_patterns = [
        'table of contents', 'toc', 'فهرس', 'قائمة',
        'list of figures', 'list of tables', 'قائمة الأشكال', 'قائمة الجداول'
    ]
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            errors = []
            
            # Validate topic
            topic = row.get('topic', '').strip()
            if not topic or len(topic) < 3:
                errors.append("Topic too short or empty")
            elif len(topic) > 100:
                errors.append("Topic too long")
            
            # Validate content
            content = row.get('content', '').strip()
            if len(content) < 50:
                errors.append("Content too short")
            elif len(content) > 10000:
                errors.append("Content too long")
            else:
                # Check for unwanted patterns
                if any(pattern in content.lower() for pattern in unwanted_patterns):
                    errors.append("Content contains unwanted patterns (TOC, figure lists, etc.)")
            
            # Validate page number
            try:
                page = int(row.get('page_number', 1))
                if page < 1:
                    errors.append("Invalid page number")
            except (ValueError, TypeError):
                errors.append("Invalid page number format")
            
            if errors:
                invalid.append({
                    'row': row,
                    'errors': errors
                })
            else:
                valid.append(row)
    
    return valid, invalid


def save_validation_report(valid: List[Dict], invalid: List[Dict], report_path: str):
    """Save validation report to file"""
    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Validation Report\n")
        f.write(f"{'='*50}\n\n")
        f.write(f"Valid entries: {len(valid)}\n")
        f.write(f"Invalid entries: {len(invalid)}\n\n")
        
        if invalid:
            f.write("Invalid Entries:\n")
            f.write(f"{'-'*50}\n")
            for item in invalid:
                f.write(f"Row: {item['row']}\n")
                f.write(f"Errors: {', '.join(item['errors'])}\n\n")


if __name__ == "__main__":
    import os
    # Test
    test_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/exports/test_materials.csv"))
    if os.path.exists(test_csv):
        valid, invalid = validate_materials(test_csv)
        print(f"Valid: {len(valid)}, Invalid: {len(invalid)}")

