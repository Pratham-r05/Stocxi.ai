"use client";

// SentimentSection — Reddit + Twitter sentiment with recharts donut chart

import { useEffect, useRef, useState } from "react";
import { fetchSentiment } from "@/lib/api";
import type { SentimentData } from "@/lib/types";
import { PieChart, Pie, Cell } from "recharts";
import Badge from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import SentimentSummary from "./SentimentSummary";

interface SentimentSectionProps {
  symbol: string;
}

function CombinedScoreBar({ score, signal }: { score: number; signal: string }) {
  const pct = ((score + 1) / 2) * 100;
  const s = signal.toLowerCase();
  const fillColour = s === "buy" ? "bg-emerald-500" : s === "avoid" ? "bg-red-500" : "bg-zinc-500";
  return (
    <div className="relative h-1.5 w-full rounded-full bg-zinc-700 mt-1">
      <div
        className={`absolute left-0 top-0 h-full rounded-full ${fillColour}`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
      <div
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-white shadow"
        style={{ left: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

function SentimentDonut({ redditScore, twitterScore }: { redditScore: number; twitterScore: number }) {
  const donutRef = useRef<HTMLDivElement | null>(null);
  const [canRenderDonut, setCanRenderDonut] = useState(false);
  const [donutSize, setDonutSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = donutRef.current;
    if (!el) return;

    const updateSizeState = () => {
      const { width, height } = el.getBoundingClientRect();
      const nextWidth = Math.max(0, Math.floor(width));
      const nextHeight = Math.max(0, Math.floor(height));
      setDonutSize({ width: nextWidth, height: nextHeight });
      setCanRenderDonut(nextWidth > 0 && nextHeight > 0);
    };

    updateSizeState();
    const observer = new ResizeObserver(updateSizeState);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Use absolute values for donut sizing; labels show actual scores
  const rAbs = Math.max(0.01, Math.abs(redditScore));
  const tAbs = Math.max(0.01, Math.abs(twitterScore));
  const total = rAbs + tAbs;
  const combined = ((redditScore + twitterScore) / 2).toFixed(2);
  const sign = parseFloat(combined) >= 0 ? "+" : "";

  const pieData = [
    { name: "Reddit", value: (rAbs / total) * 100 },
    { name: "Twitter", value: (tAbs / total) * 100 },
  ];

  return (
    <div className="flex flex-col items-center">
      <div ref={donutRef} className="relative w-28 h-28 min-w-[112px] min-h-[112px]">
        {canRenderDonut ? (
          <PieChart width={donutSize.width} height={donutSize.height}>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={38}
              outerRadius={52}
              startAngle={90}
              endAngle={-270}
              dataKey="value"
              strokeWidth={0}
            >
              <Cell fill="#d4d4d8" />
              <Cell fill="#52525b" />
            </Pie>
          </PieChart>
        ) : (
          <Skeleton className="h-full w-full rounded-full" />
        )}
        {/* Center label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="font-mono font-bold text-white text-sm leading-none">
            {sign}{combined}
          </span>
          <span className="text-zinc-600 text-[10px] mt-0.5">combined</span>
        </div>
      </div>
      <div className="flex items-center gap-4 mt-2 text-[11px] text-zinc-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-zinc-300 inline-block" />Reddit
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-zinc-600 inline-block" />Twitter/X
        </span>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <Skeleton className="h-4 w-24 mb-3" />
        <Skeleton className="h-28 w-28 rounded-full mx-auto mb-3" />
        <Skeleton className="h-2 w-full rounded-full" />
      </div>
      <div className="grid grid-cols-1 gap-4">
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
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
          {/* Combined card with donut */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 flex flex-col items-center gap-4">
            <Badge signal={data.combined_signal} label={data.combined_signal} size="lg" />
            <SentimentDonut
              redditScore={data.reddit.sentiment_score}
              twitterScore={data.twitter.sentiment_score}
            />
            <div className="w-full max-w-xs">
              <CombinedScoreBar score={data.combined_sentiment_score} signal={data.combined_signal} />
              <div className="flex justify-between text-[10px] text-zinc-600 mt-1">
                <span>−1.0</span>
                <span>0</span>
                <span>+1.0</span>
              </div>
            </div>
          </div>

          {/* Per-source cards */}
          <SentimentSummary source="reddit" data={data.reddit} />
          <SentimentSummary source="twitter" data={data.twitter} />

        </div>
      )}
    </section>
  );
}
