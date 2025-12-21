from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.quotation import QuotationStatus, ProjectType


class QuotationCreate(BaseModel):
    project_description: str = Field(..., min_length=10, description="Project description in natural language")
    location: Optional[str] = None
    zip_code: Optional[str] = None
    project_type: Optional[ProjectType] = None
    timeline: Optional[str] = None


class QuotationResponse(BaseModel):
    id: str
    project_description: str
    location: Optional[str]
    zip_code: Optional[str]
    project_type: Optional[ProjectType]
    timeline: Optional[str]
    status: QuotationStatus
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class QuotationDataResponse(BaseModel):
    quotation_id: str
    extracted_data: Optional[Dict[str, Any]]
    confidence_score: Optional[float]
    cost_breakdown: Optional[Dict[str, Any]]
    total_cost: Optional[float]
    
    class Config:
        from_attributes = True


class QuotationStatusResponse(BaseModel):
    quotation_id: str
    status: QuotationStatus
    current_stage: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    estimated_completion: Optional[datetime] = None
    last_update: datetime


class QuotationDetailResponse(QuotationResponse):
    """Extended quotation response with data"""
    quotation_data: Optional[QuotationDataResponse] = None

