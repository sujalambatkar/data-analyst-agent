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


def get_schema(engine: Engine) -> dict:
    """Return a structured dict of all tables, columns, types, and foreign keys."""
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

        # x-axis label candidates, in preference order: non-numeric columns, then
        # date-like numeric columns (year/month grouping keys), then anything != y.
        dateish = ("year", "month", "day", "week", "date", "quarter", "period", "time", "hour")
        label_cols = [c for c in text_cols if c != y_col]
        if not label_cols:
            label_cols = [c for c in numeric_cols if c != y_col and any(t in c.lower() for t in dateish)]
        if not label_cols:
            label_cols = [c for c in available if c != y_col]

        def _column_xs(col: str) -> list:
            return [row.get(col) for row in data]

        xs: list = []
        if x_col in available and x_col != y_col:
            xs = _column_xs(x_col)
            # A constant x (e.g. year="2020" on every row) collapses the whole
            # chart onto one point — treat it as a bad pick and re-resolve.
            if len(data) > 1 and len({str(v) for v in xs}) <= 1:
                xs = []
        if not xs:
            if len(label_cols) > 1:
                # Multiple grouping columns (year + month): combine into one
                # composite label instead of guessing which single one is "the" x.
                xs = [" - ".join(str(row.get(c)) for c in label_cols) for row in data]
                x_col = "-".join(label_cols)
            elif label_cols:
                x_col = label_cols[0]
                xs = _column_xs(x_col)
            else:
                x_col = available[0]
                xs = _column_xs(x_col)

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
        if chart_type == "bar":
            trace = go.Bar(x=xs, y=ys, name=y_col)
        elif chart_type == "line":
            trace = go.Scatter(x=xs, y=ys, mode="lines+markers", name=y_col)
        elif chart_type == "scatter":
            trace = go.Scatter(x=xs, y=ys, mode="markers", name=y_col)
        elif chart_type == "pie":
            trace = go.Pie(labels=xs, values=ys, name=title)
        else:
            return {"success": False, "error": f"Unsupported chart type: {chart_type}"}

        fig = go.Figure(data=[trace])
        fig.update_layout(title=title, xaxis_title=x_col, yaxis_title=y_col)
        return {"success": True, "chart_json": fig.to_json(), "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}
