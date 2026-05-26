import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Validate required env vars at startup — fail fast before any request is served
_required = ["GROQ_API_KEY", "DATABASE_URL", "REDIS_URL"]
_missing = [k for k in _required if not os.getenv(k)]
if _missing:
    print(f"[FATAL] Missing required environment variables: {', '.join(_missing)}", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router

app = FastAPI(
    title="Data Analyst Agent",
    description="LangGraph-powered autonomous data analyst with SSE streaming",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://frontend:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000
    logger.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, duration)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"service": "Data Analyst Agent", "status": "ok", "docs": "/docs"}
