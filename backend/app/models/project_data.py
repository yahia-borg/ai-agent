from pydantic import BaseModel, Field
from typing import Optional, List

class ProjectData(BaseModel):
    project_type: str = Field(..., max_length=50)
    size_sqm: Optional[float] = Field(None, ge=0, le=10000)
    current_finish_level: Optional[str] = Field(None, max_length=50)
    target_finish_level: Optional[str] = Field(None, max_length=50)
    key_requirements: List[str] = Field(default_factory=list, max_items=10)
    missing_information: List[str] = Field(default_factory=list, max_items=10)
    follow_up_questions: List[str] = Field(default_factory=list, max_items=3)
    confidence_score: float = Field(..., ge=0, le=1)

class ConstructionRequirements(BaseModel):
    materials: List[str] = Field(..., description="List of material names to search for (e.g., 'Ceramic tiles', 'Cement')")
    labor: List[str] = Field(..., description="List of labor roles to search for (e.g., 'Mason', 'Electrician')")