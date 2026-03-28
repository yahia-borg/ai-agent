"""
Seed script for construction configuration tables.
Populates tables from the current hardcoded Python values to ensure
identical calculation results after migration.

Usage:
    cd backend && python -m app.db.seed_construction_config
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.database import SessionLocal
from app.models.construction_config import (
    ConstructionConfig, RoomMultiplier, AreaDistributionDefault,
    TradeMultiplier, CostComponentSplit, CategoryKeyword, DescriptionTemplate
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_construction_config(db):
    """Seed general configuration values."""
    configs = [
        # Percentages
        {"key": "contingency_percentage", "value": 0.10, "category": "percentages",
         "description": {"en": "Standard contingency for construction projects", "ar": "نسبة الطوارئ القياسية"}},
        {"key": "markup_percentage", "value": 0.10, "category": "percentages",
         "description": {"en": "Markup percentage (50% overhead, 50% profit)", "ar": "نسبة الهامش"}},
        {"key": "markup_overhead_split", "value": 0.5, "category": "percentages",
         "description": {"en": "Overhead share of markup", "ar": "حصة المصاريف العامة من الهامش"}},

        # Compliance
        {"key": "standard_compliance_phrase", "value": "طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف",
         "category": "compliance",
         "description": {"en": "Standard compliance phrase for BOQ descriptions", "ar": "عبارة الامتثال القياسية"}},
        {"key": "standard_compliance_phrase_en",
         "value": "According to technical specifications, industry standards, and supervising engineer instructions.",
         "category": "compliance"},

        # Default brands
        {"key": "default_brand_paint", "value": "Jotun", "category": "brands",
         "description": {"en": "Default paint brand", "ar": "ماركة الدهان الافتراضية"}},

        # Default tile sizes
        {"key": "default_tile_size_porcelain", "value": "60 سم * 60 سم", "category": "defaults"},
        {"key": "default_tile_size_ceramic", "value": "40 سم * 40 سم", "category": "defaults"},

        # Plaster mix ratios
        {"key": "plaster_mix_render_coat", "value": 300, "category": "mix_ratios",
         "description": {"en": "Render coat: 300kg cement per 3m³ sand", "ar": "بياض تخشين: 300 كجم أسمنت لكل 3 م³ رمل"}},
        {"key": "plaster_mix_spatter_dash", "value": 450, "category": "mix_ratios",
         "description": {"en": "Spatter dash: 450kg cement per m³ sand", "ar": "طرطشة: 450 كجم أسمنت لكل م³ رمل"}},

        # Fallback labor rates
        {"key": "fallback_labor_rates", "value": {
            "engineer": 150.0, "electrician": 60.0, "plumber": 60.0,
            "tiler": 70.0, "painter": 55.0, "carpenter": 65.0,
            "mason": 60.0, "labor": 40.0, "helper": 40.0, "default": 50.0
        }, "category": "rates"},

        # Max items per material type
        {"key": "max_per_material_type", "value": {
            "tiles": 1, "stone": 1, "paint": 2, "plaster": 1,
            "cement": 1, "steel": 1, "wood": 1, "pipes": 2,
            "electrical": 2, "glass": 1, "brick": 1, "vinyl": 1, "default": 2
        }, "category": "limits"},

        # Finishing adjustments
        {"key": "finishing_adjustment_luxury", "value": 1.4, "category": "adjustments",
         "description": {"en": "Luxury finish labor multiplier", "ar": "معامل عمالة التشطيب الفاخر"}},
        {"key": "finishing_adjustment_premium", "value": 1.2, "category": "adjustments"},
        {"key": "finishing_adjustment_economy", "value": 0.8, "category": "adjustments"},

        # Finishing adjustment keywords
        {"key": "finishing_keywords_luxury", "value": ["luxury", "فاخر"], "category": "adjustment_keywords"},
        {"key": "finishing_keywords_premium", "value": ["premium", "ممتاز"], "category": "adjustment_keywords"},
        {"key": "finishing_keywords_economy", "value": ["economy", "اقتصادي"], "category": "adjustment_keywords"},
    ]

    for cfg in configs:
        existing = db.query(ConstructionConfig).filter_by(key=cfg["key"]).first()
        if not existing:
            db.add(ConstructionConfig(**cfg))
    db.commit()
    logger.info(f"Seeded {len(configs)} construction config entries")


def seed_room_multipliers(db):
    """Seed room material and labor multipliers."""
    # Material multipliers - from cost_calculator.py ROOM_MATERIAL_MULTIPLIERS
    material_multipliers = {
        "bathroom": {"tile": 2.5, "paint": 0.3, "plaster": 2.5, "pipes": 2.0, "electrical": 0.8, "waterproofing": 1.2, "default": 1.0},
        "kitchen": {"tile": 1.8, "paint": 1.5, "plaster": 2.0, "pipes": 1.5, "electrical": 1.5, "wood": 0.6, "default": 1.0},
        "bedroom": {"tile": 1.0, "paint": 2.8, "plaster": 2.8, "electrical": 1.0, "default": 1.0},
        "living_room": {"tile": 1.1, "paint": 2.8, "plaster": 2.8, "electrical": 1.2, "default": 1.0},
        "reception": {"tile": 1.1, "paint": 3.0, "plaster": 3.0, "electrical": 1.2, "default": 1.0},
        "office": {"tile": 1.1, "paint": 2.5, "plaster": 2.5, "electrical": 2.0, "default": 1.0},
        "meeting_room": {"tile": 1.1, "paint": 2.5, "plaster": 2.5, "electrical": 1.5, "default": 1.0},
        "corridor": {"tile": 1.0, "paint": 2.0, "plaster": 2.0, "electrical": 0.5, "default": 0.8},
        "balcony": {"tile": 1.2, "paint": 1.0, "waterproofing": 1.0, "electrical": 0.3, "default": 0.6},
        "storage": {"tile": 1.0, "paint": 2.0, "plaster": 2.0, "electrical": 0.4, "default": 0.7},
        "open_plan": {"tile": 1.1, "paint": 2.2, "plaster": 2.2, "electrical": 2.0, "default": 1.0},
        "server_room": {"tile": 1.0, "paint": 2.0, "electrical": 3.0, "default": 1.0},
    }

    # Labor multipliers - from cost_calculator.py ROOM_LABOR_MULTIPLIERS
    labor_multipliers = {
        "bathroom": {"plumber": 2.5, "tiler": 2.0, "electrician": 0.8, "painter": 0.3, "plasterer": 1.5, "default": 1.0},
        "kitchen": {"plumber": 2.0, "tiler": 1.5, "electrician": 1.5, "carpenter": 2.5, "painter": 1.0, "plasterer": 1.2, "default": 1.0},
        "bedroom": {"plumber": 0.2, "tiler": 0.8, "electrician": 1.0, "painter": 1.2, "plasterer": 1.0, "carpenter": 1.0, "default": 1.0},
        "living_room": {"plumber": 0.1, "tiler": 1.0, "electrician": 1.2, "painter": 1.2, "plasterer": 1.0, "default": 1.0},
        "reception": {"plumber": 0.1, "tiler": 1.0, "electrician": 1.2, "painter": 1.3, "plasterer": 1.0, "default": 1.0},
        "office": {"plumber": 0.3, "tiler": 1.0, "electrician": 2.0, "painter": 1.0, "carpenter": 1.5, "default": 1.0},
        "corridor": {"plumber": 0.1, "tiler": 0.8, "electrician": 0.5, "painter": 0.8, "default": 0.7},
        "balcony": {"plumber": 0.3, "tiler": 1.0, "electrician": 0.3, "painter": 0.5, "default": 0.5},
        "storage": {"plumber": 0.1, "tiler": 0.5, "electrician": 0.3, "painter": 0.8, "default": 0.5},
    }

    count = 0
    for room_type, categories in material_multipliers.items():
        for cat_key, value in categories.items():
            existing = db.query(RoomMultiplier).filter_by(
                room_type=room_type, category_key=cat_key, multiplier_type="material"
            ).first()
            if not existing:
                db.add(RoomMultiplier(
                    room_type=room_type, category_key=cat_key,
                    multiplier_type="material", value=value
                ))
                count += 1

    for room_type, trades in labor_multipliers.items():
        for trade_key, value in trades.items():
            existing = db.query(RoomMultiplier).filter_by(
                room_type=room_type, category_key=trade_key, multiplier_type="labor"
            ).first()
            if not existing:
                db.add(RoomMultiplier(
                    room_type=room_type, category_key=trade_key,
                    multiplier_type="labor", value=value
                ))
                count += 1

    db.commit()
    logger.info(f"Seeded {count} room multiplier entries")


def seed_area_distribution_defaults(db):
    """Seed area distribution defaults."""
    residential = {
        "bedroom": 0.20, "living_room": 0.15, "reception": 0.15,
        "bathroom": 0.06, "kitchen": 0.10, "corridor": 0.08, "balcony": 0.06
    }
    commercial = {
        "office": 0.30, "reception": 0.15, "meeting_room": 0.12,
        "corridor": 0.10, "storage": 0.08, "open_plan": 0.35, "server_room": 0.05
    }

    count = 0
    for room_type, pct in residential.items():
        existing = db.query(AreaDistributionDefault).filter_by(
            project_type="residential", room_type=room_type
        ).first()
        if not existing:
            db.add(AreaDistributionDefault(
                project_type="residential", room_type=room_type, percentage=pct
            ))
            count += 1

    for room_type, pct in commercial.items():
        existing = db.query(AreaDistributionDefault).filter_by(
            project_type="commercial", room_type=room_type
        ).first()
        if not existing:
            db.add(AreaDistributionDefault(
                project_type="commercial", room_type=room_type, percentage=pct
            ))
            count += 1

    db.commit()
    logger.info(f"Seeded {count} area distribution default entries")


def seed_trade_multipliers(db):
    """Seed trade multipliers."""
    trade_data = {
        "residential": {
            "electrician": 1.5, "plumber": 1.2, "tiler": 2.0,
            "painter": 1.8, "carpenter": 0.8, "mason": 1.0,
            "plasterer": 1.5, "welder": 0.3, "supervisor": 0.5, "default": 1.0
        },
        "commercial": {
            "electrician": 2.5, "plumber": 1.8, "tiler": 2.2,
            "painter": 2.0, "carpenter": 1.2, "mason": 0.8,
            "plasterer": 1.8, "welder": 0.5, "supervisor": 0.8, "default": 1.2
        },
        "factory": {
            "electrician": 3.0, "plumber": 1.5, "tiler": 1.0,
            "painter": 1.2, "carpenter": 0.5, "mason": 1.5,
            "plasterer": 1.0, "welder": 2.0, "supervisor": 1.0, "default": 1.0
        }
    }

    count = 0
    for project_type, trades in trade_data.items():
        for trade_key, value in trades.items():
            existing = db.query(TradeMultiplier).filter_by(
                project_type=project_type, trade_key=trade_key
            ).first()
            if not existing:
                db.add(TradeMultiplier(
                    project_type=project_type, trade_key=trade_key, value=value
                ))
                count += 1

    db.commit()
    logger.info(f"Seeded {count} trade multiplier entries")


def seed_cost_component_splits(db):
    """Seed cost component splits."""
    splits = {
        "flooring": {"supply": 0.65, "installation": 0.15, "transport": 0.05, "misc": 0.15},
        "painting": {"supply": 0.45, "installation": 0.35, "transport": 0.05, "misc": 0.15},
        "plastering": {"supply": 0.30, "installation": 0.50, "transport": 0.05, "misc": 0.15},
        "electrical": {"supply": 0.70, "installation": 0.20, "transport": 0.02, "misc": 0.08},
        "plumbing": {"supply": 0.60, "installation": 0.25, "transport": 0.05, "misc": 0.10},
        "default": {"supply": 0.55, "installation": 0.25, "transport": 0.05, "misc": 0.15},
    }

    labels = {
        "supply": {"en": "Supply", "ar": "توريد"},
        "installation": {"en": "Installation", "ar": "تركيب"},
        "transport": {"en": "Transport & Site Logistics", "ar": "نقل وتشوينات"},
        "misc": {"en": "Sundries & Overheads", "ar": "مصروفات نثربة وهامش ربح"},
    }

    count = 0
    for category, components in splits.items():
        for component, percentage in components.items():
            existing = db.query(CostComponentSplit).filter_by(
                category=category, component=component
            ).first()
            if not existing:
                db.add(CostComponentSplit(
                    category=category, component=component,
                    percentage=percentage, label=labels.get(component)
                ))
                count += 1

    db.commit()
    logger.info(f"Seeded {count} cost component split entries")


def seed_category_keywords(db):
    """Seed category keywords for detection, brands, colors, finishes, material types."""
    entries = []

    # Category detection keywords - from quotation_descriptions.py and tools.py
    category_detection = {
        "flooring": ["flooring", "tile", "ceramic", "porcelain", "marble", "parquet", "أرضيات", "سيراميك", "بورسلين", "رخام"],
        "painting": ["paint", "painting", "دهان", "دهانات", "طلاء"],
        "plastering": ["plaster", "plastering", "بياض", "محارة", "تخشين"],
        "plumbing": ["plumbing", "plumber", "sanitaryware", "toilet", "sink", "shower", "سباكة", "مواسير", "حمام"],
        "electrical": ["electrical", "electrician", "wiring", "كهرباء", "أسلاك", "مفاتيح"],
        "carpentry": ["carpentry", "carpenter", "door", "window", "نجارة", "أبواب", "شبابيك"],
        "demolition": ["demolition", "breaking", "هدم", "تكسير"],
    }
    for group_key, keywords in category_detection.items():
        entries.append({"keyword_type": "category_detection", "group_key": group_key, "keywords": keywords})

    # Material type keywords - from cost_calculator.py TYPE_KEYWORDS
    material_type_keywords = {
        "tiles": ["tile", "ceramic", "porcelain", "floor tile", "بلاط", "سيراميك", "بورسلين"],
        "stone": ["marble", "granite", "رخام", "جرانيت"],
        "paint": ["paint", "emulsion", "coating", "دهان", "طلاء"],
        "plaster": ["plaster", "skim", "محارة", "بياض"],
        "cement": ["cement", "أسمنت"],
        "steel": ["steel", "iron", "rebar", "حديد"],
        "wood": ["wood", "timber", "parquet", "خشب", "باركيه"],
        "pipes": ["pipe", "diameter", "مواسير", "قطر"],
        "electrical": ["cable", "wire", "switch", "كهرباء", "سلك"],
        "glass": ["glass", "زجاج"],
        "brick": ["brick", "block", "طوب", "بلوك"],
        "vinyl": ["vinyl", "فينيل"],
    }
    for group_key, keywords in material_type_keywords.items():
        entries.append({"keyword_type": "material_type", "group_key": group_key, "keywords": keywords})

    # Material type detection for cost_calculator (mat_type detection)
    mat_type_detection = {
        "tile": ["tile", "ceramic", "porcelain", "marble", "flooring"],
        "paint": ["paint", "walls", "painting"],
        "plaster": ["plaster", "plastering"],
        "pipes": ["pipe", "plumb", "plumbing"],
        "electrical": ["cable", "wire", "switch", "electric", "electrical"],
        "wood": ["wood", "parquet", "cabinet", "carpentry"],
        "waterproofing": ["waterproof", "insulation"],
        "door": ["door", "window", "doors_windows"],
        "ceiling": ["ceiling", "ceilings"],
    }
    for group_key, keywords in mat_type_detection.items():
        entries.append({"keyword_type": "mat_type_detection", "group_key": group_key, "keywords": keywords})

    # Brand keywords - from quotation_descriptions.py and tools.py
    entries.append({"keyword_type": "brand", "group_key": "all", "keywords": [
        "knauf", "jotun", "sico", "italian", "carrara", "egyptian", "local"
    ]})

    # Brand display mappings
    entries.append({"keyword_type": "brand_display", "group_key": "mappings", "keywords": {
        "knauf": "White Knauf", "jotun": "Jotun", "sico": "Sico",
        "italian": "Italian", "carrara": "Italian Carrara"
    }})

    # Color keywords
    entries.append({"keyword_type": "color", "group_key": "all", "keywords": [
        "white", "beige", "light beige", "medium beige", "dark", "black", "cream", "brown"
    ]})

    # Finish keywords
    entries.append({"keyword_type": "finish", "group_key": "all", "keywords": [
        "matt", "matte", "glossy", "semi-glossy", "semi glossy", "satin"
    ]})

    # Stop words for keyword extraction
    entries.append({"keyword_type": "stop_words", "group_key": "en", "keywords": [
        "the", "for", "with", "and", "or", "of", "in", "on", "at", "to", "a", "an"
    ]})

    # User flooring preference keywords
    entries.append({"keyword_type": "flooring_preference", "group_key": "stone", "keywords": [
        "رخام", "marble", "granite", "جرانيت", "عايز رخام", "want marble", "عايز جرانيت"
    ]})
    entries.append({"keyword_type": "flooring_preference", "group_key": "tiles", "keywords": [
        "سيراميك", "ceramic", "porcelain", "بلاط", "عايز سيراميك", "want ceramic", "want tile"
    ]})
    entries.append({"keyword_type": "flooring_preference", "group_key": "wood", "keywords": [
        "خشب", "wood", "parquet", "باركيه", "عايز خشب", "want wood"
    ]})

    # Spec/context keywords
    entries.append({"keyword_type": "area_context", "group_key": "all", "keywords": [
        "sales area", "boh", "back office", "safe room", "bathroom", "kitchen", "living room", "bedroom"
    ]})
    entries.append({"keyword_type": "spec_features", "group_key": "all", "keywords": [
        "suspended", "access doors", "shadow gap", "premium", "luxury", "standard"
    ]})

    count = 0
    for entry in entries:
        existing = db.query(CategoryKeyword).filter_by(
            keyword_type=entry["keyword_type"], group_key=entry["group_key"]
        ).first()
        if not existing:
            db.add(CategoryKeyword(**entry))
            count += 1

    db.commit()
    logger.info(f"Seeded {count} category keyword entries")


def seed_description_templates(db):
    """Seed description templates for BOQ items."""
    templates = [
        # Flooring
        {
            "category": "flooring", "template_key": "main",
            "template_ar": (
                "بالمتر المسطح توريد وتركيب ارضيات {tile_type} أبعاد {tile_size} {color_info} {finish_info}"
                "{area_info}{brand_info}{context_info}{spec_info}"
                "مع عمل طبقة التسوية من الرمل والمونة وتعتمد العينة قبل التركيب "
                "ومحمل على البند تركيب وزرة من نفس نوع {tile_type} بارتفاع 10 سم "
                "والعمل طبقاً للأصول الصناعة والمواصفات الفنية والتنفيذ طبقاً للأبعاد الموضحة "
                "بالرسومات الهندسية المعتمدة والحساب الهندسي"
            ),
            "template_en": (
                "Supply and installation of flooring ({item_name}), {tile_size}, color {color_info}. "
                "Including sand and mortar leveling layer. Samples must be approved before installation. "
                "Including 10cm matching skirting. Work to follow technical specifications and engineering drawings."
            ),
            "variables": ["tile_type", "tile_size", "color_info", "finish_info", "area_info", "brand_info", "context_info", "spec_info", "item_name"],
        },
        # Painting
        {
            "category": "painting", "template_key": "main",
            "template_ar": (
                "بالمتر المسطح توريد وعمل دهان {paint_type} {surface_type} من النوع القابل للغسيل "
                "{finish_info}{color_info} {area_info}{brand} {context_info}{spec_info}"
                "طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف"
            ),
            "template_en": (
                "Supply and application of washable paint ({item_name}), {brand}. "
                "Color {color_info}, finish as requested. According to technical specifications and industry standards."
            ),
            "variables": ["paint_type", "surface_type", "finish_info", "color_info", "area_info", "brand", "context_info", "spec_info", "item_name"],
        },
        # Plastering
        {
            "category": "plastering", "template_key": "main",
            "template_ar": (
                "بالمتر المسطح توريد وتنفيذ بياض تخشين للحوائط الداخلية من مونة الاسمنت والرمل "
                "بنسبة {render_coat_ratio} كجم اسمنت بورتلاندي عادي لكل 3 م³ رمل ويشمل البند عمل الطرطشة قبل بياض التخشين "
                "من مونة تتكون من {spatter_dash_ratio} كجم اسمنت / م³ رمل وترش بالمياه ثم عمل البؤج والأوتار على الميزان "
                "مع معالجة الرشح والرطوبة إن وجدت والسعر يشمل إزالة البياض القديم المطبل ونقل المخلفات "
                "إلى المقالب العمومية ويتم نهو العمل {compliance_phrase}"
            ),
            "template_en": (
                "Supply and execution of internal wall plastering ({render_coat_ratio}kg cement per 3m³ sand). "
                "Including spatter dash ({spatter_dash_ratio}kg cement/m³ sand), leveling, and verticality check using master line and level."
            ),
            "variables": ["render_coat_ratio", "spatter_dash_ratio", "compliance_phrase"],
        },
        # Plumbing
        {
            "category": "plumbing", "template_key": "pipes",
            "template_ar": "بالمقطوعية توريد وتركيب {item_name} طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف",
            "template_en": "Lump sum supply and installation of {item_name} according to technical specifications and industry standards.",
            "variables": ["item_name"],
        },
        {
            "category": "plumbing", "template_key": "fixtures",
            "template_ar": "بالعدد توريد وتركيب {item_name} من النوع المطابق للمواصفات المصرية {compliance_phrase}",
            "template_en": "Per unit supply and installation of {item_name} conforming to Egyptian standards. {compliance_phrase_en}",
            "variables": ["item_name", "compliance_phrase", "compliance_phrase_en"],
        },
        # Electrical
        {
            "category": "electrical", "template_key": "wiring",
            "template_ar": "بالمتر الطولي توريد وتركيب {item_name} طبقاً للمواصفات الفنية المصرية وأصول الصناعة وتعليمات المهندس المشرف",
            "template_en": "Per linear meter supply and installation of {item_name} according to Egyptian technical specifications and industry standards.",
            "variables": ["item_name"],
        },
        {
            "category": "electrical", "template_key": "fixtures",
            "template_ar": "بالعدد توريد وتركيب {item_name} من النوع المطابق للمواصفات المصرية {compliance_phrase}",
            "template_en": "Per unit supply and installation of {item_name} conforming to Egyptian standards. {compliance_phrase_en}",
            "variables": ["item_name", "compliance_phrase", "compliance_phrase_en"],
        },
        # Carpentry - doors
        {
            "category": "carpentry", "template_key": "door",
            "template_ar": (
                "بالعدد توريد وتركيب باب {door_type} {dimensions} من المصانع المتخصصة "
                "من خشب مسكي مع كسوة بلوط شامل المقابض والمفصلات وقفل إيطالي كمبيوتر "
                "والكادر والدهان {compliance_phrase}"
            ),
            "template_en": (
                "Per unit supply and installation of {door_type} door {dimensions} from specialized factories. "
                "Solid wood with oak veneer including handles, hinges, Italian computer lock, frame and painting. "
                "{compliance_phrase_en}"
            ),
            "variables": ["door_type", "dimensions", "compliance_phrase", "compliance_phrase_en"],
        },
        # Carpentry - window
        {
            "category": "carpentry", "template_key": "window",
            "template_ar": "بالعدد توريد وتركيب {item_name} {dimensions} من المصانع المتخصصة طبقاً للمواصفات الفنية وأصول الصناعة وتعليمات المهندس المشرف",
            "template_en": "Per unit supply and installation of {item_name} {dimensions} from specialized factories. According to technical specifications and industry standards.",
            "variables": ["item_name", "dimensions"],
        },
        # Demolition
        {
            "category": "demolition", "template_key": "main",
            "template_ar": "بالمتر المسطح أعمال هدم وتكسير {item_name} وتشمل نقل المخلفات إلى المقالب العمومية {compliance_phrase}",
            "template_en": "Per sqm demolition and breaking of {item_name} including removal of debris to public dumps. {compliance_phrase_en}",
            "variables": ["item_name", "compliance_phrase", "compliance_phrase_en"],
        },
        # Generic/default
        {
            "category": "default", "template_key": "main",
            "template_ar": "{unit_prefix} توريد وتركيب {item_name} {compliance_phrase}",
            "template_en": "Supply and installation of {item_name}. {compliance_phrase_en}",
            "variables": ["unit_prefix", "item_name", "compliance_phrase", "compliance_phrase_en"],
        },
        # Labor description template
        {
            "category": "labor", "template_key": "main",
            "template_ar": "بالمقطوعية اعمال {role} للموقع تشمل كل ما يلزم لنهو العمل كاملاً طبقاً للمواصفات الفنية وأصول الصناعة.",
            "template_en": "Lump sum work for {role} at the site, including everything necessary to complete the work fully according to technical specifications.",
            "variables": ["role"],
        },
    ]

    count = 0
    for tmpl in templates:
        existing = db.query(DescriptionTemplate).filter_by(
            category=tmpl["category"], template_key=tmpl["template_key"]
        ).first()
        if not existing:
            db.add(DescriptionTemplate(**tmpl))
            count += 1

    db.commit()
    logger.info(f"Seeded {count} description template entries")


def seed_all():
    """Run all seed functions."""
    db = SessionLocal()
    try:
        logger.info("Starting construction config seed...")
        seed_construction_config(db)
        seed_room_multipliers(db)
        seed_area_distribution_defaults(db)
        seed_trade_multipliers(db)
        seed_cost_component_splits(db)
        seed_category_keywords(db)
        seed_description_templates(db)
        logger.info("Construction config seed completed successfully!")
    except Exception as e:
        logger.error(f"Error during seeding: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    seed_all()
