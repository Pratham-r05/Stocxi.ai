// SentimentSummary — per-source card (Reddit or Twitter)

import Badge from "@/components/ui/Badge";
import type { SentimentSource } from "@/lib/types";

interface SentimentSummaryProps {
  source: "reddit" | "twitter";
  data: SentimentSource;
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
  const structured = data.structured_summary;

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

      {/* Structured insights */}
      {structured ? (
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Overall View</p>
            <p className="text-sm text-zinc-300 leading-relaxed">{structured.overall_view}</p>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Investor Takeaway</p>
            <p className="text-sm text-zinc-200 leading-relaxed">{structured.investor_takeaway}</p>
          </div>

          {structured.key_themes.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Key Themes</p>
              <div className="flex flex-wrap gap-1.5">
                {structured.key_themes.map((theme) => (
                  <span
                    key={theme}
                    className="text-[11px] px-2 py-0.5 rounded-full border border-zinc-700 bg-zinc-800/50 text-zinc-300"
                  >
                    {theme}
                  </span>
                ))}
              </div>
            </div>
          )}

          {structured.bullish_points.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Bullish Cues</p>
              <ul className="space-y-1 text-sm text-emerald-300/90">
                {structured.bullish_points.slice(0, 2).map((point, idx) => (
                  <li key={`${point}-${idx}`} className="leading-relaxed">• {point}</li>
                ))}
              </ul>
            </div>
          )}

          {structured.risk_points.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Risks / Cautions</p>
              <ul className="space-y-1 text-sm text-red-300/90">
                {structured.risk_points.slice(0, 2).map((point, idx) => (
                  <li key={`${point}-${idx}`} className="leading-relaxed">• {point}</li>
                ))}
              </ul>
            </div>
          )}

          {structured.key_discussions.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">What People Are Discussing</p>
              <ul className="space-y-1 text-sm text-zinc-300">
                {structured.key_discussions.slice(0, 3).map((point, idx) => (
                  <li key={`${point}-${idx}`} className="leading-relaxed">• {point}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-300 leading-relaxed">{data.summary}</p>
      )}

      {/* Post count */}
      <p className="mt-2 text-xs text-zinc-500">
        Based on {data.posts.length} post{data.posts.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}
