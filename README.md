# Data Analyst Agent

An autonomous AI agent that answers natural-language questions about your PostgreSQL database. It writes and executes SQL, detects anomalies, forecasts trends, generates interactive charts, and exports professional reports — all streamed live to a chat interface.

Built with **LangGraph** · **FastAPI** · **Groq / Llama 4 Scout** · **Next.js 15** · **Plotly** · **Docker**

---

## Features

| Feature | Description |
|---|---|
| **Autonomous ReAct loop** | Multi-step think → query → observe → answer cycle powered by LangGraph |
| **Live chart generation** | Auto-creates bar, line, scatter, and pie charts from SQL results via Plotly |
| **Anomaly detection** | IQR-based statistical outlier detection across any numeric column |
| **Trend forecasting** | Linear regression projections — "forecast next 6 months of revenue" |
| **EDA panel** | One-click table profiling: null %, distinct counts, min/max/avg, distribution charts, and an AI-written summary |
| **CSV upload** | Upload your own CSV files — they become queryable tables immediately |
| **Report generation** | Export a full Markdown business report with findings, SQL, and recommendations |
| **Pin & save insights** | Pin important answers to a persistent Saved Insights panel |
| **CSV export** | Export any query result to a CSV file in one click |
| **Session memory** | Conversation history stored in Redis — ask follow-ups without repeating context |
| **Read-only safety** | SELECT-only guard at the engine level — INSERT, UPDATE, DELETE, DROP are rejected |
| **Schema introspection** | Reads your DB schema automatically on first query — zero manual config |

---

## Quick start (Docker)

**Prerequisites:** Docker Desktop, a free [Groq API key](https://console.groq.com/)

```bash
git clone https://github.com/sujalambatkar/data-analyst-agent.git
cd data-analyst-agent

# Copy the env template and add your key
cp .env.example backend/.env
# Edit backend/.env — set GROQ_API_KEY

# Start everything
docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

Sample data (products, customers, sales tables) is seeded automatically on first start.

---

## Example questions to try

```
Which product had the highest revenue in 2024?
Show monthly revenue trends as a line chart.
Compare total revenue by region using a bar chart.
Which customer segment generates the most revenue?
Detect anomalies in the sales table.
Forecast the next 3 months of revenue.
Profile the customers table.
Upload a CSV and ask questions about it.
```

---

## Local development (without Docker)

**Prerequisites:** Python 3.11+, Node.js 18+, running PostgreSQL and Redis

```bash
# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env          # fill in your values
python -m backend.db.seed        # seed sample data
PYTHONPATH=.. uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                      # runs on http://localhost:3000
```

---

## Architecture

```
User (browser)
    │  POST /api/query (SSE)
    ▼
Next.js 15 frontend
    │  proxy /api/* → backend
    ▼
FastAPI backend
    │
    ▼
LangGraph ReAct graph
  ┌─────────────┐
  │  reason_node │◄──────────────┐
  │  (Llama 4)  │               │
  └──────┬──────┘               │
         │ should_continue?     │
  ┌──────▼──────┐               │
  │  tool_node  │───────────────┘
  │  (execute)  │
  └─────────────┘
         │ final_answer / max_iterations
         ▼
    SSE stream → frontend
```

**LangGraph ReAct loop** — `reason_node` calls the LLM which emits structured `Thought / Action / Action Input` text. `should_continue` checks for a `Final Answer` or iteration limit, then either routes to `tool_node` (tool execution) or ends the graph. The loop runs up to 2 iterations per query to stay within Groq free-tier token limits.

**SSE streaming** — every agent event (thought, action, observation, chart, final answer) is immediately yielded as a Server-Sent Event so the UI updates in real time.

**Auto-chart generation** — when the question contains chart keywords (`bar`, `line`, `trend`, `pie`, `scatter`), the backend detects this in the SSE loop and generates a Plotly chart directly from the SQL result rows — no extra LLM call needed.

**Session memory** — conversation history is stored in Redis keyed by session ID with a 24-hour TTL. The last 4 messages are included in each LLM call for context.

---

## Project structure

```
data-analyst-agent/
├── backend/
│   ├── agent/
│   │   ├── graph.py          # LangGraph graph definition
│   │   ├── nodes.py          # reason_node, tool_node, should_continue
│   │   ├── state.py          # AgentState TypedDict
│   │   └── tools.py          # query_sql, profile_table, detect_anomalies,
│   │                         #   forecast_trend, create_chart, run_python
│   ├── api/
│   │   ├── routes.py         # FastAPI endpoints + SSE streaming
│   │   └── models.py         # Pydantic request/response models
│   ├── db/
│   │   ├── postgres.py       # SQLAlchemy engine factory
│   │   ├── redis_client.py   # Redis client factory
│   │   └── seed.py           # Sample data (products, customers, sales)
│   ├── main.py               # FastAPI app, CORS, middleware
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Two-panel layout (sidebar + chat)
│   │   └── layout.tsx        # Root layout, global CSS
│   ├── components/
│   │   ├── ChatInterface.tsx # Main chat, SSE consumer, chart renderer
│   │   ├── SchemaExplorer.tsx# Table browser with row counts
│   │   ├── EDAPanel.tsx      # Streaming EDA modal
│   │   ├── CSVUpload.tsx     # Drag-and-drop CSV uploader
│   │   ├── SavedInsights.tsx # Pinned answers panel
│   │   └── ReportModal.tsx   # Markdown report generator
│   ├── lib/
│   │   └── api.ts            # Typed fetch helpers for all endpoints
│   └── Dockerfile
├── nginx/
│   └── nginx.conf            # Reverse proxy config (SSE-safe)
├── docker-compose.yml        # Development stack
├── docker-compose.prod.yml   # Production stack (env var creds, nginx)
└── .env.example              # Environment variable template
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/query` | Run a question through the agent (SSE stream) |
| `GET` | `/api/schema` | List all tables with columns and row counts |
| `GET` | `/api/schema/{table}/preview` | First 20 rows of a table |
| `GET` | `/api/eda/{table}` | Full EDA stream: profile, charts, AI summary |
| `GET` | `/api/suggestions` | Generate 3 follow-up question suggestions |
| `POST` | `/api/report` | Generate a Markdown business report |
| `POST` | `/api/upload/csv` | Upload a CSV as a new table (max 50 MB) |
| `GET` | `/api/sessions/{id}` | Get session message count |
| `DELETE` | `/api/sessions/{id}` | Clear session history |
| `GET` | `/api/health` | Check PostgreSQL + Redis connectivity |
| `GET` | `/docs` | Interactive Swagger UI |

### SSE event types (`POST /api/query`)

```jsonc
{ "type": "thought",      "content": "I need to query the sales table..." }
{ "type": "action",       "tool": "query_sql", "input": { "query": "SELECT ..." } }
{ "type": "observation",  "content": "Observation: {\"rows\": [...]}" }
{ "type": "chart",        "chart_json": "...", "title": "Revenue by Region" }
{ "type": "final",        "answer": "...", "charts": [...], "code": [...] }
{ "type": "error",        "message": "Groq rate limit reached..." }
```

---

## Production deployment

Use `docker-compose.prod.yml` which adds nginx, removes hardcoded credentials, and runs the backend as a non-root user.

```bash
cp .env.example .env.prod
# Fill in: GROQ_API_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, ALLOWED_ORIGINS

docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d
```

To enable HTTPS, add SSL certificates to `nginx/certs/` and uncomment the HTTPS server block in `nginx/nginx.conf`.

---

## Connecting your own database

Change `DATABASE_URL` in `backend/.env`:

```
DATABASE_URL=postgresql://user:password@host:5432/your_db
```

The agent reads your schema automatically on the first query — no additional config needed. Works with any PostgreSQL-compatible database.

---

## Tech stack

| Layer | Technology |
|---|---|
| LLM | Llama 4 Scout 17B via Groq API |
| Agent framework | LangGraph (ReAct graph) |
| Backend | FastAPI + Python 3.11 |
| Charts | Plotly (returned as JSON, rendered by react-plotly.js) |
| Database | PostgreSQL 16 via SQLAlchemy |
| Session store | Redis 7 |
| Frontend | Next.js 15 (App Router), Tailwind CSS |
| Containerisation | Docker + Docker Compose |
| Reverse proxy | nginx (production) |

---

## License

MIT
