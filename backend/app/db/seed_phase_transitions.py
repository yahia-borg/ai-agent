"""
Seed Qdrant with structured phase transition documents.

Replaces the PHASE-AWARE RULES hardcoded in the LLM system prompt
(cost_calculator.py) with searchable vector knowledge items.

Each document describes what materials and trades are required
when transitioning from one finishing phase to another.

Usage:
    cd backend && python -m app.db.seed_phase_transitions
"""
import logging
import uuid

logger = logging.getLogger(__name__)

# ── Phase transition knowledge items ────────────────────────────────
# Each entry maps (current_phase → target_phase) to the materials
# and trades required for the transition.

PHASE_TRANSITION_DOCUMENTS = [
    # ── Core Shell → Fully Finished ──
    {
        "topic": "Phase Transition: Core Shell to Fully Finished",
        "content": (
            "When converting a Core Shell (هيكل) unit to Fully Finished (تشطيب كامل), "
            "the following works are required:\n\n"
            "REQUIRED MATERIAL CATEGORIES:\n"
            "- Plastering (internal wall render, spatter dash, skim coat)\n"
            "- Flooring (tiles, porcelain, marble, or parquet for all rooms)\n"
            "- Painting (interior walls and ceilings, primer + 2 coats)\n"
            "- Plumbing (cold/hot water pipes, drainage, fixtures, mixers)\n"
            "- Electrical (wiring, switches, sockets, distribution board, lighting)\n"
            "- Carpentry (internal doors, kitchen cabinets, wardrobes)\n"
            "- Waterproofing (bathrooms, kitchen, balcony)\n"
            "- Ceiling (suspended gypsum board or plaster ceiling)\n"
            "- Doors & Windows (frames, hardware, glazing if not installed)\n\n"
            "REQUIRED TRADES:\n"
            "- Plasterer, Tiler, Painter, Plumber, Electrician, Carpenter, Mason, Welder\n\n"
            "NOTES:\n"
            "- This is the most comprehensive transition requiring ALL trades.\n"
            "- Structural work (columns, beams, slabs) is already complete.\n"
            "- External walls and windows may or may not be installed."
        ),
        "source_document": "phase_transition_guide",
    },
    {
        "topic": "انتقال المرحلة: هيكل خرساني إلى تشطيب كامل",
        "content": (
            "عند تحويل وحدة هيكل خرساني (Core Shell) إلى تشطيب كامل:\n\n"
            "المواد المطلوبة:\n"
            "- أعمال البياض (محارة داخلية، طرطشة، تلقيط)\n"
            "- أعمال الأرضيات (سيراميك، بورسلين، رخام، أو باركيه)\n"
            "- أعمال الدهانات (بطانة + وجهين دهان بلاستيك قابل للغسيل)\n"
            "- أعمال السباكة (مواسير مياه باردة/ساخنة، صرف، خلاطات، أدوات صحية)\n"
            "- أعمال الكهرباء (أسلاك، مفاتيح، بريز، لوحة توزيع، إنارة)\n"
            "- أعمال النجارة (أبواب داخلية، مطبخ، دواليب)\n"
            "- أعمال العزل (عزل مائي للحمامات والمطبخ والبلكونة)\n"
            "- أعمال الأسقف (جبسون بورد أو سقف جبس)\n\n"
            "الحرف المطلوبة:\n"
            "- محارة، بلاط، دهان، سباك، كهربائي، نجار، بناء، حداد"
        ),
        "source_document": "phase_transition_guide",
    },

    # ── On Plaster → Fully Finished ──
    {
        "topic": "Phase Transition: On Plaster to Fully Finished",
        "content": (
            "When converting an On Plaster (على المحارة) unit to Fully Finished:\n\n"
            "REQUIRED MATERIAL CATEGORIES:\n"
            "- Flooring (tiles, porcelain, marble, or parquet)\n"
            "- Painting (interior walls and ceilings)\n"
            "- Plumbing (fixture installation, mixers — rough-in already done)\n"
            "- Electrical (fixture installation — rough-in wiring already done)\n"
            "- Carpentry (internal doors, kitchen cabinets, wardrobes)\n"
            "- Waterproofing (bathrooms, kitchen)\n"
            "- Ceiling (suspended gypsum board if desired)\n"
            "- Doors & Windows (internal doors and hardware)\n\n"
            "REQUIRED TRADES:\n"
            "- Tiler, Painter, Plumber (finish only), Electrician (finish only), Carpenter\n\n"
            "NOTES:\n"
            "- Plastering is ALREADY DONE — no plaster materials needed.\n"
            "- Plumbing and electrical rough-in (pipes in walls) already complete.\n"
            "- Only fixture installation and finishing work required for MEP.\n"
            "- No structural or mason work needed."
        ),
        "source_document": "phase_transition_guide",
    },
    {
        "topic": "انتقال المرحلة: على المحارة إلى تشطيب كامل",
        "content": (
            "عند تحويل وحدة على المحارة إلى تشطيب كامل:\n\n"
            "المواد المطلوبة:\n"
            "- أعمال الأرضيات (بلاط، بورسلين، رخام، أو باركيه)\n"
            "- أعمال الدهانات (بطانة + وجهين)\n"
            "- أعمال السباكة (تركيب أدوات صحية وخلاطات فقط — المواسير موجودة)\n"
            "- أعمال الكهرباء (تركيب مفاتيح وبريز فقط — الأسلاك موجودة)\n"
            "- أعمال النجارة (أبواب، مطبخ، دواليب)\n"
            "- أعمال العزل المائي (حمامات ومطبخ)\n"
            "- أعمال الأسقف (اختياري)\n\n"
            "ملاحظات:\n"
            "- المحارة منتهية — لا حاجة لمواد بياض.\n"
            "- السباكة والكهرباء المدفونة منتهية.\n"
            "- فقط أعمال التشطيب النهائي."
        ),
        "source_document": "phase_transition_guide",
    },

    # ── Semi Finished → Fully Finished ──
    {
        "topic": "Phase Transition: Semi Finished to Fully Finished",
        "content": (
            "When converting a Semi Finished (نصف تشطيب) unit to Fully Finished:\n\n"
            "REQUIRED MATERIAL CATEGORIES:\n"
            "- Flooring (may need upgrade from basic to specified quality)\n"
            "- Painting (final coat — base coat may already be applied)\n"
            "- Plumbing (fixture upgrades — basic fixtures may be installed)\n"
            "- Electrical (fixture upgrades, decorative switches)\n"
            "- Carpentry (upgrade doors, add kitchen cabinets, wardrobes)\n"
            "- Ceiling (decorative ceiling work if desired)\n\n"
            "REQUIRED TRADES:\n"
            "- Painter, Tiler (if flooring upgrade), Carpenter, Electrician (finish)\n\n"
            "NOTES:\n"
            "- Semi finished means basic plaster, basic flooring, basic paint are done.\n"
            "- This transition focuses on UPGRADE and DECORATION work.\n"
            "- Waterproofing is already complete.\n"
            "- Plumbing and electrical are functional — only upgrades needed.\n"
            "- Significantly less work than core_shell or on_plaster transitions."
        ),
        "source_document": "phase_transition_guide",
    },
    {
        "topic": "انتقال المرحلة: نصف تشطيب إلى تشطيب كامل",
        "content": (
            "عند تحويل وحدة نصف تشطيب إلى تشطيب كامل:\n\n"
            "المواد المطلوبة:\n"
            "- أرضيات (ترقية من الأساسي إلى المطلوب)\n"
            "- دهانات (وجه نهائي — البطانة قد تكون موجودة)\n"
            "- سباكة (ترقية أدوات صحية)\n"
            "- كهرباء (ترقية مفاتيح وإنارة)\n"
            "- نجارة (ترقية أبواب، إضافة مطبخ ودواليب)\n"
            "- أسقف (أعمال ديكور اختيارية)\n\n"
            "ملاحظات:\n"
            "- البياض والأرضيات الأساسية والدهان الأساسي منتهي.\n"
            "- هذا الانتقال يركز على الترقية والتزيين.\n"
            "- العزل المائي منتهي.\n"
            "- عمل أقل بكثير من الهيكل أو على المحارة."
        ),
        "source_document": "phase_transition_guide",
    },

    # ── General finishing standards ──
    {
        "topic": "Egyptian Construction Finishing Standards Overview",
        "content": (
            "Egyptian construction finishing standards and common practices:\n\n"
            "PLASTERING:\n"
            "- Render coat: 300kg Portland cement per 3m³ sand\n"
            "- Spatter dash (Tartasha): 450kg cement per m³ sand\n"
            "- Must include leveling points (Bu'j) and guide rails (Awtar)\n\n"
            "FLOORING:\n"
            "- Standard porcelain: 60cm × 60cm\n"
            "- Standard ceramic: 40cm × 40cm\n"
            "- Must include sand/mortar leveling layer\n"
            "- Must include 10cm matching skirting\n"
            "- Samples must be approved before installation\n\n"
            "PAINTING:\n"
            "- Washable emulsion type (Jotun or equivalent)\n"
            "- Primer + 2 finishing coats\n"
            "- Semi-gloss default finish\n\n"
            "WATERPROOFING:\n"
            "- Bathrooms: 2 layers bituminous membrane + protective screed\n"
            "- Kitchen: single layer waterproofing under tiles\n"
            "- Balcony: waterproofing with slope to drain\n\n"
            "All work must comply with: Egyptian Code of Practice (ECP), "
            "supervising engineer instructions, and approved technical specifications."
        ),
        "source_document": "egyptian_construction_standards",
    },
    {
        "topic": "معايير التشطيب المصرية",
        "content": (
            "معايير وممارسات التشطيب في مصر:\n\n"
            "البياض:\n"
            "- طبقة التخشين: 300 كجم أسمنت بورتلاندي لكل 3 م³ رمل\n"
            "- الطرطشة: 450 كجم أسمنت لكل م³ رمل\n"
            "- يشمل عمل البؤج والأوتار\n\n"
            "الأرضيات:\n"
            "- بورسلين قياسي: 60 سم × 60 سم\n"
            "- سيراميك قياسي: 40 سم × 40 سم\n"
            "- يشمل طبقة تسوية من الرمل والمونة\n"
            "- يشمل وزرة 10 سم من نفس النوع\n"
            "- تعتمد العينة قبل التركيب\n\n"
            "الدهانات:\n"
            "- نوع بلاستيك قابل للغسيل (جوتن أو ما يماثله)\n"
            "- بطانة + وجهين تشطيب\n"
            "- نصف لمعة كافتراضي\n\n"
            "العزل المائي:\n"
            "- الحمامات: طبقتين عزل بيتوميني + طبقة حماية\n"
            "- المطبخ: طبقة عزل واحدة تحت البلاط\n"
            "- البلكونة: عزل مع ميول للصرف\n\n"
            "جميع الأعمال طبقاً للكود المصري وتعليمات المهندس المشرف."
        ),
        "source_document": "egyptian_construction_standards",
    },
]


def seed_phase_transitions():
    """Seed Qdrant with phase transition knowledge items."""
    from app.services.qdrant_service import get_qdrant_service

    qdrant = get_qdrant_service()

    # Ensure collection exists
    qdrant.init_collection()

    # Add items with unique IDs based on hash
    items_with_ids = []
    for i, doc in enumerate(PHASE_TRANSITION_DOCUMENTS):
        items_with_ids.append({
            **doc,
            "id": f"phase_transition_{i}",
            "page_number": 1,
        })

    qdrant.add_knowledge_items(items_with_ids)
    logger.info(f"Seeded {len(items_with_ids)} phase transition documents to Qdrant")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_phase_transitions()
    print(f"Done. Seeded {len(PHASE_TRANSITION_DOCUMENTS)} phase transition documents.")
