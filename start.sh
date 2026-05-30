#!/usr/bin/env bash
# Render startup script — sets PYTHONPATH, seeds DB, then starts the server.
set -e

export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)"

echo "[start] Seeding database..."
python -m backend.db.seed || echo "[start] Seed skipped or already done."

echo "[start] Starting API server on port ${PORT:-8000}..."
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
