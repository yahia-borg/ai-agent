#!/usr/bin/env python3
"""
Production Database Seeding Script

This is the SINGLE SOURCE OF TRUTH for seeding all database tables in production.
Run this script after deploying to a new server and running migrations.

Tables seeded (in order):
1. currencies - Reference table for currency support
2. units - Reference table for measurement units
3. categories - Reference table for material/labor categories
4. materials - Construction materials with prices (from CSV files)
5. labor_rates - Labor rates by role (from CSV files)

Usage:
    cd backend
    python -m scripts.seed_production

    # Or with docker:
    docker-compose exec backend python -m scripts.seed_production

    # Options:
    python -m scripts.seed_production --skip-csv     # Only seed reference tables
    python -m scripts.seed_production --clear-first  # Clear existing data first
    python -m scripts.seed_production --dry-run      # Show what would be done
"""

import argparse
import csv
import logging
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models.resources import Currency, Unit, Category, Material, LaborRate, MaterialSynonym

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# REFERENCE DATA DEFINITIONS
# =============================================================================

CURRENCIES = [
    {'code': 'EGP', 'name': {'en': 'Egyptian Pound', 'ar': 'جنيه مصري'}, 'symbol': 'ج.م', 'is_default': True},
    {'code': 'USD', 'name': {'en': 'US Dollar', 'ar': 'دولار أمريكي'}, 'symbol': '$', 'is_default': False},
    {'code': 'SAR', 'name': {'en': 'Saudi Riyal', 'ar': 'ريال سعودي'}, 'symbol': 'ر.س', 'is_default': False},
    {'code': 'EUR', 'name': {'en': 'Euro', 'ar': 'يورو'}, 'symbol': '€', 'is_default': False},
]

UNITS = [
    # Count units
    {'code': 'piece', 'name': {'en': 'Piece', 'ar': 'قطعة'}, 'symbol': 'pc', 'unit_type': 'count'},
    {'code': 'unit', 'name': {'en': 'Unit', 'ar': 'وحدة'}, 'symbol': 'u', 'unit_type': 'count'},
    {'code': 'thousand', 'name': {'en': 'Thousand', 'ar': 'ألف'}, 'symbol': '1k', 'unit_type': 'count'},
    {'code': 'board', 'name': {'en': 'Board', 'ar': 'لوح'}, 'symbol': 'bd', 'unit_type': 'count'},

    # Length units
    {'code': 'm', 'name': {'en': 'Meter', 'ar': 'متر'}, 'symbol': 'm', 'unit_type': 'length'},

    # Area units
    {'code': 'm2', 'name': {'en': 'Square Meter', 'ar': 'متر مربع'}, 'symbol': 'm²', 'unit_type': 'area'},
    {'code': 'sqft', 'name': {'en': 'Square Foot', 'ar': 'قدم مربع'}, 'symbol': 'ft²', 'unit_type': 'area'},

    # Volume units
    {'code': 'm3', 'name': {'en': 'Cubic Meter', 'ar': 'متر مكعب'}, 'symbol': 'm³', 'unit_type': 'volume'},
    {'code': 'liter', 'name': {'en': 'Liter', 'ar': 'لتر'}, 'symbol': 'L', 'unit_type': 'volume'},

    # Weight units
    {'code': 'kg', 'name': {'en': 'Kilogram', 'ar': 'كيلوجرام'}, 'symbol': 'kg', 'unit_type': 'weight'},
    {'code': 'ton', 'name': {'en': 'Ton', 'ar': 'طن'}, 'symbol': 't', 'unit_type': 'weight'},
    {'code': 'bag', 'name': {'en': 'Bag', 'ar': 'شيكارة'}, 'symbol': 'bag', 'unit_type': 'weight'},

    # Density units
    {'code': 'kg_per_m2', 'name': {'en': 'Kilogram per Square Meter', 'ar': 'كيلوجرام لكل متر مربع'}, 'symbol': 'kg/m²', 'unit_type': 'density'},
    {'code': 'kg_per_m3', 'name': {'en': 'Kilogram per Cubic Meter', 'ar': 'كيلوجرام لكل متر مكعب'}, 'symbol': 'kg/m³', 'unit_type': 'density'},

    # Time units
    {'code': 'hour', 'name': {'en': 'Hour', 'ar': 'ساعة'}, 'symbol': 'hr', 'unit_type': 'time'},
    {'code': 'day', 'name': {'en': 'Day', 'ar': 'يوم'}, 'symbol': 'day', 'unit_type': 'time'},

    # Other units
    {'code': 'roll', 'name': {'en': 'Roll', 'ar': 'رول'}, 'symbol': 'roll', 'unit_type': 'count'},
    {'code': 'watt', 'name': {'en': 'Watt', 'ar': 'واط'}, 'symbol': 'W', 'unit_type': 'power'},
]

MATERIAL_CATEGORIES = [
    {'code': 'cement', 'name': {'en': 'Cement', 'ar': 'أسمنت'}, 'sort_order': 1},
    {'code': 'steel', 'name': {'en': 'Steel & Iron', 'ar': 'حديد وصلب'}, 'sort_order': 2},
    {'code': 'bricks', 'name': {'en': 'Bricks & Blocks', 'ar': 'طوب وبلوكات'}, 'sort_order': 3},
    {'code': 'sand', 'name': {'en': 'Sand & Aggregates', 'ar': 'رمل وركام'}, 'sort_order': 4},
    {'code': 'concrete', 'name': {'en': 'Concrete', 'ar': 'خرسانة'}, 'sort_order': 5},
    {'code': 'wood', 'name': {'en': 'Wood & Timber', 'ar': 'أخشاب'}, 'sort_order': 6},
    {'code': 'tiles', 'name': {'en': 'Tiles & Flooring', 'ar': 'بلاط وأرضيات'}, 'sort_order': 7},
    {'code': 'paint', 'name': {'en': 'Paints & Finishes', 'ar': 'دهانات وتشطيبات'}, 'sort_order': 8},
    {'code': 'plumbing', 'name': {'en': 'Plumbing Materials', 'ar': 'مواد سباكة'}, 'sort_order': 9},
    {'code': 'electrical', 'name': {'en': 'Electrical Materials', 'ar': 'مواد كهرباء'}, 'sort_order': 10},
    {'code': 'insulation', 'name': {'en': 'Insulation', 'ar': 'عزل'}, 'sort_order': 11},
    {'code': 'fixtures', 'name': {'en': 'Fixtures & Fittings', 'ar': 'تركيبات'}, 'sort_order': 12},
    {'code': 'glass', 'name': {'en': 'Glass', 'ar': 'زجاج'}, 'sort_order': 13},
    {'code': 'adhesives', 'name': {'en': 'Adhesives & Sealants', 'ar': 'لواصق ومانعات تسرب'}, 'sort_order': 14},
    {'code': 'tools', 'name': {'en': 'Tools & Equipment', 'ar': 'أدوات ومعدات'}, 'sort_order': 15},
]

LABOR_CATEGORIES = [
    {'code': 'labor_masonry', 'name': {'en': 'Masonry Work', 'ar': 'أعمال بناء'}, 'sort_order': 101},
    {'code': 'labor_electrical', 'name': {'en': 'Electrical Work', 'ar': 'أعمال كهرباء'}, 'sort_order': 102},
    {'code': 'labor_plumbing', 'name': {'en': 'Plumbing Work', 'ar': 'أعمال سباكة'}, 'sort_order': 103},
    {'code': 'labor_painting', 'name': {'en': 'Painting Work', 'ar': 'أعمال دهانات'}, 'sort_order': 104},
    {'code': 'labor_tiling', 'name': {'en': 'Tiling Work', 'ar': 'أعمال بلاط'}, 'sort_order': 105},
    {'code': 'labor_carpentry', 'name': {'en': 'Carpentry Work', 'ar': 'أعمال نجارة'}, 'sort_order': 106},
    {'code': 'labor_plastering', 'name': {'en': 'Plastering Work', 'ar': 'أعمال محارة'}, 'sort_order': 107},
    {'code': 'labor_welding', 'name': {'en': 'Welding Work', 'ar': 'أعمال لحام'}, 'sort_order': 108},
    {'code': 'labor_general', 'name': {'en': 'General Labor', 'ar': 'عمالة عامة'}, 'sort_order': 109},
    {'code': 'labor_supervision', 'name': {'en': 'Supervision', 'ar': 'إشراف'}, 'sort_order': 110},
]


# =============================================================================
# UNIT NORMALIZATION MAP
# =============================================================================

UNIT_CODE_MAP = {
    # Weight
    'ton': 'ton', 'طن': 'ton',
    'kg': 'kg', 'كجم': 'kg',
    '50k.g': 'bag', 'كجم/٥٠': 'bag', '50kg': 'bag', '50kg bag': 'bag',

    # Length
    'm': 'm', 'متر': 'm', 'meter': 'm', 'linear m': 'm', 'متر طولي': 'm',

    # Area
    'm2': 'm2', 'm²': 'm2', 'متر مربع': 'm2', 'flat meter': 'm2',
    'متر مسطح': 'm2', 'square meter': 'm2', 'sq m': 'm2',

    # Volume
    'm3': 'm3', 'm³': 'm3', 'متر مكعب': 'm3', 'cubic meter': 'm3',
    'liter': 'liter', 'لتر': 'liter', 'l': 'liter',

    # Density
    'kg/m²': 'kg_per_m2', 'kg/m³': 'kg_per_m3',

    # Count
    'thousand': 'thousand', 'ألف': 'thousand', '1000 units': 'thousand',
    'thousand units': 'thousand', 'ألف وحدة': 'thousand',
    'piece': 'piece', 'قطعة': 'piece', 'pcs': 'piece',
    'unit': 'unit', 'وحدة': 'unit',
    'bag': 'bag', 'شيكارة': 'bag',
    'roll': 'roll', 'رول': 'roll',
    'board': 'board', 'panel': 'board', 'لوح': 'board',

    # Time
    'day': 'day', 'يوم': 'day',
    'hour': 'hour', 'ساعة': 'hour', 'hr': 'hour',

    # Power
    'watt': 'watt', 'w': 'watt',

    # Skip
    'multiplier': 'unit',
    'n/a': None, 'غير متاح': None,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_price(price_str: str) -> Optional[Decimal]:
    """Parse price from string, handling various formats."""
    if not price_str or str(price_str).strip() in ['N/A', '', 'nan', 'None']:
        return None

    try:
        # Remove commas, spaces, and currency symbols
        price_clean = str(price_str).replace(',', '').replace(' ', '').strip()
        price_clean = price_clean.replace('EGP', '').replace('ج.م', '').strip()
        return Decimal(price_clean)
    except (InvalidOperation, ValueError):
        return None


def normalize_unit_code(unit_str: str) -> Optional[str]:
    """Normalize unit string to standard code."""
    if not unit_str:
        return None

    unit_lower = unit_str.lower().strip()

    # Check for descriptions that got into unit field
    description_markers = [
        'طوب طفلي', 'أرضيات wpc', 'كلادينج wpc', 'بديل حجر',
        'cement-based', 'lightweight clay', 'wpc flooring',
        'pvc panel', 'polyurethane foam'
    ]
    if any(marker in unit_lower for marker in description_markers):
        return None

    # Extract just 'لوح' from descriptions
    if 'لوح' in unit_str and len(unit_str) > 10:
        unit_lower = 'لوح'

    return UNIT_CODE_MAP.get(unit_lower, unit_lower if unit_lower else None)


def get_unit_id(db: Session, unit_str: str, unit_cache: Dict[str, int]) -> Optional[int]:
    """Get unit ID by code, using cache for performance."""
    normalized = normalize_unit_code(unit_str)
    if not normalized:
        return None

    if normalized in unit_cache:
        return unit_cache[normalized]

    unit = db.query(Unit).filter(Unit.code == normalized).first()
    if unit:
        unit_cache[normalized] = unit.id
        return unit.id

    logger.warning(f"Unit not found: {unit_str} (normalized: {normalized})")
    return None


def get_or_create_category(
    db: Session,
    code: str,
    name_en: str,
    name_ar: str,
    category_type: str,
    category_cache: Dict[str, int]
) -> Optional[int]:
    """Get or create a category and return its ID."""
    if not code:
        return None

    # Normalize code
    code = code.lower().strip().replace(' ', '_').replace('&', 'and')

    if code in category_cache:
        return category_cache[code]

    category = db.query(Category).filter(Category.code == code).first()
    if category:
        category_cache[code] = category.id
        return category.id

    # Create new category
    try:
        new_category = Category(
            code=code,
            name={'en': name_en, 'ar': name_ar or name_en},
            category_type=category_type,
            is_active=True
        )
        db.add(new_category)
        db.commit()
        logger.info(f"Created new category: {code}")
        category_cache[code] = new_category.id
        return new_category.id
    except IntegrityError:
        db.rollback()
        # Race condition - try to get it again
        category = db.query(Category).filter(Category.code == code).first()
        if category:
            category_cache[code] = category.id
            return category.id
        return None


def get_currency_id(db: Session, currency_code: str = 'EGP') -> Optional[int]:
    """Get currency ID by code."""
    currency = db.query(Currency).filter(Currency.code == currency_code).first()
    return currency.id if currency else None


# =============================================================================
# REFERENCE TABLE SEEDERS
# =============================================================================

def seed_currencies(db: Session, dry_run: bool = False) -> int:
    """Seed currencies table."""
    logger.info("Seeding currencies...")
    count = 0

    for currency_data in CURRENCIES:
        existing = db.query(Currency).filter(Currency.code == currency_data['code']).first()

        if existing:
            logger.debug(f"Currency already exists: {currency_data['code']}")
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would create currency: {currency_data['code']}")
            count += 1
            continue

        try:
            currency = Currency(
                code=currency_data['code'],
                name=currency_data['name'],
                symbol=currency_data['symbol'],
                is_default=currency_data['is_default'],
                is_active=True
            )
            db.add(currency)
            db.commit()
            count += 1
            logger.info(f"Created currency: {currency_data['code']}")
        except IntegrityError:
            db.rollback()
            logger.warning(f"Currency already exists: {currency_data['code']}")

    return count


def seed_units(db: Session, dry_run: bool = False) -> int:
    """Seed units table."""
    logger.info("Seeding units...")
    count = 0

    for unit_data in UNITS:
        existing = db.query(Unit).filter(Unit.code == unit_data['code']).first()

        if existing:
            logger.debug(f"Unit already exists: {unit_data['code']}")
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would create unit: {unit_data['code']}")
            count += 1
            continue

        try:
            unit = Unit(
                code=unit_data['code'],
                name=unit_data['name'],
                symbol=unit_data['symbol'],
                unit_type=unit_data['unit_type'],
                is_active=True
            )
            db.add(unit)
            db.commit()
            count += 1
            logger.info(f"Created unit: {unit_data['code']}")
        except IntegrityError:
            db.rollback()
            logger.warning(f"Unit already exists: {unit_data['code']}")

    return count


def seed_categories(db: Session, dry_run: bool = False) -> int:
    """Seed categories table (both material and labor)."""
    logger.info("Seeding categories...")
    count = 0

    # Material categories
    for cat_data in MATERIAL_CATEGORIES:
        existing = db.query(Category).filter(Category.code == cat_data['code']).first()

        if existing:
            logger.debug(f"Category already exists: {cat_data['code']}")
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would create material category: {cat_data['code']}")
            count += 1
            continue

        try:
            category = Category(
                code=cat_data['code'],
                name=cat_data['name'],
                category_type='material',
                sort_order=cat_data['sort_order'],
                is_active=True
            )
            db.add(category)
            db.commit()
            count += 1
            logger.info(f"Created material category: {cat_data['code']}")
        except IntegrityError:
            db.rollback()
            logger.warning(f"Category already exists: {cat_data['code']}")

    # Labor categories
    for cat_data in LABOR_CATEGORIES:
        existing = db.query(Category).filter(Category.code == cat_data['code']).first()

        if existing:
            logger.debug(f"Category already exists: {cat_data['code']}")
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would create labor category: {cat_data['code']}")
            count += 1
            continue

        try:
            category = Category(
                code=cat_data['code'],
                name=cat_data['name'],
                category_type='labor',
                sort_order=cat_data['sort_order'],
                is_active=True
            )
            db.add(category)
            db.commit()
            count += 1
            logger.info(f"Created labor category: {cat_data['code']}")
        except IntegrityError:
            db.rollback()
            logger.warning(f"Category already exists: {cat_data['code']}")

    return count


# =============================================================================
# CSV SEEDERS
# =============================================================================

def seed_compressed_csv(
    db: Session,
    csv_path: str,
    currency_id: int,
    unit_cache: Dict[str, int],
    category_cache: Dict[str, int],
    dry_run: bool = False
) -> Tuple[int, int]:
    """Seed data from compressed.csv (CAPMAS bilingual data)."""
    logger.info(f"Processing {csv_path}...")
    created = 0
    updated = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            content_type = row.get('Content Type', '').strip()
            if content_type != 'Price Data':
                continue

            name_en = row.get('Content (English)', '').strip()
            name_ar = row.get('Content (Arabic)', '').strip()
            data_point = row.get('Data Point', '').strip()
            value_str = row.get('Value', '').strip()
            category_en = row.get('Document Section', '').strip()

            if not name_en or not value_str:
                continue

            price = parse_price(value_str)
            if price is None:
                continue

            # Extract unit from Data Point
            unit_str = None
            if 'per' in data_point.lower():
                parts = data_point.lower().split('per')
                if len(parts) > 1:
                    unit_str = parts[1].strip()

            unit_id = get_unit_id(db, unit_str, unit_cache) if unit_str else None
            category_id = get_or_create_category(
                db, category_en, category_en, category_en, 'material', category_cache
            )

            if dry_run:
                logger.debug(f"[DRY RUN] Would process: {name_en}")
                created += 1
                continue

            try:
                existing = db.query(Material).filter(
                    Material.name['en'].astext == name_en
                ).first()

                if existing:
                    existing.price = price
                    db.commit()
                    updated += 1
                else:
                    material = Material(
                        name={'en': name_en, 'ar': name_ar or name_en},
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='compressed.csv - CAPMAS Jan 2025',
                        is_active=True
                    )
                    db.add(material)
                    db.commit()
                    created += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to process material {name_en}: {e}")

    logger.info(f"compressed.csv: {created} created, {updated} updated")
    return created, updated


def seed_data1_csv(
    db: Session,
    csv_path: str,
    currency_id: int,
    unit_cache: Dict[str, int],
    category_cache: Dict[str, int],
    dry_run: bool = False
) -> Tuple[int, int]:
    """Seed data from data1.csv (CAPMAS commodities)."""
    logger.info(f"Processing {csv_path}...")
    created = 0
    updated = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            name_en = row.get('Commodity (English)', '').strip()
            name_ar = row.get('السلعة (Arabic)', '').strip()
            category_en = row.get('Category', '').strip()
            unit_en = row.get('Unit (English)', '').strip()
            unit_ar = row.get('الوحدة (Arabic)', '').strip()
            price_str = row.get('Jan 2025', '').strip()

            if not name_en or not price_str:
                continue

            price = parse_price(price_str)
            if price is None:
                continue

            unit_id = get_unit_id(db, unit_en, unit_cache)
            category_id = get_or_create_category(
                db, category_en, category_en, category_en, 'material', category_cache
            )

            if dry_run:
                logger.debug(f"[DRY RUN] Would process: {name_en}")
                created += 1
                continue

            try:
                existing = db.query(Material).filter(
                    Material.name['en'].astext == name_en
                ).first()

                if existing:
                    existing.price = price
                    db.commit()
                    updated += 1
                else:
                    material = Material(
                        name={'en': name_en, 'ar': name_ar or name_en},
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='data1.csv - CAPMAS Jan 2025',
                        is_active=True
                    )
                    db.add(material)
                    db.commit()
                    created += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to process material {name_en}: {e}")

    logger.info(f"data1.csv: {created} created, {updated} updated")
    return created, updated


def seed_egycon_cost_csv(
    db: Session,
    csv_path: str,
    currency_id: int,
    unit_cache: Dict[str, int],
    category_cache: Dict[str, int],
    dry_run: bool = False
) -> Tuple[int, int, int, int]:
    """Seed data from egy-con-cost_bilingual.csv (materials AND labor)."""
    logger.info(f"Processing {csv_path}...")
    materials_created = 0
    materials_updated = 0
    labor_created = 0
    labor_updated = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            main_category = row.get('Category', '').strip()
            main_category_ar = row.get('Category_AR', '').strip()
            subcategory = row.get('Subcategory', '').strip()
            subcategory_ar = row.get('Subcategory_AR', '').strip()
            item_name = row.get('Item', '').strip()
            item_name_ar = row.get('Item_AR', '').strip()
            spec = row.get('Specification', '').strip()
            spec_ar = row.get('Specification_AR', '').strip()
            unit_str = row.get('Unit', '').strip()
            unit_str_ar = row.get('Unit_AR', '').strip()
            price_range = row.get('Price Range (EGP)', '').strip()

            if not item_name or not price_range:
                continue

            # Parse price range (take average)
            try:
                if '-' in price_range:
                    prices = price_range.replace(',', '').split('-')
                    min_price = Decimal(prices[0].strip())
                    max_price = Decimal(prices[1].strip())
                    price = (min_price + max_price) / 2
                else:
                    price = parse_price(price_range)

                if price is None:
                    continue
            except Exception:
                continue

            is_labor = main_category == 'Labor Costs'

            # Build full name
            if spec and spec not in item_name and spec != 'N/A':
                full_name_en = f"{item_name} - {spec}"
            else:
                full_name_en = item_name

            if spec_ar and spec_ar not in item_name_ar and spec_ar != 'غير متاح':
                full_name_ar = f"{item_name_ar} - {spec_ar}"
            else:
                full_name_ar = item_name_ar or item_name

            if is_labor:
                # Process as labor rate
                is_daily = unit_str.lower() == 'day'
                labor_category_code = subcategory.lower().replace(' ', '_').replace('/', '_')
                category_id = get_or_create_category(
                    db,
                    f"labor_{labor_category_code}",
                    subcategory,
                    subcategory_ar or subcategory,
                    'labor',
                    category_cache
                )

                # Use specification as role name if specific trade
                if spec and spec not in ['N/A', 'غير متاح', '']:
                    role_en = spec
                    role_ar = spec_ar if spec_ar and spec_ar not in ['غير متاح', ''] else spec
                    description_en = f"{item_name} - {spec}"
                    description_ar = f"{item_name_ar} - {spec_ar}" if item_name_ar and spec_ar else description_en
                else:
                    role_en = item_name
                    role_ar = item_name_ar or item_name
                    description_en = item_name
                    description_ar = item_name_ar or item_name

                if dry_run:
                    logger.debug(f"[DRY RUN] Would process labor: {role_en}")
                    labor_created += 1
                    continue

                try:
                    existing = db.query(LaborRate).filter(
                        LaborRate.role['en'].astext == role_en
                    ).first()

                    if existing:
                        if is_daily:
                            existing.daily_rate = price
                        else:
                            existing.hourly_rate = price
                        db.commit()
                        labor_updated += 1
                    else:
                        labor = LaborRate(
                            role={'en': role_en, 'ar': role_ar},
                            description={'en': description_en, 'ar': description_ar},
                            category_id=category_id,
                            daily_rate=price if is_daily else None,
                            hourly_rate=price if not is_daily else None,
                            currency_id=currency_id,
                            source='egy-con-cost_bilingual.csv - Egypt Construction 2025',
                            is_active=True
                        )
                        db.add(labor)
                        db.commit()
                        labor_created += 1
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to process labor rate {role_en}: {e}")
            else:
                # Process as material
                unit_id = get_unit_id(db, unit_str, unit_cache)
                category_code = main_category.lower().replace(' ', '_')
                if subcategory:
                    category_code = f"{category_code}_{subcategory.lower().replace(' ', '_')}"

                category_name_en = subcategory or main_category
                category_name_ar = subcategory_ar or main_category_ar
                category_id = get_or_create_category(
                    db, category_code, category_name_en, category_name_ar, 'material', category_cache
                )

                if dry_run:
                    logger.debug(f"[DRY RUN] Would process material: {full_name_en}")
                    materials_created += 1
                    continue

                try:
                    existing = db.query(Material).filter(
                        Material.name['en'].astext == full_name_en
                    ).first()

                    if existing:
                        existing.price = price
                        db.commit()
                        materials_updated += 1
                    else:
                        material = Material(
                            name={'en': full_name_en, 'ar': full_name_ar},
                            description={'en': spec, 'ar': spec_ar} if spec and spec != 'N/A' else None,
                            category_id=category_id,
                            unit_id=unit_id,
                            price=price,
                            currency_id=currency_id,
                            source='egy-con-cost_bilingual.csv - Egypt Construction 2025',
                            is_active=True
                        )
                        db.add(material)
                        db.commit()
                        materials_created += 1
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to process material {full_name_en}: {e}")

    logger.info(f"egy-con-cost.csv: {materials_created} materials created, {materials_updated} updated")
    logger.info(f"egy-con-cost.csv: {labor_created} labor rates created, {labor_updated} updated")
    return materials_created, materials_updated, labor_created, labor_updated


def seed_data2_csv(
    db: Session,
    csv_path: str,
    currency_id: int,
    unit_cache: Dict[str, int],
    category_cache: Dict[str, int],
    dry_run: bool = False
) -> Tuple[int, int]:
    """Seed data from data2_bilingual.csv (Informatics materials)."""
    logger.info(f"Processing {csv_path}...")
    created = 0
    updated = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            category_en = row.get('Category', '').strip()
            category_ar = row.get('Category_AR', '').strip()
            subcategory_en = row.get('Subcategory', '').strip()
            subcategory_ar = row.get('Subcategory_AR', '').strip()
            product_name = row.get('Product Name', '').strip()
            product_name_ar = row.get('Product Name_AR', '').strip()
            description = row.get('Product Description', '').strip()
            description_ar = row.get('Product Description_AR', '').strip()
            unit_str = row.get('Unit', '').strip()
            unit_str_ar = row.get('Unit_AR', '').strip()

            # Use most recent price
            price_str = row.get('December', '').strip()
            if not price_str:
                price_str = row.get('November', '').strip()
            if not price_str:
                price_str = row.get('October', '').strip()

            if not product_name or not price_str:
                continue

            price = parse_price(price_str)
            if price is None:
                continue

            unit_id = get_unit_id(db, unit_str, unit_cache)
            category_code = category_en.lower().replace(' ', '_').replace('&', 'and')
            if subcategory_en:
                category_code = f"{category_code}_{subcategory_en.lower().replace(' ', '_').replace('(', '').replace(')', '')}"

            category_name_en = subcategory_en or category_en
            category_name_ar = subcategory_ar or category_ar
            category_id = get_or_create_category(
                db, category_code, category_name_en, category_name_ar, 'material', category_cache
            )

            if dry_run:
                logger.debug(f"[DRY RUN] Would process: {product_name}")
                created += 1
                continue

            try:
                existing = db.query(Material).filter(
                    Material.name['en'].astext == product_name
                ).first()

                if existing:
                    existing.price = price
                    db.commit()
                    updated += 1
                else:
                    material = Material(
                        name={'en': product_name, 'ar': product_name_ar or product_name},
                        description={'en': description, 'ar': description_ar or description} if description else None,
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='data2_bilingual.csv - Informatics 2025',
                        is_active=True
                    )
                    db.add(material)
                    db.commit()
                    created += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to process material {product_name}: {e}")

    logger.info(f"data2.csv: {created} created, {updated} updated")
    return created, updated


# =============================================================================
# MAIN SEEDING FUNCTIONS
# =============================================================================

def seed_reference_tables(db: Session, dry_run: bool = False) -> Dict[str, int]:
    """Seed all reference tables (currencies, units, categories)."""
    logger.info("=" * 60)
    logger.info("SEEDING REFERENCE TABLES")
    logger.info("=" * 60)

    results = {
        'currencies': seed_currencies(db, dry_run),
        'units': seed_units(db, dry_run),
        'categories': seed_categories(db, dry_run),
    }

    return results


def seed_csv_data(db: Session, data_dir: str, dry_run: bool = False) -> Dict[str, int]:
    """Seed materials and labor rates from CSV files."""
    logger.info("=" * 60)
    logger.info("SEEDING CSV DATA")
    logger.info("=" * 60)

    # Get currency ID
    currency_id = get_currency_id(db, 'EGP')
    if not currency_id:
        logger.error("EGP currency not found! Run reference table seeding first.")
        return {}

    # Caches for performance
    unit_cache: Dict[str, int] = {}
    category_cache: Dict[str, int] = {}

    results = {
        'materials_created': 0,
        'materials_updated': 0,
        'labor_created': 0,
        'labor_updated': 0,
    }

    # Process compressed.csv
    csv_path = os.path.join(data_dir, 'compressed.csv')
    if os.path.exists(csv_path):
        created, updated = seed_compressed_csv(
            db, csv_path, currency_id, unit_cache, category_cache, dry_run
        )
        results['materials_created'] += created
        results['materials_updated'] += updated
    else:
        logger.warning(f"File not found: {csv_path}")

    # Process data1.csv
    csv_path = os.path.join(data_dir, 'data1.csv')
    if os.path.exists(csv_path):
        created, updated = seed_data1_csv(
            db, csv_path, currency_id, unit_cache, category_cache, dry_run
        )
        results['materials_created'] += created
        results['materials_updated'] += updated
    else:
        logger.warning(f"File not found: {csv_path}")

    # Process egy-con-cost_bilingual.csv (materials + labor)
    csv_path = os.path.join(data_dir, 'egy-con-cost_bilingual.csv')
    if os.path.exists(csv_path):
        mat_created, mat_updated, lab_created, lab_updated = seed_egycon_cost_csv(
            db, csv_path, currency_id, unit_cache, category_cache, dry_run
        )
        results['materials_created'] += mat_created
        results['materials_updated'] += mat_updated
        results['labor_created'] += lab_created
        results['labor_updated'] += lab_updated
    else:
        logger.warning(f"File not found: {csv_path}")

    # Process data2_bilingual.csv
    csv_path = os.path.join(data_dir, 'data2_bilingual.csv')
    if os.path.exists(csv_path):
        created, updated = seed_data2_csv(
            db, csv_path, currency_id, unit_cache, category_cache, dry_run
        )
        results['materials_created'] += created
        results['materials_updated'] += updated
    else:
        logger.warning(f"File not found: {csv_path}")

    return results


def clear_data(db: Session, dry_run: bool = False) -> None:
    """Clear existing data (materials, labor_rates, categories created from CSV)."""
    logger.warning("CLEARING EXISTING DATA...")

    if dry_run:
        logger.info("[DRY RUN] Would delete all materials, labor_rates, and CSV-created categories")
        return

    # Delete materials (synonyms cascade)
    count = db.query(Material).delete()
    logger.info(f"Deleted {count} materials")

    # Delete labor rates
    count = db.query(LaborRate).delete()
    logger.info(f"Deleted {count} labor rates")

    # Delete CSV-created categories (not base categories)
    base_codes = [c['code'] for c in MATERIAL_CATEGORIES + LABOR_CATEGORIES]
    count = db.query(Category).filter(~Category.code.in_(base_codes)).delete()
    logger.info(f"Deleted {count} CSV-created categories")

    db.commit()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Production database seeding script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.seed_production              # Full seeding
  python -m scripts.seed_production --skip-csv   # Only reference tables
  python -m scripts.seed_production --dry-run    # Preview changes
  python -m scripts.seed_production --clear-first # Clear and reseed
        """
    )
    parser.add_argument(
        '--skip-csv',
        action='store_true',
        help='Only seed reference tables (currencies, units, categories)'
    )
    parser.add_argument(
        '--clear-first',
        action='store_true',
        help='Clear existing data before seeding'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default=None,
        help='Path to data directory containing CSV files'
    )

    args = parser.parse_args()

    # Determine data directory
    if args.data_dir:
        data_dir = args.data_dir
    else:
        # Default: backend/../data/clean
        data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../../data/clean')
        )

    logger.info("=" * 60)
    logger.info("PRODUCTION DATABASE SEEDING")
    logger.info("=" * 60)
    logger.info(f"Data directory: {data_dir}")
    if args.dry_run:
        logger.info("MODE: DRY RUN (no changes will be made)")
    logger.info("")

    db = SessionLocal()

    try:
        # Clear existing data if requested
        if args.clear_first:
            clear_data(db, args.dry_run)

        # Seed reference tables
        ref_results = seed_reference_tables(db, args.dry_run)

        # Seed CSV data
        csv_results = {}
        if not args.skip_csv:
            csv_results = seed_csv_data(db, data_dir, args.dry_run)

        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("SEEDING COMPLETE - SUMMARY")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Reference Tables:")
        logger.info(f"  - Currencies created: {ref_results.get('currencies', 0)}")
        logger.info(f"  - Units created: {ref_results.get('units', 0)}")
        logger.info(f"  - Categories created: {ref_results.get('categories', 0)}")

        if csv_results:
            logger.info("")
            logger.info("CSV Data:")
            logger.info(f"  - Materials created: {csv_results.get('materials_created', 0)}")
            logger.info(f"  - Materials updated: {csv_results.get('materials_updated', 0)}")
            logger.info(f"  - Labor rates created: {csv_results.get('labor_created', 0)}")
            logger.info(f"  - Labor rates updated: {csv_results.get('labor_updated', 0)}")

        logger.info("")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Critical error during seeding: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    main()
