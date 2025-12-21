"""
Main Orchestration Script for Processing Clean Data
Parses MD files, exports to CSV, validates, ingests to database, and creates Qdrant vector store
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.scripts.md_parser_enhanced import (
    parse_materials_from_md,
    parse_labor_rates_from_md,
    parse_knowledge_from_md
)
from app.scripts.csv_exporter import (
    export_materials_to_csv,
    export_labor_to_csv,
    export_knowledge_to_csv
)
from app.scripts.csv_validator import (
    validate_materials,
    validate_labor_rates,
    validate_knowledge_items,
    save_validation_report
)
from app.scripts.ingest_from_csv import (
    clear_all_data,
    ingest_materials_from_csv,
    ingest_labor_from_csv,
    ingest_knowledge_from_csv
)
from app.services.qdrant_service import get_qdrant_service
from app.core.database import SessionLocal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_md_files(data_dir: str) -> List[str]:
    """Get all markdown files from data/clean directory"""
    clean_dir = os.path.join(data_dir, "clean")
    if not os.path.exists(clean_dir):
        logger.error(f"Directory not found: {clean_dir}")
        return []
    
    md_files = []
    for file in os.listdir(clean_dir):
        if file.endswith('.md'):
            md_files.append(os.path.join(clean_dir, file))
    
    logger.info(f"Found {len(md_files)} markdown files")
    return md_files


def main():
    """Main orchestration function"""
    # Get data directory
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = os.path.join(project_root, "data")
    exports_dir = os.path.join(data_dir, "exports")
    
    os.makedirs(exports_dir, exist_ok=True)
    
    logger.info("="*60)
    logger.info("Starting Data Processing Pipeline")
    logger.info("="*60)
    
    # Step 1: Parse all MD files
    logger.info("\n[Step 1] Parsing Markdown files...")
    md_files = get_md_files(data_dir)
    
    all_materials = []
    all_labor_rates = []
    all_knowledge_items = []
    
    for md_file in md_files:
        logger.info(f"Processing: {os.path.basename(md_file)}")
        
        # Parse materials
        materials = parse_materials_from_md(md_file)
        all_materials.extend(materials)
        logger.info(f"  - Extracted {len(materials)} materials")
        
        # Parse labor rates
        labor = parse_labor_rates_from_md(md_file)
        all_labor_rates.extend(labor)
        logger.info(f"  - Extracted {len(labor)} labor rates")
        
        # Parse knowledge items
        knowledge = parse_knowledge_from_md(md_file)
        all_knowledge_items.extend(knowledge)
        logger.info(f"  - Extracted {len(knowledge)} knowledge items")
    
    logger.info(f"\nTotal extracted:")
    logger.info(f"  - Materials: {len(all_materials)}")
    logger.info(f"  - Labor rates: {len(all_labor_rates)}")
    logger.info(f"  - Knowledge items: {len(all_knowledge_items)}")
    
    # Step 2: Export to CSV
    logger.info("\n[Step 2] Exporting to CSV files...")
    
    materials_csv = os.path.join(exports_dir, "materials.csv")
    labor_csv = os.path.join(exports_dir, "labor_rates.csv")
    knowledge_csv = os.path.join(exports_dir, "knowledge_items.csv")
    
    export_materials_to_csv(all_materials, materials_csv)
    export_labor_to_csv(all_labor_rates, labor_csv)
    export_knowledge_to_csv(all_knowledge_items, knowledge_csv)
    
    # Step 3: Validate CSV files
    logger.info("\n[Step 3] Validating CSV files...")
    
    valid_materials, invalid_materials = validate_materials(materials_csv)
    valid_labor, invalid_labor = validate_labor_rates(labor_csv)
    valid_knowledge, invalid_knowledge = validate_knowledge_items(knowledge_csv)
    
    logger.info(f"Materials: {len(valid_materials)} valid, {len(invalid_materials)} invalid")
    logger.info(f"Labor rates: {len(valid_labor)} valid, {len(invalid_labor)} invalid")
    logger.info(f"Knowledge items: {len(valid_knowledge)} valid, {len(invalid_knowledge)} invalid")
    
    # Save validation reports
    if invalid_materials or invalid_labor or invalid_knowledge:
        report_path = os.path.join(exports_dir, "validation_report.txt")
        save_validation_report(
            valid_materials + valid_labor + valid_knowledge,
            invalid_materials + invalid_labor + invalid_knowledge,
            report_path
        )
        logger.info(f"Validation report saved to: {report_path}")
    
    # Step 4: Clear database and ingest
    logger.info("\n[Step 4] Ingesting to database...")
    db = SessionLocal()
    try:
        # Clear existing data
        clear_all_data(db)
        
        # Ingest valid data
        if valid_materials:
            # Write valid materials to temporary CSV
            import csv
            valid_materials_csv = os.path.join(exports_dir, "materials_valid.csv")
            with open(valid_materials_csv, 'w', newline='', encoding='utf-8') as f:
                if valid_materials:
                    writer = csv.DictWriter(f, fieldnames=valid_materials[0].keys())
                    writer.writeheader()
                    writer.writerows(valid_materials)
            ingest_materials_from_csv(valid_materials_csv, db)
        
        if valid_labor:
            valid_labor_csv = os.path.join(exports_dir, "labor_rates_valid.csv")
            with open(valid_labor_csv, 'w', newline='', encoding='utf-8') as f:
                if valid_labor:
                    writer = csv.DictWriter(f, fieldnames=valid_labor[0].keys())
                    writer.writeheader()
                    writer.writerows(valid_labor)
            ingest_labor_from_csv(valid_labor_csv, db)
        
        if valid_knowledge:
            valid_knowledge_csv = os.path.join(exports_dir, "knowledge_items_valid.csv")
            with open(valid_knowledge_csv, 'w', newline='', encoding='utf-8') as f:
                if valid_knowledge:
                    writer = csv.DictWriter(f, fieldnames=valid_knowledge[0].keys())
                    writer.writeheader()
                    writer.writerows(valid_knowledge)
            ingest_knowledge_from_csv(valid_knowledge_csv, db)
        
        logger.info("Database ingestion completed")
        
    except Exception as e:
        logger.error(f"Error during database ingestion: {e}")
        raise
    finally:
        db.close()
    
    # Step 5: Create Qdrant vector store
    logger.info("\n[Step 5] Creating Qdrant vector store...")
    try:
        qdrant_service = get_qdrant_service()
        qdrant_service.init_collection(recreate=True)
        
        # Get knowledge items from database for syncing
        db = SessionLocal()
        try:
            from app.models.knowledge import KnowledgeItem
            knowledge_items = db.query(KnowledgeItem).all()
            
            # Convert to dict format
            items = []
            for item in knowledge_items:
                items.append({
                    "id": item.id,
                    "topic": item.topic or "",
                    "content": item.content,
                    "source_document": item.source_document or "",
                    "page_number": item.page_number or 1
                })
            
            # Add to Qdrant
            if items:
                qdrant_service.add_knowledge_items(items)
                logger.info(f"Added {len(items)} knowledge items to Qdrant")
            else:
                logger.warning("No knowledge items to add to Qdrant")
                
        finally:
            db.close()
        
        logger.info("Qdrant vector store created successfully")
        
    except Exception as e:
        logger.error(f"Error creating Qdrant vector store: {e}")
        logger.warning("Continuing without Qdrant...")
    
    logger.info("\n" + "="*60)
    logger.info("Data Processing Pipeline Completed Successfully!")
    logger.info("="*60)
    logger.info(f"\nSummary:")
    logger.info(f"  - Materials: {len(valid_materials)} imported")
    logger.info(f"  - Labor rates: {len(valid_labor)} imported")
    logger.info(f"  - Knowledge items: {len(valid_knowledge)} imported")
    logger.info(f"\nCSV files saved to: {exports_dir}")
    logger.info(f"Qdrant collection: knowledge_items")


if __name__ == "__main__":
    main()

