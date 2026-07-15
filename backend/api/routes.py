import io
import json
import logging
import os
import re
from typing import AsyncGenerator

import groq as groq_sdk
import pandas as pd
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from langchain_groq import ChatGroq

from backend.agent.graph import build_graph
from backend.agent.state import AgentState
from backend.agent.tools import create_chart, get_schema, profile_table, query_sql
from backend.db.postgres import get_engine
from backend.db.redis_client import get_redis_client

from .models import HealthResponse, QueryRequest, SessionResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_CSV_BYTES = 50 * 1024 * 1024  # 50 MB
_ALLOWED_CSV_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"}


def _validate_table_name(table_name: str, engine) -> bool:
    """Return True only when table_name exists in the public schema."""
    try:
        import sqlalchemy as sa
        inspector = sa.inspect(engine)
        return table_name in inspector.get_table_names(schema="public")
    except Exception:
        return False


def _sse(event_type: str, payload: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


def _generate_followups(question: str, answer: str, schema_info: str) -> list[str]:
    """Ask the LLM for 3 concise follow-up questions given the current Q&A."""
    try:
        llm = ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=os.getenv("GROQ_API_KEY", ""),
            temperature=0.3,
        )
        prompt = (
            f"A data analyst asked: \"{question}\"\n"
            f"The answer was: \"{answer[:400]}\"\n\n"
            f"Database schema summary: {schema_info[:600]}\n\n"
            "Suggest exactly 3 short, specific follow-up questions the analyst might ask next. "
            "Return ONLY a JSON array of 3 strings, nothing else. Example: "
            "[\"Question 1?\", \"Question 2?\", \"Question 3?\"]"
        )
        raw = llm.invoke([{"role": "user", "content": prompt}]).content.strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        logger.warning("Follow-up generation failed: %s", e)
    return []


async def _event_stream(request: QueryRequest) -> AsyncGenerator[str, None]:
    try:
        engine = get_engine()
        redis = get_redis_client()

        schema_result = get_schema(engine)
        if schema_result.get("success"):
            lines = []
            for tname, tinfo in schema_result.get("tables", {}).items():
                cols = ", ".join(
                    f"{c['name']}({str(c['type'])[:12]})" for c in tinfo.get("columns", [])
                )
                lines.append(f"{tname}: {cols}")
            schema_info = "\n".join(lines)
        else:
            schema_info = "Schema unavailable"

        history_key = f"session:{request.session_id}:history"
        raw_history = redis.get(history_key)
        prior_messages: list = json.loads(raw_history) if raw_history else []

        initial_state: AgentState = {
            "question": request.question,
            "messages": list(prior_messages),
            "session_id": request.session_id,
            "datasource": request.datasource,
            "schema_info": schema_info,
            "iterations": 0,
            "max_iterations": request.max_iterations,
            "final_answer": None,
            "charts": [],
            "code_used": [],
        }

        graph = build_graph()
        final_state: AgentState = initial_state
        charts_emitted = 0

        async for chunk in graph.astream(initial_state):
            node_name = list(chunk.keys())[0]
            node_state: AgentState = chunk[node_name]
            final_state = node_state

            if node_name == "reason":
                messages = node_state.get("messages", [])
                last_msg = next(
                    (m for m in reversed(messages) if m.get("role") == "assistant"),
                    None,
                )
                if last_msg:
                    parsed = last_msg.get("parsed", {})
                    if "thought" in parsed:
                        yield _sse("thought", {"content": parsed["thought"]})
                    if "action" in parsed:
                        yield _sse("action", {"tool": parsed["action"], "input": parsed.get("action_input", {})})
                    if "final_answer" in parsed:
                        yield _sse("thought", {"content": f"Final Answer: {parsed['final_answer']}"})

            elif node_name == "tool":
                messages = node_state.get("messages", [])
                last_obs = next(
                    (m for m in reversed(messages) if m.get("role") == "user" and "Observation:" in m.get("content", "")),
                    None,
                )
                if last_obs:
                    yield _sse("observation", {"content": last_obs["content"]})

                # Charts (auto-generated from query rows, forecasts, explicit
                # create_chart) all live in state["charts"] — stream new ones.
                all_charts = node_state.get("charts", [])
                for chart in all_charts[charts_emitted:]:
                    yield _sse("chart", {"chart_json": chart["chart_json"], "title": chart.get("title", "")})
                charts_emitted = len(all_charts)

        # Persist conversation
        all_messages = final_state.get("messages", [])
        redis.setex(history_key, 3600 * 24, json.dumps(all_messages, default=str))

        final_answer = final_state.get("final_answer")
        if not final_answer:
            # Synthesize from last assistant thought rather than returning a useless fallback
            messages_list = final_state.get("messages", [])
            last_assistant = next(
                (m for m in reversed(messages_list) if m.get("role") == "assistant"),
                None,
            )
            if last_assistant:
                parsed = last_assistant.get("parsed", {})
                thought = parsed.get("thought", "")
                if thought and len(thought) > 30:
                    final_answer = (
                        f"Based on my analysis: {thought}\n\n"
                        "Note: The agent reached its iteration limit. Try asking a more specific question "
                        "for a more complete answer."
                    )
            if not final_answer:
                final_answer = (
                    "I was unable to retrieve a complete answer within the allowed steps. "
                    "Try rephrasing your question to be more specific, or check the Tables tab to confirm the data exists."
                )
        yield _sse(
            "final",
            {
                "answer": final_answer,
                "charts": final_state.get("charts", []),
                "code": final_state.get("code_used", []),
            },
        )

        yield "data: [DONE]\n\n"

    except groq_sdk.RateLimitError:
        yield _sse("error", {"message": "Groq rate limit reached. Please wait 30–60 seconds and try again."})
        yield "data: [DONE]\n\n"
    except groq_sdk.AuthenticationError:
        yield _sse("error", {"message": "Invalid GROQ_API_KEY. Check your backend/.env file."})
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("Error in event stream")
        exc_str = str(exc)
        if "RetryError" in exc_str or "RateLimitError" in exc_str:
            msg = "Groq rate limit reached after retries. Please wait 30–60 seconds and try again."
        else:
            msg = "An unexpected error occurred. Please try again."
        yield _sse("error", {"message": msg})
        yield "data: [DONE]\n\n"


def _generate_eda_summary(table_name: str, profile: dict) -> str:
    """Ask the LLM to write a plain-English summary of the table profile."""
    try:
        llm = ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=os.getenv("GROQ_API_KEY", ""),
            temperature=0.2,
        )
        col_lines = []
        for col in profile.get("columns", []):
            line = f"- {col['column']} ({col['type']}): {col['distinct_count']} distinct, {col['null_pct']}% null"
            if col.get("avg") is not None:
                line += f", avg={col['avg']}, min={col['min']}, max={col['max']}"
            col_lines.append(line)
        prompt = (
            f"You are a senior data analyst reviewing a database table for the first time. "
            f"Write a concise 4-6 sentence summary for a business stakeholder. Cover: "
            f"(1) what this table likely represents, "
            f"(2) any data quality concerns (nulls, low cardinality), "
            f"(3) 2-3 specific patterns or metrics worth investigating further.\n\n"
            f"Table: {table_name}\n"
            f"Total rows: {profile.get('row_count', 'unknown')}\n"
            f"Columns:\n" + "\n".join(col_lines)
        )
        return llm.invoke([{"role": "user", "content": prompt}]).content.strip()
    except Exception as e:
        logger.warning("EDA summary failed: %s", e)
        return ""


async def _eda_stream(table_name: str) -> AsyncGenerator[str, None]:
    NUMERIC_TYPES = ("INT", "FLOAT", "NUMERIC", "DECIMAL", "DOUBLE", "REAL", "BIGINT", "SMALLINT")
    DATE_TYPES = ("DATE", "TIMESTAMP", "TIME")
    try:
        engine = get_engine()

        yield _sse("eda_status", {"message": "Profiling columns..."})
        profile = profile_table(table_name, engine)
        if not profile.get("success"):
            yield _sse("eda_error", {"message": profile.get("error", "Profile failed")})
            yield "data: [DONE]\n\n"
            return
        yield _sse("eda_profile", profile)

        yield _sse("eda_status", {"message": "Generating charts..."})
        charts_generated = 0
        for col in profile.get("columns", []):
            if charts_generated >= 3:
                break
            col_name = col["column"]
            col_type = col["type"].upper()
            distinct = col["distinct_count"]
            is_numeric = any(t in col_type for t in NUMERIC_TYPES)
            is_date = any(t in col_type for t in DATE_TYPES)

            if is_date and distinct > 1:
                res = query_sql(
                    f"SELECT TO_CHAR(DATE_TRUNC('month', \"{col_name}\"), 'YYYY-MM') AS month, "
                    f"COUNT(*) AS count FROM \"{table_name}\" "
                    f"WHERE \"{col_name}\" IS NOT NULL GROUP BY month ORDER BY month",
                    engine,
                )
                if res.get("success") and res["rows"]:
                    chart = create_chart("line", res["rows"], "Records Over Time", "month", "count")
                    if chart.get("success"):
                        yield _sse("eda_chart", {"chart_json": chart["chart_json"], "title": chart["title"]})
                        charts_generated += 1

            elif not is_numeric and not is_date and 1 < distinct <= 20:
                res = query_sql(
                    f"SELECT \"{col_name}\" AS value, COUNT(*) AS count FROM \"{table_name}\" "
                    f"WHERE \"{col_name}\" IS NOT NULL "
                    f"GROUP BY \"{col_name}\" ORDER BY count DESC LIMIT 10",
                    engine,
                )
                if res.get("success") and res["rows"]:
                    chart = create_chart("bar", res["rows"], f"{col_name} Distribution", "value", "count")
                    if chart.get("success"):
                        yield _sse("eda_chart", {"chart_json": chart["chart_json"], "title": chart["title"]})
                        charts_generated += 1

        yield _sse("eda_status", {"message": "Writing AI summary..."})
        summary = _generate_eda_summary(table_name, profile)
        if summary:
            yield _sse("eda_summary", {"content": summary})

        yield "data: [DONE]\n\n"
    except Exception:
        logger.exception("EDA stream error")
        yield _sse("eda_error", {"message": "An error occurred while analyzing the table."})
        yield "data: [DONE]\n\n"


@router.get("/eda/{table_name}")
@limiter.limit("10/minute")
async def eda_endpoint(request: Request, table_name: str) -> StreamingResponse:
    engine = get_engine()
    if not _validate_table_name(table_name, engine):
        async def _not_found():
            yield _sse("eda_error", {"message": f"Table '{table_name}' not found."})
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            _not_found(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return StreamingResponse(
        _eda_stream(table_name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query")
@limiter.limit("10/minute")
async def query_endpoint(request: Request, body: QueryRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/schema")
async def schema_endpoint() -> dict:
    """Return all tables with column info and row counts."""
    engine = get_engine()
    schema = get_schema(engine)
    if not schema.get("success"):
        return schema

    tables = schema.get("tables", {})
    result = {}
    try:
        with engine.connect() as conn:
            for table_name in tables:
                row_count = conn.execute(
                    __import__("sqlalchemy").text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()
                result[table_name] = {**tables[table_name], "row_count": row_count}
    except Exception:
        result = tables
    return {"success": True, "tables": result}


@router.get("/schema/{table_name}/preview")
async def table_preview(table_name: str) -> dict:
    """Return the first 20 rows of a table."""
    engine = get_engine()
    if not _validate_table_name(table_name, engine):
        return {"success": False, "error": f"Table '{table_name}' not found."}
    result = query_sql(f'SELECT * FROM "{table_name}" LIMIT 20', engine)
    return result


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    redis = get_redis_client()
    raw = redis.get(f"session:{session_id}:history")
    messages: list = json.loads(raw) if raw else []
    return SessionResponse(session_id=session_id, message_count=len(messages))


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str) -> dict:
    redis = get_redis_client()
    redis.delete(f"session:{session_id}:history")
    return {"cleared": True, "session_id": session_id}


@router.post("/report")
@limiter.limit("5/minute")
async def generate_report(request: Request, payload: dict) -> dict:
    """Generate a professional markdown business report from a conversation."""
    try:
        exchanges = payload.get("exchanges", [])
        if not exchanges:
            return {"success": False, "error": "No conversation data."}

        conv_lines = []
        for ex in exchanges:
            conv_lines.append(f"Q: {ex.get('question', '')}")
            conv_lines.append(f"A: {ex.get('answer', '')[:400]}")
            if ex.get("sql"):
                conv_lines.append(f"SQL: {ex['sql'][0][:200]}")
            conv_lines.append("")

        llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", api_key=os.getenv("GROQ_API_KEY", ""), temperature=0.3)
        prompt = (
            "You are a senior data analyst writing a business report. "
            "Based on the analysis conversation below, produce a professional Markdown report.\n\n"
            "Structure:\n"
            "# [Report Title]\n"
            "_Generated: [today's date]_\n\n"
            "## Executive Summary\n(2-3 sentences with the most important numbers)\n\n"
            "## Key Findings\n(bullet points, each with a specific number or percentage)\n\n"
            "## Detailed Analysis\n(one section per question answered)\n\n"
            "## Recommendations\n(2-3 actionable next steps based on the data)\n\n"
            f"Conversation:\n{''.join(conv_lines)[:2500]}\n\n"
            "Return ONLY the Markdown. No preamble."
        )
        report_md = llm.invoke([{"role": "user", "content": prompt}]).content.strip()
        return {"success": True, "report": report_md}
    except Exception:
        logger.exception("Report generation error")
        return {"success": False, "error": "Report generation failed. Please try again."}


@router.get("/suggestions")
async def suggestions_endpoint(question: str = "", answer: str = "") -> dict:
    """On-demand follow-up question generation."""
    engine = get_engine()
    schema_result = get_schema(engine)
    schema_info = ", ".join(schema_result.get("tables", {}).keys()) if schema_result.get("success") else ""
    questions = _generate_followups(question, answer[:300], schema_info[:200])
    return {"questions": questions}


@router.post("/upload/csv")
async def upload_csv(file: UploadFile = File(...), if_exists: str = "replace") -> dict:
    """Upload a CSV file and create (or replace) a PostgreSQL table from it."""
    # Validate if_exists to prevent arbitrary SQL modes
    if if_exists not in ("replace", "append", "fail"):
        if_exists = "replace"

    # MIME type check
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in _ALLOWED_CSV_CONTENT_TYPES:
        return {"success": False, "error": "Only CSV files are accepted."}

    try:
        content = await file.read(_MAX_CSV_BYTES + 1)
        if len(content) > _MAX_CSV_BYTES:
            return {"success": False, "error": "File exceeds the 50 MB limit."}

        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception:
            return {"success": False, "error": "Could not parse the file as CSV."}

        # Sanitize column names
        df.columns = [
            re.sub(r"[^a-z0-9_]", "_", str(c).lower()).strip("_") or f"col_{i}"
            for i, c in enumerate(df.columns)
        ]

        raw = (file.filename or "upload").rsplit(".", 1)[0]
        table_name = re.sub(r"[^a-z0-9_]", "_", raw.lower()).strip("_") or "upload"

        engine = get_engine()
        df.to_sql(table_name, engine, if_exists=if_exists, index=False)

        return {
            "success": True,
            "table_name": table_name,
            "rows": len(df),
            "columns": list(df.columns),
        }
    except Exception:
        logger.exception("CSV upload error")
        return {"success": False, "error": "Upload failed. Please check your file and try again."}


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    postgres_ok = False
    redis_ok = False
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        postgres_ok = True
    except Exception:
        pass
    try:
        get_redis_client().ping()
        redis_ok = True
    except Exception:
        pass
    return HealthResponse(
        status="ok" if postgres_ok and redis_ok else "degraded",
        postgres=postgres_ok,
        redis=redis_ok,
    )
