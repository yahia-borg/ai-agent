from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeItem

def seed_standards():
    db = SessionLocal()
    try:
        # Check if already exists
        exists = db.query(KnowledgeItem).filter(KnowledgeItem.topic == "Standard Finishing Requirements").first()
        if exists:
            print("Standard Finishing Requirements already exist.")
            return

        item = KnowledgeItem(
            topic="Standard Finishing Requirements",
            source_document="Egyptian Code of Practice",
            page_number=1,
            content="""
            For 'Core & Shell' to 'Full Finish' (Modern/Deluxe):
            1. Plastering: Requires Cement (Ordinary Portland) and Sand. Ratio 1:4. Thickness 2cm.
            2. Flooring: Ceramic or Porcelain Tiles. Requires Cement Mortar (Sand + Cement).
            3. Painting: 3 layers of Putty (Gypsum/Acrylic), 1 layer Primer, 2 layers Finish Paint (Jotun/Sipes).
            4. Plumbing: PVC Pipes (Assumed 1/2 inch and 4 inch), Valves, Mixers.
            5. Electrical: Copper Wires (2mm, 4mm, 6mm), Conduits, Sockets, Switches.
            
            Consumption Rates (Approx per m2 floor):
            - Cement: 25 kg (Plaster + Flooring)
            - Sand: 0.1 m3
            - Paint: 0.5 Liters (all layers)
            - Tiles: 1.05 m2 (5% waste)
            """
        )
        db.add(item)
        db.commit()
        print("Seeded Standard Finishing Requirements.")
    except Exception as e:
        print(f"Error seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_standards()
