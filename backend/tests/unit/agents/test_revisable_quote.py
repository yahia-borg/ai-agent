"""
Unit tests for the revisable-quote logic (workflow_node) and the cost-presentation
detection (builder). Guards: a COMPLETE quotation re-quotes when the user adds new
structural info, but a bare confirmation does not; and the cost table is rendered
only on the turn calculate_costs ran.
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.graph.workflow_node import _data_changed, _room_signature


def test_data_changed_on_new_field():
    old = {"size_sqm": 300, "project_type": "commercial",
           "current_finish_level": "on_plaster", "target_finish_level": "turnkey"}
    # Adding floors is a material change → re-quote
    new = {**old, "num_floors": 2}
    assert _data_changed(old, new) is True


def test_data_changed_on_rooms():
    old = {"size_sqm": 300, "rooms": []}
    new = {"size_sqm": 300, "rooms": [
        {"room_type": "office", "count": 13},
        {"room_type": "teller", "count": 10},
    ]}
    assert _data_changed(old, new) is True


def test_data_unchanged_on_confirmation():
    # Same data echoed back (a 'تمام' turn re-extracts the same fields) → no re-quote
    snap = {"size_sqm": 300, "project_type": "commercial",
            "current_finish_level": "on_plaster", "target_finish_level": "turnkey",
            "rooms": [{"room_type": "office", "count": 13}]}
    assert _data_changed(snap, dict(snap)) is False
    # None vs missing treated equal
    assert _data_changed({"size_sqm": 300, "num_floors": None}, {"size_sqm": 300}) is False


def test_room_signature_order_insensitive():
    a = {"rooms": [{"room_type": "office", "count": 13}, {"room_type": "teller", "count": 10}]}
    b = {"rooms": [{"room_type": "teller", "count": 10}, {"room_type": "office", "count": 13}]}
    assert _room_signature(a) == _room_signature(b)


def test_cost_presentation_turn_detection():
    from app.graph.builder import _is_cost_presentation_turn

    # calc ran this turn → True
    msgs_calc = [
        HumanMessage(content="13 offices"),
        ToolMessage(content="Cost Calculation Complete. total=655,380.00 EGP", tool_call_id="t1"),
    ]
    assert _is_cost_presentation_turn(msgs_calc) is True

    # follow-up turn after COMPLETE (no new tool) → False, even though an older
    # cost ToolMessage exists earlier in history
    msgs_followup = [
        ToolMessage(content="Cost Calculation Complete. total=655,380.00 EGP", tool_call_id="t1"),
        AIMessage(content="here is your quote"),
        HumanMessage(content="can you export pdf?"),
    ]
    assert _is_cost_presentation_turn(msgs_followup) is False

    # pure collection turn → False
    msgs_collect = [
        HumanMessage(content="apartment 150m"),
        ToolMessage(content="Data Extracted:\n- Missing Info: target finish", tool_call_id="t2"),
    ]
    assert _is_cost_presentation_turn(msgs_collect) is False
