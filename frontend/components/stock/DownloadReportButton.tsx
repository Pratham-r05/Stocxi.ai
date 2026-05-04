"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

interface DownloadReportButtonProps {
  symbol: string;
  type: "analysis" | "graph";
  horizon?: "short" | "medium" | "long";
  risk?: "conservative" | "moderate" | "aggressive";
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function DownloadReportButton({
  symbol,
  type,
  horizon = "short",
  risk = "moderate",
}: DownloadReportButtonProps) {
  const [loading, setLoading] = useState(false);

  function triggerDownload() {
    const encoded = encodeURIComponent(symbol.toUpperCase());
    const params = new URLSearchParams({ horizon, risk });
    const path = type === "analysis"
      ? `/api/v2/analysis/${encoded}/report?${params.toString()}`
      : `/api/v2/analysis/${encoded}/graph/report`;

    setLoading(true);

    const a = document.createElement("a");
    a.href = `${API_BASE}${path}`;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    window.setTimeout(() => setLoading(false), 1200);
  }

  return (
    <button
      type="button"
      onClick={triggerDownload}
      disabled={loading}
      className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-900/80 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:border-zinc-600 hover:bg-zinc-800 disabled:opacity-60 transition-colors"
    >
      {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      <span className="hidden sm:inline">Download</span>
      <span className="sm:hidden">PDF</span>
    </button>
  );
}
