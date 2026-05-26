import type { Metadata, Viewport } from "next";
import ErrorBoundary from "@/components/ErrorBoundary";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Analyst Agent",
  description: "Ask questions about your data in plain English. Powered by LangGraph, Groq llama-3.3-70b, and PostgreSQL.",
  keywords: ["data analyst", "AI", "SQL", "LangGraph", "Groq", "natural language", "business intelligence"],
  authors: [{ name: "Data Analyst Agent" }],
  robots: "noindex, nofollow",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[var(--background)] text-[var(--text)] antialiased">
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </body>
    </html>
  );
}
