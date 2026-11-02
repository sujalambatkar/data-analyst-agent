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

export async function fetchSchema(timeoutMs = 25000): Promise<SchemaResponse> {
  const res = await fetch("/api/schema", { signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) throw new Error(`Schema request failed (${res.status})`);
  return res.json();
}

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
}
