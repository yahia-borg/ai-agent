from pydantic import BaseModel, Field
from typing import Optional, List

class ProjectData(BaseModel):
    project_type: str = Field(..., max_length=50)
    size_sqm: Optional[float] = Field(None, ge=0, le=10000)
    size_sqft: Optional[float] = Field(None, ge=0, le=100000)
    current_finish_level: Optional[str] = Field(None, max_length=50)
    target_finish_level: Optional[str] = Field(None, max_length=50)
    timeline_weeks: Optional[int] = Field(None, ge=0)
    key_requirements: List[str] = Field(default_factory=list, max_items=10)
    missing_information: List[str] = Field(default_factory=list, max_items=10)
    follow_up_questions: List[str] = Field(default_factory=list, max_items=3)
    confidence_score: float = Field(..., ge=0, le=1)