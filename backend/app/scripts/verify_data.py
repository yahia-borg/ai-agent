from ..core.database import SessionLocal
from ..models.resources import Material
from ..models.knowledge import KnowledgeItem

def verify_data():
    db = SessionLocal()
    try:
        # Check Materials
        mat_count = db.query(Material).count()
        print(f"\n--- Materials ({mat_count} total) ---")
        materials = db.query(Material).order_by(Material.id.desc()).limit(5).all()
        for m in materials:
            print(f"- [ID: {m.id}] {m.name} | Price: {m.price_per_unit} {m.currency}/{m.unit} | Source: {m.source_document}")
            
        # Check Knowledge Base
        know_count = db.query(KnowledgeItem).count()
        print(f"\n--- Knowledge Base ({know_count} pages/chunks) ---")
        items = db.query(KnowledgeItem).limit(3).all()
        for k in items:
            preview = k.content[:100].replace('\n', ' ') + "..."
            print(f"- [ID: {k.id}] Topic: {k.topic} | Page: {k.page_number} | Content: {preview}")

    except Exception as e:
        print(f"Error resolving data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_data()
