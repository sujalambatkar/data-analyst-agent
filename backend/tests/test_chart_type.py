import json

from backend.agent.nodes import _auto_chart_from_rows

ROWS = [{"category": c, "revenue": float(v)} for c, v in zip("abcd", (4, 3, 2, 1))]


def _types(question: str) -> list[str]:
    chart = _auto_chart_from_rows(question, ROWS)
    return [t["type"] for t in json.loads(chart["chart_json"])["data"]]


def test_pie_variants():
    for q in ["show pie chart", "show pi chart of product data", "make it a donut chart", "Pie please"]:
        assert _types(q) == ["pie"], q


def test_other_types_unchanged():
    assert _types("revenue by category") == ["bar"]
    assert _types("show a scatter plot") == ["scatter"]
    assert _types("monthly trend") == ["scatter"]  # plotly line charts use the scatter trace
