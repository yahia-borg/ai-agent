"""
SQLAlchemy ORM models for construction configuration tables.
These replace hardcoded constants across the codebase.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class ConstructionConfig(Base):
    """General key-value configuration store for construction parameters."""
    __tablename__ = "construction_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSONB, nullable=False)
    description = Column(JSONB, nullable=True)  # {"en": "...", "ar": "..."}
    category = Column(String(50), nullable=True, index=True)  # grouping: 'percentages', 'rates', 'brands', etc.
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class RoomMultiplier(Base):
    """Room-specific multipliers for materials and labor."""
    __tablename__ = "room_multipliers"

    id = Column(Integer, primary_key=True, index=True)
    room_type = Column(String(50), nullable=False, index=True)  # bathroom, kitchen, bedroom, etc.
    category_key = Column(String(50), nullable=False, index=True)  # tile, paint, plaster, plumber, tiler, etc.
    multiplier_type = Column(String(20), nullable=False, index=True)  # 'material' or 'labor'
    value = Column(Float, nullable=False)
    description = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AreaDistributionDefault(Base):
    """Default area distribution percentages for room types by project type."""
    __tablename__ = "area_distribution_defaults"

    id = Column(Integer, primary_key=True, index=True)
    project_type = Column(String(50), nullable=False, index=True)  # residential, commercial
    room_type = Column(String(50), nullable=False)  # bedroom, bathroom, office, etc.
    percentage = Column(Float, nullable=False)  # 0.0 to 1.0
    description = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TradeMultiplier(Base):
    """Trade multipliers (hours/sqm) by project type."""
    __tablename__ = "trade_multipliers"

    id = Column(Integer, primary_key=True, index=True)
    project_type = Column(String(50), nullable=False, index=True)  # residential, commercial, factory
    trade_key = Column(String(50), nullable=False)  # electrician, plumber, tiler, etc.
    value = Column(Float, nullable=False)  # hours per sqm
    description = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CostComponentSplit(Base):
    """Cost splits (supply/install/transport/misc) by category."""
    __tablename__ = "cost_component_splits"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # flooring, painting, etc.
    component = Column(String(30), nullable=False)  # supply, installation, transport, misc
    percentage = Column(Float, nullable=False)  # 0.0 to 1.0
    label = Column(JSONB, nullable=True)  # {"en": "Supply", "ar": "توريد"}
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CategoryKeyword(Base):
    """Keywords for category detection, brand/color/finish lists, material type keywords."""
    __tablename__ = "category_keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword_type = Column(String(50), nullable=False, index=True)  # 'category_detection', 'brand', 'color', 'finish', 'material_type', 'stop_words', 'max_per_type'
    group_key = Column(String(50), nullable=False, index=True)  # category name or group identifier
    keywords = Column(JSONB, nullable=False)  # list of keywords or single value
    description = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DescriptionTemplate(Base):
    """Bilingual BOQ description templates by category."""
    __tablename__ = "description_templates"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # flooring, painting, plastering, etc.
    template_key = Column(String(50), nullable=False, index=True)  # 'main', 'tile_porcelain', 'paint_emulsion', etc.
    template_ar = Column(Text, nullable=True)
    template_en = Column(Text, nullable=True)
    variables = Column(JSONB, nullable=True)  # list of variable names used in template
    description = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
