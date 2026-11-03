import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import plotly.graph_objects as go
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _normalize_value(v: Any) -> Any:
    """
    Coerce DB driver types into JSON/Plotly-friendly primitives.
    Postgres NUMERIC comes back as Decimal, which fails isinstance(int|float)
    checks downstream and serializes as a string via json.dumps(default=str) —
    both of which silently break chart column detection.
    """
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _next_months(last_month: str, n: int) -> list[str]:
    year, month = int(last_month[:4]), int(last_month[5:7])
    result = []
    for _ in range(n):
        month += 1
        if month > 12:
            month, year = 1, year + 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def query_sql(query: str, engine: Engine) -> dict:
    """Execute a read-only SQL query and return rows as dicts."""
    stripped = query.strip().upper()
    first_word = stripped.split()[0] if stripped.split() else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        return {"success": False, "error": "Only SELECT/WITH/EXPLAIN queries are allowed."}

    write_pattern = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE)\b",
        re.IGNORECASE,
    )
    if write_pattern.search(query):
        return {"success": False, "error": "Write operations are not permitted."}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = [
                {col: _normalize_value(val) for col, val in zip(columns, row)}
                for row in result.fetchmany(500)
            ]
            return {"success": True, "rows": rows, "columns": columns, "row_count": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e)}


_COLUMNS_SQL = text("""
    SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY c.relname, a.attnum
""")

_FKS_SQL = text("""
    SELECT rel.relname, frel.relname,
           ARRAY(SELECT attname FROM pg_attribute WHERE attrelid = con.conrelid AND attnum = ANY(con.conkey)),
           ARRAY(SELECT attname FROM pg_attribute WHERE attrelid = con.confrelid AND attnum = ANY(con.confkey))
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_class frel ON frel.oid = con.confrelid
    JOIN pg_namespace n ON n.oid = rel.relnamespace
    WHERE con.contype = 'f' AND n.nspname = 'public'
""")


def _pg_type_name(raw: str) -> str:
    return raw.upper().replace("CHARACTER VARYING", "VARCHAR").replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")


def _get_schema_fast(engine: Engine) -> dict:
    """Two catalog queries instead of per-table reflection (~5 round trips per table)."""
    tables: dict[str, Any] = {}
    with engine.connect() as conn:
        for table, col, col_type, nullable in conn.execute(_COLUMNS_SQL):
            tables.setdefault(table, {"columns": [], "foreign_keys": []})["columns"].append(
                {"name": col, "type": _pg_type_name(col_type), "nullable": bool(nullable)}
            )
        for table, ref_table, cols, ref_cols in conn.execute(_FKS_SQL):
            if table in tables:
                tables[table]["foreign_keys"].append(
                    {"constrained_columns": list(cols), "referred_table": ref_table, "referred_columns": list(ref_cols)}
                )
    return {"success": True, "tables": tables}


def get_schema(engine: Engine) -> dict:
    """Return a structured dict of all tables, columns, types, and foreign keys."""
    try:
        return _get_schema_fast(engine)
    except Exception:
        pass  # non-Postgres or restricted catalog access: fall back to SQLAlchemy reflection
    try:
        inspector = inspect(engine)
        tables: dict[str, Any] = {}
        for table_name in inspector.get_table_names():
            columns = [
                {"name": col["name"], "type": str(col["type"]), "nullable": col.get("nullable", True)}
                for col in inspector.get_columns(table_name)
            ]
            fks = [
                {
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table": fk["referred_table"],
                    "referred_columns": fk["referred_columns"],
                }
                for fk in inspector.get_foreign_keys(table_name)
            ]
            tables[table_name] = {"columns": columns, "foreign_keys": fks}
        return {"success": True, "tables": tables}
    except Exception as e:
        return {"success": False, "error": str(e)}


def profile_table(table_name: str, engine: Engine) -> dict:
    """
    Return a statistical profile of every column in a table:
    row count, null count, null %, distinct count, and (for numerics)
    min / max / avg / stddev.
    """
    try:
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        if table_name not in all_tables:
            return {"success": False, "error": f"Table '{table_name}' not found. Available: {all_tables}"}

        columns = inspector.get_columns(table_name)
        numeric_types = ("INT", "FLOAT", "NUMERIC", "DECIMAL", "DOUBLE", "REAL", "BIGINT", "SMALLINT")

        with engine.connect() as conn:
            total_rows = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            profile: list[dict] = []

            for col in columns:
                col_name = col["name"]
                col_type = str(col["type"]).upper()
                quoted = f'"{col_name}"'

                null_count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}" WHERE {quoted} IS NULL')
                ).scalar()
                distinct_count = conn.execute(
                    text(f'SELECT COUNT(DISTINCT {quoted}) FROM "{table_name}"')
                ).scalar()

                entry: dict[str, Any] = {
                    "column": col_name,
                    "type": str(col["type"]),
                    "total_rows": total_rows,
                    "null_count": null_count,
                    "null_pct": round(null_count / total_rows * 100, 1) if total_rows else 0,
                    "distinct_count": distinct_count,
                }

                is_numeric = any(t in col_type for t in numeric_types)
                if is_numeric:
                    stats = conn.execute(
                        text(
                            f'SELECT MIN({quoted}), MAX({quoted}), AVG({quoted}), '
                            f'STDDEV({quoted}) FROM "{table_name}"'
                        )
                    ).fetchone()
                    if stats:
                        entry["min"] = float(stats[0]) if stats[0] is not None else None
                        entry["max"] = float(stats[1]) if stats[1] is not None else None
                        entry["avg"] = round(float(stats[2]), 2) if stats[2] is not None else None
                        entry["stddev"] = round(float(stats[3]), 2) if stats[3] is not None else None

                profile.append(entry)

        return {"success": True, "table": table_name, "row_count": total_rows, "columns": profile}
    except Exception as e:
        return {"success": False, "error": str(e)}


def detect_anomalies(table_name: str, engine: Engine) -> dict:
    """
    Scan a table for statistical anomalies:
    - Numeric columns: values beyond 3 standard deviations from the mean
    - Date/time columns: gaps longer than 2x the average interval
    """
    NUMERIC_TYPES = ("INT", "FLOAT", "NUMERIC", "DECIMAL", "DOUBLE", "REAL", "BIGINT", "SMALLINT")
    try:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            return {"success": False, "error": f"Table '{table_name}' not found."}

        columns = inspector.get_columns(table_name)
        anomalies: list[dict] = []

        with engine.connect() as conn:
            total_rows = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

            for col in columns:
                col_name = col["name"]
                col_type = str(col["type"]).upper()
                is_numeric = any(t in col_type for t in NUMERIC_TYPES)

                if not is_numeric:
                    continue

                row = conn.execute(text(
                    f'SELECT AVG("{col_name}"), STDDEV("{col_name}") FROM "{table_name}"'
                )).fetchone()
                if not row or row[0] is None or not row[1] or float(row[1]) == 0:
                    continue

                mean, std = float(row[0]), float(row[1])
                outliers = conn.execute(text(
                    f'SELECT "{col_name}" FROM "{table_name}" '
                    f'WHERE "{col_name}" IS NOT NULL '
                    f'AND ABS("{col_name}" - {mean}) > {3 * std} '
                    f'ORDER BY ABS("{col_name}" - {mean}) DESC LIMIT 5'
                )).fetchall()

                if outliers:
                    anomalies.append({
                        "column": col_name,
                        "type": "outlier",
                        "mean": round(mean, 2),
                        "stddev": round(std, 2),
                        "outlier_values": [round(float(r[0]), 2) for r in outliers],
                        "count": len(outliers),
                    })

        return {
            "success": True,
            "table": table_name,
            "total_rows": total_rows,
            "anomalies_found": len(anomalies),
            "anomalies": anomalies,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def forecast_trend(table_name: str, date_col: str, value_col: str, periods: int, engine: Engine) -> dict:
    """
    Forecast future values using linear regression on monthly-aggregated historical data.
    Returns a Plotly chart with historical line, forecast line, and confidence interval.
    """
    try:
        result = query_sql(
            f"SELECT TO_CHAR(DATE_TRUNC('month', \"{date_col}\"), 'YYYY-MM') AS month, "
            f"SUM(\"{value_col}\") AS value FROM \"{table_name}\" "
            f"WHERE \"{date_col}\" IS NOT NULL "
            f"GROUP BY month ORDER BY month",
            engine,
        )
        if not result.get("success") or not result.get("rows"):
            return {"success": False, "error": "Could not retrieve trend data."}

        rows = result["rows"]
        if len(rows) < 3:
            return {"success": False, "error": "Need at least 3 months of data to forecast."}

        hist_months = [r["month"] for r in rows]
        hist_values = np.array([float(r["value"]) for r in rows])
        x = np.arange(len(hist_values), dtype=float)

        slope, intercept = np.polyfit(x, hist_values, 1)
        fitted = slope * x + intercept
        residual_std = float(np.std(hist_values - fitted))

        forecast_x = np.arange(len(hist_values), len(hist_values) + periods, dtype=float)
        forecast_vals = slope * forecast_x + intercept
        forecast_months = _next_months(hist_months[-1], periods)

        ci_upper = (forecast_vals + 2 * residual_std).tolist()
        ci_lower = (forecast_vals - 2 * residual_std).tolist()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_months, y=hist_values.tolist(),
            mode="lines+markers", name="Historical",
            line=dict(color="#6366f1"),
        ))
        fig.add_trace(go.Scatter(
            x=forecast_months, y=forecast_vals.tolist(),
            mode="lines+markers", name="Forecast",
            line=dict(color="#f59e0b", dash="dash"),
        ))
        fig.add_trace(go.Scatter(
            x=forecast_months + forecast_months[::-1],
            y=ci_upper + ci_lower[::-1],
            fill="toself", fillcolor="rgba(245,158,11,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="95% CI", showlegend=True,
        ))
        title = f"{value_col} Forecast — Next {periods} Months"
        fig.update_layout(title=title)

        return {
            "success": True,
            "chart_json": fig.to_json(),
            "title": title,
            "forecast": [{"month": m, "value": round(v, 2)} for m, v in zip(forecast_months, forecast_vals)],
            "monthly_trend": round(float(slope), 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_python(code: str, data: dict | None = None) -> dict:
    """Execute Python code inside an isolated Docker container."""
    import os
    try:
        import docker
    except ImportError:
        return {"success": False, "error": "Docker SDK not available in this environment."}

    image = os.getenv("SANDBOX_IMAGE", "analyst-sandbox:latest")
    payload = json.dumps({"code": code, "data": data or {}})

    try:
        client = docker.from_env()
        container = client.containers.run(
            image=image,
            command=None,
            stdin_open=True,
            detach=True,
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,
            network_disabled=True,
            remove=False,
        )
        sock = container.attach_socket(params={"stdin": 1, "stream": 1, "stdout": 0, "stderr": 0})
        sock._sock.sendall((payload + "\n").encode())
        sock._sock.close()

        try:
            container.wait(timeout=10)
        except Exception:
            container.kill()
            container.remove(force=True)
            return {"success": False, "error": "Execution timed out after 10s"}

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        container.remove(force=True)
        return {"success": True, "stdout": stdout, "stderr": stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_chart(chart_type: str, data: list, title: str, x_col: str, y_col: str) -> dict:
    """Generate a Plotly figure and return its JSON representation."""
    try:
        if not data:
            return {"success": False, "error": "No data provided. Run query_sql first, then call create_chart."}

        available = list(data[0].keys())

        def _first_non_null(col: str) -> Any:
            for row in data[:20]:
                if row.get(col) is not None:
                    return row[col]
            return None

        def _is_numeric(v: Any) -> bool:
            return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)

        numeric_cols = [c for c in available if _is_numeric(_first_non_null(c))]
        text_cols = [c for c in available if c not in numeric_cols]

        # y must be numeric even if the model's y_col name happens to match a text
        # column (e.g. picking "month" instead of "total_revenue"). Fall back to the
        # LAST numeric column: aggregates conventionally come last in a SELECT list
        # (SELECT region, SUM(revenue) ...), while leading numerics are often
        # year/month grouping keys.
        if y_col not in numeric_cols:
            y_col = numeric_cols[-1] if numeric_cols else (available[-1] if available else y_col)

        # x-axis label candidates, in preference order: date-like columns
        # (year/month/etc, regardless of type) first — a trend/line chart
        # should progress along time when a time column exists, even if a
        # text column (e.g. product name) is also present — then any other
        # non-numeric column, then anything != y.
        # Ordered coarsest-to-finest so a composite label/sort-key built from
        # multiple date parts (e.g. "month" + "year" selected in that order)
        # reads and sorts chronologically (year-month), not by whatever order
        # the SQL happened to list the columns in (which would sort by month
        # first, scrambling years together).
        dateish = ("year", "quarter", "month", "week", "date", "day", "time", "hour", "period")

        def _date_rank(col: str) -> int:
            low = col.lower()
            for i, term in enumerate(dateish):
                if term in low:
                    return i
            return len(dateish)

        label_cols = sorted(
            (c for c in available if c != y_col and any(t in c.lower() for t in dateish)),
            key=_date_rank,
        )
        if not label_cols:
            label_cols = [c for c in text_cols if c != y_col]
        if not label_cols:
            label_cols = [c for c in available if c != y_col]

        def _column_xs(col: str) -> list:
            return [row.get(col) for row in data]

        def _sort_key(v: Any) -> tuple:
            # (type_rank, value) so numeric and string x-values never get
            # compared directly against each other (which raises in Python),
            # and numeric labels sort numerically rather than lexicographically
            # ("2020 - 2" before "2020 - 10", not after).
            if _is_numeric(v):
                return (0, float(v))
            if isinstance(v, str):
                try:
                    return (0, float(v.replace(",", "")))
                except ValueError:
                    return (1, v)
            return (1, str(v))

        xs: list = []
        sort_keys: list = []
        x_used_cols: set = set()
        if x_col in available and x_col != y_col:
            raw = _column_xs(x_col)
            # A constant x (e.g. year="2020" on every row) collapses the whole
            # chart onto one point — treat it as a bad pick and re-resolve.
            if not (len(data) > 1 and len({str(v) for v in raw}) <= 1):
                xs = raw
                sort_keys = [_sort_key(v) for v in raw]
                x_used_cols = {x_col}
        if not xs:
            if len(label_cols) > 1:
                # Multiple grouping columns (year + month): combine into one
                # composite label instead of guessing which single one is "the" x.
                col_vals = [[row.get(c) for c in label_cols] for row in data]
                xs = [" - ".join(str(v) for v in vals) for vals in col_vals]
                sort_keys = [tuple(_sort_key(v) for v in vals) for vals in col_vals]
                x_col = "-".join(label_cols)
                x_used_cols = set(label_cols)
            elif label_cols:
                x_col = label_cols[0]
                xs = _column_xs(x_col)
                sort_keys = [_sort_key(v) for v in xs]
                x_used_cols = {x_col}
            else:
                x_col = available[0]
                xs = _column_xs(x_col)
                sort_keys = [_sort_key(v) for v in xs]
                x_used_cols = {x_col}

        def _to_num(v: Any) -> Any:
            if _is_numeric(v):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(",", ""))
                except ValueError:
                    return v
            return v

        ys = [_to_num(row.get(y_col)) for row in data]

        chart_type = chart_type.lower()

        # A leftover column not used for x or y (e.g. product_id when the
        # x-axis is year) means the same x value can repeat once per group —
        # connecting those rows in raw SQL order draws one nonsensical
        # zigzagging line through unrelated groups. Split into one sorted
        # series per group instead; if there are too many groups to show
        # legibly, aggregate (sum) across them into a single coherent trend.
        MAX_SERIES = 20
        leftover_cols = [c for c in available if c != y_col and c not in x_used_cols]
        series_col = leftover_cols[0] if leftover_cols and chart_type != "pie" else None

        series: list[tuple[str, list, list]] = []
        if series_col:
            groups: dict[Any, list[tuple[Any, tuple, Any]]] = {}
            for row, x, sk, y in zip(data, xs, sort_keys, ys):
                groups.setdefault(row.get(series_col), []).append((x, sk, y))
            if 1 < len(groups) <= MAX_SERIES:
                for key, pts in groups.items():
                    pts.sort(key=lambda p: p[1])
                    series.append((f"{series_col}={key}", [p[0] for p in pts], [p[2] for p in pts]))
            elif len(groups) > MAX_SERIES:
                agg: dict[Any, float] = {}
                agg_key: dict[Any, tuple] = {}
                for x, sk, y in zip(xs, sort_keys, ys):
                    agg[x] = agg.get(x, 0.0) + (y if isinstance(y, (int, float)) else 0.0)
                    agg_key[x] = sk
                ordered = sorted(agg.keys(), key=lambda x: agg_key[x])
                series.append((f"Total {y_col}", ordered, [agg[x] for x in ordered]))

        if not series:
            pts = sorted(zip(xs, sort_keys, ys), key=lambda p: p[1])
            series.append((y_col, [p[0] for p in pts], [p[2] for p in pts]))

        traces = []
        for name, sx, sy in series:
            if chart_type == "bar":
                traces.append(go.Bar(x=sx, y=sy, name=name))
            elif chart_type == "line":
                traces.append(go.Scatter(x=sx, y=sy, mode="lines+markers", name=name))
            elif chart_type == "scatter":
                traces.append(go.Scatter(x=sx, y=sy, mode="markers", name=name))
            elif chart_type == "pie":
                traces.append(go.Pie(labels=sx, values=sy, name=title))
            else:
                return {"success": False, "error": f"Unsupported chart type: {chart_type}"}

        fig = go.Figure(data=traces)
        fig.update_layout(title=title, xaxis_title=x_col, yaxis_title=y_col)
        return {"success": True, "chart_json": fig.to_json(), "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}
