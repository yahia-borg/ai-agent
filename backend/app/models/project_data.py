from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any


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
    project_type: Optional[str] = Field(None, max_length=50)

    @field_validator("project_type", mode="before")
    @classmethod
    def normalize_project_type(cls, v):
        """Accept null/None from LLM — downstream code uses 'unknown' as the sentinel."""
        if v is None or (isinstance(v, str) and v.strip().lower() in ("null", "none", "")):
            return "unknown"
        return str(v).strip()

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
    num_floors: Optional[int] = Field(
        None, ge=1, le=200,
        description="Number of floors/storeys the unit spans (e.g. a two-floor shop = 2)",
    )

    key_requirements: List[str] = Field(default_factory=list, max_length=10)
    missing_information: List[str] = Field(default_factory=list, max_length=10)
    follow_up_questions: List[str] = Field(default_factory=list, max_length=3)
    confidence_score: float = Field(0.5, ge=0, description="Confidence 0-1")

    @field_validator("rooms", mode="before")
    @classmethod
    def clean_rooms(cls, v: Any) -> List[Dict]:
        """
        Filter out invalid room entries produced by malformed LLM output:
        - Non-dict items (strings, nulls, flat field names leaked from the schema)
        - Dicts missing 'room_type' or with a non-string room_type
        - Dicts whose keys contain '$', '_comment_', or similar noise fields
        """
        if not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if not isinstance(item, dict):
                continue
            room_type = item.get("room_type")
            if not room_type or not isinstance(room_type, str):
                continue
            # Skip meta/noise entries injected by the LLM
            if any(k.startswith("$") or "_comment" in k for k in item):
                continue
            # Sanitize numeric-ish fields: vLLM sometimes emits ":null," as a
            # string value (e.g. `"area_sqm": ":null,"`).  Convert any value
            # that starts with ":" or is a null-like string to None before
            # Pydantic tries to coerce it to float.
            for num_field in ("area_sqm",):
                val = item.get(num_field)
                if isinstance(val, str):
                    stripped = val.strip().lstrip(":").rstrip(",").strip()
                    if stripped.lower() in ("null", "none", ""):
                        item = dict(item, **{num_field: None})

            # Normalise count: default to 1 when null/missing/invalid.
            # RoomBreakdown.count is a required int — it won't accept None even
            # though a default is declared (Pydantic only applies the default when
            # the key is *absent*, not when it's explicitly null).
            count_raw = item.get("count")
            if count_raw is None or count_raw == "":
                item = dict(item, count=1)
            else:
                try:
                    coerced = max(1, int(float(count_raw)))
                    item = dict(item, count=coerced)
                except (TypeError, ValueError):
                    item = dict(item, count=1)
            cleaned.append(item)
        return cleaned

    @field_validator("confidence_score", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        """
        LLMs sometimes return values > 1, as strings, inside nested dicts/lists,
        or with mangled key names like '__confidence_score__' or ':confidence_score'.
        Unwrap and clamp to [0, 1].
        """
        if isinstance(v, dict):
            # Find the first numeric-looking value among known variant key names
            for key in ("confidence_score", "__confidence_score__", ":confidence_score"):
                if key in v:
                    inner = v[key]
                    v = inner[0] if isinstance(inner, list) and inner else inner
                    break
            else:
                # Last resort: grab the first value in the dict
                first = next(iter(v.values()), 0.5)
                v = first[0] if isinstance(first, list) and first else first
        if isinstance(v, list):
            v = v[0] if v else 0.5
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("key_requirements", "missing_information", "follow_up_questions", mode="before")
    @classmethod
    def clean_string_lists(cls, v: Any, info) -> List[str]:
        """
        Filter out non-string or empty entries that LLMs sometimes inject, then
        silently truncate to the per-field maximum instead of raising a validation
        error.  LLMs routinely return 4+ follow-up questions even when instructed
        to return at most 3 — truncation here prevents the ValidationError that
        would otherwise trigger the fallback extractor.
        """
        if not isinstance(v, list):
            return []
        cleaned = [str(item) for item in v if item and isinstance(item, (str, int, float))]
        # Per-field hard caps (mirror the Field max_length constraints)
        limits = {"follow_up_questions": 3, "key_requirements": 10, "missing_information": 10}
        field_name = info.field_name if hasattr(info, "field_name") else ""
        limit = limits.get(field_name, 10)
        return cleaned[:limit]

class ConstructionRequirements(BaseModel):
    materials: List[str] = Field(..., description="List of material names to search for (e.g., 'Ceramic tiles', 'Cement')")
    labor: List[str] = Field(..., description="List of labor roles to search for (e.g., 'Mason', 'Electrician')")


class EngineeringQuestion(BaseModel):
    """One targeted engineering question that materially affects the BOQ."""
    topic: str = Field(
        ..., max_length=40,
        description="Short tag for the BOQ area, e.g. flooring, mep, hvac, ceiling, fire_safety, kitchen, facade, sanitary",
    )
    question: str = Field(
        ..., max_length=300,
        description="The question phrased in simple Egyptian Arabic (اللهجة المصرية), Western digits 0-9.",
    )

    @field_validator("topic", "question", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        return "" if v is None else str(v)


class EngineeringAssessment(BaseModel):
    """LLM verdict: does the engineer have enough to build an accurate BOQ, and if
    not, the most important next questions (grounded strictly in the reference KB)."""
    enough_info: bool = Field(
        False,
        description="True when the reference knowledge + known facts are sufficient to build an accurate BOQ.",
    )
    questions: List[EngineeringQuestion] = Field(
        default_factory=list,
        description="The 1-3 most important missing engineering questions (empty when enough_info is true).",
    )

    @field_validator("questions", mode="before")
    @classmethod
    def _clean_questions(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            return []
        out = [q for q in v if isinstance(q, dict) and q.get("question")]
        return out[:3]  # hard cap: never ask more than 3 per round


class BOQLineItem(BaseModel):
    """One named finishing work-package the engineer would put on the BOQ.
    ``weight`` is a RELATIVE cost proportion — it is normalised against the
    market-anchored allowance downstream, never trusted as an absolute amount."""
    name_en: str = Field(..., max_length=80)
    name_ar: str = Field(..., max_length=80)
    weight: float = Field(1.0, description="Relative cost share (normalised later).")

    @field_validator("name_en", "name_ar", mode="before")
    @classmethod
    def _coerce_name(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("weight", mode="before")
    @classmethod
    def _coerce_weight(cls, v: Any) -> float:
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 1.0


class BOQScope(BaseModel):
    """LLM-synthesised BOQ work breakdown for the finishing allowance, derived from
    the engineering Q&A (in any language — Arabic, English, or Franco-Arabic). Used
    only to shape the BREAKDOWN + scope summary; the grand total stays the market
    anchor, so the LLM is never trusted with absolute money."""
    summary_en: str = Field("", max_length=400)
    summary_ar: str = Field("", max_length=400)
    line_items: List[BOQLineItem] = Field(default_factory=list)

    @field_validator("summary_en", "summary_ar", mode="before")
    @classmethod
    def _coerce_summary(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("line_items", mode="before")
    @classmethod
    def _clean_items(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            return []
        out = [i for i in v if isinstance(i, dict) and (i.get("name_en") or i.get("name_ar"))]
        return out[:16]  # sane cap on BOQ line count