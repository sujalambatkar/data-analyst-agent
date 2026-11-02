"use client";

import { useEffect, useRef, useState } from "react";
import { SchemaResponse } from "@/lib/api";

interface DataPanelProps {
  schema: SchemaResponse | null;
  error: boolean;
  onReload: () => void;
  onClose: () => void;
  onAsk: (question: string) => void;
}

interface UploadResult {
  success: boolean;
  table_name?: string;
  rows?: number;
  error?: string;
}

export default function DataPanel({ schema, error, onReload, onClose, onAsk }: DataPanelProps) {
  const [slow, setSlow] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Free-tier hosting can take a while to wake up; say so instead of spinning silently.
  useEffect(() => {
    if (schema || error) return;
    const t = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(t);
  }, [schema, error]);

  const upload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setResult({ success: false, error: "Please choose a .csv file." });
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/upload/csv?if_exists=replace", { method: "POST", body: form });
      const data: UploadResult = await res.json();
      setResult(data);
      if (data.success) onReload();
    } catch {
      setResult({ success: false, error: "Upload failed. Please try again." });
    } finally {
      setUploading(false);
    }
  };

  const tables = schema ? Object.entries(schema.tables) : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="w-full max-w-sm h-full bg-[var(--surface)] border-l border-[var(--border)] overflow-y-auto scrollbar-thin"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <h2 className="font-semibold text-sm">Your data</h2>
          <button onClick={onClose} className="text-sm text-[var(--text-muted)] hover:text-[var(--text)]">Close</button>
        </div>

        <div className="p-5 space-y-6">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-2">Tables</h3>
            {!schema && !error && (
              <p className="text-sm text-[var(--text-muted)] animate-pulse">
                {slow ? "Still loading — the server may be waking up, this can take up to a minute…" : "Loading your tables…"}
              </p>
            )}
            {error && (
              <div className="text-sm text-red-700">
                <p>Couldn’t load your tables.</p>
                <button
                  onClick={onReload}
                  className="mt-2 text-xs px-3 py-1.5 rounded-lg border border-red-300 hover:bg-red-100"
                >
                  Try again
                </button>
              </div>
            )}
            {schema && !error && tables.length === 0 && (
              <p className="text-sm text-[var(--text-muted)]">No tables yet. Upload a CSV below to get started.</p>
            )}
            <div className="space-y-2">
              {tables.map(([name, info]) => (
                <div key={name} className="border border-[var(--border)] rounded-lg">
                  <button
                    onClick={() => setOpen(open === name ? null : name)}
                    className="w-full text-left px-3 py-2.5 flex items-center justify-between"
                  >
                    <span>
                      <span className="text-sm font-medium block">{name}</span>
                      <span className="text-xs text-[var(--text-muted)]">
                        {info.row_count?.toLocaleString()} rows · {info.columns.length} columns
                      </span>
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">{open === name ? "▲" : "▼"}</span>
                  </button>
                  {open === name && (
                    <div className="px-3 pb-3 border-t border-[var(--border)] pt-2">
                      <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                        {info.columns.map((c) => c.name).join(", ")}
                      </p>
                      <button
                        onClick={() => { onAsk(`Give me an overview of the ${name} table.`); onClose(); }}
                        className="mt-2 text-xs px-2.5 py-1 rounded-lg border border-[var(--border)] text-[var(--accent-light)] hover:border-[var(--accent)]"
                      >
                        Ask about this table
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-2">Add your own data</h3>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="w-full border-2 border-dashed border-[var(--border)] hover:border-[var(--accent)] rounded-xl px-4 py-6 text-sm text-[var(--text-muted)] transition-colors disabled:opacity-50"
            >
              {uploading ? "Importing…" : "Choose a CSV file"}
            </button>
            {result && (
              <p className={`mt-2 text-xs ${result.success ? "text-green-700" : "text-red-700"}`}>
                {result.success
                  ? `Added “${result.table_name}” (${result.rows?.toLocaleString()} rows). You can ask about it now.`
                  : result.error}
              </p>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
