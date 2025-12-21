"""
Enhanced Markdown Parser for Mixed Format Files
Handles HTML tables, markdown tables, sections, and lists
Extracts Materials, Labor Rates, and Knowledge Items
"""
import os
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import markdown

# Exclusion patterns for invalid material entries
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


def parse_materials_from_md(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse materials from markdown file with mixed formats.
    Handles HTML tables, markdown tables, and structured sections.
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    materials = []
    source_doc = os.path.basename(file_path)
    
    # Convert markdown to HTML for table parsing
    html_content = markdown.markdown(md_content, extensions=['tables'])
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all tables (both HTML and markdown converted)
    tables = soup.find_all('table')
    
    current_category = "General"
    
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        rows = table.find_all('tr')
        
        # Skip if no headers or too few columns
        if not headers or len(headers) < 2:
            continue
        
        # Detect material table patterns
        has_price = any("price" in h.lower() or "سعر" in h or "جنيه" in h for h in headers)
        has_unit = any("unit" in h.lower() or "وحدة" in h or "الوحدة" in h for h in headers)
        has_material = any("material" in h.lower() or "نوع" in h or "النوع" in h or "product" in h.lower() or "منتج" in h for h in headers)
        
        # Skip tables that are clearly not about materials (demographics, economics, etc.)
        headers_text = ' '.join(h.lower() for h in headers)
        
        # Skip if table is clearly about demographics, economics, statistics, or sectors
        skip_table = False
        if any(pattern in headers_text for pattern in EXCLUDED_DEMOGRAPHIC_PATTERNS):
            skip_table = True
        if any(pattern in headers_text for pattern in EXCLUDED_ECONOMIC_PATTERNS):
            skip_table = True
        if any(pattern in headers_text for pattern in EXCLUDED_STATISTICAL_PATTERNS):
            skip_table = True
        if any(pattern in headers_text for pattern in EXCLUDED_SECTOR_PATTERNS):
            skip_table = True
        
        # Only skip if it's NOT actually a materials table
        if skip_table and not (has_material or any(keyword in headers_text for keyword in 
            ['material', 'product', 'item', 'type', 'name', 'brand', 'cement', 'steel', 'brick', 'concrete'])):
            continue
        
        # Check for category header row
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) == 1 or (len(cols) > 0 and cols[0].get('colspan')):
                text = cols[0].get_text(strip=True)
                if text and len(text) < 50 and not any(char.isdigit() for char in text[:5]):
                    current_category = text
                    continue
        
        # Detect CAPMAS format table (has "Jan/يناير 2025" column)
        # CAPMAS tables have structure: Commodity, Change rates (2 cols), Jan 2024, Jan 2025, Dec 2024, Unit, Arabic name
        is_capmas_format = False
        jan_2025_col_idx = -1
        headers_lower = [h.lower() for h in headers]
        
        # Look for "Jan/يناير 2025" pattern in headers
        for i, h in enumerate(headers):
            h_lower = h.lower()
            # Check for Jan 2025 pattern (case insensitive, handles Arabic)
            if (('jan' in h_lower or 'يناير' in h) and ('2025' in h or '٢٠٢٥' in h)) or \
               ('jan/يناير' in h_lower and '2025' in h):
                is_capmas_format = True
                # In CAPMAS format, headers have colspan, so we need to find the actual data column index
                # The header row structure makes it tricky, but we can use the header text to identify the column
                # We'll look for the column index by checking which column contains "2025" in header
                # For data rows, Jan 2025 is typically the 5th column (index 4): Commodity(0), Chg1(1), Chg2(2), Jan2024(3), Jan2025(4)
                # But we need to find it dynamically based on header content
                break
        
        # If CAPMAS format detected, try to find the actual column index by looking at a sample row
        # We'll identify it when parsing rows by looking for reasonable price values in columns
        
        # Parse material rows
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 2:
                continue
            
            vals = [col.get_text(strip=True) for col in cols]
            
            # Skip header rows
            if any("price" in v.lower() or "unit" in v.lower() or "material" in v.lower() 
                   or "سعر" in v or "وحدة" in v or "نوع" in v for v in vals):
                continue
            
            try:
                # Find price column
                price = None
                price_idx = -1
                unit = ""
                name = ""
                
                # For CAPMAS format tables, we need to find the Jan 2025 price column
                # Skip change rate columns (typically < 50, often in parentheses or percentages)
                if is_capmas_format:
                    # In CAPMAS format, the structure is:
                    # Col 0: Commodity name
                    # Col 1: Change rate Jan 2024 (percentage, usually < 50, may be negative, in parentheses)
                    # Col 2: Change rate Dec 2024 (percentage, usually < 50)
                    # Col 3: Jan 2024 price
                    # Col 4: Jan 2025 price (THIS IS WHAT WE WANT - latest price)
                    # Col 5: Dec 2024 price
                    # Col 6: Unit
                    # Col 7: Arabic name
                    
                    # Strategy: Find all numeric columns, filter out change rates, pick the middle/latest price
                    candidate_prices = []
                    for i, val in enumerate(vals):
                        # Skip first column (name) and last 2 columns (unit, Arabic name)
                        if i == 0 or i >= len(vals) - 2:
                            continue
                        
                        # Skip if value is in parentheses (indicates change rate/percentage)
                        val_stripped = val.strip()
                        if '(' in val_stripped or ')' in val_stripped:
                            continue
                        
                        cleaned = re.sub(r'[^\d.,-]', '', val_stripped)
                        cleaned = cleaned.replace(',', '')
                        
                        if cleaned:
                            try:
                                test_price = float(cleaned)
                        # Change rates are typically < 50 (percentages, often in parentheses)
                        # Actual prices vary: cement ~140, steel ~35000/ton, bricks ~1785/1000
                        # We want to skip change rates (< 50) and find actual prices (>= 50)
                        # For most materials in the table, prices are 100-50000 range
                                if test_price >= 50:  # Exclude change rates (percentages < 50)
                                    candidate_prices.append((i, test_price))
                            except ValueError:
                                continue
                    
                    # If we found candidate prices, prefer the one that's in the middle of the range
                    # (Jan 2025 is typically between Jan 2024 and Dec 2024, so middle value)
                    if candidate_prices:
                        # Sort by column index to get them in order
                        candidate_prices.sort(key=lambda x: x[0])
                        # In a well-formed CAPMAS table, we should have 3 prices: [Jan2024, Jan2025, Dec2024]
                        # Jan 2025 should be the middle one (index 1 in a list of 3)
                        if len(candidate_prices) >= 3:
                            # Take the middle price (should be Jan 2025)
                            price_idx, price = candidate_prices[1]
                        elif len(candidate_prices) >= 2:
                            # If only 2 prices, take the second one (likely Jan 2025 if table is truncated)
                            price_idx, price = candidate_prices[-1]
                        else:
                            # If only one candidate, use it
                            price_idx, price = candidate_prices[0]
                
                # If CAPMAS format detection failed or no price found, use fallback logic
                if price_idx == -1 or price is None:
                    # Look for price (number with currency or just number)
                    for i, val in enumerate(vals):
                        # Skip first and last columns (name and unit/description)
                        if i == 0 or i >= len(vals) - 1:
                            continue
                            
                        # Skip if value is in parentheses (indicates change rate/percentage)
                        if '(' in val or ')' in val:
                            continue
                        
                        # Clean and extract number
                        cleaned = re.sub(r'[^\d.,-]', '', val)
                        cleaned = cleaned.replace(',', '')
                        
                        # Check for price range
                        if '-' in cleaned:
                            parts = cleaned.split('-')
                            if len(parts) == 2:
                                try:
                                    p1 = float(parts[0].strip())
                                    p2 = float(parts[1].strip())
                                    price = (p1 + p2) / 2  # Average
                                    price_idx = i
                                    break
                                except ValueError:
                                    continue
                        else:
                            try:
                                test_price = float(cleaned)
                                # Skip percentages (change rates are typically < 50)
                                # For actual prices, expect higher values (100+ for most materials)
                                if 100 <= test_price <= 1000000:  # Reasonable price range, excluding percentages
                                    price = test_price
                                    price_idx = i
                                    break
                            except ValueError:
                                continue
                
                if price is None or price_idx == -1:
                    continue
                
                # Find name (usually first column or before price)
                for i in range(price_idx):
                    if vals[i] and len(vals[i]) > 2:
                        # Skip if looks like unit
                        if vals[i].lower() in ['m²', 'm2', 'm³', 'm3', 'ton', 'kg', 'unit', 'lot', 
                                               'طن', 'كيلو', 'متر', 'وحدة']:
                            continue
                        name = vals[i]
                        break
                
                # Find unit (usually after name, before price, or in separate column)
                # For CAPMAS format, unit is in second-to-last column
                if is_capmas_format and len(vals) >= 2:
                    # Unit is typically in the column before the last (Arabic name is last)
                    unit_candidate = vals[-2] if len(vals) >= 2 else ""
                    # CAPMAS units are like "50K.g/كجم/٥٠" - extract the unit type
                    unit_candidate_lower = unit_candidate.lower()
                    if 'kg' in unit_candidate_lower or 'كجم' in unit_candidate or 'كيلو' in unit_candidate:
                        # Extract number if present (e.g., "50kg" -> "50 kg" or just "kg")
                        if re.search(r'\d+', unit_candidate):
                            num_match = re.search(r'(\d+)', unit_candidate)
                            if num_match:
                                unit = f"{num_match.group(1)} kg"
                            else:
                                unit = "kg"
                        else:
                            unit = "kg"
                    elif 'ton' in unit_candidate_lower or 'طن' in unit_candidate:
                        unit = "ton"
                    elif 'm²' in unit_candidate or 'm2' in unit_candidate or 'متر مربع' in unit_candidate:
                        unit = "m²"
                    elif 'm³' in unit_candidate or 'm3' in unit_candidate or 'متر مكعب' in unit_candidate:
                        unit = "m³"
                    elif 'thousand' in unit_candidate_lower or 'ألف' in unit_candidate:
                        unit = "1000 units"
                    elif 'unit' in unit_candidate_lower or 'وحدة' in unit_candidate or 'bag' in unit_candidate_lower or 'كيس' in unit_candidate:
                        # For "50kg/كجم" format, it's actually per sack/bag
                        if '50' in unit_candidate or '٥٠' in unit_candidate:
                            unit = "sack (50kg)"
                        else:
                            unit = "unit"
                    else:
                        # Use the unit as-is if we can't parse it
                        unit = unit_candidate.split('/')[0].strip() if '/' in unit_candidate else unit_candidate
                
                if not unit:
                    # Fallback: Check column before price
                    if price_idx > 0 and price_idx > 1:
                        unit_candidate = vals[price_idx - 1]
                        if unit_candidate.lower() in ['m²', 'm2', 'm³', 'm3', 'ton', 'kg', 'unit', 'lot',
                                                       'طن', 'كيلو', 'متر', 'وحدة', 'bag', 'كيس']:
                            unit = unit_candidate
                    
                    # Also check headers for unit info
                    if not unit:
                        for h in headers:
                            if 'm²' in h or 'm2' in h:
                                unit = 'm²'
                            elif 'm³' in h or 'm3' in h:
                                unit = 'm³'
                            elif 'ton' in h.lower() or 'طن' in h:
                                unit = 'ton'
                            elif 'kg' in h.lower() or 'كيلو' in h or 'كجم' in h:
                                unit = 'kg'
                
                # Validate name
                if not name or len(name) < 3:
                    continue
                
                # Skip invalid patterns (basic patterns)
                invalid_patterns = ['figure', 'table', 'issue date', 'www.', '@', 'http', 
                                   'صورة', 'جدول', 'تاريخ', 'شكل', 'page', 'صفحة']
                if any(pattern in name.lower() for pattern in invalid_patterns):
                    continue
                
                # Skip excluded patterns (demographics, economics, currencies, locations, statistics, sectors)
                name_lower = name.lower()
                
                # Check each excluded pattern category more carefully
                if any(pattern in name_lower for pattern in EXCLUDED_DEMOGRAPHIC_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_ECONOMIC_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_CURRENCY_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_STATISTICAL_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_LOCATION_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_SECTOR_PATTERNS):
                    continue
                if any(pattern in name_lower for pattern in EXCLUDED_NON_CONSTRUCTION_PATTERNS):
                    continue
                
                # Additional validation: skip if it looks like a location (starts with location pattern)
                # or contains typical non-material indicators
                if any(name_lower.startswith(pattern) or f" {pattern} " in name_lower 
                       for pattern in EXCLUDED_LOCATION_PATTERNS):
                    continue
                
                # Skip entries that are clearly economic/statistical indicators
                indicator_patterns = ['indicator', 'index', 'balance', 'total', 'average', 'rate', 'ratio']
                if any(pattern in name_lower for pattern in indicator_patterns) and not any(
                    material_keyword in name_lower for material_keyword in 
                    ['cement', 'steel', 'brick', 'concrete', 'wood', 'glass', 'paint', 'tile', 'marble']
                ):
                    continue
                
                # Skip dates/years (patterns like "February 2024", "2024", etc.)
                if re.search(r'\b(19|20)\d{2}\b', name) or re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}', name_lower):
                    continue
                
                # Skip entries that are just numbers or look like codes
                if re.match(r'^[-]?\d+[.]?\d*$', name.strip()) or re.match(r'^[A-Z]-\s*\d+', name):
                    continue
                
                # Clean name
                name = re.sub(r'\s+', ' ', name).strip()
                name = name[:255]  # DB limit
                
                # Normalize unit
                if unit:
                    unit = unit.lower()
                    if unit in ['m2', 'm²']:
                        unit = 'm²'
                    elif unit in ['m3', 'm³']:
                        unit = 'm³'
                
                materials.append({
                    "name": name,
                    "category": current_category[:100] if current_category else "General",
                    "unit": unit or "unit",
                    "price_per_unit": price,
                    "currency": "EGP",
                    "source_document": source_doc
                })
                
            except (ValueError, IndexError) as e:
                continue
    
    return materials


def parse_labor_rates_from_md(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse labor rates from markdown file.
    Looks for labor-related sections and tables.
    Supports both daily and hourly wage formats.
    """
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    labor_rates = []
    source_doc = os.path.basename(file_path)
    
    # Convert to HTML
    html_content = markdown.markdown(md_content, extensions=['tables'])
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for labor-related sections
    labor_keywords = ['labor', 'worker', 'technician', 'craftsman', 'mason', 'carpenter',
                     'plumber', 'electrician', 'painter', 'tiler', 'foreman', 'supervisor',
                     'engineer', 'manager',
                     'عامل', 'عمال', 'نجار', 'بناء', 'مهندس', 'فني']
    
    tables = soup.find_all('table')
    
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        headers_lower = [h.lower() for h in headers]
        rows = table.find_all('tr')
        
        # Check if table is about labor (check headers for labor keywords)
        is_labor_table = any(keyword in ' '.join(headers_lower) for keyword in labor_keywords)
        
        # Also check for wage-related keywords in headers
        wage_keywords = ['wage', 'rate', 'hourly', 'daily', 'salary', 'payment', 'cost']
        has_wage_header = any(keyword in ' '.join(headers_lower) for keyword in wage_keywords)
        
        if not (is_labor_table or has_wage_header):
            continue
        
        # Determine if rates are daily or hourly based on headers
        is_daily_rate = any('daily' in h.lower() or 'day' in h.lower() for h in headers_lower)
        is_hourly_rate = any('hourly' in h.lower() or 'hour' in h.lower() for h in headers_lower)
        
        # Find the rate column index
        rate_col_idx = -1
        for i, h in enumerate(headers_lower):
            if any(keyword in h for keyword in ['wage', 'rate', 'cost', 'price', 'payment']):
                rate_col_idx = i
                break
        
        # If no explicit rate column found, assume it's after the role name (usually second column)
        if rate_col_idx == -1 and len(headers) >= 2:
            rate_col_idx = 1
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 2:
                continue
            
            vals = [col.get_text(strip=True) for col in cols]
            
            # Skip header rows
            if any(keyword in ' '.join(v.lower() for v in vals) for keyword in ['worker type', 'role', 'rate', 'wage', 'hourly', 'daily']):
                continue
            
            try:
                # Find role name (usually first column)
                role = ""
                role_candidate = vals[0].strip() if vals else ""
                
                # Material keywords to exclude (these are materials, not labor roles)
                material_keywords = ['brick', 'cement', 'steel', 'concrete', 'glass', 'gravel', 
                                    'sand', 'tile', 'marble', 'paint', 'wood', 'plaster', 'gypsum',
                                    'copper', 'aluminum', 'iron', 'diameter', 'elsen', 'granite',
                                    'foundry', 'oil', 'wheat', 'meat', 'poultry']
                
                # Check if first column contains labor keywords (must be a clear labor role)
                if role_candidate:
                    role_lower = role_candidate.lower()
                    
                    # Skip if it looks like a material name
                    if any(material_kw in role_lower for material_kw in material_keywords):
                        continue
                    
                    # Must contain explicit labor keywords to be considered a role
                    if any(keyword in role_lower for keyword in labor_keywords):
                        role = role_candidate
                
                # If no role found in first column, try finding one with keywords
                if not role:
                    for val in vals:
                        val_lower = val.lower().strip()
                        # Skip if it looks like a material
                        if any(material_kw in val_lower for material_kw in material_keywords):
                            continue
                        # Must contain labor keywords
                        if any(keyword in val_lower for keyword in labor_keywords):
                            role = val.strip()
                            break
                
                if not role:
                    continue
                
                # Additional validation: role must primarily be a labor role, not a material
                role_lower_final = role.lower()
                if any(material_kw in role_lower_final for material_kw in material_keywords):
                    continue
                
                # Find rate in the rate column or search all columns after role
                rate = None
                start_idx = rate_col_idx if rate_col_idx >= 0 else 1
                
                for j in range(start_idx, len(vals)):
                    val = vals[j]
                    # Clean and extract number (handle ranges like "250 - 400")
                    cleaned = re.sub(r'[^\d.,-]', '', val)
                    cleaned = cleaned.replace(',', '')
                    
                    # Check for price range
                    if '-' in cleaned:
                        parts = cleaned.split('-')
                        if len(parts) == 2:
                            try:
                                p1 = float(parts[0].strip())
                                p2 = float(parts[1].strip())
                                rate = (p1 + p2) / 2  # Average for ranges
                                break
                            except ValueError:
                                continue
                    else:
                        try:
                            candidate_rate = float(cleaned)
                            # Validate based on whether it's daily or hourly
                            if is_daily_rate:
                                # Daily rates typically 200-3000 EGP
                                if 200 <= candidate_rate <= 3000:
                                    rate = candidate_rate
                                    break
                            elif is_hourly_rate:
                                # Hourly rates typically 30-350 EGP
                                if 30 <= candidate_rate <= 350:
                                    rate = candidate_rate
                                    break
                            else:
                                # Unknown format, try both ranges
                                if 200 <= candidate_rate <= 3000:
                                    # Assume daily if in daily range
                                    rate = candidate_rate
                                    is_daily_rate = True
                                    break
                                elif 30 <= candidate_rate <= 350:
                                    # Assume hourly if in hourly range
                                    rate = candidate_rate
                                    break
                        except ValueError:
                            continue
                
                if role and rate:
                    # Convert daily to hourly if needed (divide by 8 hours)
                    if is_daily_rate:
                        hourly_rate = rate / 8.0
                    else:
                        hourly_rate = rate
                    
                    # Final validation: hourly rate should be in reasonable range
                    # Also verify role doesn't look like a material after cleaning
                    role_clean = re.sub(r'\*\*', '', role).strip()
                    role_clean_lower = role_clean.lower()
                    
                    material_keywords = ['brick', 'cement', 'steel', 'concrete', 'glass', 'gravel', 
                                        'sand', 'tile', 'marble', 'paint', 'wood', 'plaster', 'gypsum',
                                        'copper', 'aluminum', 'iron', 'diameter', 'elsen', 'granite',
                                        'foundry']
                    
                    # Skip if cleaned role looks like a material name
                    if any(material_kw in role_clean_lower for material_kw in material_keywords):
                        continue
                    
                    if 30 <= hourly_rate <= 350:
                        labor_rates.append({
                            "role": role_clean[:100],
                            "hourly_rate": hourly_rate,
                            "currency": "EGP",
                            "source_document": source_doc
                        })
                    
            except (ValueError, IndexError, TypeError):
                continue
    
    return labor_rates


def parse_knowledge_from_md(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse knowledge items from markdown file.
    Extracts meaningful sections with topics, filters out TOC and figure lists.
    """
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    knowledge_items = []
    source_doc = os.path.basename(file_path)
    
    # Convert to HTML
    html_content = markdown.markdown(md_content, extensions=['tables'])
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Filter out unwanted patterns
    unwanted_patterns = [
        'table of contents', 'toc', 'فهرس', 'قائمة',
        'list of figures', 'list of tables', 'قائمة الأشكال', 'قائمة الجداول',
        'figure', 'table', 'صورة', 'جدول'
    ]
    
    current_topic = None
    current_content = []
    
    # Process headers and paragraphs
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol']):
        text = tag.get_text(strip=True)
        
        if not text or len(text) < 10:
            continue
        
        # Skip unwanted content
        if any(pattern in text.lower() for pattern in unwanted_patterns):
            continue
        
        # Skip if looks like page number or metadata
        if re.match(r'^(page|صفحة)\s*\d+', text.lower()):
            continue
        
        # Header becomes new topic
        if tag.name in ['h1', 'h2', 'h3', 'h4']:
            # Save previous knowledge item
            if current_topic and current_content:
                content_text = '\n'.join(current_content).strip()
                if 50 <= len(content_text) <= 10000:  # Valid content length
                    knowledge_items.append({
                        "topic": current_topic[:100],
                        "content": content_text,
                        "source_document": source_doc,
                        "page_number": 1  # Markdown doesn't have pages
                    })
            
            # Start new topic
            current_topic = text[:100]
            current_content = []
        else:
            # Add to current content
            current_content.append(text)
    
    # Save last item
    if current_topic and current_content:
        content_text = '\n'.join(current_content).strip()
        if 50 <= len(content_text) <= 10000:
            knowledge_items.append({
                "topic": current_topic[:100],
                "content": content_text,
                "source_document": source_doc,
                "page_number": 1
            })
    
    return knowledge_items


if __name__ == "__main__":
    # Test
    test_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/clean/egypt-construction-costs-2025.md"))
    if os.path.exists(test_file):
        materials = parse_materials_from_md(test_file)
        print(f"Extracted {len(materials)} materials")
        if materials:
            print("Sample:", materials[0])
        
        labor = parse_labor_rates_from_md(test_file)
        print(f"Extracted {len(labor)} labor rates")
        
        knowledge = parse_knowledge_from_md(test_file)
        print(f"Extracted {len(knowledge)} knowledge items")

