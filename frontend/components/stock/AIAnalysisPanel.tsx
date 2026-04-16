"use client";

import { useEffect, useState, useCallback } from "react";
import Badge from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import Tabs from "@/components/ui/Tabs";
import { fetchAIAnalysis } from "@/lib/api";
import type { AIAnalysis } from "@/lib/types";

interface AIAnalysisPanelProps {
  symbol: string;
}

const RISK_TABS = [
  { id: "low", label: "Low Risk" },
  { id: "medium", label: "Medium Risk" },
  { id: "high", label: "High Risk" },
] as const;

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {/* Verdict placeholder */}
      <div className="flex justify-center">
        <Skeleton className="h-12 w-32 mx-auto" />
      </div>
      {/* Plain English placeholder */}
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
      {/* 4 breakdown cards */}
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
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
        className="px-4 py-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm font-medium transition-colors"
      >
        Retry
      </button>
    </div>
  );
}

export default function AIAnalysisPanel({ symbol }: AIAnalysisPanelProps) {
  const [riskLevel, setRiskLevel] = useState<"low" | "medium" | "high">("medium");
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    const result = await fetchAIAnalysis(symbol, riskLevel);
    if (result) {
      setAnalysis(result);
      setFailed(false);
    } else {
      setFailed(true);
    }
    setLoading(false);
  }, [symbol, riskLevel]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRiskChange = (id: string) => {
    setRiskLevel(id as "low" | "medium" | "high");
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch {
      return iso;
    }
  };

  return (
    <section>
      <SectionHeader title="AI Analysis" />

      <Tabs
        tabs={RISK_TABS as unknown as { id: string; label: string }[]}
        active={riskLevel}
        onChange={handleRiskChange}
        className="mb-4"
      />

      {loading ? (
        <LoadingSkeleton />
      ) : failed || !analysis ? (
        <ErrorState onRetry={load} />
      ) : (
        <div className="space-y-4">

          {/* Final Verdict */}
          <div className="text-center space-y-2">
            <Badge signal={analysis.final_verdict} size="lg" />
            <p className={`text-sm ${analysis.risk_match ? "text-emerald-400" : "text-amber-400"}`}>
              {analysis.risk_match
                ? `✓ Suitable for ${riskLevel} risk investors`
                : `⚠ May not suit ${riskLevel} risk profile`}
            </p>
          </div>

          {/* Plain English summary */}
          <div className="text-zinc-300 text-sm leading-relaxed bg-zinc-800/50 rounded-xl p-4 border border-zinc-700/50">
            {analysis.plain_english}
          </div>

          {/* Breakdown grid */}
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                { key: "fundamentals", label: "Fundamentals" },
                { key: "technicals", label: "Technicals" },
                { key: "news", label: "News" },
                { key: "social", label: "Social" },
              ] as const
            ).map(({ key, label }) => {
              const item = analysis[key];
              return (
                <div key={key} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs text-zinc-500">{label}</span>
                    <Badge signal={item.verdict} size="sm" />
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{item.summary}</p>
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
