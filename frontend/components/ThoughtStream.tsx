"use client";

import { useEffect, useRef, useState } from "react";
import { SSEEvent } from "@/lib/api";

interface ThoughtStreamProps {
  events: SSEEvent[];
}

function ToolBadge({ tool }: { tool: string }) {
  const colors: Record<string, string> = {
    query_sql: "bg-blue-900 text-blue-300",
    run_python: "bg-green-900 text-green-300",
    create_chart: "bg-purple-900 text-purple-300",
    get_schema: "bg-yellow-900 text-yellow-300",
    final_answer: "bg-emerald-900 text-emerald-300",
  };
  const cls = colors[tool] ?? "bg-gray-700 text-gray-300";
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded ${cls}`}>
      {tool}
    </span>
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
                  <span className="text-xs font-semibold text-indigo-400 not-italic">Thought</span>
                  <p className="mt-0.5">{evt.content}</p>
                </div>
              );
            }
            if (evt.type === "action") {
              return (
                <div key={i} className="text-sm pl-2 border-l-2 border-blue-700">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-blue-400">Action</span>
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
                <div key={i} className="text-sm pl-2 border-l-2 border-green-800">
                  <span className="text-xs font-semibold text-green-400">Observation</span>
                  <pre className="text-xs bg-[var(--surface-2)] rounded p-2 mt-1 overflow-x-auto text-[var(--text-muted)] whitespace-pre-wrap break-all">
                    {evt.content}
                  </pre>
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
