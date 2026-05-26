"use client";

import { useRef, useState } from "react";

interface UploadResult {
  success: boolean;
  table_name?: string;
  rows?: number;
  columns?: string[];
  error?: string;
}

export default function CSVUpload() {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [ifExists, setIfExists] = useState<"replace" | "append">("replace");
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    if (!file.name.endsWith(".csv")) {
      setResult({ success: false, error: "Only CSV files are supported." });
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/upload/csv?if_exists=${ifExists}`, {
        method: "POST",
        body: form,
      });
      const data: UploadResult = await res.json();
      setResult(data);
    } catch {
      setResult({ success: false, error: "Upload failed. Is the backend running?" });
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload(file);
    e.target.value = "";
  };

  return (
    <div className="p-4 space-y-4">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-1">
          Upload CSV
        </h2>
        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          Drop any CSV file to create a new table. You can query it immediately after upload.
        </p>
      </div>

      {/* If-exists toggle */}
      <div className="flex gap-2">
        {(["replace", "append"] as const).map((opt) => (
          <button
            key={opt}
            onClick={() => setIfExists(opt)}
            className={`flex-1 py-1.5 text-xs rounded-lg border transition-colors capitalize ${
              ifExists === opt
                ? "border-[var(--accent)] text-[var(--accent-light)] bg-[var(--surface-2)]"
                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
      <p className="text-xs text-[var(--text-muted)] -mt-2">
        {ifExists === "replace"
          ? "Replaces the table if it already exists."
          : "Appends rows to an existing table (must match columns)."}
      </p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl px-4 py-8 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-[var(--accent)] bg-[var(--surface-2)]"
            : "border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--surface-2)]"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={onFileChange}
        />
        {uploading ? (
          <div className="flex items-center justify-center gap-2 text-sm text-[var(--text-muted)]">
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:300ms]" />
            </span>
            Importing...
          </div>
        ) : (
          <div>
            <p className="text-sm text-[var(--text-muted)]">Drop a CSV file here</p>
            <p className="text-xs text-[var(--text-muted)] mt-1 opacity-60">or click to browse</p>
          </div>
        )}
      </div>

      {/* Result */}
      {result && (
        <div
          className={`rounded-xl border px-4 py-3 text-xs ${
            result.success
              ? "border-green-800 bg-green-950 text-green-300"
              : "border-red-800 bg-red-950 text-red-300"
          }`}
        >
          {result.success ? (
            <div className="space-y-1">
              <p className="font-semibold">Table created: {result.table_name}</p>
              <p>{result.rows?.toLocaleString()} rows imported</p>
              <p className="text-green-400/70 font-mono truncate">
                {result.columns?.join(", ")}
              </p>
              <p className="text-green-400/50 mt-1">
                Switch to the Tables tab to explore it, or ask the agent a question.
              </p>
            </div>
          ) : (
            <p><span className="font-semibold">Error:</span> {result.error}</p>
          )}
        </div>
      )}
    </div>
  );
}
