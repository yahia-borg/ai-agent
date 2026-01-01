from sqlalchemy import Column, Integer, String, Float, Text
from app.core.database import Base

class Material(Base):
    """Materials pricing table - matches existing database schema"""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)  # Bilingual names (e.g., "General Number /الرقم العام")
    category = Column(String, index=True, nullable=False)  # e.g., "General"
    unit = Column(String, nullable=False)  # e.g., "unit", "m²", "ton"
    price_per_unit = Column(Float, nullable=False)  # Price in EGP
    currency = Column(String, default="EGP", nullable=False)

class LaborRate(Base):
    """Labor rates table - matches existing database schema"""
    __tablename__ = "labor_rates"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False, index=True)  # e.g., "Skilled Worker (Mason)"
    hourly_rate = Column(Float, nullable=False)  # Hourly rate in EGP
    currency = Column(String, default="EGP", nullable=False)
