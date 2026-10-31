"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownProps {
  children: string;
  className?: string;
}

export default function Markdown({ children, className = "" }: MarkdownProps) {
  return (
    <div
      className={`break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0
        [&_p]:my-2 [&_strong]:font-semibold
        [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_li]:my-0.5
        [&_h1]:text-base [&_h1]:font-semibold [&_h1]:mt-4 [&_h1]:mb-2
        [&_h2]:text-[0.95rem] [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-2
        [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1
        [&_code]:font-mono [&_code]:text-xs [&_code]:bg-[var(--surface-2)] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded
        [&_pre]:bg-[var(--surface-2)] [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre_code]:bg-transparent [&_pre_code]:p-0
        [&_a]:text-[var(--accent-light)] [&_a]:underline
        [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--border)] [&_blockquote]:pl-3 [&_blockquote]:text-[var(--text-muted)]
        [&_table]:w-full [&_table]:my-2 [&_table]:text-xs [&_table]:border-collapse
        [&_th]:border [&_th]:border-[var(--border)] [&_th]:bg-[var(--surface-2)] [&_th]:px-2 [&_th]:py-1 [&_th]:text-left
        [&_td]:border [&_td]:border-[var(--border)] [&_td]:px-2 [&_td]:py-1
        ${className}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
