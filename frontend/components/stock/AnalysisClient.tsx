"use client";

// AnalysisClient — fetches the simple Gemini analysis and renders HTML inline.
// KG button opens the knowledge graph page for this symbol.

import { useState, useEffect } from "react";
import Link from "next/link";
import { Network, RefreshCw, AlertCircle, Loader2, Clock, ShieldCheck, TrendingUp, TrendingDown } from "lucide-react";
import { fetchAIAnalysisV2 } from "@/lib/api";
import type { V2AnalysisResult } from "@/lib/types";
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
  const [result, setResult]   = useState<V2AnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed,  setFailed]  = useState(false);
  const sectorLabel = _sector.trim();
  const graphParams = new URLSearchParams({ horizon, risk });
  if (sectorLabel) graphParams.set("sector", sectorLabel);

  async function run() {
    setLoading(true);
    setFailed(false);
    const r = await fetchAIAnalysisV2(symbol, horizon, risk, sectorLabel);
    if (r) { setResult(r); setFailed(false); }
    else   { setFailed(true); }
    setLoading(false);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const load = async () => {
        setLoading(true);
        setFailed(false);
        const r = await fetchAIAnalysisV2(symbol, horizon, risk, sectorLabel);
        if (r) { setResult(r); setFailed(false); }
        else   { setFailed(true); }
        setLoading(false);
      };
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [symbol, horizon, risk, sectorLabel]);

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Analysis</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            {symbol} · {HORIZON_LABEL[horizon]} · {risk.charAt(0).toUpperCase() + risk.slice(1)}
            {sectorLabel && ` · ${sectorLabel}`}
            {result?.cache_hit && (
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
        <article className="space-y-6">
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-zinc-700 px-3 py-1 text-xs font-medium uppercase text-zinc-300">
                {result.overall_signal}
              </span>
              {result.calibrated_confidence != null && (
                <span className="text-xs text-zinc-500">
                  Confidence {(result.calibrated_confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <h2 className="mt-5 text-2xl font-semibold text-white">What the Data Suggests</h2>
            <p className="mt-3 text-sm leading-7 text-zinc-300">{result.what_data_suggests}</p>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <section className="rounded-2xl border border-emerald-900/60 bg-emerald-950/20 p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-200">
                <TrendingUp className="h-4 w-4" />
                Signals In Favor
              </h3>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-zinc-300">
                {result.signals_in_favor.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </section>

            <section className="rounded-2xl border border-red-900/60 bg-red-950/20 p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-red-200">
                <TrendingDown className="h-4 w-4" />
                Signals Against
              </h3>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-zinc-300">
                {result.signals_against.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </section>
          </div>

          <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
              <ShieldCheck className="h-4 w-4 text-indigo-300" />
              Data Disclosure
            </h3>
            <p className="mt-3 text-sm leading-6 text-zinc-400">{result.data_disclosure}</p>
            <p className="mt-4 text-xs leading-5 text-zinc-600">{result.disclaimer}</p>
          </section>
        </article>
      )}
    </div>
  );
}
