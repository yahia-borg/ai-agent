from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base


class QuotationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DATA_COLLECTION = "data_collection"
    COST_CALCULATION = "cost_calculation"
    COMPLETED = "completed"
    FAILED = "failed"


class ProjectType(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RENOVATION = "renovation"
    NEW_CONSTRUCTION = "new_construction"


class Quotation(Base):
    __tablename__ = "quotations"
    
    id = Column(String, primary_key=True, index=True)
    project_description = Column(String, nullable=False)
    location = Column(String)
    zip_code = Column(String)
    project_type = Column(SQLEnum(ProjectType), nullable=True)
    timeline = Column(String)
    status = Column(SQLEnum(QuotationStatus), default=QuotationStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    quotation_data = relationship("QuotationData", back_populates="quotation", uselist=False)


class QuotationData(Base):
    __tablename__ = "quotation_data"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    quotation_id = Column(String, ForeignKey("quotations.id"), unique=True, nullable=False)
    extracted_data = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    cost_breakdown = Column(JSON, nullable=True)
    total_cost = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    quotation = relationship("Quotation", back_populates="quotation_data")

