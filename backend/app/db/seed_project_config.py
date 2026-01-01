"""
Seed script for project configuration data (area ranges, finishing options, room layouts)
"""
from app.core.database import SessionLocal
from app.models.project_config import (
    ProjectAreaRange,
    FinishingOption,
    RoomLayout,
    ProjectTypeEnum,
    FinishingLevelEnum
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_project_config():
    """Seed project configuration data"""
    db = SessionLocal()
    try:
        # ============= AREA RANGES =============
        logger.info("Seeding area ranges...")
        
        area_ranges = [
            {
                "project_type": ProjectTypeEnum.RESIDENTIAL,
                "min_area": 20.0,
                "max_area": 500.0,
                "typical_range": "20-200",
                "description": "Residential projects typically range from small apartments to large villas"
            },
            {
                "project_type": ProjectTypeEnum.COMMERCIAL,
                "min_area": 50.0,
                "max_area": 5000.0,
                "typical_range": "100-2000",
                "description": "Commercial projects include shops, offices, and retail spaces"
            },
            {
                "project_type": ProjectTypeEnum.FACTORY,
                "min_area": 100.0,
                "max_area": 10000.0,
                "typical_range": "500-5000",
                "description": "Factory and industrial projects require larger spaces"
            }
        ]
        
        for area_data in area_ranges:
            existing = db.query(ProjectAreaRange).filter(
                ProjectAreaRange.project_type == area_data["project_type"]
            ).first()
            
            if not existing:
                area_range = ProjectAreaRange(**area_data)
                db.add(area_range)
                logger.info(f"Added area range for {area_data['project_type'].value}")
            else:
                # Update existing
                for key, value in area_data.items():
                    setattr(existing, key, value)
                logger.info(f"Updated area range for {area_data['project_type'].value}")
        
        db.commit()
        
        # ============= FINISHING OPTIONS =============
        logger.info("Seeding finishing options...")
        
        finishing_options = [
            # Residential
            {
                "project_type": ProjectTypeEnum.RESIDENTIAL,
                "level": FinishingLevelEnum.BASIC,
                "description": "Basic finishing with standard materials. Suitable for rental properties.",
                "price_min_per_sqm": 800.0,
                "price_max_per_sqm": 1200.0,
                "currency": "EGP",
                "features": ["Standard tiles", "Basic paint", "Standard fixtures"]
            },
            {
                "project_type": ProjectTypeEnum.RESIDENTIAL,
                "level": FinishingLevelEnum.STANDARD,
                "description": "Standard finishing with good quality materials. Most common choice.",
                "price_min_per_sqm": 1200.0,
                "price_max_per_sqm": 2000.0,
                "currency": "EGP",
                "features": ["Quality tiles", "Good paint", "Standard fixtures", "Modern design"]
            },
            {
                "project_type": ProjectTypeEnum.RESIDENTIAL,
                "level": FinishingLevelEnum.PREMIUM,
                "description": "Premium finishing with high-quality materials and modern fixtures.",
                "price_min_per_sqm": 2000.0,
                "price_max_per_sqm": 3500.0,
                "currency": "EGP",
                "features": ["Premium tiles", "High-quality paint", "Premium fixtures", "Modern design", "Smart features"]
            },
            {
                "project_type": ProjectTypeEnum.RESIDENTIAL,
                "level": FinishingLevelEnum.LUXURY,
                "description": "Luxury finishing with top-tier materials and designer fixtures.",
                "price_min_per_sqm": 3500.0,
                "price_max_per_sqm": 6000.0,
                "currency": "EGP",
                "features": ["Luxury tiles", "Premium paint", "Designer fixtures", "Luxury design", "Smart home integration"]
            },
            # Commercial
            {
                "project_type": ProjectTypeEnum.COMMERCIAL,
                "level": FinishingLevelEnum.BASIC,
                "description": "Basic commercial finishing. Focus on functionality.",
                "price_min_per_sqm": 640.0,
                "price_max_per_sqm": 1080.0,
                "currency": "EGP",
                "features": ["Functional tiles", "Basic paint", "Commercial fixtures"]
            },
            {
                "project_type": ProjectTypeEnum.COMMERCIAL,
                "level": FinishingLevelEnum.STANDARD,
                "description": "Standard commercial finishing with durable materials.",
                "price_min_per_sqm": 960.0,
                "price_max_per_sqm": 1800.0,
                "currency": "EGP",
                "features": ["Durable tiles", "Quality paint", "Commercial fixtures", "Professional design"]
            },
            {
                "project_type": ProjectTypeEnum.COMMERCIAL,
                "level": FinishingLevelEnum.PREMIUM,
                "description": "Premium commercial finishing for professional spaces.",
                "price_min_per_sqm": 1600.0,
                "price_max_per_sqm": 3150.0,
                "currency": "EGP",
                "features": ["Premium tiles", "High-quality paint", "Premium fixtures", "Professional design", "Modern aesthetics"]
            },
            # Factory
            {
                "project_type": ProjectTypeEnum.FACTORY,
                "level": FinishingLevelEnum.BASIC,
                "description": "Minimal industrial finishing. Focus on functionality.",
                "price_min_per_sqm": 400.0,
                "price_max_per_sqm": 800.0,
                "currency": "EGP",
                "features": ["Industrial flooring", "Basic paint", "Functional fixtures"]
            }
        ]
        
        for option_data in finishing_options:
            existing = db.query(FinishingOption).filter(
                FinishingOption.project_type == option_data["project_type"],
                FinishingOption.level == option_data["level"]
            ).first()
            
            if not existing:
                option = FinishingOption(**option_data)
                db.add(option)
                logger.info(f"Added finishing option: {option_data['project_type'].value} - {option_data['level'].value}")
            else:
                # Update existing
                for key, value in option_data.items():
                    setattr(existing, key, value)
                logger.info(f"Updated finishing option: {option_data['project_type'].value} - {option_data['level'].value}")
        
        db.commit()
        
        # ============= ROOM LAYOUTS =============
        logger.info("Seeding room layouts...")
        
        # Delete existing layouts to avoid duplicates
        db.query(RoomLayout).delete()
        
        room_layouts = [
            # Residential
            {"project_type": ProjectTypeEnum.RESIDENTIAL, "room_name": "Living Room", "percentage": 0.25, "order": 1},
            {"project_type": ProjectTypeEnum.RESIDENTIAL, "room_name": "Bedroom", "percentage": 0.20, "order": 2},
            {"project_type": ProjectTypeEnum.RESIDENTIAL, "room_name": "Kitchen", "percentage": 0.15, "order": 3},
            {"project_type": ProjectTypeEnum.RESIDENTIAL, "room_name": "Bathroom", "percentage": 0.10, "order": 4},
            {"project_type": ProjectTypeEnum.RESIDENTIAL, "room_name": "Other", "percentage": 0.30, "order": 5},
            # Commercial
            {"project_type": ProjectTypeEnum.COMMERCIAL, "room_name": "Main Space", "percentage": 0.80, "order": 1},
            {"project_type": ProjectTypeEnum.COMMERCIAL, "room_name": "Office", "percentage": 0.10, "order": 2},
            {"project_type": ProjectTypeEnum.COMMERCIAL, "room_name": "Bathroom", "percentage": 0.10, "order": 3},
            # Factory
            {"project_type": ProjectTypeEnum.FACTORY, "room_name": "Workshop/Warehouse", "percentage": 0.90, "order": 1},
            {"project_type": ProjectTypeEnum.FACTORY, "room_name": "Office", "percentage": 0.10, "order": 2},
        ]
        
        for layout_data in room_layouts:
            layout = RoomLayout(**layout_data)
            db.add(layout)
            logger.info(f"Added room layout: {layout_data['project_type'].value} - {layout_data['room_name']}")
        
        db.commit()
        logger.info("Project configuration seeding completed successfully!")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding project configuration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_project_config()

