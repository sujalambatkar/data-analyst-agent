"use client";

import { useState } from "react";
import ChatInterface from "@/components/ChatInterface";
import SchemaExplorer from "@/components/SchemaExplorer";
import EDAPanel from "@/components/EDAPanel";
import CSVUpload from "@/components/CSVUpload";

const FEATURES = [
  { title: "Autonomous Reasoning", desc: "Multi-step ReAct loop — thinks, queries, observes, and refines until it has a confident answer." },
  { title: "Live Chart Generation", desc: "Automatically creates bar, line, scatter, and pie charts from query results using Plotly." },
  { title: "Anomaly Detection", desc: "Statistically flags outliers in any numeric column using IQR-based analysis across your tables." },
  { title: "Trend Forecasting", desc: "Projects future values using linear regression — ask for a 30-day or 12-week forecast on any metric." },
  { title: "EDA & Data Profiling", desc: "Profile any table instantly: null %, distinct counts, min/max/avg per column, all in one click." },
  { title: "CSV Upload", desc: "Upload your own CSV files — they're imported as new tables and immediately available for queries." },
  { title: "Report Generation", desc: "Export a full markdown report of your analysis with charts, SQL, and key findings." },
  { title: "Pin & Export Insights", desc: "Pin important answers to your Saved Insights panel. Export any query result to CSV in one click." },
  { title: "Session Memory", desc: "Conversation history stored in Redis — ask follow-up questions without repeating context." },
  { title: "Read-Only Safety", desc: "All SQL is strictly SELECT-only. INSERT, UPDATE, DELETE and DROP are blocked at the engine level." },
];

const EXAMPLES = [
  { q: "Which product had the highest revenue in 2024?",         table: "products · sales" },
  { q: "Show monthly revenue trends as a line chart.",            table: "sales" },
  { q: "Compare total revenue by region using a bar chart.",      table: "sales" },
  { q: "Which customer segment generates the most revenue?",      table: "customers · sales" },
  { q: "Which quarter had the highest growth from 2023 to 2024?", table: "sales" },
  { q: "Profile the customers table.",                            table: "customers" },
];

type Tab = "about" | "schema" | "upload";

export default function Home() {
  const [tab, setTab] = useState<Tab>("about");
  const [edaTable, setEdaTable] = useState<string | null>(null);

  return (
    <div className="flex h-screen overflow-hidden">
      {edaTable && <EDAPanel tableName={edaTable} onClose={() => setEdaTable(null)} />}
      {/* Left panel */}
      <aside className="hidden lg:flex flex-col w-80 xl:w-96 border-r border-[var(--border)] bg-[var(--surface)] flex-shrink-0 min-h-0">
        {/* Brand */}
        <div className="p-5 border-b border-[var(--border)] flex-shrink-0">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-[var(--accent)] flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
              DA
            </div>
            <div>
              <h1 className="font-bold text-[var(--text)] leading-tight text-sm">Data Analyst Agent</h1>
              <p className="text-xs text-[var(--text-muted)]">LangGraph · Groq · Llama 4 Scout</p>
            </div>
          </div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Ask questions about your data in plain English. The agent writes SQL, runs analysis, and generates charts — autonomously.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border)] flex-shrink-0">
          {(["about", "schema", "upload"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors capitalize ${
                tab === t
                  ? "text-[var(--accent-light)] border-b-2 border-[var(--accent)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              {t === "schema" ? "Tables" : t === "upload" ? "Upload" : "About"}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto scrollbar-thin min-h-0">
          {tab === "about" && (
            <div>
              {/* How it works */}
              <div className="p-5 border-b border-[var(--border)]">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                  How it works
                </h2>
                <ol className="space-y-2.5 text-sm text-[var(--text-muted)]">
                  {[
                    "You ask a question in plain English",
                    "Agent reads your database schema",
                    "Writes and executes SQL queries",
                    "Generates charts and delivers insights",
                  ].map((step, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="w-5 h-5 rounded-full bg-[var(--accent)] text-white text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-sm">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Features */}
              <div className="p-5 border-b border-[var(--border)]">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                  Features
                </h2>
                <div className="space-y-3">
                  {FEATURES.map((f) => (
                    <div key={f.title} className="flex gap-2.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] flex-shrink-0 mt-2" />
                      <div>
                        <p className="text-sm font-medium text-[var(--text)]">{f.title}</p>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5 leading-relaxed">{f.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Use cases */}
              <div className="p-5 border-b border-[var(--border)]">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                  Use cases
                </h2>
                <ul className="space-y-2 text-sm text-[var(--text-muted)]">
                  {[
                    "Sales and revenue analysis",
                    "KPI dashboards on demand",
                    "Anomaly detection in metrics",
                    "Cohort and retention analysis",
                    "Inventory and supply reporting",
                    "Ad-hoc business intelligence",
                    "Trend forecasting and projections",
                    "Upload and explore custom CSV data",
                    "Automated EDA on any table",
                    "Exportable analysis reports",
                  ].map((u) => (
                    <li key={u} className="flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-[var(--accent)] flex-shrink-0" />
                      {u}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Stack */}
              <div className="p-5">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                  Tech stack
                </h2>
                <div className="flex flex-wrap gap-1.5">
                  {["LangGraph", "FastAPI", "Groq", "Llama 4 Scout", "PostgreSQL", "Redis", "Next.js 15", "Plotly", "Docker"].map((t) => (
                    <span key={t} className="text-xs px-2 py-1 rounded-md bg-[var(--surface-2)] text-[var(--text-muted)] border border-[var(--border)]">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "schema" && <SchemaExplorer onAnalyze={setEdaTable} />}
          {tab === "upload" && <CSVUpload />}
        </div>
      </aside>

      {/* Right: chat */}
      <main className="flex flex-col flex-1 min-w-0">
        <header className="lg:hidden border-b border-[var(--border)] px-4 py-3 flex items-center gap-3 bg-[var(--surface)] flex-shrink-0">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent)] flex items-center justify-center text-white font-bold text-sm">
            DA
          </div>
          <div>
            <h1 className="text-sm font-semibold">Data Analyst Agent</h1>
            <p className="text-xs text-[var(--text-muted)]">LangGraph · Groq · Llama 4 Scout</p>
          </div>
        </header>
        <div className="flex-1 overflow-hidden min-h-0">
          <ChatInterface exampleQuestions={EXAMPLES} />
        </div>
      </main>
    </div>
  );
}
