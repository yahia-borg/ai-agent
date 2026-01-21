from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate
from app.models.knowledge import KnowledgeItem
from app.scripts.pdf_parser import extract_data_from_pdfs, extract_text_for_knowledge
from app.scripts.md_parser import parse_markdown_materials, parse_markdown_knowledge
import os
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_db():
    db = SessionLocal()
    try:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
        logger.info(f"Using data directory: {data_dir}")

        # 1. Parse Markdown for Materials
        logger.info("Parsing Markdown files for materials...")
        md_file = os.path.join(data_dir, "compressed.md")
        materials_data = parse_markdown_materials(md_file)
        
        august_md = os.path.join(data_dir, "august_data.md")
        if os.path.exists(august_md):
             august_data = parse_markdown_materials(august_md)
             materials_data.extend(august_data)
        
        egypt_costs_md = os.path.join(data_dir, "egypt-construction-costs-2025.md")
        if os.path.exists(egypt_costs_md):
             egypt_data = parse_markdown_materials(egypt_costs_md)
             materials_data.extend(egypt_data)
        
        # 2. Extract Knowledge from PDF
        logger.info("Extracting Knowledge Base items...")
        knowledge_data = extract_text_for_knowledge(data_dir, "egyptian_code.pdf")
        
        # 2a. Extract Knowledge from Markdown
        finishing_md = os.path.join(data_dir, "construction_finishing_knowledge_base_egypt.md")
        if os.path.exists(finishing_md):
            logger.info("Parsing Markdown Knowledge Base...")
            md_knowledge = parse_markdown_knowledge(finishing_md)
            knowledge_data.extend(md_knowledge)

        # 3. Seed Materials
        # labor_data = extracted_data.get("labor_rates", []) 
        # We currently don't have labor data from MD, so list is empty for now
        labor_data = []
        
        logger.info(f"Process {len(materials_data)} materials...")
        success_mat = 0
        for item in materials_data:
            try:
                # Deduplication logic
                existing = db.query(Material).filter(Material.name == item["name"]).first()
                if not existing:
                    material = Material(
                        name=item["name"][:255].strip(), 
                        category=item.get("category", "General"),
                        unit=item.get("unit"),
                        price_per_unit=item["price_per_unit"],
                        currency="EGP",
                        source_document=str(item.get("source_document"))[:255]
                    )
                    db.add(material)
                else:
                    existing.price_per_unit = item["price_per_unit"]
                
                db.commit() 
                success_mat += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to insert material {item.get('name')}: {e}")

        logger.info(f"Successfully inserted/updated {success_mat} materials.")

        # 4. Seed Knowledge Items
        logger.info(f"Process {len(knowledge_data)} knowledge items...")
        success_know = 0
        for item in knowledge_data:
            try:
                # Simple check to avoid exact duplication
                existing = db.query(KnowledgeItem).filter(
                    KnowledgeItem.source_document == item["source_document"],
                    KnowledgeItem.page_number == item["page_number"]
                ).first()
                
                if not existing:
                    k_item = KnowledgeItem(
                        topic=item["topic"],
                        content=item["content"],
                        page_number=item["page_number"],
                        source_document=item["source_document"]
                    )
                    db.add(k_item)
                    db.commit()
                    success_know += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to insert knowledge item page {item.get('page_number')}: {e}")
        
        logger.info(f"Successfully inserted {success_know} knowledge items.")
        
    except Exception as e:
        logger.error(f"Critical error in seeding: {e}")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
