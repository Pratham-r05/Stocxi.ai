"use client";

// AIAnalysisLauncher — button beside Financials tab that opens a modal
// to configure horizon + risk, then kicks off the analysis pipeline
// and navigates to the analysis result page.

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Brain, X, ChevronRight, Loader2 } from "lucide-react";

const HORIZONS = [
  { id: "short",  label: "Short Term",  desc: "1 – 3 months" },
  { id: "medium", label: "Medium Term", desc: "3 months – 1 year" },
  { id: "long",   label: "Long Term",   desc: "1 – 5 years" },
] as const;

const RISKS = [
  { id: "conservative", label: "Conservative", desc: "Low risk tolerance" },
  { id: "moderate",     label: "Moderate",     desc: "Balanced risk/reward" },
  { id: "aggressive",   label: "Aggressive",   desc: "High growth focus" },
] as const;

type Horizon = "short" | "medium" | "long";
type Risk    = "conservative" | "moderate" | "aggressive";

export default function AIAnalysisLauncher({
  symbol,
  sector = "",
}: {
  symbol: string;
  sector?: string;
}) {
  const router = useRouter();
  const [open, setOpen]         = useState(false);
  const [horizon, setHorizon]   = useState<Horizon>("short");
  const [risk, setRisk]         = useState<Risk>("moderate");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const handleProceed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Trigger the pipeline — the analysis page will poll / stream
      const params = new URLSearchParams({ horizon, risk });
      if (sector) params.set("sector", sector);
      router.push(`/stock/${symbol}/analysis?${params.toString()}`);
    } catch {
      setError("Failed to start analysis. Please try again.");
      setLoading(false);
    }
  }, [symbol, horizon, risk, sector, router]);

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors whitespace-nowrap"
      >
        <Brain className="w-3.5 h-3.5" />
        AI Analysis
      </button>

      {/* Modal overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => !loading && setOpen(false)}
          />

          {/* Panel */}
          <div className="relative z-10 w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-indigo-400" />
                <h2 className="text-base font-semibold text-white">Configure Analysis</h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                disabled={loading}
                className="text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-zinc-400">
              Stocxi will fetch live data, build a knowledge graph, and generate an AI analysis for{" "}
              <span className="text-white font-medium">{symbol}</span>.
            </p>

            {/* Horizon */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Horizon</p>
              <div className="grid grid-cols-3 gap-2">
                {HORIZONS.map((h) => (
                  <button
                    key={h.id}
                    onClick={() => setHorizon(h.id)}
                    className={`rounded-xl border p-3 text-left transition-colors ${
                      horizon === h.id
                        ? "border-indigo-500 bg-indigo-950/60 text-white"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600"
                    }`}
                  >
                    <p className="text-sm font-medium">{h.label}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{h.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Risk */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Risk Appetite</p>
              <div className="grid grid-cols-3 gap-2">
                {RISKS.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setRisk(r.id)}
                    className={`rounded-xl border p-3 text-left transition-colors ${
                      risk === r.id
                        ? "border-indigo-500 bg-indigo-950/60 text-white"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600"
                    }`}
                  >
                    <p className="text-xs font-medium">{r.label}</p>
                    <p className="text-[10px] text-zinc-500 mt-0.5 leading-tight">{r.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <p className="text-xs text-red-400 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            {/* Proceed */}
            <button
              onClick={handleProceed}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium py-2.5 transition-colors"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Starting analysis…
                </>
              ) : (
                <>
                  Proceed
                  <ChevronRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
