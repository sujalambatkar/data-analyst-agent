"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ChartRendererProps {
  chartJson: string;
  title?: string;
}

export default function ChartRenderer({ chartJson, title }: ChartRendererProps) {
  const figure = useMemo(() => {
    try {
      return JSON.parse(chartJson);
    } catch {
      return null;
    }
  }, [chartJson]);

  if (!figure) {
    return (
      <div className="border border-red-800 rounded-lg p-4 text-sm text-red-400">
        Failed to parse chart data.
      </div>
    );
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      {title && (
        <div className="px-4 py-2 bg-[var(--surface-2)] text-sm font-medium text-[var(--text-muted)]">
          {title}
        </div>
      )}
      <div className="bg-[var(--surface)] p-2">
        <Plot
          data={figure.data}
          layout={{
            ...figure.layout,
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#e2e8f0" },
            margin: { t: 40, b: 60, l: 60, r: 20 },
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: "100%", minHeight: "320px" }}
        />
      </div>
    </div>
  );
}
