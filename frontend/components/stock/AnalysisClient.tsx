"use client";

// AnalysisClient — fetches the simple Gemini analysis and renders HTML inline.
// KG button opens the knowledge graph page for this symbol.

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { Network, RefreshCw, AlertCircle, Loader2, Clock } from "lucide-react";
import { fetchSimpleAnalysis, type SimpleAnalysisResult } from "@/lib/api";
import DownloadReportButton from "@/components/stock/DownloadReportButton";

interface Props {
  symbol:  string;
  horizon: "short" | "medium" | "long";
  risk:    "conservative" | "moderate" | "aggressive";
  sector:  string;
}

const HORIZON_LABEL: Record<string, string> = {
  short:  "Short Term (1–3M)",
  medium: "Medium Term (3M–1Y)",
  long:   "Long Term (1–5Y)",
};

function LoadingState() {
  const steps = [
    "Fetching live market data…",
    "Building knowledge graph…",
    "Running AI analysis…",
    "Formatting report…",
  ];
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timings = [8000, 25000, 50000];
    const timers = timings.map((ms, i) =>
      setTimeout(() => setStep(i + 1), ms)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-10 flex flex-col items-center gap-5">
      <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
      <div className="text-center space-y-1">
        <p className="text-white font-medium">Generating AI Analysis</p>
        <p className="text-sm text-zinc-400">{steps[step]}</p>
      </div>
      <div className="flex gap-1.5 mt-1">
        {steps.map((_, i) => (
          <div
            key={i}
            className={`h-1 rounded-full transition-all duration-500 ${
              i <= step ? "w-8 bg-indigo-500" : "w-4 bg-zinc-700"
            }`}
          />
        ))}
      </div>
      <p className="text-xs text-zinc-600 flex items-center gap-1">
        <Clock className="w-3 h-3" />
        First-time analysis may take 2–4 minutes
      </p>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-10 text-center space-y-4">
      <AlertCircle className="w-10 h-10 text-zinc-600 mx-auto" />
      <p className="text-zinc-400 text-sm">
        Analysis pipeline failed. Check that the backend is running and try again.
      </p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm text-zinc-200 border border-zinc-700 transition-colors"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Try again
      </button>
    </div>
  );
}

export default function AnalysisClient({ symbol, horizon, risk, sector: _sector }: Props) {
  const [result, setResult]   = useState<SimpleAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed,  setFailed]  = useState(false);
  const sectorLabel = _sector.trim();
  const graphParams = new URLSearchParams({ horizon, risk });
  if (sectorLabel) graphParams.set("sector", sectorLabel);

  const run = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    const r = await fetchSimpleAnalysis(symbol, horizon, risk);
    if (r) { setResult(r); setFailed(false); }
    else   { setFailed(true); }
    setLoading(false);
  }, [symbol, horizon, risk]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void run();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [run]);

  const reportHtml = useMemo(() => {
    if (!result?.analysis_html) return "";
    if (typeof window === "undefined") return result.analysis_html;
    const doc = new DOMParser().parseFromString(result.analysis_html, "text/html");
    return doc.body.innerHTML || result.analysis_html;
  }, [result?.analysis_html]);

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Analysis</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            {symbol} · {HORIZON_LABEL[horizon]} · {risk.charAt(0).toUpperCase() + risk.slice(1)}
            {sectorLabel && ` · ${sectorLabel}`}
            {result?.cached && (
              <span className="ml-2 text-zinc-600">(cached)</span>
            )}
          </p>
        </div>

        {!loading && result && (
          <div className="flex items-center gap-2">
            <DownloadReportButton
              symbol={symbol}
              type="analysis"
              horizon={horizon}
              risk={risk}
            />
            <Link
              href={`/stock/${symbol}/knowledge?${graphParams.toString()}`}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 hover:border-zinc-500 text-zinc-400 hover:text-white transition-all text-sm"
              title="Open Knowledge Graph"
            >
              <Network className="w-4 h-4" />
              <span className="hidden sm:inline">Knowledge Graph</span>
            </Link>
          </div>
        )}
      </div>

      {loading ? (
        <LoadingState />
      ) : failed || !result ? (
        <ErrorState onRetry={run} />
      ) : (
        <article
          className="analysis-report w-full max-w-none text-zinc-300 leading-7
            [&_a]:text-indigo-300 [&_a]:break-words [&_a:hover]:underline
            [&_blockquote]:my-6 [&_blockquote]:border-l-2 [&_blockquote]:border-zinc-600 [&_blockquote]:pl-5 [&_blockquote]:text-zinc-400
            [&_code]:rounded-md [&_code]:border [&_code]:border-zinc-800 [&_code]:bg-zinc-950 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-violet-200
            [&_h1]:mb-8 [&_h1]:border-b [&_h1]:border-zinc-800 [&_h1]:pb-5 [&_h1]:text-3xl [&_h1]:font-bold [&_h1]:leading-tight [&_h1]:text-white
            [&_h2]:mb-4 [&_h2]:mt-12 [&_h2]:text-2xl [&_h2]:font-semibold [&_h2]:leading-tight [&_h2]:text-white
            [&_h3]:mb-3 [&_h3]:mt-8 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-zinc-100
            [&_h4]:mb-2 [&_h4]:mt-6 [&_h4]:font-semibold [&_h4]:text-zinc-100
            [&_hr]:my-10 [&_hr]:border-zinc-800
            [&_li]:my-2 [&_ol]:my-5 [&_ol]:pl-6 [&_p]:mb-5
            [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-zinc-800 [&_pre]:bg-zinc-950 [&_pre]:p-4
            [&_strong]:font-semibold [&_strong]:text-white
            [&_table]:my-6 [&_table]:block [&_table]:w-full [&_table]:overflow-x-auto [&_table]:border-collapse
            [&_td]:border [&_td]:border-zinc-800 [&_td]:p-3 [&_td]:text-zinc-300
            [&_th]:border [&_th]:border-zinc-800 [&_th]:bg-zinc-900 [&_th]:p-3 [&_th]:text-left [&_th]:text-zinc-100
            [&_ul]:my-5 [&_ul]:pl-6"
          dangerouslySetInnerHTML={{ __html: reportHtml }}
        />
      )}
    </div>
  );
}
