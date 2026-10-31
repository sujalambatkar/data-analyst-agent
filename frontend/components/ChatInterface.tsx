"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { SSEEvent, streamQuery, clearSession, fetchSchema } from "@/lib/api";
import Markdown from "./Markdown";
import ChartRenderer from "./ChartRenderer";
import ResultTable from "./ResultTable";
import DataPanel from "./DataPanel";

interface Message {
  id: string;
  role: "user" | "assistant";
  text?: string;
  question?: string;
  status: string;
  charts: Array<{ chart_json: string; title: string }>;
  code: string[];
  rows?: Record<string, unknown>[];
  columns?: string[];
  rowCount?: number;
  streaming: boolean;
  error?: string;
}

const EXAMPLES = [
  "Which product had the highest revenue in 2024?",
  "Show monthly revenue trends as a line chart.",
  "Compare total revenue by region.",
  "Which customer segment generates the most revenue?",
];

const STATUS_BY_EVENT: Record<string, string> = {
  thought: "Thinking…",
  action: "Looking through your data…",
  observation: "Putting the answer together…",
};

export default function ChatInterface() {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [showData, setShowData] = useState(false);
  const [tableCount, setTableCount] = useState<number | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setSessionId(`session_${Math.random().toString(36).slice(2, 9)}`);
  }, []);

  useEffect(() => {
    fetchSchema()
      .then((res) => { if (res.success) setTableCount(Object.keys(res.tables).length); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const updateLast = useCallback((updater: (m: Message) => Message) => {
    setMessages((prev) => {
      const idx = prev.length - 1;
      if (idx < 0 || prev[idx].role !== "assistant") return prev;
      const next = [...prev];
      next[idx] = updater(next[idx]);
      return next;
    });
  }, []);

  const ask = useCallback((raw: string) => {
    const question = raw.trim();
    if (!question || running || !sessionId) return;

    setInput("");
    setRunning(true);
    const now = Date.now();
    setMessages((prev) => [
      ...prev,
      { id: `u${now}`, role: "user", text: question, status: "", charts: [], code: [], streaming: false },
      { id: `a${now}`, role: "assistant", question, status: "Thinking…", charts: [], code: [], streaming: true },
    ]);

    cancelRef.current = streamQuery(
      { question, session_id: sessionId, datasource: "postgres", max_iterations: 4 },
      (event: SSEEvent) => {
        if (event.type === "thought" || event.type === "action") {
          updateLast((m) => ({ ...m, status: STATUS_BY_EVENT[event.type] }));
        } else if (event.type === "observation") {
          updateLast((m) => ({ ...m, status: STATUS_BY_EVENT.observation }));
          try {
            const obs = JSON.parse((event.content ?? "").replace(/^Observation:\s*/, ""));
            if (obs.success && Array.isArray(obs.rows) && obs.rows.length > 0) {
              updateLast((m) => ({ ...m, rows: obs.rows, columns: obs.columns, rowCount: obs.row_count }));
            }
          } catch { /* not a result set */ }
        } else if (event.type === "chart" && event.chart_json) {
          updateLast((m) => ({
            ...m,
            charts: [...m.charts, { chart_json: event.chart_json!, title: event.title ?? "" }],
          }));
        } else if (event.type === "final") {
          updateLast((m) => ({
            ...m,
            text: event.answer,
            charts: event.charts?.length ? event.charts : m.charts,
            code: event.code?.length ? event.code : m.code,
            streaming: false,
          }));
        } else if (event.type === "error") {
          updateLast((m) => ({ ...m, error: event.message, streaming: false }));
        }
      },
      () => {
        setRunning(false);
        updateLast((m) => ({ ...m, streaming: false }));
      },
      (err: string) => {
        setRunning(false);
        updateLast((m) => ({ ...m, error: err, streaming: false }));
      }
    );
  }, [running, sessionId, updateLast]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input);
    }
  };

  const newChat = async () => {
    cancelRef.current?.();
    setRunning(false);
    if (sessionId) await clearSession(sessionId).catch(() => {});
    setMessages([]);
  };

  const askFromPanel = (q: string) => {
    setInput(q);
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-screen">
      {showData && <DataPanel onClose={() => setShowData(false)} onAsk={askFromPanel} />}

      <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-[var(--border)] flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent)] flex items-center justify-center text-white font-bold text-xs">DA</div>
          <h1 className="font-semibold text-sm">Data Analyst</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowData(true)}
            className="text-sm px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--accent-light)] hover:border-[var(--accent)] transition-colors"
          >
            Your data
          </button>
          {messages.length > 0 && (
            <button
              onClick={newChat}
              className="text-sm px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
            >
              New chat
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="pt-8 sm:pt-16 text-center">
              <h2 className="text-2xl font-semibold mb-2">What would you like to know?</h2>
              <p className="text-sm text-[var(--text-muted)] mb-8">
                Ask a question about your data in plain English.
                {tableCount !== null && ` Connected to ${tableCount} table${tableCount === 1 ? "" : "s"}.`}
              </p>
              <div className="grid gap-2 sm:grid-cols-2 text-left">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    onClick={() => ask(q)}
                    disabled={!sessionId}
                    className="px-4 py-3 rounded-xl border border-[var(--border)] text-sm text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--surface-2)] transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) =>
            msg.role === "user" ? (
              <div key={msg.id} className="ml-auto w-fit max-w-[80%] bg-[var(--accent)] text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
                {msg.text}
              </div>
            ) : (
              <div key={msg.id}>
                {msg.streaming && (
                  <div className="flex items-center gap-2 text-sm text-[var(--text-muted)] py-2">
                    <span className="flex gap-1">
                      <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0ms]" />
                      <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:150ms]" />
                      <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:300ms]" />
                    </span>
                    {msg.status}
                  </div>
                )}

                {msg.error && (
                  <div className="border border-red-200 bg-red-50 rounded-xl px-4 py-3 text-sm text-red-700">
                    <p>{msg.error}</p>
                    {msg.question && (
                      <button
                        onClick={() => ask(msg.question!)}
                        disabled={running}
                        className="mt-2 text-xs px-3 py-1.5 rounded-lg border border-red-300 hover:bg-red-100 disabled:opacity-40"
                      >
                        Try again
                      </button>
                    )}
                  </div>
                )}

                {msg.text && (
                  <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-5 py-4 text-sm leading-relaxed">
                    <Markdown>{msg.text}</Markdown>
                  </div>
                )}

                {msg.charts.map((chart, i) => (
                  <div key={i} className="mt-4">
                    <ChartRenderer chartJson={chart.chart_json} title={chart.title} />
                  </div>
                ))}

                {!msg.streaming && msg.text && (msg.code.length > 0 || msg.rows) && (
                  <details className="mt-3 group">
                    <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text)] select-none">
                      How I got this
                    </summary>
                    <div className="mt-2 space-y-3">
                      {msg.code.map((snippet, i) => (
                        <pre key={i} className="text-xs font-mono bg-[var(--surface-2)] rounded-lg p-3 overflow-x-auto text-[var(--text-muted)] whitespace-pre-wrap">
                          {snippet.replace(/^-- SQL\n/, "")}
                        </pre>
                      ))}
                      {msg.rows && <ResultTable rows={msg.rows} columns={msg.columns} total={msg.rowCount} />}
                    </div>
                  </details>
                )}
              </div>
            )
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-[var(--border)] px-4 py-4 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={running}
            placeholder="Ask anything about your data…"
            rows={1}
            className="flex-1 resize-none bg-[var(--surface)] border border-[var(--border)] rounded-xl px-4 py-3 text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors disabled:opacity-50"
            style={{ maxHeight: "120px", overflowY: "auto" }}
          />
          <button
            onClick={() => ask(input)}
            disabled={running || !input.trim() || !sessionId}
            className="bg-[var(--accent)] hover:bg-[var(--accent-light)] text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {running ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
