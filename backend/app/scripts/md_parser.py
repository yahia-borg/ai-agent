from bs4 import BeautifulSoup
import markdown
import os
import re
from typing import List, Dict, Any

def parse_markdown_materials(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses a markdown file containing HTML tables to extract material prices.
    Returns a list of material dictionaries.
    """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Convert Markdown to HTML (thoughtables are likely already HTML)
    html_content = markdown.markdown(md_content, extensions=['tables'])
    soup = BeautifulSoup(html_content, 'html.parser')
    
    materials = []
    
    # Tables in provided MD seem to be raw HTML <table> tags
    # We look for all tables
    tables = soup.find_all('table')
    


    for table in tables:
        # Heuristic: Check headers for "Commodity", "Unit", "Jan", "Dec" etc
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        
        # Check for egypt-construction-costs-2025 format: "Item", "Quantity", "Unit", "Unit Price", "Total Cost"
        is_generic_cost_table = any("Unit Price" in h for h in headers) and any("Item" in h for h in headers)

        # Check for Material price list: "Material", "Price", maybe "Quality"
        is_price_list_table = any("Material" in h for h in headers) and any("Price" in h for h in headers)

        # Check for CAPMAS format
        is_capmas_table = any("Commodity" in h or "السلعة" in h for h in headers)

        if not (is_capmas_table or is_generic_cost_table or is_price_list_table):
            continue
            
        # Parse rows
        rows = table.find_all('tr')
        category = "General"
        
        for row in rows:
            # Check for category header row (colspan usually)
            cols = row.find_all(['td', 'th'])
            if len(cols) == 1 or (len(cols) > 0 and cols[0].get('colspan')):
                 text = cols[0].get_text(strip=True)
                 if text and len(text) < 50: # Likely a category
                     category = text
                     continue

            vals = [col.get_text(strip=True) for col in cols]
            if len(vals) < 3: 
                continue

            try:
                if is_capmas_table:
                   if len(vals) >= 8:
                        price_str = vals[4].replace(',', '')
                        if not price_str or not price_str[0].isdigit(): price_str = vals[5].replace(',', '') 
                        
                        price = float(re.sub(r'[^\d.]', '', price_str))
                        name = vals[-1]
                        unit = vals[-2]
                        
                        mat_cat = category
                        if "Change rate" in mat_cat: mat_cat = "General"

                        materials.append({
                            "name": name,
                            "category": mat_cat,
                            "unit": unit,
                            "price_per_unit": price,
                            "currency": "EGP",
                            "source_document": os.path.basename(file_path)
                        })

                elif is_generic_cost_table:
                    # Item | Quantity | Unit | Unit Price | Total
                    # 0 | 1 | 2 | 3 | 4
                    if len(vals) >= 4:
                        name_raw = vals[0]
                        price_raw = vals[3]
                        
                        # Handle range
                        price_clean = re.sub(r'[^\d.-]', '', price_raw)
                        if '-' in price_clean:
                            parts = price_clean.split('-')
                            if len(parts) == 2 and parts[0] and parts[1]:
                                price = (float(parts[0]) + float(parts[1])) / 2
                            else:
                                price = float(re.sub(r'[^\d.]', '', price_raw))
                        else:
                             price = float(re.sub(r'[^\d.]', '', price_raw))
                        
                        unit = vals[2]
                        
                        materials.append({
                            "name": name_raw,
                            "category": category,
                            "unit": unit,
                            "price_per_unit": price,
                            "currency": "EGP",
                            "source_document": os.path.basename(file_path)
                        })

                elif is_price_list_table:
                     # Material | [Quality] | Price [Unit?]
                     # Varies. e.g. Material | Unit | Price (often) OR Material | Quality | Price/m2
                     
                     # Find price column index
                     price_idx = -1
                     for i, h in enumerate(headers):
                         if "Price" in h:
                             price_idx = i
                             break
                     if price_idx == -1: continue # Should not happen given heuristic

                     # Find unit if in headers
                     unit = "unit"
                     for h in headers:
                         if "m2" in h or "m²" in h: unit = "m2"
                         elif "ton" in h.lower(): unit = "ton"
                         elif "m3" in h.lower() or "m³" in h.lower(): unit = "m3"
                     
                     if len(vals) > price_idx:
                         name_raw = vals[0]
                         if len(vals) > 1 and "Quality" in headers[1]:
                             name_raw += f" ({vals[1]})" # Append quality to name

                         price_raw = vals[price_idx]
                         price_clean = re.sub(r'[^\d.-]', '', price_raw)
                         if '-' in price_clean:
                            parts = price_clean.split('-')
                            if len(parts) == 2 and parts[0] and parts[1]:
                                price = (float(parts[0]) + float(parts[1])) / 2
                            else:
                                price = float(re.sub(r'[^\d.]', '', price_raw))
                         else:
                             price = float(re.sub(r'[^\d.]', '', price_raw))
                             
                         # Check if unit is in col?
                         # Sometimes Unit is a column
                         unit_idx = -1
                         for i, h in enumerate(headers):
                             if "Unit" in h:
                                 unit_idx = i
                                 break
                         if unit_idx != -1 and len(vals) > unit_idx:
                             unit = vals[unit_idx]

                         materials.append({
                            "name": name_raw,
                            "category": category,
                            "unit": unit,
                            "price_per_unit": price,
                            "currency": "EGP",
                            "source_document": os.path.basename(file_path)
                        })

            except (ValueError, IndexError):
                continue
                

    return materials

def parse_markdown_knowledge(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses a markdown file to extract knowledge items based on headers.
    Headers (H1, H2, H3) become topics, and following text becomes content.
    """
    if not os.path.exists(file_path):
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    html_content = markdown.markdown(md_content)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    items = []
    current_topic = "General"
    current_content = []
    
    # Iterate through all tags
    for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol']):
        if tag.name in ['h1', 'h2', 'h3']:
            # Save previous item if exists
            if current_content:
                items.append({
                    "topic": current_topic,
                    "content": "\n".join(current_content).strip(),
                    "source_document": os.path.basename(file_path),
                    "page_number": 1 # Markdown doesn't have pages, default to 1
                })
                current_content = []
            
            # Start new topic
            current_topic = tag.get_text(strip=True)
        else:
            # Append content
            text = tag.get_text(strip=True)
            if text:
                current_content.append(text)
                
    # Add last item
    if current_content:
        items.append({
            "topic": current_topic,
            "content": "\n".join(current_content).strip(),
            "source_document": os.path.basename(file_path),
            "page_number": 1
        })
            
    return items


if __name__ == "__main__":
    # Test
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/compressed.md"))
    data = parse_markdown_materials(path)
    print(f"Extracted {len(data)} materials.")
    if data: print(data[0])
