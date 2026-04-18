"use client";

// PriceChart — ComposedChart with price line + volume bars, 5 period tabs with % changes

import { useEffect, useState, useMemo, useRef } from "react";
import { fetchHistory } from "@/lib/api";
import type { HistoryPoint } from "@/lib/types";
import {
  ComposedChart,
  CartesianGrid,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { Skeleton } from "@/components/ui/Skeleton";

type Period = "1d" | "1w" | "1mo" | "6mo" | "1y";

interface ChartPoint {
  date: string;    // formatted label for X-axis
  close: number;
  volume: number;
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

function parseChartDate(dateStr: string): Date {
  // Safari can fail on "YYYY-MM-DD HH:MM"; normalize to ISO-like format first.
  const normalized = dateStr.includes(" ") ? dateStr.replace(" ", "T") : dateStr;
  return new Date(normalized);
}

function formatDate(dateStr: string, period: Period): string {
  try {
    const d = parseChartDate(dateStr);
    if (period === "1d") {
      // True intraday data → show time; daily fallback → show short date
      if (isIntradayDate(dateStr)) {
        return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
      }
      return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    }
    if (period === "1w") {
      if (isIntradayDate(dateStr)) {
        return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
      }
      return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric" });
    }
    if (period === "1mo") {
      if (isIntradayDate(dateStr)) {
        const day = d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
        const half = d.getHours() < 12 ? "AM" : "PM";
        return `${day} ${half}`;
      }
      return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    }
    return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  } catch {
    return dateStr.slice(0, 10);
  }
}

function formatTooltipDate(rawDate: string, period: Period): string {
  try {
    const d = parseChartDate(rawDate);
    if (period === "1d" && isIntradayDate(rawDate)) {
      return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    }
    if (period === "1w" && isIntradayDate(rawDate)) {
      return d.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }) + " " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    }
    if (period === "1mo" && isIntradayDate(rawDate)) {
      return d.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }) + " " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
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
  const abs = Math.abs(v);
  if (abs >= 1_00_00_000) return `₹${(v / 1_00_00_000).toFixed(1)}Cr`;
  if (abs >= 1_00_000) return `₹${(v / 1_00_000).toFixed(1)}L`;
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
}

function formatVolumeTick(v: number): string {
  if (v >= 1_00_00_000) return `${(v / 1_00_00_000).toFixed(1)}Cr`;
  if (v >= 1_00_000) return `${(v / 1_00_000).toFixed(1)}L`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return `${Math.round(v)}`;
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
  const volumeEntry = payload.find((p) => p.dataKey === "volume");
  const rawDate = payload[0]?.payload?.rawDate;
  const volumeValue =
    typeof volumeEntry?.payload?.volume === "number"
      ? volumeEntry.payload.volume
      : volumeEntry?.value;

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
      {typeof volumeValue === "number" && volumeValue > 0 && (
        <div className="mt-1 text-[11px] text-zinc-400 font-medium">
          Vol {Math.round(volumeValue).toLocaleString("en-IN")} ({formatVolumeTick(volumeValue)})
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
  const [period, setPeriod]     = useState<Period>("1d");
  const [dataMap, setDataMap]   = useState<Partial<Record<Period, HistoryPoint[]>>>({});
  const [loading, setLoading]   = useState(true);
  const [failed, setFailed]     = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const chartBodyRef = useRef<HTMLDivElement | null>(null);
  const [canRenderChart, setCanRenderChart] = useState(false);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = chartBodyRef.current;
    if (!el) return;

    const updateSizeState = () => {
      const { width, height } = el.getBoundingClientRect();
      const nextWidth = Math.max(0, Math.floor(width));
      const nextHeight = Math.max(0, Math.floor(height));
      setChartSize({ width: nextWidth, height: nextHeight });
      setCanRenderChart(nextWidth > 0 && nextHeight > 0);
    };

    updateSizeState();
    const observer = new ResizeObserver(updateSizeState);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setFailed(false);
      setDataMap({});

      let gotAnyResponse = false;

      // Fetch selected default period first so the first render has matching data.
      const primaryPeriod: Period = "1d";
      try {
        const primaryData = await fetchHistory(symbol, primaryPeriod);
        if (primaryData !== null) {
          gotAnyResponse = true;
        }
        if (active && primaryData?.closes?.length) {
          setDataMap((prev) => ({ ...prev, [primaryPeriod]: primaryData.closes }));
          setLoading(false);
        }
      } catch { /**/ }

      // Fetch remaining periods in parallel
      const rest: Period[] = ["1w", "1mo", "6mo", "1y"];
      const results = await Promise.allSettled(
        rest.map((p) => fetchHistory(symbol, p))
      );
      if (!active) return;

      const updates: Partial<Record<Period, HistoryPoint[]>> = {};
      rest.forEach((p, i) => {
        const r = results[i];
        if (r.status === "fulfilled") {
          if (r.value !== null) {
            gotAnyResponse = true;
          }
          if (r.value?.closes?.length) {
            updates[p] = r.value.closes;
          }
        }
      });

      const missingLongPeriods = (["6mo", "1y"] as const).filter((p) => !updates[p]);
      for (const longPeriod of missingLongPeriods) {
        try {
          const retryData = await fetchHistory(symbol, longPeriod);
          if (retryData !== null) {
            gotAnyResponse = true;
          }
          if (retryData?.closes?.length) {
            updates[longPeriod] = retryData.closes;
          }
        } catch {
          // Keep existing behavior: show available periods even if one range fails.
        }
      }

      setDataMap((prev) => ({ ...prev, ...updates }));
      if (active) {
        setFailed(!gotAnyResponse);
        setLoading(false);
      }
    };

    void load();
    return () => { active = false; };
  }, [symbol, reloadToken]);

  const currentData = useMemo<HistoryPoint[]>(() => dataMap[period] ?? [], [dataMap, period]);

  const change = useMemo(() => {
    if (period === "1d" && !dataMap["1d"] && defaultChangePercent !== undefined) {
      return defaultChangePercent ?? null;
    }
    return calcChange(currentData);
  }, [period, currentData, dataMap, defaultChangePercent]);

  const strokeColor = change === null ? "#71717a" : change >= 0 ? "#10b981" : "#ef4444";
  const gradientId  = `priceGrad_${symbol}`;

  const thinned = useMemo(() => {
    const maxPoints =
      period === "1d" ? 800 :
      period === "1w" ? 400 :
      period === "1mo" ? 280 :
      period === "1y" ? 500 :
      260;
    if (currentData.length <= maxPoints) return currentData;
    const step = Math.ceil(currentData.length / maxPoints);
    return currentData.filter((_, i) => i % step === 0 || i === currentData.length - 1);
  }, [currentData, period]);

  const chartData: ChartPoint[] = thinned.map((p) => ({
    date: p.date,
    close: Number(p.close),
    volume: Number(p.volume ?? 0),
    rawDate: String(p.date),
  })).filter((p) => Number.isFinite(p.close));

  const hasVolume = chartData.some((p) => p.volume > 0);

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3 sm:p-5 h-full flex flex-col overflow-hidden">
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
      <div ref={chartBodyRef} className="h-[clamp(270px,52vw,420px)] sm:h-[360px] lg:h-[420px] min-h-[270px]">
      {loading ? (
        <Skeleton className="h-full w-full rounded-xl" />
      ) : failed ? (
        <div className="h-full flex flex-col items-center justify-center gap-3 text-sm">
          <p className="text-red-300">Unable to load chart data. Check backend connection.</p>
          <button
            onClick={() => setReloadToken((t) => t + 1)}
            className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
          >
            Retry
          </button>
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-full flex items-center justify-center text-zinc-600 text-sm">
          No price history available
        </div>
      ) : !canRenderChart ? (
        <Skeleton className="h-full w-full rounded-xl" />
      ) : (
        <ComposedChart width={chartSize.width} height={chartSize.height} data={chartData} margin={{ top: 8, right: 2, left: 0, bottom: 6 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={strokeColor} stopOpacity={0.12} />
                <stop offset="100%" stopColor={strokeColor} stopOpacity={0}    />
              </linearGradient>
            </defs>

            <CartesianGrid stroke="#27272a" strokeOpacity={0.4} vertical={false} />

            <XAxis
              dataKey="rawDate"
              tickFormatter={(v: string) => formatDate(v, period)}
              tick={{ fill: "#52525b", fontSize: 10 }}
              axisLine={{ stroke: "#27272a", strokeOpacity: 0.7 }}
              tickLine={false}
              minTickGap={period === "1d" ? 24 : period === "1w" ? 48 : period === "1mo" ? 42 : 36}
              tickMargin={6}
              interval="preserveStartEnd"
              mirror
            />
            {hasVolume && (
              <YAxis
                yAxisId="volume"
                hide
                domain={[0, "dataMax"]}
              />
            )}
            <YAxis
              yAxisId="price"
              orientation="right"
              tick={{ fill: "#52525b", fontSize: 10, dx: -2 }}
              axisLine={{ stroke: "#27272a", strokeOpacity: 0.7 }}
              tickLine={false}
              width={42}
              tickMargin={2}
              tickFormatter={formatPriceTick}
              tickCount={6}
              domain={["auto", "auto"]}
            />

            <Tooltip
              content={<CustomTooltip period={period} />}
              cursor={{ stroke: "#3f3f46", strokeWidth: 1, strokeDasharray: "4 3" }}
            />

            {hasVolume && (
              <Bar
                yAxisId="volume"
                dataKey="volume"
                fill="#52525b"
                fillOpacity={0.22}
                barSize={period === "1d" ? 1 : period === "1w" ? 3 : period === "1mo" ? 4 : period === "1y" ? 2 : 3}
                radius={[1, 1, 0, 0]}
                isAnimationActive={false}
              />
            )}

            <Line
              yAxisId="price"
              type="linear"
              dataKey="close"
              stroke={strokeColor}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: strokeColor, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </ComposedChart>
      )}
      </div>
    </div>
  );
}
