"""
Seed database with bilingual data from CSV files.

This script reads CSV files (compressed.csv, data1.csv, data2.csv, egy-con-cost.csv)
and populates the materials and labor_rates tables with JSONB bilingual data.
"""

import csv
import os
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.resources import Material, LaborRate, Category, Unit, Currency

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_or_create_unit(db: Session, unit_code: str, unit_name_en: str, unit_name_ar: str = None) -> Optional[int]:
    """Get or create a unit and return its ID."""
    if not unit_code:
        return None

    # Normalize unit codes
    unit_code_map = {
        'ton': 'ton', 'طن': 'ton',
        'm': 'm', 'متر': 'm', 'meter': 'm', 'linear m': 'm', 'متر طولي': 'm',
        'm2': 'm2', 'm²': 'm2', 'متر مربع': 'm2', 'flat meter': 'm2', 'متر مسطح': 'm2', 'square meter': 'm2',
        'm3': 'm3', 'm³': 'm3', 'متر مكعب': 'm3', 'cubic meter': 'm3',
        'kg': 'kg', 'كجم': 'kg',
        'kg/m²': 'kg_per_m2', 'kg/m³': 'kg_per_m3',  # Map to composite units
        '50k.g': 'bag', 'كجم/٥٠': 'bag', '50kg': 'bag', '50kg bag': 'bag',
        'thousand': 'thousand', 'ألف': 'thousand', '1000 units': 'thousand', 'thousand units': 'thousand', 'ألف وحدة': 'thousand',
        'piece': 'piece', 'قطعة': 'piece',
        'unit': 'unit', 'وحدة': 'unit',
        'day': 'day', 'يوم': 'day',
        'hour': 'hour', 'ساعة': 'hour', 'hr': 'hour',
        'bag': 'bag', 'شيكارة': 'bag',
        'roll': 'roll', 'رول': 'roll',
        'liter': 'liter', 'لتر': 'liter',
        'board': 'board', 'panel': 'board', 'لوح': 'board',
        'watt': 'watt', 'w': 'watt',
        'multiplier': 'unit',  # For price multipliers
        'n/a': None, 'غير متاح': None,  # Skip N/A units
    }

    # Handle Arabic descriptions that got into unit field
    if any(arabic_word in unit_code.lower() for arabic_word in ['طوب طفلي', 'أرضيات wpc', 'كلادينج wpc', 'بديل حجر']):
        logger.warning(f"Unit field contains description, skipping: {unit_code}")
        return None

    # Handle English descriptions that got into unit field
    if any(desc_word in unit_code.lower() for desc_word in ['cement-based insulating', 'lightweight clay', 'wpc flooring', 'pvc panel', 'polyurethane foam']):
        logger.warning(f"Unit field contains description, skipping: {unit_code}")
        return None

    # Extract just 'لوح' from descriptions like 'لوح PVC بطباعة رخام'
    if 'لوح' in unit_code and len(unit_code) > 10:  # If it's a long description containing لوح
        logger.debug(f"Extracting 'board' from description: {unit_code}")
        unit_code = 'لوح'

    normalized_code = unit_code_map.get(unit_code.lower().strip(), unit_code.lower().strip())

    unit = db.query(Unit).filter(Unit.code == normalized_code).first()
    if unit:
        return unit.id

    # If unit doesn't exist, log warning (units should be created by migration)
    logger.warning(f"Unit not found: {unit_code} (normalized: {normalized_code})")
    return None


def get_or_create_category(db: Session, category_code: str, category_name_en: str, category_name_ar: str = None, category_type: str = 'material') -> Optional[int]:
    """Get or create a category and return its ID."""
    if not category_code:
        return None

    # Normalize category codes
    category_code = category_code.lower().strip().replace(' ', '_').replace('&', 'and')

    category = db.query(Category).filter(Category.code == category_code).first()
    if category:
        return category.id

    # Create new category if it doesn't exist
    try:
        new_category = Category(
            code=category_code,
            name={
                "en": category_name_en,
                "ar": category_name_ar or category_name_en
            },
            category_type=category_type,
            is_active=True
        )
        db.add(new_category)
        db.commit()
        logger.info(f"Created new category: {category_code}")
        return new_category.id
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create category {category_code}: {e}")
        return None


def get_currency_id(db: Session, currency_code: str = 'EGP') -> Optional[int]:
    """Get currency ID by code."""
    currency = db.query(Currency).filter(Currency.code == currency_code).first()
    return currency.id if currency else None


def parse_price(price_str: str) -> Optional[Decimal]:
    """Parse price from string, handling various formats."""
    if not price_str or price_str in ['N/A', '', 'nan']:
        return None

    try:
        # Remove commas and spaces
        price_clean = str(price_str).replace(',', '').replace(' ', '').strip()
        return Decimal(price_clean)
    except Exception:
        return None


def seed_compressed_csv(db: Session, csv_path: str) -> int:
    """Seed data from compressed.csv (bilingual CAPMAS data)."""
    logger.info(f"Seeding from {csv_path}...")
    count = 0
    skipped = 0

    currency_id = get_currency_id(db, 'EGP')

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            content_type = row.get('Content Type', '').strip()

            # Only process price data rows
            if content_type != 'Price Data':
                continue

            name_en = row.get('Content (English)', '').strip()
            name_ar = row.get('Content (Arabic)', '').strip()
            data_point = row.get('Data Point', '').strip()  # e.g., "Price per Ton"
            value_str = row.get('Value', '').strip()
            category_en = row.get('Document Section', '').strip()

            if not name_en or not value_str:
                logger.debug(f"Skipping row - missing name or value: {name_en}")
                continue

            price = parse_price(value_str)
            if price is None:
                logger.debug(f"Skipping row - invalid price: {value_str}")
                continue

            # Extract unit from Data Point (e.g., "Price per Ton" → "Ton")
            unit_str = None
            if 'per' in data_point.lower():
                parts = data_point.lower().split('per')
                if len(parts) > 1:
                    unit_str = parts[1].strip()

            logger.debug(f"Processing: {name_en} | Unit: {unit_str} | Price: {price}")

            # Get unit ID
            unit_id = get_or_create_unit(db, unit_str, unit_str, unit_str) if unit_str else None

            # Get category ID
            category_id = get_or_create_category(db, category_en, category_en, category_en)

            try:
                # Check if material exists
                existing = db.query(Material).filter(
                    Material.name['en'].astext == name_en
                ).first()

                if existing:
                    # Update price
                    existing.price = price
                    existing.updated_at = None  # Will trigger auto-update
                    skipped += 1
                    logger.debug(f"Updated existing material: {name_en}")
                else:
                    # Create new material
                    material = Material(
                        name={"en": name_en, "ar": name_ar if name_ar else name_en},
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='compressed.csv - CAPMAS Jan 2025',
                        is_active=True
                    )
                    db.add(material)
                    count += 1

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to insert/update material {name_en}: {e}")
                import traceback
                traceback.print_exc()

    logger.info(f"Seeded {count} new materials from compressed.csv ({skipped} already existed and were updated)")
    return count + skipped


def seed_data1_csv(db: Session, csv_path: str) -> int:
    """Seed data from data1.csv (bilingual material data)."""
    logger.info(f"Seeding from {csv_path}...")
    count = 0

    currency_id = get_currency_id(db, 'EGP')

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            name_en = row.get('Commodity (English)', '').strip()
            name_ar = row.get('السلعة (Arabic)', '').strip()
            category_en = row.get('Category', '').strip()
            unit_en = row.get('Unit (English)', '').strip()
            unit_ar = row.get('الوحدة (Arabic)', '').strip()

            # Use Jan 2025 price
            price_str = row.get('Jan 2025', '').strip()

            if not name_en or not price_str:
                continue

            price = parse_price(price_str)
            if price is None:
                continue

            # Get unit ID
            unit_id = get_or_create_unit(db, unit_en, unit_en, unit_ar)

            # Get category ID
            category_id = get_or_create_category(db, category_en, category_en, category_en)

            try:
                # Check if material exists
                existing = db.query(Material).filter(
                    Material.name['en'].astext == name_en
                ).first()

                if existing:
                    # Update price
                    existing.price = price
                    existing.updated_at = None
                else:
                    # Create new material
                    material = Material(
                        name={"en": name_en, "ar": name_ar if name_ar else name_en},
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='data1.csv - CAPMAS Jan 2025',
                        is_active=True
                    )
                    db.add(material)

                db.commit()
                count += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to insert material {name_en}: {e}")

    logger.info(f"Seeded {count} materials from data1.csv")
    return count


def seed_egycon_cost_csv(db: Session, csv_path: str) -> int:
    """Seed data from egy-con-cost_bilingual.csv (Egypt construction costs with Arabic)."""
    logger.info(f"Seeding from {csv_path}...")
    materials_count = 0
    labor_count = 0

    currency_id = get_currency_id(db, 'EGP')

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

            # Parse price range (take average or min)
            try:
                if '-' in price_range:
                    # Range: "6,000 - 8,500"
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

            # Determine if this is labor or material
            is_labor = main_category == 'Labor Costs'

            # Build full name (English and Arabic)
            if spec and spec not in item_name and spec != 'N/A':
                full_name_en = f"{item_name} - {spec}"
            else:
                full_name_en = item_name

            if spec_ar and spec_ar not in item_name_ar and spec_ar != 'غير متاح':
                full_name_ar = f"{item_name_ar} - {spec_ar}"
            else:
                full_name_ar = item_name_ar if item_name_ar else item_name

            if is_labor:
                # Seed as labor rate
                # Extract daily or hourly rate
                is_daily = unit_str.lower() == 'day'

                # Get category
                labor_category_code = subcategory.lower().replace(' ', '_').replace('/', '_')
                category_id = get_or_create_category(
                    db,
                    f"labor_{labor_category_code}",
                    subcategory,
                    subcategory_ar if subcategory_ar else subcategory,
                    'labor'
                )

                try:
                    # Check if labor rate exists
                    existing = db.query(LaborRate).filter(
                        LaborRate.role['en'].astext == item_name
                    ).first()

                    if existing:
                        if is_daily:
                            existing.daily_rate = price
                        else:
                            existing.hourly_rate = price
                        existing.updated_at = None
                    else:
                        labor = LaborRate(
                            role={"en": item_name, "ar": full_name_ar},
                            description={"en": spec, "ar": spec_ar} if spec and spec != 'N/A' else None,
                            category_id=category_id,
                            daily_rate=price if is_daily else None,
                            hourly_rate=price if not is_daily else None,
                            currency_id=currency_id,
                            source='egy-con-cost_bilingual.csv - Egypt Construction Costs 2025',
                            is_active=True
                        )
                        db.add(labor)

                    db.commit()
                    labor_count += 1
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to insert labor rate {item_name}: {e}")
            else:
                # Seed as material
                # Get unit ID
                unit_id = get_or_create_unit(db, unit_str, unit_str, unit_str_ar)

                # Get category ID
                category_code = main_category.lower().replace(' ', '_')
                if subcategory:
                    category_code = f"{category_code}_{subcategory.lower().replace(' ', '_')}"

                category_name_en = subcategory if subcategory else main_category
                category_name_ar = subcategory_ar if subcategory_ar else main_category_ar
                category_id = get_or_create_category(db, category_code, category_name_en, category_name_ar)

                try:
                    # Check if material exists
                    existing = db.query(Material).filter(
                        Material.name['en'].astext == full_name_en
                    ).first()

                    if existing:
                        existing.price = price
                        existing.updated_at = None
                    else:
                        material = Material(
                            name={"en": full_name_en, "ar": full_name_ar},
                            description={"en": spec, "ar": spec_ar} if spec and spec != 'N/A' else None,
                            category_id=category_id,
                            unit_id=unit_id,
                            price=price,
                            currency_id=currency_id,
                            source='egy-con-cost_bilingual.csv - Egypt Construction Costs 2025',
                            is_active=True
                        )
                        db.add(material)

                    db.commit()
                    materials_count += 1
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to insert material {full_name_en}: {e}")

    logger.info(f"Seeded {materials_count} materials and {labor_count} labor rates from egy-con-cost_bilingual.csv")
    return materials_count + labor_count


def seed_data2_csv(db: Session, csv_path: str) -> int:
    """Seed data from data2_bilingual.csv (Informatics materials data with Arabic)."""
    logger.info(f"Seeding from {csv_path}...")
    count = 0

    currency_id = get_currency_id(db, 'EGP')

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

            # Use most recent price (December)
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

            # Get unit ID
            unit_id = get_or_create_unit(db, unit_str, unit_str, unit_str_ar)

            # Get category ID
            category_code = category_en.lower().replace(' ', '_').replace('&', 'and')
            if subcategory_en:
                category_code = f"{category_code}_{subcategory_en.lower().replace(' ', '_').replace('(', '').replace(')', '')}"

            category_name_en = subcategory_en if subcategory_en else category_en
            category_name_ar = subcategory_ar if subcategory_ar else category_ar
            category_id = get_or_create_category(db, category_code, category_name_en, category_name_ar)

            try:
                # Check if material exists
                existing = db.query(Material).filter(
                    Material.name['en'].astext == product_name
                ).first()

                if existing:
                    existing.price = price
                    existing.updated_at = None
                else:
                    material = Material(
                        name={"en": product_name, "ar": product_name_ar if product_name_ar else product_name},
                        description={"en": description, "ar": description_ar if description_ar else description} if description else None,
                        category_id=category_id,
                        unit_id=unit_id,
                        price=price,
                        currency_id=currency_id,
                        source='data2_bilingual.csv - Informatics 2025',
                        is_active=True
                    )
                    db.add(material)

                db.commit()
                count += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to insert material {product_name}: {e}")

    logger.info(f"Seeded {count} materials from data2_bilingual.csv")
    return count


def seed_all_csv_files():
    """Main function to seed all CSV files."""
    db = SessionLocal()
    try:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/clean"))
        logger.info(f"Using data directory: {data_dir}")
        logger.info("=" * 80)

        total_count = 0

        # Seed compressed.csv (CAPMAS bilingual data)
        compressed_csv = os.path.join(data_dir, "compressed.csv")
        if os.path.exists(compressed_csv):
            logger.info("📁 Processing compressed.csv...")
            total_count += seed_compressed_csv(db, compressed_csv)
        else:
            logger.warning(f"⚠️  File not found: {compressed_csv}")

        # Seed data1.csv (CAPMAS bilingual data)
        data1_csv = os.path.join(data_dir, "data1.csv")
        if os.path.exists(data1_csv):
            logger.info("📁 Processing data1.csv...")
            total_count += seed_data1_csv(db, data1_csv)
        else:
            logger.warning(f"⚠️  File not found: {data1_csv}")

        # Seed egy-con-cost_bilingual.csv (Egypt construction costs with Arabic)
        egycon_csv = os.path.join(data_dir, "egy-con-cost_bilingual.csv")
        if os.path.exists(egycon_csv):
            logger.info("📁 Processing egy-con-cost_bilingual.csv...")
            total_count += seed_egycon_cost_csv(db, egycon_csv)
        else:
            logger.warning(f"⚠️  File not found: {egycon_csv}")

        # Seed data2_bilingual.csv (Informatics data with Arabic)
        data2_csv = os.path.join(data_dir, "data2_bilingual.csv")
        if os.path.exists(data2_csv):
            logger.info("📁 Processing data2_bilingual.csv...")
            total_count += seed_data2_csv(db, data2_csv)
        else:
            logger.warning(f"⚠️  File not found: {data2_csv}")

        logger.info("=" * 80)
        logger.info(f"✅ COMPLETE: Seeded {total_count} total items from CSV files")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Critical error in seeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed_all_csv_files()
