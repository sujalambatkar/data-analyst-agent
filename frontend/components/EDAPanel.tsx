"use client";

import { useEffect, useState } from "react";
import { streamEDA, EDAEvent, EDAColumnProfile } from "@/lib/api";
import ChartRenderer from "./ChartRenderer";

interface EDAPanelProps {
  tableName: string;
  onClose: () => void;
}

export default function EDAPanel({ tableName, onClose }: EDAPanelProps) {
  const [status, setStatus] = useState("Starting analysis...");
  const [profile, setProfile] = useState<{ row_count: number; columns: EDAColumnProfile[] } | null>(null);
  const [charts, setCharts] = useState<Array<{ chart_json: string; title: string }>>([]);
  const [summary, setSummary] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const cancel = streamEDA(
      tableName,
      (event: EDAEvent) => {
        if (event.type === "eda_status") {
          setStatus(event.message ?? "");
        } else if (event.type === "eda_profile") {
          setProfile({ row_count: event.row_count!, columns: event.columns! });
        } else if (event.type === "eda_chart" && event.chart_json) {
          setCharts((prev) => [...prev, { chart_json: event.chart_json!, title: event.title ?? "" }]);
        } else if (event.type === "eda_summary") {
          setSummary(event.content ?? "");
        } else if (event.type === "eda_error") {
          setError(event.message ?? "Unknown error");
          setDone(true);
        }
      },
      () => setDone(true),
      (err) => { setError(err); setDone(true); }
    );
    return cancel;
  }, [tableName]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">Auto EDA — {tableName}</h2>
            {profile && (
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                {profile.row_count.toLocaleString()} rows · {profile.columns.length} columns
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text)] text-sm px-3 py-1.5 rounded-lg border border-[var(--border)] transition-colors"
          >
            Close
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto scrollbar-thin flex-1 p-6 space-y-6">
          {/* Status */}
          {!done && !error && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <span className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:300ms]" />
              </span>
              {status}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-sm text-red-400 border border-red-800 bg-red-950 rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          {/* AI Summary */}
          {summary && (
            <div className="bg-[var(--surface-2)] border border-[var(--border)] rounded-xl px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-2">
                AI Insight
              </p>
              <p className="text-sm text-[var(--text)] leading-relaxed">{summary}</p>
            </div>
          )}

          {/* Charts */}
          {charts.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                Charts
              </p>
              <div className="space-y-4">
                {charts.map((chart, i) => (
                  <ChartRenderer key={i} chartJson={chart.chart_json} title={chart.title} />
                ))}
              </div>
            </div>
          )}

          {/* Column Profile */}
          {profile && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">
                Column Profile
              </p>
              <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
                <table className="text-xs w-full">
                  <thead>
                    <tr className="bg-[var(--surface-2)] border-b border-[var(--border)]">
                      {["Column", "Type", "Nulls", "Distinct", "Min", "Max", "Avg", "Std Dev"].map((h) => (
                        <th
                          key={h}
                          className="px-3 py-2 text-left text-[var(--text-muted)] font-medium whitespace-nowrap"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {profile.columns.map((col) => (
                      <tr key={col.column} className="border-b border-[var(--border)] last:border-0">
                        <td className="px-3 py-2 font-mono text-[var(--text)]">{col.column}</td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.type}</td>
                        <td className={`px-3 py-2 ${col.null_pct > 10 ? "text-yellow-400" : "text-[var(--text-muted)]"}`}>
                          {col.null_pct}%
                        </td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.distinct_count.toLocaleString()}</td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.min ?? "—"}</td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.max ?? "—"}</td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.avg ?? "—"}</td>
                        <td className="px-3 py-2 text-[var(--text-muted)]">{col.stddev ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
