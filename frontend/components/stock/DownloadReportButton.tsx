"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, Loader2 } from "lucide-react";

interface DownloadReportButtonProps {
  symbol: string;
}

type ReportTier = "orbiter" | "stellar" | "apex";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const REPORT_OPTIONS: Array<{
  tier: ReportTier;
  title: string;
  subtitle: string;
}> = [
  {
    tier: "orbiter",
    title: "Orbiter (Beginner)",
    subtitle: "Friendly, simple, direct guidance.",
  },
  {
    tier: "stellar",
    title: "Stellar (Mediocre)",
    subtitle: "Balanced depth with key market context.",
  },
  {
    tier: "apex",
    title: "Apex (Pro)",
    subtitle: "Technical expert-level language and detail.",
  },
];

export default function DownloadReportButton({ symbol }: DownloadReportButtonProps) {
  const [open, setOpen] = useState(false);
  const [loadingTier, setLoadingTier] = useState<ReportTier | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function onEsc(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEsc);
    };
  }, []);

  function triggerDownload(tier: ReportTier) {
    const encoded = encodeURIComponent(symbol.toUpperCase());
    const url = `${API_BASE}/api/v1/analysis/${encoded}/report?tier=${tier}&risk_level=medium`;

    setLoadingTier(tier);
    setOpen(false);

    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    window.setTimeout(() => setLoadingTier(null), 1200);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-900/80 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:border-zinc-600 hover:bg-zinc-800 transition-colors"
      >
        {loadingTier ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
        <span className="hidden sm:inline">Download Report</span>
        <span className="sm:hidden">Report</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : "rotate-0"}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-zinc-700 bg-zinc-950 shadow-2xl shadow-black/60 overflow-hidden z-[70]">
          <div className="border-b border-zinc-800 px-3 py-2.5">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 font-semibold">Choose Report Depth</p>
            <p className="text-[11px] text-zinc-400 mt-0.5">1-page AI PDF using all major stock data sections.</p>
          </div>

          <div className="p-1.5 space-y-1">
            {REPORT_OPTIONS.map((option) => (
              <button
                key={option.tier}
                type="button"
                onClick={() => triggerDownload(option.tier)}
                className="w-full text-left rounded-lg border border-transparent hover:border-zinc-700 hover:bg-zinc-900 px-3 py-2.5 transition-colors"
              >
                <p className="text-sm font-semibold text-zinc-100">{option.title}</p>
                <p className="text-xs text-zinc-400 mt-0.5">{option.subtitle}</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
