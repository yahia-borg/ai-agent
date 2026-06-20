"""
Unit tests for the deterministic cost renderer (utils/cost_formatter).

These guard the fix for the response-LLM degeneration meltdown: the BOQ table is
rendered in Python, never re-typed by the model. Pure-Python module (no heavy
deps) so it also runs on the host.
"""
import pytest

from app.utils.cost_formatter import (
    format_egp,
    render_cost_table_markdown,
)


SAMPLE_BREAKDOWN = {
    "materials": {
        "subtotal": 113850.0,
        "percentage": 50.0,
        "items": [
            {"name": "Ceramic Tiles - Standard", "quantity": 300, "unit": "sqm",
             "unit_price": 220.0, "total": 66000.0},
            {"name": "Emulsion Paint - Standard", "quantity": 300, "unit": "sqm",
             "unit_price": 71.5, "total": 21450.0},
        ],
    },
    "labor": {
        "subtotal": 192000.0,
        "percentage": 50.0,
        "trades": [
            {"trade": "Mason", "quantity": 1600, "unit": "hours",
             "unit_price": 60.0, "total": 96000.0},
            {"trade": "Electrician", "quantity": 1600, "unit": "hours",
             "unit_price": 60.0, "total": 96000.0},
        ],
    },
    "contingency": {"subtotal": 30585.0, "percentage": 10.0},
    "markup": {"subtotal": 30585.0, "percentage": 10.0,
               "breakdown": {"overhead": 15292.5, "profit": 15292.5}},
}
TOTAL = 655380.0


def test_format_egp_western_numerals():
    assert format_egp(655380.0) == "655,380.00 EGP"
    assert format_egp(0) == "0.00 EGP"
    # Garbage in → safe default, never raises
    assert format_egp(None) == "0.00 EGP"
    assert format_egp("notanumber") == "0.00 EGP"


def test_render_contains_total_and_rows():
    md = render_cost_table_markdown(SAMPLE_BREAKDOWN, TOTAL, lang="ar")
    # Grand total present and correctly formatted
    assert "655,380.00 EGP" in md
    # Each line item rendered with its total
    assert "Ceramic Tiles - Standard" in md
    assert "66,000.00" in md
    assert "Mason" in md
    assert "96,000.00" in md
    # Subtotals / contingency / markup surfaced
    assert "113,850.00 EGP" in md  # materials subtotal
    assert "192,000.00 EGP" in md  # labor subtotal
    # Markdown table structure
    assert md.count("| :--") >= 1


def test_render_never_emits_eastern_arabic_numerals():
    md = render_cost_table_markdown(SAMPLE_BREAKDOWN, TOTAL, lang="ar")
    for ch in "٠١٢٣٤٥٦٧٨٩":
        assert ch not in md, f"Eastern Arabic numeral {ch} leaked into output"


def test_render_empty_breakdown_is_safe():
    # Empty/missing breakdown must not raise — returns a one-line total fallback.
    md = render_cost_table_markdown(None, TOTAL, lang="ar")
    assert "655,380.00 EGP" in md
    md2 = render_cost_table_markdown({}, 0, lang="en")
    assert "0.00 EGP" in md2


def test_render_english_headers():
    md = render_cost_table_markdown(SAMPLE_BREAKDOWN, TOTAL, lang="en")
    assert "Unit Price" in md and "Total" in md
