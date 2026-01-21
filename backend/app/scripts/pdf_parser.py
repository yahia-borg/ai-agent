import pdfplumber
import re
import os
from typing import List, Dict, Any

def extract_data_from_pdfs(data_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extracts material and labor data from PDFs in the given directory.
    Returns a dictionary with keys 'materials' and 'labor_rates'.
    """
    materials = []
    labor_rates = []
    
    if not os.path.exists(data_dir):
        print(f"Directory not found: {data_dir}")
        return {"materials": [], "labor_rates": []}

    for filename in os.listdir(data_dir):
        if not filename.endswith(".pdf"):
            continue

        # Skip scanning/parsing for known image-only/unsupported PDFs if text extraction isn't needed
        # We only really care about materials/labor from tables here, but we now have MD files for that.
        # So we might want to skip the problematic ones or just let them fail gracefully.
        
        filepath = os.path.join(data_dir, filename)
        # print(f"Processing {filename}...")
        
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    # Try to extract tables first
                    tables = page.extract_tables()
                    
                    if tables:
                        for table in tables:
                            # Heuristic: Check headers or content row by row
                            # formats often have: Item | Unit | Price
                            for row in table:
                                process_row(row, filename, materials, labor_rates)
                    else:
                        # Fallback to text lines if no tables found (less reliable)
                        text = page.extract_text()
                        if text:
                            lines = text.split('\n')
                            for line in lines:
                                process_line(line, filename, materials, labor_rates)
                                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    return {
        "materials": materials,
        "labor_rates": labor_rates
    }

def extract_text_for_knowledge(data_dir: str, target_file="egyptian_code.pdf") -> List[Dict[str, Any]]:
    """
    Extracts plain text from specific PDF for Knowledge Base.
    Returns list of chunks.
    """
    knowledge_items = []
    filepath = os.path.join(data_dir, target_file)
    
    if not os.path.exists(filepath):
        print(f"Knowledge source not found: {target_file}")
        return []

    print(f"Extracting knowledge from {target_file}...")
    try:
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    # Simple chunking: One page = One item for now. 
                    # Can be improved to split by paragraphs.
                    knowledge_items.append({
                        "topic": "Building Code",
                        "content": text,
                        "page_number": i + 1,
                        "source_document": target_file
                    })
    except Exception as e:
        print(f"Error extracting knowledge: {e}")
        
    return knowledge_items

def process_row(row: List[str], source: str, materials: List[Dict], labor_rates: List[Dict]):
    """
    Process a table row to find materials or labor.
    This is a heuristic implementation and will need tuning based on actual PDF content.
    """
    # Clean row items
    row = [item.strip() if item else "" for item in row]
    
    # Skip empty rows or headers
    if not any(row) or "Price" in row or "Unit" in row or "Description" in row:
        return

    # Basic Heuristic for Material: Name | Unit | Price (often 3 cols or more)
    # We look for a row with a number in the last or second to last column
    
    # Try to identify price
    price = None
    price_index = -1
    
    for i, cell in enumerate(row):
        # Remove currency symbols and commas
        cleaned = re.sub(r'[^\d.]', '', cell)
        if cleaned and cleaned.count('.') <= 1:
            try:
                price = float(cleaned)
                price_index = i
                break # Take first valid number? Or last? Usually price is towards the end.
            except ValueError:
                continue
    
    if price is not None:
        # Assuming Name is first non-empty column before price
        name = ""
        unit = ""
        
        # Look for name
        for i in range(price_index):
            if row[i] and len(row[i]) > 2: # Name usually longer than 2 chars
                name = row[i]
                # Look for unit in between name and price?
                if i + 1 < price_index:
                     unit = row[i+1] # extremely naive
                break
        
        if name:
            # Check if it looks like labor
            if "labor" in name.lower() or "worker" in name.lower() or "technician" in name.lower():
               labor_rates.append({
                   "role": name,
                   "hourly_rate": price,
                   "source_document": source
               })
            else:
               materials.append({
                   "name": name,
                   "unit": unit,
                   "price_per_unit": price,
                   "category": "General", # Default
                   "source_document": source
               })

def process_line(line: str, source: str, materials: List[Dict], labor_rates: List[Dict]):
    # Fallback for text mode - very basic
    # Format: "Cement 50kg bag 200.00"
    match = re.search(r'(.+?)\s+(\d+(?:\.\d{1,2})?)$', line)
    if match:
        name_part = match.group(1).strip()
        price = float(match.group(2))
        
        if "labor" in name_part.lower():
             labor_rates.append({
                   "role": name_part,
                   "hourly_rate": price,
                   "source_document": source
             })
        else:
             materials.append({
                   "name": name_part,
                   "unit": "",
                   "price_per_unit": price,
                   "category": "General",
                   "source_document": source
               })

if __name__ == "__main__":
    # Test run
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
    extracted = extract_data_from_pdfs(data_dir)
    print(f"Extracted {len(extracted['materials'])} materials")
    print(f"Extracted {len(extracted['labor_rates'])} labor rates")
    
    # Print sample
    if extracted['materials']:
        print("Sample Material:", extracted['materials'][0])
