"""
State schemas for the cost estimation multi-agent system.

This module defines:
- TypedDict for graph state
- Pydantic models for validated data
- Type-safe routing destinations for Command pattern
- Workflow status enum
"""
from typing import TypedDict, Annotated, Optional, Dict, Any, List, Literal
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ============= REDUCERS =============

def _merge_errors(left: List[str], right: List[str]) -> List[str]:
    """Reducer that accumulates errors without duplicates."""
    if not isinstance(left, list):
        left = []
    if not isinstance(right, list):
        right = []
    # Accumulate but avoid duplicates
    seen = set(left)
    result = list(left)
    for err in right:
        if err not in seen:
            result.append(err)
            seen.add(err)
    return result


# ============= ENUMS =============

class WorkflowStatus(str, Enum):
    """Workflow status values with string serialization."""
    PENDING = "pending"
    GATHERING_REQUIREMENTS = "gathering_requirements"
    RETRIEVING_DATA = "retrieving_data"
    SELECTING_MATERIALS = "selecting_materials"
    CALCULATING = "calculating"
    COMPLETE = "complete"
    FORCED_COMPLETION = "forced_completion"
    TIMEOUT = "timeout"
    ERROR = "error"


class SubgraphStatus(str, Enum):
    """Subgraph execution status for streaming."""
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"


class ProjectType(str, Enum):
    """Valid project types."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    FACTORY = "factory"


class FinishingLevel(str, Enum):
    """Valid finishing levels."""
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    LUXURY = "luxury"


# ============= TYPE-SAFE ROUTING =============

# All valid routing destinations for Command[RoutingDest]
RoutingDest = Literal[
    "supervisor",
    "requirements_subgraph",          # Subgraph (was requirements_agent)
    "postgres_data_subgraph",         # Subgraph (split from data_retrieval_agent)
    "qdrant_knowledge_subgraph",      # Subgraph (split from data_retrieval_agent)
    "materials_subgraph",             # Subgraph (was material_selection_agent)
    "calculation_agent",              # Simple agent (no subgraph needed)
    "force_complete",
    "__end__"
]


# ============= PYDANTIC MODELS =============

class RoomInfo(BaseModel):
    """Individual room information"""
    room_type: str  # e.g., "bedroom", "kitchen", "bathroom", "living_room"
    area_sqm: float = Field(gt=0, description="Room area in square meters")
    count: Optional[int] = Field(1, gt=0, description="Number of rooms of this type")


class Requirements(BaseModel):
    """Validated requirements model."""
    # === Core Project Info ===
    project_type: Optional[Literal["residential", "commercial", "factory"]] = None
    total_area_sqm: Optional[float] = Field(None, gt=0, description="Total area in square meters")
    location: Optional[str] = "Cairo"

    # === Room Breakdown (NEW - REQUIRED) ===
    rooms_breakdown: Optional[List[RoomInfo]] = Field(None, description="Detailed room-by-room breakdown")

    # === Finishing Status (NEW - REQUIRED) ===
    current_finishing_status: Optional[Literal[
        "bare_concrete",      # بدون تشطيب - needs everything
        "plastered",          # محارة فقط - needs paint, tiles, fixtures
        "semi_finished",      # نصف تشطيب - needs final finishes
        "painted"             # دهان فقط - needs tiles, fixtures
    ]] = None

    # === Finishing Style (NEW - REQUIRED) ===
    desired_finishing_style: Optional[str] = Field(None, description="Style: modern, classic, minimalist, luxury, etc.")
    finishing_level: Optional[Literal["basic", "standard", "premium", "luxury"]] = "standard"

    # === Optional Details ===
    specific_materials: Optional[List[str]] = None
    timeline_months: Optional[int] = Field(None, gt=0)
    budget_limit: Optional[float] = Field(None, gt=0, description="Budget in EGP")

    class Config:
        extra = "allow"  # Allow additional fields from extraction


class RoomBreakdown(BaseModel):
    """Room breakdown model."""
    room: str
    area_sqm: float = Field(gt=0)


class MaterialItem(BaseModel):
    """Material pricing item."""
    name: str
    unit: str
    price_per_unit: float = Field(gt=0)
    category: Optional[str] = None


class LaborRate(BaseModel):
    """Labor rate item."""
    category: str
    daily_rate: float = Field(gt=0)
    description: Optional[str] = None


# ============= GRAPH STATE =============

class CostEstimationState(TypedDict, total=False):
    """
    Main graph state schema for cost estimation workflow.

    All values must be JSON-serializable for LangGraph checkpointing.
    Uses reducers for messages (add_messages) and errors (accumulate).
    """
    # === Conversation ===
    messages: Annotated[List[BaseMessage], add_messages]

    # === Workflow Control ===
    current_agent: str
    workflow_status: str  # WorkflowStatus enum value

    # === Requirements Stage ===
    requirements: Optional[Dict[str, Any]]
    requirements_complete: bool
    requirements_validation: Optional[Dict[str, Any]]  # Intermediate validation results

    # === Data Retrieval Stage (Split into Postgres + Qdrant) ===
    materials: List[Dict[str, Any]]  # From PostgreSQL
    labor_rates: List[Dict[str, Any]]  # From PostgreSQL
    postgres_data_complete: bool  # Completion flag for Postgres data subgraph
    postgres_validation: Optional[Dict[str, Any]]  # Intermediate validation results for Postgres data

    qdrant_knowledge: List[Dict[str, Any]]  # Building regulations and finishing info from Qdrant
    qdrant_knowledge_complete: bool  # Completion flag for Qdrant knowledge subgraph
    qdrant_validation: Optional[Dict[str, Any]]  # Intermediate validation results for Qdrant knowledge

    # === Material Selection Stage ===
    material_selections: Optional[Dict[str, Any]]  # User's material choices per room/area
    material_selection_complete: bool
    materials_room_groups: Optional[Dict[str, Any]]  # Intermediate room grouping
    materials_needed_selections: Optional[List[str]]  # Intermediate list of needed selections
    materials_selection_progress: Optional[Dict[str, Any]]  # Intermediate selection progress
    materials_validation: Optional[Dict[str, Any]]  # Intermediate validation results

    # === Calculation Stage ===
    quotation: Optional[Dict[str, Any]]
    calculation_complete: bool

    # === Loop Protection ===
    turn_count: int
    agent_attempts: Dict[str, int]
    started_at: Optional[str]  # ISO timestamp

    # === User Control ===
    user_confirmed_proceed: bool

    # === Errors (accumulated) ===
    errors: Annotated[List[str], _merge_errors]


# ============= STATE INITIALIZATION =============

def create_initial_state() -> CostEstimationState:
    """Create initial state with defaults."""
    from datetime import datetime

    return CostEstimationState(
        messages=[],
        current_agent="supervisor",
        workflow_status=WorkflowStatus.PENDING.value,
        requirements=None,
        requirements_complete=False,
        materials=[],
        labor_rates=[],
        postgres_data_complete=False,  # NEW: Split from data_retrieval_complete
        qdrant_knowledge=[],
        qdrant_knowledge_complete=False,  # NEW: Split from data_retrieval_complete
        material_selections=None,
        material_selection_complete=False,
        quotation=None,
        calculation_complete=False,
        turn_count=0,
        agent_attempts={},
        started_at=datetime.utcnow().isoformat(),
        user_confirmed_proceed=False,
        errors=[],
    )