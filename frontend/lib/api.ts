export interface SSEEvent {
  type: "thought" | "action" | "observation" | "chart" | "final" | "suggestions" | "error";
  content?: string;
  tool?: string;
  input?: Record<string, unknown>;
  chart_json?: string;
  title?: string;
  answer?: string;
  charts?: Array<{ chart_json: string; title: string }>;
  code?: string[];
  questions?: string[];
  message?: string;
}

export interface QueryPayload {
  question: string;
  session_id: string;
  datasource: string;
  max_iterations: number;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
}

export interface TableInfo {
  columns: ColumnInfo[];
  foreign_keys: Array<{ constrained_columns: string[]; referred_table: string; referred_columns: string[] }>;
  row_count: number;
}

export interface SchemaResponse {
  success: boolean;
  tables: Record<string, TableInfo>;
}

// If no bytes arrive for this long, the connection is treated as stalled
// (Render cold start / a dropped proxy connection) and aborted with a
// visible error — otherwise the fetch reader can hang forever with no
// onDone/onError ever firing, leaving the UI spinner stuck indefinitely.
const SSE_IDLE_TIMEOUT_MS = 55000;

function streamSSE<E>(
  url: string,
  init: RequestInit,
  onEvent: (event: E) => void,
  onDone: () => void,
  onError: (err: string) => void,
  idleTimeoutMs: number = SSE_IDLE_TIMEOUT_MS
): () => void {
  const controller = new AbortController();
  let settled = false;
  let watchdog: ReturnType<typeof setTimeout> | undefined;

  const clearWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
  };

  const resetWatchdog = () => {
    clearWatchdog();
    watchdog = setTimeout(() => {
      if (settled) return;
      settled = true;
      controller.abort();
      onError("No response from server — the connection may have stalled. Please try again.");
    }, idleTimeoutMs);
  };

  const finishOnce = (fn: () => void) => {
    if (settled) return;
    settled = true;
    clearWatchdog();
    fn();
  };

  resetWatchdog();

  fetch(url, { ...init, signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) {
        finishOnce(() => onError(`HTTP ${res.status}: ${res.statusText}`));
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        finishOnce(() => onError("No response body"));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (settled) return;
        if (done) break;
        resetWatchdog();
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") { finishOnce(onDone); return; }
            try { onEvent(JSON.parse(raw)); } catch { /* skip malformed */ }
          }
        }
      }
      finishOnce(onDone);
    })
    .catch((err) => {
      if (err.name !== "AbortError") finishOnce(() => onError(err.message ?? "Stream error"));
    });

  return () => {
    settled = true;
    clearWatchdog();
    controller.abort();
  };
}

export function streamQuery(
  payload: QueryPayload,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (err: string) => void
): () => void {
  return streamSSE<SSEEvent>(
    "/api/query",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    onEvent,
    onDone,
    onError
  );
}

export async function fetchSchema(): Promise<SchemaResponse> {
  const res = await fetch("/api/schema");
  return res.json();
}

export async function fetchTablePreview(tableName: string): Promise<{ success: boolean; rows: Record<string, unknown>[]; columns: string[] }> {
  const res = await fetch(`/api/schema/${encodeURIComponent(tableName)}/preview`);
  return res.json();
}

export interface EDAColumnProfile {
  column: string;
  type: string;
  total_rows: number;
  null_count: number;
  null_pct: number;
  distinct_count: number;
  min?: number;
  max?: number;
  avg?: number;
  stddev?: number;
}

export interface EDAEvent {
  type: "eda_status" | "eda_profile" | "eda_chart" | "eda_summary" | "eda_error";
  message?: string;
  table?: string;
  row_count?: number;
  columns?: EDAColumnProfile[];
  chart_json?: string;
  title?: string;
  content?: string;
}

export function streamEDA(
  tableName: string,
  onEvent: (event: EDAEvent) => void,
  onDone: () => void,
  onError: (err: string) => void
): () => void {
  return streamSSE<EDAEvent>(
    `/api/eda/${encodeURIComponent(tableName)}`,
    {},
    onEvent,
    onDone,
    onError
  );
}

export interface ReportExchange {
  question: string;
  answer: string;
  sql: string[];
}

export async function generateReport(exchanges: ReportExchange[]): Promise<{ success: boolean; report?: string; error?: string }> {
  try {
    const res = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exchanges }),
    });
    return res.json();
  } catch {
    return { success: false, error: "Request failed." };
  }
}

export async function fetchSuggestions(question: string, answer: string): Promise<string[]> {
  try {
    const res = await fetch(
      `/api/suggestions?question=${encodeURIComponent(question)}&answer=${encodeURIComponent(answer)}`
    );
    const data = await res.json();
    return data.questions ?? [];
  } catch {
    return [];
  }
}

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
}
