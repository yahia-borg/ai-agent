from sqlalchemy import Column, Integer, String, Float, DateTime, func, UniqueConstraint
from app.core.database import Base

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    category = Column(String, index=True, nullable=True)
    unit = Column(String, nullable=True)
    price_per_unit = Column(Float, nullable=False)
    currency = Column(String, default="EGP", nullable=False)
    source_document = Column(String, nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class LaborRate(Base):
    __tablename__ = "labor_rates"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, unique=True, index=True, nullable=False)
    hourly_rate = Column(Float, nullable=False)
    currency = Column(String, default="EGP", nullable=False)
    source_document = Column(String, nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
