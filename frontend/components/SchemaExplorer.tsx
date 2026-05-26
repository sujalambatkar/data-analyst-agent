"use client";

import { useEffect, useState } from "react";
import { fetchSchema, fetchTablePreview, SchemaResponse, TableInfo } from "@/lib/api";

interface SchemaExplorerProps {
  onAnalyze?: (tableName: string) => void;
}

export default function SchemaExplorer({ onAnalyze }: SchemaExplorerProps) {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ rows: Record<string, unknown>[]; columns: string[] } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    fetchSchema()
      .then(setSchema)
      .catch(() => setSchema({ success: false, tables: {} }))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (tableName: string) => {
    if (selected === tableName) {
      setSelected(null);
      setPreview(null);
      return;
    }
    setSelected(tableName);
    setPreview(null);
    setPreviewLoading(true);
    try {
      const data = await fetchTablePreview(tableName);
      if (data.success) setPreview(data);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-sm text-[var(--text-muted)] animate-pulse">
        Loading schema...
      </div>
    );
  }

  if (!schema?.success || !Object.keys(schema.tables).length) {
    return (
      <div className="p-6 text-sm text-[var(--text-muted)]">
        No tables found. Run the seed script to populate sample data.
      </div>
    );
  }

  const tables = schema.tables;

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      <div className="p-4 border-b border-[var(--border)]">
        <p className="text-xs text-[var(--text-muted)]">
          {Object.keys(tables).length} table{Object.keys(tables).length !== 1 ? "s" : ""}
        </p>
      </div>

      <div className="divide-y divide-[var(--border)]">
        {Object.entries(tables).map(([name, info]: [string, TableInfo]) => (
          <div key={name}>
            {/* Table header */}
            <div
              onClick={() => handleSelect(name)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--surface-2)] transition-colors cursor-pointer"
            >
              <div>
                <p className="text-sm font-medium text-[var(--text)]">{name}</p>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  {info.row_count?.toLocaleString()} rows · {info.columns.length} columns
                </p>
              </div>
              <div className="flex items-center gap-2">
                {onAnalyze && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onAnalyze(name); }}
                    className="text-xs px-2 py-1 rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent-light)] transition-colors"
                  >
                    Analyze
                  </button>
                )}
                <span className="text-[var(--text-muted)] text-xs">{selected === name ? "▲" : "▼"}</span>
              </div>
            </div>

            {/* Expanded: columns + preview */}
            {selected === name && (
              <div className="bg-[var(--surface-2)] border-t border-[var(--border)]">
                {/* Column list */}
                <div className="px-4 py-3">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
                    Columns
                  </p>
                  <div className="space-y-1">
                    {info.columns.map((col) => (
                      <div key={col.name} className="flex items-center justify-between text-xs">
                        <span className="text-[var(--text)] font-mono">{col.name}</span>
                        <span className="text-[var(--text-muted)]">{col.type}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Row preview */}
                <div className="px-4 pb-3">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
                    Sample rows
                  </p>
                  {previewLoading && (
                    <p className="text-xs text-[var(--text-muted)] animate-pulse">Loading...</p>
                  )}
                  {preview && preview.rows.length > 0 && (
                    <div className="overflow-x-auto rounded border border-[var(--border)]">
                      <table className="text-xs w-full">
                        <thead>
                          <tr className="bg-[var(--surface)] border-b border-[var(--border)]">
                            {preview.columns.map((col) => (
                              <th key={col} className="px-2 py-1.5 text-left text-[var(--text-muted)] font-medium whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.rows.slice(0, 5).map((row, i) => (
                            <tr key={i} className="border-b border-[var(--border)] last:border-0">
                              {preview.columns.map((col) => (
                                <td key={col} className="px-2 py-1.5 text-[var(--text-muted)] whitespace-nowrap max-w-[120px] truncate">
                                  {String(row[col] ?? "")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
