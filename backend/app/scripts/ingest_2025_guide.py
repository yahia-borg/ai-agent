import os
import re
from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeItem

def ingest_guide():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "../../../data/clean/egypt-construction-costs-2025.md")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by headers (## or ###)
    # We want to capture the header text as the topic
    # Regex lookahead to split but keep delimiter? 
    # Simpler: Split by newlines, detect headers.
    
    sections = []
    current_header = "Intro"
    current_content = []
    
    for line in content.splitlines():
        if line.startswith("## "):
            # New main section
            if current_content:
                sections.append((current_header, "\n".join(current_content)))
            current_header = line.strip("# ").strip()
            current_content = [line]
        elif line.startswith("### "):
            # Sub section - treat as separate chunk or append to current?
            # Let's treat as separate chunk for better semantic search
            if current_content:
                 sections.append((current_header, "\n".join(current_content)))
            current_header = line.strip("# ").strip()
            current_content = [line]
        else:
            current_content.append(line)
            
    if current_content:
        sections.append((current_header, "\n".join(current_content)))

    # Save to DB
    db = SessionLocal()
    try:
        count = 0
        for header, text in sections:
            if len(text.strip()) < 10: continue
            
            # Check duplicates
            exists = db.query(KnowledgeItem).filter(
                KnowledgeItem.topic == f"2025 Cost Guide - {header}"
            ).first()
            
            if not exists:
                kb_item = KnowledgeItem(
                    topic=f"2025 Cost Guide - {header}",
                    source_document="egypt-construction-costs-2025.md",
                    page_number=1, # Virtual page
                    content=text
                )
                db.add(kb_item)
                count += 1
                
        db.commit()
        print(f"Successfully ingested {count} sections from 2025 Guide.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ingest_guide()
