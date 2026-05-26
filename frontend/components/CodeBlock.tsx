"use client";

import { useState } from "react";

interface CodeBlockProps {
  codeItems: string[];
}

export default function CodeBlock({ codeItems }: CodeBlockProps) {
  const [open, setOpen] = useState(false);

  if (codeItems.length === 0) return null;

  return (
    <div className="mt-3 border border-[var(--border)] rounded-lg overflow-hidden text-sm">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2 bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
      >
        <span className="font-medium">Code used ({codeItems.length} snippet{codeItems.length !== 1 ? "s" : ""})</span>
        <span>{open ? "▲ Hide" : "▼ Show"}</span>
      </button>

      {open && (
        <div className="space-y-2 p-3 bg-[var(--surface)]">
          {codeItems.map((snippet, i) => (
            <pre
              key={i}
              className="text-xs font-mono bg-[var(--surface-2)] rounded p-3 overflow-x-auto text-[var(--text-muted)] whitespace-pre-wrap"
            >
              {snippet}
            </pre>
          ))}
        </div>
      )}
    </div>
  );
}
