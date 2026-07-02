"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { SSEEvent, streamQuery, clearSession, fetchSuggestions, fetchSchema, ReportExchange } from "@/lib/api";
import ThoughtStream from "./ThoughtStream";
import ChartRenderer from "./ChartRenderer";
import CodeBlock from "./CodeBlock";
import FollowUpSuggestions from "./FollowUpSuggestions";
import ReportModal from "./ReportModal";
import SavedInsights from "./SavedInsights";

interface Message {
  id: string;
  role: "user" | "assistant";
  text?: string;
  thoughts: SSEEvent[];
  charts: Array<{ chart_json: string; title: string }>;
  code: string[];
  suggestions: string[];
  loadingSuggestions: boolean;
  streaming: boolean;
  error?: string;
  question?: string;
  queryRows?: Record<string, unknown>[];
  queryColumns?: string[];
  pinned?: boolean;
}

interface DbSummary {
  tables: string[];
  totalRows: number;
}

interface ExampleQuestion {
  q: string;
  table: string;
}

interface ChatInterfaceProps {
  exampleQuestions?: ExampleQuestion[];
}

const DEFAULT_EXAMPLES: ExampleQuestion[] = [
  { q: "Which product had the highest total revenue in 2024?",    table: "products · sales" },
  { q: "Show monthly revenue trends as a line chart.",             table: "sales" },
  { q: "Compare total revenue by region using a bar chart.",       table: "sales" },
  { q: "Which customer segment generates the most revenue?",       table: "customers · sales" },
  { q: "Which quarter had the highest growth from 2023 to 2024?",  table: "sales" },
];

export default function ChatInterface({ exampleQuestions = DEFAULT_EXAMPLES }: ChatInterfaceProps) {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [showInsights, setShowInsights] = useState(false);
  const [dbSummary, setDbSummary] = useState<DbSummary | null>(null);
  const [streamElapsed, setStreamElapsed] = useState(0);
  const [cooldown, setCooldown] = useState(0);
  const cancelRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cooldownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const COOLDOWN_SECONDS = 20;

  useEffect(() => {
    setSessionId(`session_${Math.random().toString(36).slice(2, 9)}`);
  }, []);

  useEffect(() => {
    fetchSchema().then((res) => {
      if (res.success) {
        const tables = Object.keys(res.tables);
        const totalRows = Object.values(res.tables).reduce(
          (sum, t) => sum + (t.row_count ?? 0), 0
        );
        setDbSummary({ tables, totalRows });
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (running) {
      setStreamElapsed(0);
      streamTimerRef.current = setInterval(() => setStreamElapsed((s) => s + 1), 1000);
    } else {
      if (streamTimerRef.current) clearInterval(streamTimerRef.current);
      setStreamElapsed(0);
    }
    return () => { if (streamTimerRef.current) clearInterval(streamTimerRef.current); };
  }, [running]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const updateLastAssistant = useCallback((updater: (m: Message) => Message) => {
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === "assistant");
      if (idx === -1) return prev;
      const realIdx = prev.length - 1 - idx;
      const updated = [...prev];
      updated[realIdx] = updater(updated[realIdx]);
      return updated;
    });
  }, []);

  const startCooldown = useCallback(() => {
    setCooldown(COOLDOWN_SECONDS);
    if (cooldownTimerRef.current) clearInterval(cooldownTimerRef.current);
    cooldownTimerRef.current = setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) {
          clearInterval(cooldownTimerRef.current!);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }, []);

  const handleSubmit = useCallback(() => {
    const question = input.trim();
    if (!question || running || !sessionId || cooldown > 0) return;

    setInput("");
    setRunning(true);

    addMessage({
      id: `u${Date.now()}`,
      role: "user",
      text: question,
      thoughts: [],
      charts: [],
      code: [],
      suggestions: [],
      loadingSuggestions: false,
      streaming: false,
    });

    addMessage({
      id: `a${Date.now()}`,
      role: "assistant",
      thoughts: [],
      charts: [],
      code: [],
      suggestions: [],
      loadingSuggestions: false,
      streaming: true,
      question,
    });

    const cancel = streamQuery(
      { question, session_id: sessionId, datasource: "postgres", max_iterations: 4 },
      (event: SSEEvent) => {
        if (event.type === "thought" || event.type === "action" || event.type === "observation") {
          updateLastAssistant((m) => ({ ...m, thoughts: [...m.thoughts, event] }));
          // Extract query rows from observation events for CSV export
          if (event.type === "observation" && event.content) {
            try {
              const obs = JSON.parse(event.content.replace("Observation:", "").trim());
              if (obs.success && Array.isArray(obs.rows) && obs.rows.length > 0) {
                updateLastAssistant((m) => ({
                  ...m,
                  queryRows: obs.rows,
                  queryColumns: obs.columns ?? Object.keys(obs.rows[0]),
                }));
              }
            } catch { /* not parseable, skip */ }
          }
        } else if (event.type === "chart" && event.chart_json) {
          updateLastAssistant((m) => ({
            ...m,
            charts: [...m.charts, { chart_json: event.chart_json!, title: event.title ?? "" }],
          }));
        } else if (event.type === "final") {
          updateLastAssistant((m) => ({
            ...m,
            text: event.answer,
            charts: event.charts?.length ? event.charts : m.charts,
            code: event.code?.length ? event.code : m.code,
            streaming: false,
          }));
        } else if (event.type === "suggestions") {
          updateLastAssistant((m) => ({ ...m, suggestions: event.questions ?? [] }));
        } else if (event.type === "error") {
          updateLastAssistant((m) => ({ ...m, error: event.message, streaming: false }));
        }
      },
      () => {
        setRunning(false);
        updateLastAssistant((m) => ({ ...m, streaming: false }));
        startCooldown();
      },
      (err: string) => {
        setRunning(false);
        updateLastAssistant((m) => ({ ...m, error: err, streaming: false }));
        startCooldown();
      }
    );

    cancelRef.current = cancel;
  }, [input, running, sessionId, cooldown, addMessage, updateLastAssistant, startCooldown]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = async () => {
    if (sessionId) await clearSession(sessionId);
    setMessages([]);
  };

  const downloadCSV = (rows: Record<string, unknown>[], columns: string[], question: string) => {
    const header = columns.join(",");
    const body = rows.map((row) =>
      columns.map((c) => {
        const val = row[c] ?? "";
        const s = String(val);
        return s.includes(",") || s.includes('"') || s.includes("\n")
          ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(",")
    ).join("\n");
    const blob = new Blob([header + "\n" + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `query-result.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const pinnedInsights = messages.filter(
    (m) => m.role === "assistant" && m.pinned && m.text && m.question
  );

  const togglePin = (id: string) => {
    setMessages((prev) => prev.map((m) => m.id === id ? { ...m, pinned: !m.pinned } : m));
  };

  const buildExchanges = (): ReportExchange[] => {
    const exchanges: ReportExchange[] = [];
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role === "user" && messages[i].text) {
        const next = messages[i + 1];
        if (next?.role === "assistant" && next.text) {
          exchanges.push({ question: messages[i].text!, answer: next.text, sql: next.code ?? [] });
        }
      }
    }
    return exchanges;
  };

  return (
    <div className="flex flex-col h-full">
      {showReport && (
        <ReportModal exchanges={buildExchanges()} onClose={() => setShowReport(false)} />
      )}
      {showInsights && (
        <SavedInsights
          insights={pinnedInsights.map((m) => ({ id: m.id, question: m.question!, answer: m.text! }))}
          onClose={() => setShowInsights(false)}
          onUnpin={(id) => togglePin(id)}
          onAsk={(q) => { setInput(q); setShowInsights(false); inputRef.current?.focus(); }}
        />
      )}
      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto">
            {/* DB context card */}
            <div className="mb-5 px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--surface-2)]">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="text-xs font-semibold text-[var(--text)]">
                    Connected to{" "}
                    <span className="font-mono text-[var(--accent-light)]">sales_db</span>
                  </p>
                  {dbSummary ? (
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      {dbSummary.tables.length} tables ·{" "}
                      {dbSummary.totalRows.toLocaleString()} rows ·{" "}
                      <span className="font-mono">{dbSummary.tables.join(", ")}</span>
                    </p>
                  ) : (
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">Loading schema…</p>
                  )}
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-400 border border-emerald-800/50">
                  Connected
                </span>
              </div>
            </div>

            <p className="text-center text-[var(--text)] text-sm font-medium mb-3">
              What would you like to analyze?
            </p>
            <div className="grid gap-2">
              {exampleQuestions.map(({ q, table }) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="text-left px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--accent)] hover:bg-[var(--surface-2)] transition-colors group"
                >
                  <span className="text-sm text-[var(--text-muted)] group-hover:text-[var(--text)] block">{q}</span>
                  <span className="text-xs font-mono text-[var(--accent-light)] opacity-60 mt-0.5 block">{table}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={msg.role === "user" ? "ml-auto w-fit max-w-[75%]" : "mr-auto w-full max-w-3xl"}
          >
            {msg.role === "user" ? (
              <div className="bg-[var(--accent)] text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
                {msg.text}
              </div>
            ) : (
              <div>
                {msg.streaming && msg.thoughts.length === 0 && (
                  <div className="py-2">
                    <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
                      <span className="flex gap-1">
                        <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0ms]" />
                        <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:150ms]" />
                        <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:300ms]" />
                      </span>
                      Agent thinking...
                    </div>
                    {streamElapsed >= 15 && (
                      <p className="text-xs text-amber-500/80 mt-1.5">
                        {streamElapsed}s elapsed — Groq API may be rate-limiting. Retrying automatically…
                      </p>
                    )}
                  </div>
                )}
                {msg.streaming && msg.thoughts.length > 0 && streamElapsed >= 20 && (
                  <p className="text-xs text-amber-500/70 mb-2">
                    {streamElapsed}s elapsed — waiting on API…
                  </p>
                )}

                {msg.thoughts.length > 0 && <ThoughtStream events={msg.thoughts} />}

                {msg.error && (
                  <div className="border border-red-800 bg-red-950 rounded-lg px-4 py-3 text-sm text-red-300">
                    <span className="font-semibold">Error:</span> {msg.error}
                  </div>
                )}

                {msg.text && (
                  <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-5 py-4 text-sm text-[var(--text)] leading-relaxed whitespace-pre-wrap">
                    {msg.text}
                  </div>
                )}

                {msg.charts.map((chart, i) => (
                  <div key={i} className="mt-4">
                    <ChartRenderer chartJson={chart.chart_json} title={chart.title} />
                  </div>
                ))}

                {msg.code.length > 0 && <CodeBlock codeItems={msg.code} />}

                {!msg.streaming && !msg.error && msg.text && (
                  <div className="mt-3 space-y-2">
                    {/* Action row: pin + CSV export */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => togglePin(msg.id)}
                        className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                          msg.pinned
                            ? "border-amber-600 text-amber-400 bg-amber-900/20"
                            : "border-[var(--border)] text-[var(--text-muted)] hover:text-amber-400 hover:border-amber-600"
                        }`}
                        title={msg.pinned ? "Unpin insight" : "Pin as saved insight"}
                      >
                        {msg.pinned ? "Pinned" : "Pin insight"}
                      </button>
                      {msg.queryRows && msg.queryRows.length > 0 && msg.queryColumns && (
                        <button
                          onClick={() => downloadCSV(msg.queryRows!, msg.queryColumns!, msg.question ?? "query")}
                          className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--accent-light)] hover:border-[var(--accent)] transition-colors"
                        >
                          Export CSV ({msg.queryRows.length} rows)
                        </button>
                      )}
                    </div>

                    {/* Follow-up suggestions */}
                    {msg.suggestions.length > 0 ? (
                      <FollowUpSuggestions
                        questions={msg.suggestions}
                        onSelect={(q) => { setInput(q); inputRef.current?.focus(); }}
                      />
                    ) : (
                      <button
                        onClick={async () => {
                          setMessages((prev) => prev.map((m) =>
                            m.id === msg.id ? { ...m, loadingSuggestions: true } : m
                          ));
                          const qs = await fetchSuggestions(msg.question ?? "", msg.text ?? "");
                          setMessages((prev) => prev.map((m) =>
                            m.id === msg.id ? { ...m, suggestions: qs, loadingSuggestions: false } : m
                          ));
                        }}
                        disabled={msg.loadingSuggestions || running}
                        className="text-xs text-[var(--text-muted)] hover:text-[var(--accent-light)] border border-[var(--border)] hover:border-[var(--accent)] rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
                      >
                        {msg.loadingSuggestions ? "Loading suggestions..." : "Suggest follow-ups"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-[var(--border)] px-4 py-4 bg-[var(--background)]">
        <div className="max-w-3xl mx-auto flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={running}
            placeholder="Ask anything about your data..."
            rows={1}
            className="flex-1 resize-none bg-[var(--surface)] border border-[var(--border)] rounded-xl px-4 py-3 text-sm text-[var(--text)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors disabled:opacity-50"
            style={{ maxHeight: "120px", overflowY: "auto" }}
          />
          <button
            onClick={handleSubmit}
            disabled={running || !input.trim() || !sessionId || cooldown > 0}
            className="bg-[var(--accent)] hover:bg-[var(--accent-light)] text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {running ? "..." : cooldown > 0 ? `${cooldown}s` : "Send"}
          </button>
          {messages.length > 0 && (
            <>
              {pinnedInsights.length > 0 && (
                <button
                  onClick={() => setShowInsights(true)}
                  className="relative text-[var(--text-muted)] hover:text-amber-400 text-sm px-3 py-3 rounded-xl border border-[var(--border)] hover:border-amber-600 transition-colors whitespace-nowrap"
                >
                  Insights
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-amber-500 text-white text-[10px] flex items-center justify-center font-bold">
                    {pinnedInsights.length}
                  </span>
                </button>
              )}
              <button
                onClick={() => setShowReport(true)}
                disabled={running}
                className="text-[var(--text-muted)] hover:text-[var(--accent-light)] text-sm px-3 py-3 rounded-xl border border-[var(--border)] hover:border-[var(--accent)] transition-colors disabled:opacity-40 whitespace-nowrap"
              >
                Report
              </button>
              <button
                onClick={handleClear}
                disabled={running}
                className="text-[var(--text-muted)] hover:text-[var(--text)] text-sm px-3 py-3 rounded-xl border border-[var(--border)] transition-colors disabled:opacity-40"
              >
                Clear
              </button>
            </>
          )}
        </div>
        <p className="text-center text-xs text-[var(--text-muted)] mt-2">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
