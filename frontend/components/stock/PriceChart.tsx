"use client";

// PriceChart — recharts AreaChart with white line, period tabs

import { useEffect, useState } from "react";
import { fetchHistory } from "@/lib/api";
import type { HistoryPoint } from "@/lib/types";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/Skeleton";

type Period = "1mo" | "3mo" | "6mo" | "1y";

const PERIODS: { id: Period; label: string }[] = [
  { id: "1mo", label: "1M" },
  { id: "3mo", label: "3M" },
  { id: "6mo", label: "6M" },
  { id: "1y", label: "1Y" },
];

function normalizeHistory(points: HistoryPoint[]): HistoryPoint[] {
  return points
    .filter((p) => p?.date && Number.isFinite(p?.close) && p.close > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
}

function formatDate(dateStr: string, period: Period): string {
  try {
    const d = new Date(dateStr);
    if (period === "1mo") return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  } catch {
    return dateStr;
  }
}

function formatPriceTick(v: number): string {
  if (Math.abs(v) >= 1_00_000) return `₹${(v / 1_00_000).toFixed(1)}L`;
  if (Math.abs(v) >= 1_000) return `₹${(v / 1_000).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 shadow-xl text-xs">
      <div className="text-zinc-500 mb-0.5">{label}</div>
      <div className="font-mono font-semibold text-white">
        ₹{payload[0].value.toLocaleString("en-IN")}
      </div>
    </div>
  );
}

export default function PriceChart({ symbol }: { symbol: string }) {
  const [period, setPeriod] = useState<Period>("1y");
  const [data, setData] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [usedFallback, setUsedFallback] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);

    const load = async () => {
      try {
        const primary = await fetchHistory(symbol, period);
        let closes = normalizeHistory(primary?.closes ?? []);
        let fallback = false;

        // For thin/missing short windows, fallback to 1Y to keep chart usable.
        if (closes.length < 2 && period !== "1y") {
          const backup = await fetchHistory(symbol, "1y");
          const backupCloses = normalizeHistory(backup?.closes ?? []);
          if (backupCloses.length >= 2) {
            closes = backupCloses;
            fallback = true;
          }
        }

        if (!active) return;
        setData(closes);
        setUsedFallback(fallback);
      } catch {
        if (!active) return;
        setData([]);
        setUsedFallback(false);
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, [symbol, period]);

  // Thin data to max 120 points
  const thinned =
    data.length > 120
      ? data.filter((_, i) => i % Math.ceil(data.length / 120) === 0)
      : data;

  const chartData = thinned.map((p) => ({
    date: formatDate(p.date, period),
    close: p.close,
  }));

  // Period change %
  const first = data[0]?.close;
  const last = data[data.length - 1]?.close;
  const change = first && last ? ((last - first) / first) * 100 : null;

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Price History
          </span>
          {usedFallback && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-zinc-700 bg-zinc-800/50 text-zinc-400">
              showing 1Y
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {change !== null && (
            <span
              className={`text-xs font-mono font-semibold px-2 py-0.5 rounded-full ${
                change >= 0
                  ? "text-emerald-400 bg-emerald-500/10"
                  : "text-red-400 bg-red-500/10"
              }`}
            >
              {change >= 0 ? "+" : ""}
              {change.toFixed(2)}%
            </span>
          )}
          <div className="flex bg-zinc-800/60 rounded-lg p-0.5 gap-0.5">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                onClick={() => setPeriod(p.id)}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors font-medium ${
                  period === p.id
                    ? "bg-zinc-700 text-white"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-zinc-600 text-sm">
          No price history available for {symbol}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#a1a1aa" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#a1a1aa" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fill: "#52525b", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={26}
              tickMargin={8}
            />
            <YAxis
              tick={{ fill: "#52525b", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={56}
              tickFormatter={formatPriceTick}
              tickCount={5}
              domain={["auto", "auto"]}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#3f3f46", strokeWidth: 1 }} />
            <Area
              type="monotone"
              dataKey="close"
              stroke="#a1a1aa"
              strokeWidth={1.75}
              fill="url(#priceGradient)"
              dot={false}
              activeDot={{ r: 4, fill: "#d4d4d8", strokeWidth: 0 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
