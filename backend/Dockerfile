FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code into /app/backend/ so imports like "from backend.xxx" resolve correctly
COPY . ./backend/

# Make backend a proper Python package
RUN touch /app/backend/__init__.py

# Run as non-root user
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /app appuser \
    && chown -R appuser:appgroup /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Seed DB at startup (not build time — DB isn't running during build)
CMD ["sh", "-c", "python -m backend.db.seed || true && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
