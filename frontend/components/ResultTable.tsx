"use client";

const PREVIEW_ROWS = 10;

interface ResultTableProps {
  rows: Record<string, unknown>[];
  columns?: string[];
  total?: number;
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(v);
}

export default function ResultTable({ rows, columns, total }: ResultTableProps) {
  if (rows.length === 0) return null;
  const cols = columns ?? Object.keys(rows[0]);
  const count = total ?? rows.length;
  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="text-xs w-full">
          <thead className="bg-[var(--surface-2)] text-[var(--text-muted)]">
            <tr>
              {cols.map((c) => (
                <th key={c} className="text-left font-medium px-3 py-1.5 whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, PREVIEW_ROWS).map((row, r) => (
              <tr key={r} className="border-t border-[var(--border)]">
                {cols.map((c) => (
                  <td key={c} className="px-3 py-1.5 whitespace-nowrap text-[var(--text)]">{formatCell(row[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--text-muted)] mt-1.5">
        {count} row{count === 1 ? "" : "s"}
        {count > PREVIEW_ROWS ? ` · showing the first ${PREVIEW_ROWS}` : ""}
      </p>
    </div>
  );
}
