"""
Unit tests for LLM JSON repair pipeline and resilient ProjectData validators.

These tests cover the malformed output patterns observed from local vLLM models:
- Mixed single/double quotes
- Python literal syntax (None, True, False)
- confidence_score buried in nested structures or as a string
- Noise entries ($comment, strings) injected into the rooms array
- project_type null / missing
"""
import pytest
from app.agents.llm_client import _repair_and_parse
from app.models.project_data import ProjectData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_payload(**overrides) -> dict:
    base = {
        "project_type": "commercial",
        "size_sqm": 200.0,
        "current_finish_level": "core_shell",
        "target_finish_level": "fully_finished",
        "rooms": [{"room_type": "office", "count": 3}],
        "num_bathrooms": 2,
        "num_kitchens": 1,
        "key_requirements": ["air conditioning"],
        "missing_information": [],
        "follow_up_questions": [],
        "confidence_score": 0.85,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _repair_and_parse tests
# ---------------------------------------------------------------------------

class TestRepairAndParse:
    def test_valid_json_passes_through(self):
        import json
        payload = _make_valid_payload()
        raw = json.dumps(payload)
        result = _repair_and_parse(raw, ProjectData)
        assert result.project_type == "commercial"
        assert result.confidence_score == pytest.approx(0.85)

    def test_markdown_fenced_json(self):
        import json
        payload = _make_valid_payload()
        raw = f"```json\n{json.dumps(payload)}\n```"
        result = _repair_and_parse(raw, ProjectData)
        assert result.size_sqm == 200.0

    def test_python_literals_none_true_false(self):
        # LLM uses Python None/True/False instead of JSON null/true/false
        raw = """{
            "project_type": "residential",
            "size_sqm": None,
            "current_finish_level": None,
            "target_finish_level": "fully_finished",
            "rooms": [{"room_type": "bedroom", "count": 2, "area_sqm": None, "notes": None}],
            "num_bathrooms": 1,
            "num_kitchens": 1,
            "key_requirements": [],
            "missing_information": [],
            "follow_up_questions": [],
            "confidence_score": 0.7
        }"""
        result = _repair_and_parse(raw, ProjectData)
        assert result.project_type == "residential"
        assert result.size_sqm is None

    def test_single_quoted_python_dict(self):
        # LLM produces a fully single-quoted Python dict literal
        raw = """{
            'project_type': 'commercial',
            'size_sqm': 150,
            'current_finish_level': None,
            'target_finish_level': 'turnkey',
            'rooms': [{'room_type': 'office', 'count': 1, 'area_sqm': None, 'notes': None}],
            'num_bathrooms': 1,
            'num_kitchens': 0,
            'key_requirements': ['modern design'],
            'missing_information': [],
            'follow_up_questions': [],
            'confidence_score': 0.9
        }"""
        result = _repair_and_parse(raw, ProjectData)
        assert result.project_type == "commercial"
        assert result.confidence_score == pytest.approx(0.9)

    def test_raises_on_completely_unparseable(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _repair_and_parse("this is not json at all <<<", ProjectData)


# ---------------------------------------------------------------------------
# ProjectData validator tests
# ---------------------------------------------------------------------------

class TestProjectDataValidators:
    def test_confidence_score_as_string(self):
        payload = _make_valid_payload(confidence_score="0.75")
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == pytest.approx(0.75)

    def test_confidence_score_clamped_above_one(self):
        payload = _make_valid_payload(confidence_score=1.5)
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == pytest.approx(1.0)

    def test_confidence_score_nested_dict(self):
        payload = _make_valid_payload(confidence_score={"__confidence_score__": [0.65]})
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == pytest.approx(0.65)

    def test_confidence_score_string_colon_prefix(self):
        payload = _make_valid_payload(confidence_score={":confidence_score": "0.55"})
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == pytest.approx(0.55)

    def test_confidence_score_missing_defaults_to_half(self):
        payload = _make_valid_payload()
        del payload["confidence_score"]
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == pytest.approx(0.5)

    def test_rooms_filters_non_dict_entries(self):
        # LLM leaks field names as strings into the rooms array
        payload = _make_valid_payload(rooms=[
            {"room_type": "office", "count": 2},
            "num_bathrooms",          # stray string
            None,                     # null
            42,                       # integer
            {"room_type": "storage", "count": 1},
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.rooms) == 2
        assert pd.rooms[0].room_type == "office"
        assert pd.rooms[1].room_type == "storage"

    def test_rooms_filters_dollar_sign_noise_entries(self):
        payload = _make_valid_payload(rooms=[
            {"room_type": "bedroom", "count": 1},
            {"$comment": "schema example", "room_type": None},  # noise entry
            {"$defs": {"room_type": "X"}},
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.rooms) == 1
        assert pd.rooms[0].room_type == "bedroom"

    def test_rooms_filters_missing_room_type(self):
        payload = _make_valid_payload(rooms=[
            {"count": 2},  # no room_type
            {"room_type": "kitchen", "count": 1},
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.rooms) == 1

    def test_project_type_null_becomes_unknown(self):
        payload = _make_valid_payload(project_type=None)
        pd = ProjectData.model_validate(payload)
        assert pd.project_type == "unknown"

    def test_key_requirements_filters_non_strings(self):
        payload = _make_valid_payload(key_requirements=["AC needed", None, 123, "", "parking"])
        pd = ProjectData.model_validate(payload)
        # None and "" are dropped; 123 is coerced to "123"
        assert "AC needed" in pd.key_requirements
        assert "parking" in pd.key_requirements
        assert None not in pd.key_requirements
        assert "" not in pd.key_requirements

    def test_rooms_count_null_defaults_to_one(self):
        """LLM returned count: null — should silently default to 1, not crash."""
        payload = _make_valid_payload(rooms=[
            {"room_type": "office", "count": None},   # count is explicitly null
            {"room_type": "storage"},                  # count is absent
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.rooms) == 2
        assert pd.rooms[0].count == 1
        assert pd.rooms[1].count == 1

    def test_rooms_count_float_string_coerced(self):
        """LLM returned count as "2.0" string — should be coerced to int."""
        payload = _make_valid_payload(rooms=[
            {"room_type": "bedroom", "count": "2.0"},
        ])
        pd = ProjectData.model_validate(payload)
        assert pd.rooms[0].count == 2

    def test_rooms_area_sqm_colon_null_string(self):
        """vLLM emits area_sqm as ':null,' string — must become None, not crash."""
        payload = _make_valid_payload(rooms=[
            {"room_type": "office", "count": 3, "area_sqm": ":null,"},
            {"room_type": "storage", "count": 1, "area_sqm": ": None,"},
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.rooms) == 2
        assert pd.rooms[0].area_sqm is None
        assert pd.rooms[1].area_sqm is None

    def test_follow_up_questions_truncated_to_3(self):
        """LLM returned 4 follow-up questions — must be silently truncated, not raise."""
        payload = _make_valid_payload(follow_up_questions=[
            "Question 1?", "Question 2?", "Question 3?", "Question 4?"
        ])
        pd = ProjectData.model_validate(payload)
        assert len(pd.follow_up_questions) == 3

    def test_key_requirements_truncated_to_10(self):
        """LLM returned 12 key requirements — silently truncated to 10."""
        payload = _make_valid_payload(key_requirements=[f"req{i}" for i in range(12)])
        pd = ProjectData.model_validate(payload)
        assert len(pd.key_requirements) == 10

    def test_confidence_score_zero_not_defaulted(self):
        """confidence_score of exactly 0.0 should be preserved, not replaced with 0.5."""
        payload = _make_valid_payload(confidence_score=0.0)
        pd = ProjectData.model_validate(payload)
        assert pd.confidence_score == 0.0
