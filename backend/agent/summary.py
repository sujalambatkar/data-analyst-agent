"""Compact whole-result statistics for query results too large to show the LLM in full."""
import math
import re
from typing import Any

MAX_MEASURES = 3

_TIME_PART_COLS = ("year", "yr", "month", "mon", "quarter", "week", "day")
_ID_COL_RE = re.compile(r"(^id$|_id$)", re.IGNORECASE)
_DATE_LABEL_RE = re.compile(r"^(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v))


def _round(v: float) -> float | int:
    r = round(v, 2)
    return int(r) if r == int(r) and abs(r) < 1e15 else r


def _row_labels(rows: list[dict], columns: list[str], numeric: set[str]) -> list[str]:
    """Label each row: composed year-month for split date parts, else the first text column."""
    parts = [c for c in columns if c.lower() in _TIME_PART_COLS and c in numeric]
    by_name = {c.lower(): c for c in parts}
    year_col = by_name.get("year") or by_name.get("yr")
    month_col = by_name.get("month") or by_name.get("mon")
    if year_col:
        labels = []
        for r in rows:
            y, m = r.get(year_col), r.get(month_col) if month_col else None
            if not _is_num(y):
                labels.append("?")
            elif _is_num(m):
                labels.append(f"{int(y):04d}-{int(m):02d}")
            else:
                labels.append(f"{int(y):04d}")
        return labels

    text_col = next((c for c in columns if c not in numeric), None)
    if text_col:
        return [str(r.get(text_col)) if r.get(text_col) is not None else "?" for r in rows]
    return [str(i + 1) for i in range(len(rows))]


def summarize_rows(rows: list[dict]) -> dict:
    """
    Whole-result statistics for the LLM. Per numeric column: min/max (with the
    label of that row), mean, total. When labels are dates/periods also: first
    vs last, overall % change, and per-year totals when spanning multiple years.
    Returns {"rows": N, "measures": {...}}; measures is empty when nothing is numeric.
    """
    out: dict[str, Any] = {"rows": len(rows), "measures": {}}
    if not rows:
        return out

    columns = list(rows[0].keys())
    numeric = {c for c in columns if any(_is_num(r.get(c)) for r in rows)}
    time_parts = {c for c in numeric if c.lower() in _TIME_PART_COLS}
    measures = [c for c in columns if c in numeric and c not in time_parts and not _ID_COL_RE.search(c)]
    measures = measures[:MAX_MEASURES]
    if not measures:
        return out

    labels = _row_labels(rows, columns, numeric)
    time_like = all(_DATE_LABEL_RE.match(l) for l in labels)
    order = sorted(range(len(rows)), key=lambda i: labels[i]) if time_like else list(range(len(rows)))
    # per-year totals only add information when rows are finer than a year
    multi_year = time_like and len({_DATE_LABEL_RE.match(l).group(1) for l in labels}) > 1 and any(  # type: ignore[union-attr]
        _DATE_LABEL_RE.match(l).group(2) for l in labels  # type: ignore[union-attr]
    )

    for col in measures:
        pts = [(labels[i], rows[i][col]) for i in order if _is_num(rows[i].get(col))]
        if not pts:
            continue
        vals = [v for _, v in pts]
        lo = min(pts, key=lambda p: p[1])
        hi = max(pts, key=lambda p: p[1])
        total = sum(vals)
        m: dict[str, Any] = {
            "min": [lo[0], _round(lo[1])],
            "max": [hi[0], _round(hi[1])],
            "mean": _round(total / len(vals)),
            "total": _round(total),
        }
        if time_like and len(pts) > 1:
            first, last = pts[0], pts[-1]
            m["first"] = [first[0], _round(first[1])]
            m["last"] = [last[0], _round(last[1])]
            if first[1]:
                m["pct_change"] = round((last[1] - first[1]) / abs(first[1]) * 100, 1)
            if multi_year:
                years: dict[str, float] = {}
                for label, v in pts:
                    y = _DATE_LABEL_RE.match(label).group(1)  # type: ignore[union-attr]
                    years[y] = years.get(y, 0) + v
                m["by_year"] = {y: _round(t) for y, t in years.items()}
        if len(pts) < len(rows):
            m["nulls"] = len(rows) - len(pts)
        out["measures"][col] = m
    return out
