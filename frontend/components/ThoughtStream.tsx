"use client";

import { useEffect, useRef, useState } from "react";
import { SSEEvent } from "@/lib/api";

interface ThoughtStreamProps {
  events: SSEEvent[];
}

function ToolBadge({ tool }: { tool: string }) {
  const colors: Record<string, string> = {
    query_sql: "bg-blue-50 text-blue-700",
    run_python: "bg-green-50 text-green-700",
    create_chart: "bg-purple-50 text-purple-700",
    get_schema: "bg-yellow-50 text-yellow-700",
    final_answer: "bg-emerald-50 text-emerald-700",
  };
  const cls = colors[tool] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded ${cls}`}>
      {tool}
    </span>
  );
}

const PREVIEW_ROWS = 10;

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(v);
}

function ObservationView({ content }: { content: string }) {
  let obs: { success?: boolean; error?: string; rows?: Record<string, unknown>[]; columns?: string[]; row_count?: number } | null = null;
  try {
    obs = JSON.parse(content.replace(/^Observation:\s*/, ""));
  } catch { /* fall through to raw text */ }

  if (obs && obs.success === false) {
    return <p className="text-xs text-red-600 mt-1">{obs.error ?? "Tool call failed"}</p>;
  }

  if (obs && Array.isArray(obs.rows) && obs.rows.length > 0) {
    const columns = obs.columns ?? Object.keys(obs.rows[0]);
    const total = obs.row_count ?? obs.rows.length;
    return (
      <div className="mt-1">
        <div className="overflow-x-auto rounded border border-[var(--border)]">
          <table className="text-xs w-full">
            <thead className="bg-[var(--surface-2)] text-[var(--text-muted)]">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="text-left font-medium px-2 py-1 whitespace-nowrap">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {obs.rows.slice(0, PREVIEW_ROWS).map((row, r) => (
                <tr key={r} className="border-t border-[var(--border)]">
                  {columns.map((c) => (
                    <td key={c} className="px-2 py-1 whitespace-nowrap text-[var(--text)]">{formatCell(row[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          {total} row{total === 1 ? "" : "s"} total
          {total > PREVIEW_ROWS ? ` · showing first ${PREVIEW_ROWS}` : ""}
        </p>
      </div>
    );
  }

  return (
    <pre className="text-xs bg-[var(--surface-2)] rounded p-2 mt-1 overflow-x-auto text-[var(--text-muted)] whitespace-pre-wrap break-all">
      {obs ? JSON.stringify(obs, null, 2) : content}
    </pre>
  );
}

export default function ThoughtStream({ events }: ThoughtStreamProps) {
  const [collapsed, setCollapsed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!collapsed) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, collapsed]);

  if (events.length === 0) return null;

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden mb-4">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-2 bg-[var(--surface-2)] text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
      >
        <span className="font-medium">Agent Reasoning ({events.length} steps)</span>
        <span>{collapsed ? "▶" : "▼"}</span>
      </button>

      {!collapsed && (
        <div className="max-h-80 overflow-y-auto scrollbar-thin p-3 space-y-2 bg-[var(--surface)]">
          {events.map((evt, i) => {
            if (evt.type === "thought") {
              return (
                <div key={i} className="text-sm text-[var(--text-muted)] italic pl-2 border-l-2 border-[var(--border)]">
                  <span className="text-xs font-semibold text-indigo-600 not-italic">Thought</span>
                  <p className="mt-0.5">{evt.content}</p>
                </div>
              );
            }
            if (evt.type === "action") {
              return (
                <div key={i} className="text-sm pl-2 border-l-2 border-blue-300">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-blue-600">Action</span>
                    {evt.tool && <ToolBadge tool={evt.tool} />}
                  </div>
                  {evt.input && (
                    <pre className="text-xs bg-[var(--surface-2)] rounded p-2 overflow-x-auto text-[var(--text-muted)]">
                      {JSON.stringify(evt.input, null, 2)}
                    </pre>
                  )}
                </div>
              );
            }
            if (evt.type === "observation") {
              return (
                <div key={i} className="text-sm pl-2 border-l-2 border-green-300">
                  <span className="text-xs font-semibold text-green-600">Observation</span>
                  <ObservationView content={evt.content ?? ""} />
                </div>
              );
            }
            return null;
          })}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
