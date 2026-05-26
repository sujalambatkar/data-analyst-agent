"use client";

interface Insight {
  id: string;
  question: string;
  answer: string;
}

interface SavedInsightsProps {
  insights: Insight[];
  onClose: () => void;
  onUnpin: (id: string) => void;
  onAsk: (question: string) => void;
}

export default function SavedInsights({ insights, onClose, onUnpin, onAsk }: SavedInsightsProps) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">Saved Insights</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">{insights.length} pinned finding{insights.length !== 1 ? "s" : ""}</p>
          </div>
          <button
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
          >
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-3">
          {insights.length === 0 && (
            <p className="text-sm text-[var(--text-muted)] text-center py-8">
              No insights pinned yet. Click "Pin insight" on any answer to save it here.
            </p>
          )}
          {insights.map((ins) => (
            <div key={ins.id} className="border border-amber-800/40 bg-amber-900/10 rounded-xl p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs font-semibold text-amber-400 flex-1">{ins.question}</p>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => onAsk(ins.question)}
                    className="text-xs px-2.5 py-1 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--accent-light)] hover:border-[var(--accent)] transition-colors"
                  >
                    Ask again
                  </button>
                  <button
                    onClick={() => onUnpin(ins.id)}
                    className="text-xs px-2.5 py-1 rounded-lg border border-amber-800/40 text-amber-500/70 hover:text-red-400 hover:border-red-800 transition-colors"
                  >
                    Unpin
                  </button>
                </div>
              </div>
              <p className="text-sm text-[var(--text)] mt-2 leading-relaxed line-clamp-4">{ins.answer}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
