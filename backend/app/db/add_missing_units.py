"""
Add missing units to the database.

This script adds units that are referenced in CSV files but missing from the migration.
"""

import logging
from sqlalchemy.exc import IntegrityError
from app.core.database import SessionLocal
from app.models.resources import Unit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_missing_units():
    """Add missing units to the database."""
    db = SessionLocal()

    missing_units = [
        # Count units
        {'code': 'thousand', 'name': {'en': 'Thousand', 'ar': 'ألف'}, 'symbol': '1k', 'unit_type': 'count'},

        # Composite units (density/intensity)
        {'code': 'kg_per_m2', 'name': {'en': 'Kilogram per Square Meter', 'ar': 'كيلوجرام لكل متر مربع'}, 'symbol': 'kg/m²', 'unit_type': 'density'},
        {'code': 'kg_per_m3', 'name': {'en': 'Kilogram per Cubic Meter', 'ar': 'كيلوجرام لكل متر مكعب'}, 'symbol': 'kg/m³', 'unit_type': 'density'},

        # Board/Panel
        {'code': 'board', 'name': {'en': 'Board', 'ar': 'لوح'}, 'symbol': 'bd', 'unit_type': 'count'},

        # Watt
        {'code': 'watt', 'name': {'en': 'Watt', 'ar': 'واط'}, 'symbol': 'W', 'unit_type': 'power'},
    ]

    added_count = 0

    try:
        for unit_data in missing_units:
            try:
                # Check if unit already exists
                existing = db.query(Unit).filter(Unit.code == unit_data['code']).first()

                if existing:
                    logger.info(f"Unit already exists: {unit_data['code']}")
                    continue

                # Create new unit
                unit = Unit(
                    code=unit_data['code'],
                    name=unit_data['name'],
                    symbol=unit_data['symbol'],
                    unit_type=unit_data['unit_type'],
                    is_active=True
                )
                db.add(unit)
                db.commit()
                added_count += 1
                logger.info(f"✅ Added unit: {unit_data['code']} ({unit_data['name']['en']})")

            except IntegrityError as e:
                db.rollback()
                logger.warning(f"⚠️  Unit {unit_data['code']} already exists or constraint error: {e}")
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Failed to add unit {unit_data['code']}: {e}")

        logger.info(f"\n✅ Added {added_count} new units to the database")

    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    add_missing_units()
