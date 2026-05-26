from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The analytical question to answer")
    session_id: str = Field(default="default", description="Session identifier for conversation memory")
    datasource: str = Field(default="postgres", description="Datasource to query: 'postgres' or 'mongodb'")
    max_iterations: int = Field(default=6, ge=1, le=20, description="Maximum agent loop iterations")


class SessionResponse(BaseModel):
    session_id: str
    message_count: int


class HealthResponse(BaseModel):
    status: str
    postgres: bool
    redis: bool
