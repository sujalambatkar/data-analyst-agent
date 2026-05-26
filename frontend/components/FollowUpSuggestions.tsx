"use client";

interface FollowUpSuggestionsProps {
  questions: string[];
  onSelect: (q: string) => void;
}

export default function FollowUpSuggestions({ questions, onSelect }: FollowUpSuggestionsProps) {
  if (!questions.length) return null;

  return (
    <div className="mt-3">
      <p className="text-xs text-[var(--text-muted)] mb-2 font-medium">Follow-up questions</p>
      <div className="flex flex-col gap-1.5">
        {questions.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="text-left text-xs px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)] hover:text-[var(--accent-light)] text-[var(--text-muted)] transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
