from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="The analytical question to answer")
    session_id: str = Field(
        default="default",
        pattern=r"^[a-zA-Z0-9_-]{1,64}$",
        description="Session identifier (alphanumeric, hyphens, underscores; max 64 chars)",
    )
    datasource: str = Field(default="postgres", description="Datasource to query")
    max_iterations: int = Field(default=4, ge=1, le=6, description="Maximum agent loop iterations")


class SessionResponse(BaseModel):
    session_id: str
    message_count: int


class HealthResponse(BaseModel):
    status: str
    postgres: bool
    redis: bool
