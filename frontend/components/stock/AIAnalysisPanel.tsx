"use client";

// AIAnalysisPanel — AI verdict with icons, glow, and Framer Motion

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { DollarSign, BarChart2, Newspaper, MessageCircle, TrendingUp, AlertTriangle, Minus } from "lucide-react";
import Badge from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import Tabs from "@/components/ui/Tabs";
import { fetchAIAnalysis } from "@/lib/api";
import type { AIAnalysis } from "@/lib/types";

const RISK_TABS = [
  { id: "low", label: "Low Risk" },
  { id: "medium", label: "Medium Risk" },
  { id: "high", label: "High Risk" },
] as const;

const FACTOR_ICONS = {
  fundamentals: DollarSign,
  technicals: BarChart2,
  news: Newspaper,
  social: MessageCircle,
};

function VerdictIcon({ verdict }: { verdict: string }) {
  const v = verdict.toLowerCase();
  if (v === "buy") return <TrendingUp className="w-5 h-5 text-emerald-400" />;
  if (v === "avoid") return <AlertTriangle className="w-5 h-5 text-red-400" />;
  return <Minus className="w-5 h-5 text-zinc-400" />;
}

function verdictGlow(verdict: string): string {
  const v = verdict.toLowerCase();
  if (v === "buy") return "glow-signal-buy";
  if (v === "avoid") return "glow-signal-avoid";
  return "";
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex justify-center"><Skeleton className="h-12 w-32 mx-auto" /></div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-3">
      <p className="text-zinc-400 text-sm">AI analysis unavailable</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium transition-colors border border-zinc-700"
      >
        Retry
      </button>
    </div>
  );
}

export default function AIAnalysisPanel({ symbol }: { symbol: string }) {
  const [riskLevel, setRiskLevel] = useState<"low" | "medium" | "high">("medium");
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    const result = await fetchAIAnalysis(symbol, riskLevel);
    if (result) { setAnalysis(result); setFailed(false); }
    else setFailed(true);
    setLoading(false);
  }, [symbol, riskLevel]);

  useEffect(() => { load(); }, [load]);

  const formatDate = (iso: string) => {
    try { return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  };

  return (
    <section>
      <SectionHeader title="AI Analysis" />
      <Tabs
        tabs={RISK_TABS as unknown as { id: string; label: string }[]}
        active={riskLevel}
        onChange={(id) => setRiskLevel(id as "low" | "medium" | "high")}
        className="mb-4"
      />

      {loading ? (
        <LoadingSkeleton />
      ) : failed || !analysis ? (
        <ErrorState onRetry={load} />
      ) : (
        <div className="space-y-4">
          {/* Verdict card */}
          <motion.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className={`rounded-2xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-3 ${verdictGlow(analysis.final_verdict)}`}
          >
            <Badge signal={analysis.final_verdict} size="lg" />
            <p className={`text-sm flex items-center justify-center gap-1.5 ${analysis.risk_match ? "text-emerald-400" : "text-amber-400"}`}>
              {analysis.risk_match ? "✓" : "⚠"}
              {analysis.risk_match
                ? `Suitable for ${riskLevel} risk investors`
                : `May not suit ${riskLevel} risk profile`}
            </p>
          </motion.div>

          {/* Plain English */}
          <div className="flex gap-3 text-zinc-300 text-sm leading-relaxed bg-zinc-800/40 rounded-xl p-4 border border-zinc-700/40">
            <VerdictIcon verdict={analysis.final_verdict} />
            <p>{analysis.plain_english}</p>
          </div>

          {/* Breakdown grid */}
          <div className="grid grid-cols-2 gap-3">
            {(["fundamentals", "technicals", "news", "social"] as const).map((key) => {
              const item = analysis[key];
              const Icon = FACTOR_ICONS[key];
              return (
                <div key={key} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-1.5 mb-2">
                    <Icon className="w-3.5 h-3.5 text-zinc-500" />
                    <span className="text-xs text-zinc-500 capitalize">{key}</span>
                  </div>
                  <Badge signal={item.verdict} size="sm" />
                  <p className="mt-2 text-xs text-zinc-400 leading-relaxed">{item.summary}</p>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-600">Generated {formatDate(analysis.generated_at)}</p>
            <p className="text-xs text-zinc-700 italic">{analysis.disclaimer}</p>
          </div>
        </div>
      )}
    </section>
  );
}
