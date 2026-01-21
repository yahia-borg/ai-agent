"""
Database Ingest Script for CSV Files
Replaces existing data and imports from CSV
"""
import csv
import os
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.models.knowledge import KnowledgeItem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_all_data(db: Session):
    """Clear all existing data from materials, labor_rates, and knowledge_items tables"""
    try:
        logger.info("Clearing existing data...")
        db.query(Material).delete()
        db.query(LaborRate).delete()
        db.query(KnowledgeItem).delete()
        db.commit()
        logger.info("All existing data cleared")
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing data: {e}")
        raise


def ingest_materials_from_csv(csv_path: str, db: Session):
    """Import materials from CSV file"""
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        return
    
    logger.info(f"Importing materials from {csv_path}")
    
    materials_added = 0
    materials_updated = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                name = row.get('name', '').strip()
                if not name:
                    continue
                
                # Check if exists
                existing = db.query(Material).filter(Material.name == name).first()
                
                if existing:
                    # Update existing
                    existing.category = row.get('category', 'General')
                    existing.unit = row.get('unit', 'unit')
                    existing.price_per_unit = float(row.get('price_per_unit', 0))
                    existing.currency = row.get('currency', 'EGP')
                    existing.source_document = row.get('source_document', '')
                    materials_updated += 1
                else:
                    # Create new
                    material = Material(
                        name=name,
                        category=row.get('category', 'General'),
                        unit=row.get('unit', 'unit'),
                        price_per_unit=float(row.get('price_per_unit', 0)),
                        currency=row.get('currency', 'EGP'),
                        source_document=row.get('source_document', '')
                    )
                    db.add(material)
                    materials_added += 1
                
                db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error importing material {row.get('name', 'unknown')}: {e}")
                continue
    
    logger.info(f"Materials: {materials_added} added, {materials_updated} updated")


def ingest_labor_from_csv(csv_path: str, db: Session):
    """Import labor rates from CSV file"""
    if not os.path.exists(csv_path):
        logger.warning(f"CSV file not found: {csv_path}")
        return
    
    logger.info(f"Importing labor rates from {csv_path}")
    
    labor_added = 0
    labor_updated = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                role = row.get('role', '').strip()
                if not role:
                    continue
                
                # Check if exists
                existing = db.query(LaborRate).filter(LaborRate.role == role).first()
                
                if existing:
                    # Update existing
                    existing.hourly_rate = float(row.get('hourly_rate', 0))
                    existing.currency = row.get('currency', 'EGP')
                    existing.source_document = row.get('source_document', '')
                    labor_updated += 1
                else:
                    # Create new
                    labor = LaborRate(
                        role=role,
                        hourly_rate=float(row.get('hourly_rate', 0)),
                        currency=row.get('currency', 'EGP'),
                        source_document=row.get('source_document', '')
                    )
                    db.add(labor)
                    labor_added += 1
                
                db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error importing labor rate {row.get('role', 'unknown')}: {e}")
                continue
    
    logger.info(f"Labor rates: {labor_added} added, {labor_updated} updated")


def ingest_knowledge_from_csv(csv_path: str, db: Session):
    """Import knowledge items from CSV file"""
    if not os.path.exists(csv_path):
        logger.warning(f"CSV file not found: {csv_path}")
        return
    
    logger.info(f"Importing knowledge items from {csv_path}")
    
    knowledge_added = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                topic = row.get('topic', '').strip()
                content = row.get('content', '').strip()
                
                if not topic or not content:
                    continue
                
                # Check if exists (by topic and source_document)
                source_doc = row.get('source_document', '')
                page_num = int(row.get('page_number', 1))
                
                existing = db.query(KnowledgeItem).filter(
                    KnowledgeItem.topic == topic,
                    KnowledgeItem.source_document == source_doc,
                    KnowledgeItem.page_number == page_num
                ).first()
                
                if not existing:
                    # Create new
                    knowledge = KnowledgeItem(
                        topic=topic,
                        content=content,
                        source_document=source_doc,
                        page_number=page_num
                    )
                    db.add(knowledge)
                    knowledge_added += 1
                    db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error importing knowledge item: {e}")
                continue
    
    logger.info(f"Knowledge items: {knowledge_added} added")


if __name__ == "__main__":
    # Test
    db = SessionLocal()
    try:
        # Example usage
        materials_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/exports/materials.csv"))
        labor_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/exports/labor_rates.csv"))
        knowledge_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/exports/knowledge_items.csv"))
        
        clear_all_data(db)
        
        if os.path.exists(materials_csv):
            ingest_materials_from_csv(materials_csv, db)
        
        if os.path.exists(labor_csv):
            ingest_labor_from_csv(labor_csv, db)
        
        if os.path.exists(knowledge_csv):
            ingest_knowledge_from_csv(knowledge_csv, db)
            
    finally:
        db.close()

