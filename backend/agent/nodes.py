import json
import logging
import os
import re
from typing import Any

import groq as groq_sdk
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .llm import invoke_llm
from .state import AgentState
from .summary import summarize_rows
from .tools import create_chart, detect_anomalies, forecast_trend, get_schema, profile_table, query_sql, run_python

logger = logging.getLogger(__name__)

_FULL_ROWS_MAX = 8  # results up to this size reach the LLM untouched
_SAMPLE_ROWS = 5  # larger results are cut to this many rows plus a summary

SYSTEM_PROMPT = """You are a data analyst agent with PostgreSQL access. Answer in at most 2 steps.

SCOPE: You ONLY help with the data in the schema below: analysis, charts, trends, forecasts, anomalies, questions about the tables/columns, and short greetings or "what can you do". For ANYTHING else — general knowledge, definitions, explanations of everyday things, advice, coding help, creative writing, news, trivia, math unrelated to the data — do NOT answer, even if you know the answer. Reply with exactly these two lines and nothing else:
Thought: This is not about the data.
Final Answer: [OFF_TOPIC]
Follow-ups, corrections and feedback about the conversation so far are ON-topic: "i said pie chart", "make it a bar chart instead", "now by region", "why?", "thanks". Use the earlier messages to understand them and redo the analysis. Only if there is no earlier conversation and the message is unrelated to the data is it off-topic.
Examples: "what is an apple" -> off-topic. "write a poem" -> off-topic. "who won the world cup" -> off-topic. "which product sold most" -> on-topic (query the data). "what tables do you have" -> on-topic (answer from the schema). "hi" -> on-topic (greet briefly and say what you can do).

TOOLS (call one per turn):
- query_sql: {{"query":"SELECT ..."}}
- profile_table: {{"table_name":"..."}}
- detect_anomalies: {{"table_name":"..."}}
- forecast_trend: {{"table_name":"...","date_col":"...","value_col":"...","periods":3}}
- final_answer: {{"answer":"..."}}

RULES:
0. Run query_sql in EVERY turn that asks about the data — including follow-ups, corrections and chart-type changes ("make it a pie chart"). Never answer from results shown in earlier messages: charts are only drawn from a query run in the current turn.
1. Schema is provided — do NOT call get_schema.
2. Charts are generated automatically from query results — just run query_sql, then final_answer.
3. Always alias aggregates: SUM(x) AS x, COUNT(*) AS count, AVG(x) AS avg_x.
4. SELECT only — never INSERT/UPDATE/DELETE/DROP.
5. After seeing query results, immediately call final_answer with the complete answer. Never run a second query to "improve" or "add detail" — one query is enough.
6. When the result is truncated ("truncated": true), the rows are only a sample. Base your Final Answer on the "summary" (it covers ALL rows: min/max with their labels, mean, total, first/last, pct_change, by_year) — never describe only the sample rows as if they were the whole result.
7. When the user asks for a chart/graph/plot/bar/line/pie/trend, your query MUST return a label column AND a numeric column so it can be plotted — always GROUP BY a category or time period (e.g. SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region). Never return a single aggregate value for a chart request.

FORMAT every turn:
Thought: <one sentence>
Action: <tool>
Action Input: <JSON>

When done:
Thought: <reasoning>
Final Answer: <complete answer with specific numbers>

Schema:
{schema_info}
"""


@retry(
    retry=retry_if_exception_type((groq_sdk.RateLimitError, groq_sdk.APIConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _call_llm(messages: list) -> str:
    # Without a stop sequence, llama-3.3-70b-versatile sometimes keeps
    # generating past a complete "Action Input: {...}" block and hallucinates
    # a fake Thought/Final Answer for an observation it hasn't actually seen
    # yet — producing a confident-looking answer with no real data behind it.
    # Cutting generation off at the next label prevents that runaway.
    return invoke_llm(messages, temperature=0, stop=["\nThought:", "\nObservation:"])


def _extract_json(text: str, marker: str) -> dict | list | None:
    """
    Extract the JSON object/array that immediately follows `marker` in text.
    Uses bracket matching so nested structures are handled correctly —
    unlike a regex with .*? which stops at the first closing bracket.
    """
    idx = text.find(marker)
    if idx == -1:
        return None
    rest = text[idx + len(marker):].lstrip()
    if not rest or rest[0] not in ('{', '['):
        return None

    open_char = rest[0]
    close_char = '}' if open_char == '{' else ']'
    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(rest):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(rest[: i + 1])
                except json.JSONDecodeError as e:
                    logger.warning("JSON parse failed after bracket match: %s", e)
                    return None
    return None


_LABEL_RE = re.compile(
    r"[*_`#\s]*\b(Thought|Action Input|Action|Final Answer)\b[*_`\s]*:[*_`\s]*",
    re.IGNORECASE,
)

_LABEL_CANONICAL = {
    "thought": "Thought",
    "action input": "Action Input",
    "action": "Action",
    "final answer": "Final Answer",
}


def _normalize_labels(text: str) -> str:
    """
    Groq's Llama 4 Scout frequently wraps ReAct labels in markdown
    (e.g. "**Action:**", "`Action:`", "**Action**:") since we drive it with a
    plain-text prompt rather than native tool-calling. The label regexes below
    expect a literal "Action:" etc., so markdown noise around the label makes
    them silently fail to match, leaving action/thought unset. Normalize just
    the label + colon (not the JSON/SQL payload that follows) to plain text.
    """

    def repl(match: re.Match) -> str:
        canonical = _LABEL_CANONICAL[match.group(1).lower()]
        return f"\n{canonical}: "

    return _LABEL_RE.sub(repl, text)


def _parse_llm_response(text: str) -> dict[str, Any]:
    text = _normalize_labels(text)
    result: dict[str, Any] = {}

    thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", text, re.DOTALL)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    final_match = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL)
    if final_match:
        # The model sometimes echoes a redundant "Action: final_answer / Action Input"
        # block after its answer; that is not part of the answer text.
        answer = re.split(r"\n\s*Action(?: Input)?:", final_match.group(1))[0]
        result["final_answer"] = answer.strip()
        return result

    action_match = re.search(r"Action:\s*(\w+)", text)
    if action_match:
        result["action"] = action_match.group(1).strip()

    parsed_input = _extract_json(text, "Action Input:")
    if parsed_input is not None:
        result["action_input"] = parsed_input
    else:
        result["action_input"] = {}

    if not result.get("action_input") and result.get("action"):
        logger.warning("Could not parse Action Input for action=%s. Raw:\n%s", result.get("action"), text[:500])

    return result


_OFF_TOPIC_RE = re.compile(r"^[\s*_`\[(]*OFF[_ -]?TOPIC\b", re.IGNORECASE)


def _is_off_topic(answer: str) -> bool:
    return bool(_OFF_TOPIC_RE.match(answer))


def _decline_message(schema_info: str) -> str:
    tables = [line.split(":", 1)[0].strip() for line in (schema_info or "").splitlines() if ":" in line]
    have = f" Right now that's: {', '.join(tables)}." if tables else ""
    return (
        "I can only help with questions about your data."
        f"{have}\n\n"
        "Try something like “Which product had the highest revenue in 2024?” or "
        "“Show monthly revenue as a line chart.”"
    )


def _auto_chart_from_rows(question: str, rows: list) -> dict | None:
    """
    Build a chart directly from query results whenever they are chartable,
    without requiring the model to call create_chart (it reliably won't) or
    the question to contain a chart keyword. Runs on the FULL result set —
    the observation stored in messages is truncated to 8 rows for token
    budget, which previously capped auto-charts at 8 points.
    """
    if not rows or len(rows) < 2:
        return None
    first = rows[0]
    if len(first) < 2:
        return None
    if not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in first.values()):
        return None

    q = (question or "").lower()
    if re.search(r"\b(pie|pi|donut|doughnut)\b", q):
        ctype = "pie"
    elif "scatter" in q:
        ctype = "scatter"
    elif any(k in q for k in ("line", "trend", "over time", "time series", "growth", "monthly", "weekly", "daily")):
        ctype = "line"
    else:
        ctype = "bar"

    result = create_chart(ctype, rows, (question or "Chart")[:60], "", "")
    if result.get("success"):
        return {"chart_json": result["chart_json"], "title": result.get("title", "Chart")}
    logger.warning("Auto-chart failed: %s", result.get("error"))
    return None


def reason_node(state: AgentState) -> AgentState:
    system_content = SYSTEM_PROMPT.format(schema_info=state.get("schema_info", "Not loaded yet"))

    history: list[dict] = [{"role": "system", "content": system_content}]

    # The current question is marked in `messages`. Show up to 4 earlier messages
    # (previous turns) first, then the current question and everything this turn.
    msgs = [m for m in state.get("messages", []) if m.get("role") in ("assistant", "user") and m.get("content")]
    q_idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i].get("question")), None)
    if q_idx is None:
        msgs = msgs + [{"role": "user", "content": state["question"]}]
        q_idx = len(msgs) - 1
    start = max(0, q_idx - 4)
    for i, msg in enumerate(msgs[start:], start=start):
        content = msg["content"]
        if i < q_idx:
            # The "you have the data, don't query again" nudge only applies within its own turn.
            content = content.split("\n\nYou now have the data needed")[0]
        history.append({"role": msg["role"], "content": content})

    raw = _call_llm(history)
    logger.info("LLM raw response:\n%s", raw)
    parsed = _parse_llm_response(raw)

    # Model sometimes uses "Action: final_answer" instead of "Final Answer:" format.
    # Capture it here so should_continue (which runs next) sees final_answer is set.
    if parsed.get("action") == "final_answer" and parsed.get("action_input", {}).get("answer"):
        parsed["final_answer"] = parsed["action_input"]["answer"]

    if _is_off_topic(parsed.get("final_answer", "")):
        parsed["thought"] = "This question is not about the data."
        parsed["final_answer"] = _decline_message(state.get("schema_info", ""))

    logger.info("Parsed: action=%s input_keys=%s", parsed.get("action"), list(parsed.get("action_input", {}).keys()))

    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": raw, "parsed": parsed})

    new_state = dict(state)
    new_state["messages"] = messages
    new_state["iterations"] = state.get("iterations", 0) + 1
    new_state["charts"] = list(state.get("charts", []))
    new_state["code_used"] = list(state.get("code_used", []))

    if "final_answer" in parsed:
        new_state["final_answer"] = parsed["final_answer"]

    return new_state  # type: ignore[return-value]


def tool_node(state: AgentState) -> AgentState:
    from backend.db.postgres import get_engine

    messages = list(state.get("messages", []))
    charts = list(state.get("charts", []))
    code_used = list(state.get("code_used", []))

    last_msg = next(
        (m for m in reversed(messages) if m.get("role") == "assistant"),
        None,
    )
    if last_msg is None:
        return state  # type: ignore[return-value]

    parsed = last_msg.get("parsed", {})
    action = parsed.get("action", "")
    action_input = parsed.get("action_input", {})

    logger.info("Executing tool: %s | input keys: %s", action, list(action_input.keys()) if action_input else [])

    observation: dict[str, Any] = {"success": False, "error": f"Unknown tool: {action}"}

    if action == "get_schema":
        engine = get_engine()
        observation = get_schema(engine)

    elif action == "query_sql":
        query = action_input.get("query", "")
        engine = get_engine()
        observation = query_sql(query, engine)
        if query:
            code_used.append(f"-- SQL\n{query}")
        if observation.get("success"):
            auto = _auto_chart_from_rows(state.get("question", ""), observation.get("rows", []))
            if auto:
                charts.append(auto)
                logger.info("Auto-chart generated from query rows: %s", auto["title"])

    elif action == "profile_table":
        table_name = action_input.get("table_name", "")
        engine = get_engine()
        observation = profile_table(table_name, engine)

    elif action == "detect_anomalies":
        engine = get_engine()
        observation = detect_anomalies(action_input.get("table_name", ""), engine)

    elif action == "forecast_trend":
        engine = get_engine()
        result = forecast_trend(
            table_name=action_input.get("table_name", ""),
            date_col=action_input.get("date_col", ""),
            value_col=action_input.get("value_col", ""),
            periods=int(action_input.get("periods", 3)),
            engine=engine,
        )
        observation = result
        if result.get("success") and result.get("chart_json"):
            charts.append({"chart_json": result["chart_json"], "title": result.get("title", "Forecast")})
            logger.info("Forecast chart created: %s", result.get("title"))

    elif action == "run_python":
        code = action_input.get("code", "")
        data = action_input.get("data", None)
        observation = run_python(code, data)
        if code:
            code_used.append(f"# Python\n{code}")

    elif action == "create_chart":
        data = action_input.get("data", [])
        # Auto-inject rows from the most recent query_sql observation when
        # the model omits or empties the data field (common with smaller models).
        if not data:
            for msg in reversed(messages):
                if msg.get("role") == "user" and "Observation:" in msg.get("content", ""):
                    try:
                        obs = json.loads(msg["content"].replace("Observation:", "", 1).strip())
                        if obs.get("success") and obs.get("rows"):
                            data = obs["rows"]
                            break
                    except (json.JSONDecodeError, KeyError):
                        pass
        logger.info("create_chart called — rows=%d x_col=%s y_col=%s",
                    len(data), action_input.get("x_col"), action_input.get("y_col"))
        observation = create_chart(
            chart_type=action_input.get("chart_type", "bar"),
            data=data,
            title=action_input.get("title", "Chart"),
            x_col=action_input.get("x_col", ""),
            y_col=action_input.get("y_col", ""),
        )
        if observation.get("success"):
            charts.append({
                "chart_json": observation["chart_json"],
                "title": observation.get("title", "Chart"),
            })
            logger.info("Chart created successfully: %s", observation.get("title"))
        else:
            logger.warning("create_chart failed: %s", observation.get("error"))

    elif action == "final_answer":
        new_state = dict(state)
        new_state["final_answer"] = action_input.get("answer", "")
        return new_state  # type: ignore[return-value]

    # Long results are cut down to a small sample for the LLM's token budget, but a
    # sample alone makes the written answer describe only the first few rows. Attach
    # whole-result statistics so the answer can cover all of them. The full rows are
    # still available in `observation` for charts and the UI.
    obs_for_msg = dict(observation)
    truncated = isinstance(obs_for_msg.get("rows"), list) and len(obs_for_msg["rows"]) > _FULL_ROWS_MAX
    if truncated:
        summary = summarize_rows(obs_for_msg["rows"])
        obs_for_msg["rows"] = obs_for_msg["rows"][:_SAMPLE_ROWS]
        obs_for_msg["truncated"] = True
        if summary["measures"]:
            obs_for_msg["summary"] = summary

    obs_text = f"Observation: {json.dumps(obs_for_msg, default=str)}"

    # Nudge the model to finish. Small models (Llama 4 Scout) tend to keep running
    # "just one more" query and blow the iteration budget without ever calling
    # final_answer. Once a query succeeded, the answer is in hand — tell it to stop.
    # Any chart the user asked for is rendered automatically from these rows.
    if action == "query_sql" and observation.get("success") and observation.get("rows"):
        obs_text += (
            "\n\nYou now have the data needed. Do NOT run another query. "
            + (
                "The rows shown are only a sample; the `summary` covers ALL rows. "
                "Respond with `Final Answer:` based on the summary (peaks, lows, totals, trend across the whole range)."
                if truncated and "summary" in obs_for_msg
                else "Respond with `Final Answer:` containing the specific numbers from the rows above."
            )
        )

    # `display` is the clean observation the UI shows. It carries every row (the
    # LLM's copy above is truncated) and never includes the nudge text.
    messages.append({
        "role": "user",
        "content": obs_text,
        "display": json.dumps(observation, default=str),
    })

    new_state = dict(state)
    new_state["messages"] = messages
    new_state["charts"] = charts
    new_state["code_used"] = code_used
    return new_state  # type: ignore[return-value]


def should_continue(state: AgentState) -> str:
    if state.get("final_answer") is not None:
        return "end"
    if state.get("iterations", 0) >= state.get("max_iterations", 6):
        return "end"
    return "continue"
