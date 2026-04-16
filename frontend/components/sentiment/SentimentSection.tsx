"use client";

// SentimentSection — fetches + displays Reddit + Twitter sentiment

import { useEffect, useState } from "react";
import { fetchSentiment } from "@/lib/api";
import type { SentimentData } from "@/lib/types";
import Badge from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import SentimentSummary from "./SentimentSummary";
import SentimentChart from "./SentimentChart";

interface SentimentSectionProps {
  symbol: string;
}

function CombinedScoreBar({ score, signal }: { score: number; signal: string }) {
  const pct = ((score + 1) / 2) * 100;
  const s = signal.toLowerCase();
  const fillColour =
    s === "buy" ? "bg-emerald-500" : s === "avoid" ? "bg-red-500" : "bg-zinc-500";

  return (
    <div className="relative h-2 w-full rounded-full bg-zinc-700 mt-1">
      <div
        className={`absolute left-0 top-0 h-full rounded-full ${fillColour}`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
      <div
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-white shadow border border-zinc-400"
        style={{ left: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-4/6" />
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-4/6" />
        </div>
      </div>
      <Skeleton className="h-40 w-full rounded-xl" />
    </div>
  );
}

export default function SentimentSection({ symbol }: SentimentSectionProps) {
  const [data, setData] = useState<SentimentData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchSentiment(symbol).then((result) => {
      if (result) setData(result);
      else setError(true);
      setLoading(false);
    });
  }, [symbol]);

  return (
    <section>
      <SectionHeader title="Social Sentiment" />

      {loading && <LoadingSkeleton />}

      {!loading && (error || !data) && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center text-zinc-500 text-sm">
          Social sentiment data unavailable for {symbol}
        </div>
      )}

      {!loading && data && (
        <div className="space-y-4">
          {/* Combined signal bar */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 flex flex-col items-center gap-3">
            <Badge signal={data.combined_signal} label={data.combined_signal} size="lg" />
            <div className="text-sm text-zinc-400">
              Combined Score:{" "}
              <span className="font-mono font-semibold text-zinc-200">
                {data.combined_sentiment_score >= 0 ? "+" : ""}
                {data.combined_sentiment_score.toFixed(2)}
              </span>
            </div>
            <div className="w-full max-w-sm">
              <CombinedScoreBar
                score={data.combined_sentiment_score}
                signal={data.combined_signal}
              />
              <div className="flex justify-between text-xs text-zinc-600 mt-1">
                <span>−1.0</span>
                <span>0</span>
                <span>+1.0</span>
              </div>
            </div>
          </div>

          {/* Per-source cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SentimentSummary source="reddit" data={data.reddit} />
            <SentimentSummary source="twitter" data={data.twitter} />
          </div>

          {/* 7-day chart */}
          {data.chart_data && data.chart_data.length > 1 && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="text-xs text-zinc-500 font-medium mb-3">7-Day Sentiment Trend</div>
              <SentimentChart data={data.chart_data} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
