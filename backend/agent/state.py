from typing import TypedDict


class AgentState(TypedDict):
    question: str
    messages: list
    session_id: str
    datasource: str
    schema_info: str
    iterations: int
    max_iterations: int
    final_answer: str | None
    charts: list[dict]
    code_used: list[str]
