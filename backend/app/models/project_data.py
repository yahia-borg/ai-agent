from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict


class RoomBreakdown(BaseModel):
    """Single room/space entry in the project breakdown."""
    room_type: str = Field(
        ...,
        description=(
            "Room type. Residential: bedroom, bathroom, kitchen, living_room, "
            "reception, balcony, corridor. "
            "Commercial: office, reception, meeting_room, storage, corridor, "
            "open_plan, server_room."
        ),
    )
    count: int = Field(1, ge=1, description="How many rooms of this type")
    area_sqm: Optional[float] = Field(
        None, ge=0,
        description="Area per room in sqm (optional — can be inferred from total)",
    )
    notes: Optional[str] = Field(
        None, max_length=200,
        description="Special requirements for this room, e.g. 'waterproofing needed'",
    )


class ProjectData(BaseModel):
    project_type: str = Field(..., max_length=50)
    size_sqm: Optional[float] = Field(None, ge=0, le=100000)
    current_finish_level: Optional[str] = Field(None, max_length=50)
    target_finish_level: Optional[str] = Field(None, max_length=50)

    # Room / space breakdown
    rooms: List[RoomBreakdown] = Field(
        default_factory=list,
        description="Breakdown of rooms/spaces in the project",
    )
    num_bathrooms: Optional[int] = Field(None, ge=0, description="Number of bathrooms")
    num_kitchens: Optional[int] = Field(None, ge=0, description="Number of kitchens")

    key_requirements: List[str] = Field(default_factory=list, max_items=10)
    missing_information: List[str] = Field(default_factory=list, max_items=10)
    follow_up_questions: List[str] = Field(default_factory=list, max_items=3)
    confidence_score: float = Field(..., ge=0, description="Confidence 0-1")

    @field_validator("confidence_score", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        """LLMs sometimes return values > 1; clamp to [0, 1]."""
        return max(0.0, min(1.0, float(v)))

class ConstructionRequirements(BaseModel):
    materials: List[str] = Field(..., description="List of material names to search for (e.g., 'Ceramic tiles', 'Cement')")
    labor: List[str] = Field(..., description="List of labor roles to search for (e.g., 'Mason', 'Electrician')")