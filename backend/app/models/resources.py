from sqlalchemy import Column, Integer, String, Float, DateTime, func, UniqueConstraint, ForeignKey, Boolean, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class Currency(Base):
    """Currency reference table with bilingual names."""
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(3), unique=True, index=True, nullable=False)  # EGP, USD, SAR, EUR
    name = Column(JSONB, nullable=False)  # {"en": "Egyptian Pound", "ar": "جنيه مصري"}
    symbol = Column(String(10), nullable=True)  # ج.م, $, ر.س, €
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Unit(Base):
    """Unit of measurement reference table with bilingual names."""
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)  # m2, m3, kg, ton, piece, etc.
    name = Column(JSONB, nullable=False)  # {"en": "Square Meter", "ar": "متر مربع"}
    symbol = Column(String(10), nullable=True)  # m², m³, kg, t
    unit_type = Column(String(20), nullable=True)  # area, volume, weight, count, time, length
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    """Category reference table with bilingual names for materials and labor."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)  # cement, steel, labor_masonry, etc.
    name = Column(JSONB, nullable=False)  # {"en": "Cement", "ar": "أسمنت"}
    category_type = Column(String(20), index=True, nullable=False)  # 'material' or 'labor'
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    icon = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Self-referential relationship for subcategories
    parent = relationship("Category", remote_side=[id], backref="subcategories")


class Material(Base):
    """Material pricing table with bilingual JSONB fields."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=True)  # Optional unique code
    name = Column(JSONB, nullable=False, index=True)  # {"en": "Portland Cement", "ar": "أسمنت بورتلاند"}
    description = Column(JSONB, nullable=True)  # {"en": "...", "ar": "..."}

    # Foreign keys to reference tables
    category_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), index=True, nullable=True)
    unit_id = Column(Integer, ForeignKey('units.id', ondelete='SET NULL'), nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id', ondelete='SET NULL'), nullable=True)

    # Pricing
    price = Column(Numeric(12, 2), nullable=False)

    # Additional metadata
    brand = Column(String(100), nullable=True)
    supplier = Column(String(200), nullable=True)
    specifications = Column(JSONB, nullable=True)  # Any additional specs as JSON
    source = Column(String(100), nullable=True)  # Source document reference

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("Category", backref="materials")
    unit = relationship("Unit", backref="materials")
    currency = relationship("Currency", backref="materials")
    synonyms = relationship("MaterialSynonym", back_populates="material", cascade="all, delete-orphan")


class MaterialSynonym(Base):
    """Alternative names/synonyms for materials to improve search."""
    __tablename__ = "material_synonyms"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'), nullable=False, index=True)
    language_code = Column(String(5), nullable=False, index=True)  # 'en' or 'ar'
    synonym = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    material = relationship("Material", back_populates="synonyms")

    __table_args__ = (
        UniqueConstraint('material_id', 'language_code', 'synonym', name='uq_material_synonym'),
    )


class LaborRate(Base):
    """Labor rate table with bilingual JSONB fields."""
    __tablename__ = "labor_rates"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=True)  # Optional unique code
    role = Column(JSONB, nullable=False, index=True)  # {"en": "Mason", "ar": "بناء"}
    description = Column(JSONB, nullable=True)  # {"en": "...", "ar": "..."}

    # Foreign keys to reference tables
    category_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), index=True, nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id', ondelete='SET NULL'), nullable=True)

    # Rates (Egyptian market uses both hourly and daily)
    hourly_rate = Column(Numeric(10, 2), nullable=True)
    daily_rate = Column(Numeric(10, 2), nullable=True)

    # Skill level
    skill_level = Column(String(20), nullable=True)  # 'unskilled', 'skilled', 'master'

    # Metadata
    source = Column(String(100), nullable=True)  # Source document reference

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("Category", backref="labor_rates")
    currency = relationship("Currency", backref="labor_rates")
