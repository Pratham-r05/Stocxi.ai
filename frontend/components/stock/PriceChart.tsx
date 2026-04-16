"use client";

// PriceChart — ComposedChart with price line + volume bars, 5 period tabs with % changes

import { useEffect, useState, useMemo } from "react";
import { fetchHistory } from "@/lib/api";
import type { HistoryPoint } from "@/lib/types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/Skeleton";

type Period = "1d" | "1w" | "1mo" | "6mo" | "1y";

interface ChartPoint {
  date: string;    // formatted label for X-axis
  close: number;
  rawDate: string; // original date string from backend
}

const PERIODS: { id: Period; label: string }[] = [
  { id: "1d",  label: "1D"  },
  { id: "1w",  label: "1W"  },
  { id: "1mo", label: "1M"  },
  { id: "6mo", label: "6M"  },
  { id: "1y",  label: "1Y"  },
];

function calcChange(points: HistoryPoint[]): number | null {
  if (points.length < 2) return null;
  const first = points[0].close;
  const last  = points[points.length - 1].close;
  if (!first) return null;
  return ((last - first) / first) * 100;
}

function isIntradayDate(dateStr: string): boolean {
  // Backend returns "YYYY-MM-DD HH:MM" for intraday, "YYYY-MM-DD" for daily
  return dateStr.length > 10;
}

function formatDate(dateStr: string, period: Period): string {
  try {
    const d = new Date(dateStr);
    if (period === "1d") {
      // True intraday data → show time; daily fallback → show short date
      if (isIntradayDate(dateStr)) {
        return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
      }
      return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    }
    if (period === "1w")  return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric" });
    if (period === "1mo") return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  } catch {
    return dateStr.slice(0, 10);
  }
}

function formatTooltipDate(rawDate: string, period: Period): string {
  try {
    const d = new Date(rawDate);
    if (period === "1d" && isIntradayDate(rawDate)) {
      return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    }
    if (period === "1d" || period === "1w") {
      return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    }
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return rawDate.slice(0, 10);
  }
}

function formatPriceTick(v: number): string {
  if (Math.abs(v) >= 1_00_000) return `₹${(v / 1_00_000).toFixed(1)}L`;
  if (Math.abs(v) >= 1_000)    return `₹${(v / 1_000).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

function CustomTooltip({
  active,
  payload,
  period,
}: {
  active?: boolean;
  payload?: Array<{ value: number; dataKey: string; payload: ChartPoint }>;
  label?: string;
  period: Period;
}) {
  if (!active || !payload?.length) return null;
  const priceEntry = payload.find((p) => p.dataKey === "close");
  const rawDate = payload[0]?.payload?.rawDate;

  return (
    <div className="bg-zinc-900 border border-zinc-700/80 rounded-xl px-4 py-3 shadow-2xl text-xs min-w-[150px]">
      {rawDate && (
        <div className="text-zinc-500 mb-2 text-[11px] font-medium">
          {formatTooltipDate(rawDate, period)}
        </div>
      )}
      {priceEntry && (
        <div className="font-mono font-bold text-white text-sm">
          ₹{priceEntry.value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}

export default function PriceChart({
  symbol,
  defaultChangePercent,
}: {
  symbol: string;
  defaultChangePercent?: number | null;
}) {
  const [period, setPeriod]     = useState<Period>("1y");
  const [dataMap, setDataMap]   = useState<Partial<Record<Period, HistoryPoint[]>>>({});
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);

    const load = async () => {
      // Fetch 1Y first to show chart ASAP
      try {
        const d1y = await fetchHistory(symbol, "1y");
        if (active && d1y?.closes?.length) {
          setDataMap((prev) => ({ ...prev, "1y": d1y.closes }));
          setLoading(false);
        }
      } catch { /**/ }

      // Fetch remaining periods in parallel
      const rest: Period[] = ["1d", "1w", "1mo", "6mo"];
      const results = await Promise.allSettled(
        rest.map((p) => fetchHistory(symbol, p))
      );
      if (!active) return;

      const updates: Partial<Record<Period, HistoryPoint[]>> = {};
      rest.forEach((p, i) => {
        const r = results[i];
        if (r.status === "fulfilled" && r.value?.closes?.length) {
          updates[p] = r.value.closes;
        }
      });
      setDataMap((prev) => ({ ...prev, ...updates }));
      if (active) setLoading(false);
    };

    void load();
    return () => { active = false; };
  }, [symbol]);

  const currentData = dataMap[period] ?? [];

  const change = useMemo(() => {
    if (period === "1d" && !dataMap["1d"] && defaultChangePercent !== undefined) {
      return defaultChangePercent ?? null;
    }
    return calcChange(currentData);
  }, [period, currentData, dataMap, defaultChangePercent]);

  const strokeColor = change === null ? "#71717a" : change >= 0 ? "#10b981" : "#ef4444";
  const gradientId  = `priceGrad_${symbol}`;

  const thinned = useMemo(() => {
    if (currentData.length <= 150) return currentData;
    const step = Math.ceil(currentData.length / 150);
    return currentData.filter((_, i) => i % step === 0 || i === currentData.length - 1);
  }, [currentData]);

  const chartData: ChartPoint[] = thinned.map((p) => ({
    date:    formatDate(p.date, period),
    close:   p.close,
    rawDate: p.date,
  }));

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      {/* Period tabs */}
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        {PERIODS.map((p) => {
          const pData   = dataMap[p.id];
          const pChange = p.id === "1d" && !dataMap["1d"]
            ? (defaultChangePercent ?? null)
            : pData ? calcChange(pData) : null;
          const isActive = period === p.id;
          const isPos = pChange !== null && pChange >= 0;
          const isNeg = pChange !== null && pChange < 0;

          return (
            <button
              key={p.id}
              onClick={() => setPeriod(p.id)}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
                transition-all duration-150
                ${isActive
                  ? isPos
                    ? "bg-emerald-500/15 border border-emerald-500/30 text-emerald-400"
                    : isNeg
                      ? "bg-red-500/15 border border-red-500/30 text-red-400"
                      : "bg-zinc-700 border border-zinc-600 text-white"
                  : "border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                }
              `}
            >
              <span>{p.label}</span>
              {pChange !== null && (
                <span className={isPos ? "text-emerald-400" : "text-red-400"}>
                  {isPos ? "+" : ""}{pChange.toFixed(2)}%
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Chart body */}
      {loading ? (
        <Skeleton className="h-[280px] w-full rounded-xl" />
      ) : currentData.length === 0 ? (
        <div className="h-[280px] flex items-center justify-center text-zinc-600 text-sm">
          No price history available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={strokeColor} stopOpacity={0.12} />
                <stop offset="100%" stopColor={strokeColor} stopOpacity={0}    />
              </linearGradient>
            </defs>

            <XAxis
              dataKey="date"
              tick={{ fill: "#52525b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              minTickGap={36}
              tickMargin={8}
            />
            <YAxis
              tick={{ fill: "#52525b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={60}
              tickFormatter={formatPriceTick}
              tickCount={5}
              domain={["auto", "auto"]}
            />

            <Tooltip
              content={<CustomTooltip period={period} />}
              cursor={{ stroke: "#3f3f46", strokeWidth: 1, strokeDasharray: "4 3" }}
            />

            <Line
              type="monotone"
              dataKey="close"
              stroke={strokeColor}
              strokeWidth={1.75}
              dot={false}
              activeDot={{ r: 4, fill: strokeColor, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
