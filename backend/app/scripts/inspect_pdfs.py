import pdfplumber
import os

def inspect_pdfs():
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
    files = [
        "Informatics August 2025.pdf",
        "egyptian_code.pdf",
        "نشرة مواد البناء يناير 2025 _compressed.pdf"
    ]
    
    for filename in files:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            print(f"Skipping {filename} (not found)")
            continue
            
        print(f"\n--- Inspecting {filename} ---")
        try:
            with pdfplumber.open(filepath) as pdf:
                if len(pdf.pages) > 0:
                    page = pdf.pages[0]
                    print("First Page Text Snippet:")
                    print(page.extract_text()[:500] if page.extract_text() else "No text found")
                    print("\nFirst Page Tables:")
                    tables = page.extract_tables()
                    if tables:
                        print(f"Found {len(tables)} tables.")
                        if len(tables) > 0 and len(tables[0]) > 0:
                            print("Sample Row:", tables[0][0])
                    else:
                        print("No tables found on first page.")
                else:
                    print("Empty PDF")
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == "__main__":
    inspect_pdfs()
