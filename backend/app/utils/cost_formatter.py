"""
Deterministic, bilingual rendering of a cost breakdown into Markdown.

The response LLM must NEVER re-type cost figures (it loops/degenerates on the
task — see the bank-branch incident). Instead the cost table is rendered here in
Python from the persisted ``QuotationData.cost_breakdown`` and appended verbatim
to the assistant reply. All numerals are forced to Western digits (0-9).

``cost_breakdown`` shape (produced by CostCalculatorAgent.execute, see
``agents/cost_calculator.py:1030``)::

    {
      "materials": {"subtotal": float, "percentage": float,
                    "items": [{"name", "quantity", "unit", "unit_price", "total", ...}]},
      "labor":     {"subtotal": float, "percentage": float,
                    "trades": [{"trade", "quantity", "unit", "unit_price", "total", ...}]},
      "contingency": {"subtotal": float, "percentage": float, ...},
      "markup":      {"subtotal": float, "percentage": float, "breakdown": {...}},
    }
"""
from typing import Any, Dict, Optional

# Arabic-Indic → Western numerals (lifted from services/pdf_generator.py so the
# chat renderer and the PDF/Excel exporters share one source of truth).
_ARABIC_TO_ENGLISH = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "٫": ".", "٬": ",",
}

# Bilingual labels — keyed by detected language ("ar" default for this market).
_LABELS = {
    "ar": {
        "materials": "📦 الخامات",
        "labor": "👷 العمالة",
        "item": "البند",
        "qty": "الكمية",
        "unit": "الوحدة",
        "unit_price": "سعر الوحدة",
        "total": "الإجمالي",
        "materials_subtotal": "إجمالي الخامات",
        "labor_subtotal": "إجمالي العمالة",
        "contingency": "احتياطي",
        "markup": "أرباح ومصاريف إدارية",
        "grand_total": "الإجمالي التقديري",
    },
    "en": {
        "materials": "📦 Materials",
        "labor": "👷 Labor",
        "item": "Item",
        "qty": "Qty",
        "unit": "Unit",
        "unit_price": "Unit Price",
        "total": "Total",
        "materials_subtotal": "Materials subtotal",
        "labor_subtotal": "Labor subtotal",
        "contingency": "Contingency",
        "markup": "Overhead & profit",
        "grand_total": "Estimated total",
    },
}


def _to_western(text: str) -> str:
    """Force any Arabic-Indic digits/separators to Western form."""
    for arabic, english in _ARABIC_TO_ENGLISH.items():
        text = text.replace(arabic, english)
    return text


def format_egp(value: Any) -> str:
    """Format a monetary amount as ``"655,380.00 EGP"`` (Western numerals)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return f"0.00 EGP"
    return _to_western(f"{num:,.2f}") + " EGP"


def _fmt_qty(value: Any) -> str:
    """Format a quantity compactly (drop trailing ``.0``), Western numerals."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _to_western(str(value)) if value is not None else "—"
    text = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    return _to_western(text)


def _money_cell(value: Any) -> str:
    try:
        return _to_western(f"{float(value):,.2f}")
    except (TypeError, ValueError):
        return "0.00"


def _render_line_table(rows: list, name_key: str, labels: Dict[str, str]) -> str:
    """Render a list of {name/qty/unit/unit_price/total} rows as a markdown table."""
    header = (
        f"| {labels['item']} | {labels['qty']} | {labels['unit']} | "
        f"{labels['unit_price']} | {labels['total']} |\n"
        "| :-- | --: | :-- | --: | --: |\n"
    )
    body = ""
    for row in rows:
        name = str(row.get(name_key) or row.get("name") or "—").replace("|", "/")
        qty = _fmt_qty(row.get("quantity"))
        unit = str(row.get("unit") or "—").replace("|", "/")
        unit_price = _money_cell(row.get("unit_price"))
        total = _money_cell(row.get("total"))
        body += f"| {name} | {qty} | {unit} | {unit_price} | {total} |\n"
    return header + body


def render_cost_table_markdown(
    cost_breakdown: Optional[Dict[str, Any]],
    total_cost: Any,
    lang: str = "ar",
) -> str:
    """
    Render the full quotation breakdown (materials + labor tables + summary) as
    Markdown. Returns a short fallback line if the breakdown is empty/malformed.
    Never raises — presentation must not break the chat reply.
    """
    labels = _LABELS.get(lang, _LABELS["ar"])

    if not isinstance(cost_breakdown, dict) or not cost_breakdown:
        return f"**{labels['grand_total']}: {format_egp(total_cost)}**"

    parts = [f"**{labels['grand_total']}: {format_egp(total_cost)}**", ""]

    # Engineering-Q&A scope summary (rendered above the tables when present).
    scope = cost_breakdown.get("scope")
    if isinstance(scope, dict):
        scope_text = scope.get(lang) or scope.get("ar") or scope.get("en")
        if scope_text:
            parts.append(f"_{_to_western(str(scope_text))}_")
            parts.append("")

    materials = cost_breakdown.get("materials") or {}
    mat_items = materials.get("items") or []
    if mat_items:
        parts.append(f"#### {labels['materials']}")
        parts.append(_render_line_table(mat_items, "name", labels))

    labor = cost_breakdown.get("labor") or {}
    trades = labor.get("trades") or []
    if trades:
        parts.append(f"#### {labels['labor']}")
        parts.append(_render_line_table(trades, "trade", labels))

    # Summary rows
    summary_lines = []
    if materials.get("subtotal") is not None:
        summary_lines.append(f"- {labels['materials_subtotal']}: {format_egp(materials.get('subtotal'))}")
    if labor.get("subtotal") is not None:
        summary_lines.append(f"- {labels['labor_subtotal']}: {format_egp(labor.get('subtotal'))}")

    contingency = cost_breakdown.get("contingency") or {}
    if contingency.get("subtotal") is not None:
        pct = _to_western(f"{contingency.get('percentage', 0):g}")
        summary_lines.append(f"- {labels['contingency']} ({pct}%): {format_egp(contingency.get('subtotal'))}")

    markup = cost_breakdown.get("markup") or {}
    if markup.get("subtotal") is not None:
        pct = _to_western(f"{markup.get('percentage', 0):g}")
        summary_lines.append(f"- {labels['markup']} ({pct}%): {format_egp(markup.get('subtotal'))}")

    if summary_lines:
        parts.append("\n".join(summary_lines))

    parts.append(f"\n**{labels['grand_total']}: {format_egp(total_cost)}**")
    return "\n".join(parts).strip()
