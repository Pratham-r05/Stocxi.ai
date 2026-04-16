// SentimentSummary — per-source card (Reddit or Twitter)

import Badge from "@/components/ui/Badge";

interface SentimentSummaryProps {
  source: "reddit" | "twitter";
  data: {
    summary: string;
    sentiment: string;
    sentiment_score: number;
    signal: "BUY" | "HOLD" | "AVOID";
    posts: unknown[];
    fetched_at: string;
  };
}

function ScoreBar({ score, signal }: { score: number; signal: string }) {
  // Map score -1..1 to 0..100%
  const fillPct = ((score + 1) / 2) * 100;
  const s = signal.toLowerCase();
  const fillColour =
    s === "buy" ? "bg-emerald-500" : s === "avoid" ? "bg-red-500" : "bg-zinc-500";

  return (
    <div className="mt-2 relative h-1.5 w-full rounded-full bg-zinc-700">
      <div
        className={`absolute left-0 top-0 h-full rounded-full ${fillColour}`}
        style={{ width: `${Math.min(100, Math.max(0, fillPct))}%` }}
      />
    </div>
  );
}

export default function SentimentSummary({ source, data }: SentimentSummaryProps) {
  const isReddit = source === "reddit";
  const sourceLabel = isReddit ? "Reddit" : "Twitter / X";
  const sourceSymbol = isReddit ? "r/" : "𝕏";
  const sourceLabelColour = isReddit ? "text-orange-400" : "text-sky-400";

  const scoreSign = data.sentiment_score >= 0 ? "+" : "";
  const scoreStr = `${scoreSign}${data.sentiment_score.toFixed(2)}`;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className={`flex items-center gap-1.5 font-semibold text-sm ${sourceLabelColour}`}>
          <span className="font-mono text-xs">{sourceSymbol}</span>
          <span>{sourceLabel}</span>
        </div>
        <Badge signal={data.signal} label={data.signal} size="sm" />
      </div>

      {/* Score row */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400">{data.sentiment}</span>
        <span className="font-mono font-semibold text-zinc-200">{scoreStr}</span>
      </div>
      <ScoreBar score={data.sentiment_score} signal={data.signal} />

      {/* Summary */}
      <p className="mt-3 text-sm text-zinc-300 leading-relaxed">{data.summary}</p>

      {/* Post count */}
      <p className="mt-2 text-xs text-zinc-500">
        Based on {data.posts.length} post{data.posts.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}
