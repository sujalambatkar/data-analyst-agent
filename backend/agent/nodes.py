import json
import logging
import os
import re
from typing import Any

import groq as groq_sdk
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .state import AgentState
from .tools import create_chart, detect_anomalies, forecast_trend, get_schema, profile_table, query_sql, run_python

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a data analyst agent with PostgreSQL access. Answer in at most 2 steps.

TOOLS (call one per turn):
- query_sql: {{"query":"SELECT ..."}}
- profile_table: {{"table_name":"..."}}
- detect_anomalies: {{"table_name":"..."}}
- forecast_trend: {{"table_name":"...","date_col":"...","value_col":"...","periods":3}}
- final_answer: {{"answer":"..."}}

RULES:
1. Schema is provided — do NOT call get_schema.
2. Charts are generated automatically from query results — just run query_sql, then final_answer.
3. Always alias aggregates: SUM(x) AS x, COUNT(*) AS count, AVG(x) AS avg_x.
4. SELECT only — never INSERT/UPDATE/DELETE/DROP.
5. After seeing query results, immediately call final_answer with the complete answer.

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


def _build_llm() -> ChatGroq:
    return ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        api_key=os.getenv("GROQ_API_KEY", ""),
        temperature=0,
    )


@retry(
    retry=retry_if_exception_type((groq_sdk.RateLimitError, groq_sdk.APIConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _call_llm(llm: ChatGroq, messages: list) -> str:
    response = llm.invoke(messages)
    return response.content


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


def _parse_llm_response(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}

    thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", text, re.DOTALL)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    final_match = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL)
    if final_match:
        result["final_answer"] = final_match.group(1).strip()
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


def reason_node(state: AgentState) -> AgentState:
    llm = _build_llm()
    system_content = SYSTEM_PROMPT.format(schema_info=state.get("schema_info", "Not loaded yet"))

    history: list[dict] = [{"role": "system", "content": system_content}]
    history.append({"role": "user", "content": state["question"]})

    prior = [
        m for m in state.get("messages", [])
        if m.get("role") in ("assistant", "user") and m.get("content")
    ]
    for msg in prior[-4:]:
        history.append({"role": msg["role"], "content": msg["content"]})

    raw = _call_llm(llm, history)
    logger.info("LLM raw response:\n%s", raw)
    parsed = _parse_llm_response(raw)

    # Model sometimes uses "Action: final_answer" instead of "Final Answer:" format.
    # Capture it here so should_continue (which runs next) sees final_answer is set.
    if parsed.get("action") == "final_answer" and parsed.get("action_input", {}).get("answer"):
        parsed["final_answer"] = parsed["action_input"]["answer"]

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

    # Truncate rows in the observation stored in messages to stay within token limits.
    # The full rows are still available in `observation` for create_chart auto-inject above.
    obs_for_msg = dict(observation)
    if isinstance(obs_for_msg.get("rows"), list) and len(obs_for_msg["rows"]) > 8:
        obs_for_msg["rows"] = obs_for_msg["rows"][:8]
        obs_for_msg["truncated"] = True

    obs_text = f"Observation: {json.dumps(obs_for_msg, default=str)}"
    messages.append({"role": "user", "content": obs_text})

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
