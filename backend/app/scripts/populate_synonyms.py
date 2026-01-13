"""
Populate material and labor synonyms for better Arabic search matching.

This script adds common Arabic construction term synonyms to help with search.
For example: "جص" (gypsum) should match materials with "محارة" (plastering) or "جبس" (gypsum).
"""
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate, MaterialSynonym
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def populate_material_synonyms():
    """Populate common Arabic synonyms for materials."""
    db = SessionLocal()
    try:
        # Common Arabic construction term mappings
        synonym_mappings = [
            # Plaster/Gypsum related
            ("جص", ["محارة", "جبس", "gypsum", "plaster"]),
            ("جبس", ["محارة", "جص", "gypsum", "plaster"]),
            ("محارة", ["جص", "جبس", "plaster", "plastering"]),
            
            # Tiles/Flooring related
            ("بلاط", ["سيراميك", "أرضيات", "tile", "ceramic", "flooring"]),
            ("سيراميك", ["بلاط", "أرضيات", "ceramic", "tile"]),
            ("أرضيات", ["بلاط", "سيراميك", "flooring", "tiles"]),
            
            # Cement related
            ("أسمنت", ["cement", "concrete"]),
            
            # Paint related
            ("دهان", ["paint", "painting", "طلاء"]),
            ("طلاء", ["paint", "painting", "دهان"]),
            
            # Marble/Granite related
            ("رخام", ["marble", "جرانيت"]),
            ("جرانيت", ["granite", "رخام"]),
            ("مرمر", ["marble", "رخام"]),
        ]
        
        added_count = 0
        seen_synonyms = set()  # Track (material_id, language_code, synonym) to avoid duplicates
        
        for synonym_term, search_terms in synonym_mappings:
            # Find materials that match any of the search terms
            for search_term in search_terms:
                # Search in both English and Arabic names
                materials = db.execute(
                    text("""
                        SELECT id FROM materials
                        WHERE is_active = true
                        AND (
                            name->>'en' ILIKE :term
                            OR name->>'ar' ILIKE :term
                        )
                    """),
                    {"term": f"%{search_term}%"}
                ).fetchall()
                
                for (material_id,) in materials:
                    # Create unique key
                    synonym_key = (material_id, "ar", synonym_term)
                    
                    # Skip if we've already processed this combination
                    if synonym_key in seen_synonyms:
                        continue
                    seen_synonyms.add(synonym_key)
                    
                    # Check if synonym already exists in database
                    existing = db.query(MaterialSynonym).filter(
                        MaterialSynonym.material_id == material_id,
                        MaterialSynonym.language_code == "ar",
                        MaterialSynonym.synonym == synonym_term
                    ).first()
                    
                    if not existing:
                        synonym = MaterialSynonym(
                            material_id=material_id,
                            language_code="ar",
                            synonym=synonym_term
                        )
                        db.add(synonym)
                        added_count += 1
                        
                        # Commit in batches to avoid memory issues
                        if added_count % 50 == 0:
                            db.commit()
                            logger.info(f"Committed {added_count} synonyms so far...")
        
        db.commit()
        logger.info(f"Added {added_count} material synonyms")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error populating material synonyms: {e}", exc_info=True)
        raise
    finally:
        db.close()


def populate_labor_synonyms():
    """Populate common Arabic synonyms for labor roles."""
    db = SessionLocal()
    try:
        # Common Arabic labor term mappings
        synonym_mappings = [
            # Mason/Building related
            ("بناء", ["mason", "masonry", "بناء"]),
            ("ماسون", ["mason", "masonry", "بناء"]),
            ("ماسونز", ["mason", "masonry", "بناء"]),
            
            # Tiler related
            ("فني بلاط", ["tiler", "tile installer", "بلاط"]),
            ("بلاط", ["tiler", "tile installer"]),
            
            # Finishing technician
            ("فني تشطيب", ["finishing technician", "finisher", "تشطيب"]),
            ("فني تشطيبات", ["finishing technician", "finisher", "تشطيب"]),
            
            # Electrician
            ("كهربائي", ["electrician", "electrical"]),
            
            # Plumber
            ("سباك", ["plumber", "plumbing"]),
            
            # Painter
            ("دهان", ["painter", "painting"]),
        ]
        
        added_count = 0
        
        for synonym_term, search_terms in synonym_mappings:
            # Find labor rates that match any of the search terms
            for search_term in search_terms:
                # Search in both English and Arabic roles
                labor_rates = db.execute(
                    text("""
                        SELECT id FROM labor_rates
                        WHERE is_active = true
                        AND (
                            role->>'en' ILIKE :term
                            OR role->>'ar' ILIKE :term
                        )
                    """),
                    {"term": f"%{search_term}%"}
                ).fetchall()
                
                # Note: LaborRate doesn't have a synonyms table in the schema
                # We might need to add one, or handle this differently
                # For now, we'll just log that we found matches
                if labor_rates:
                    logger.info(f"Found {len(labor_rates)} labor rates matching '{search_term}' for synonym '{synonym_term}'")
        
        logger.info(f"Labor synonym mapping completed (note: labor_synonyms table may need to be created)")
        
    except Exception as e:
        logger.error(f"Error populating labor synonyms: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Starting synonym population...")
    populate_material_synonyms()
    populate_labor_synonyms()
    logger.info("Synonym population completed!")
