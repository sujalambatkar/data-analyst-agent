"use client";

import { useEffect, useState } from "react";
import { generateReport, ReportExchange } from "@/lib/api";

interface ReportModalProps {
  exchanges: ReportExchange[];
  onClose: () => void;
}

export default function ReportModal({ exchanges, onClose }: ReportModalProps) {
  const [report, setReport] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    generateReport(exchanges).then((res) => {
      if (res.success && res.report) setReport(res.report);
      else setError(res.error ?? "Generation failed.");
      setLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const download = () => {
    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "analysis-report.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  const copy = () => {
    navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">AI Analysis Report</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">Generated from your conversation</p>
          </div>
          <div className="flex items-center gap-2">
            {report && (
              <>
                <button
                  onClick={copy}
                  className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
                <button
                  onClick={download}
                  className="text-xs px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white hover:bg-[var(--accent-light)] transition-colors"
                >
                  Download .md
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
            >
              Close
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-6">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <span className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:300ms]" />
              </span>
              Generating report...
            </div>
          )}
          {error && (
            <div className="text-sm text-red-400 border border-red-800 bg-red-950 rounded-lg px-4 py-3">
              {error}
            </div>
          )}
          {report && (
            <pre className="text-sm text-[var(--text)] whitespace-pre-wrap font-mono leading-relaxed">
              {report}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
