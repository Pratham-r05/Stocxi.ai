"use client";

// PriceChart — price line + volume bars, period tabs with % changes, drag-to-select range, current price badge

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
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
  ReferenceArea,
  ReferenceLine,
  ReferenceDot,
} from "recharts";
import { Skeleton } from "@/components/ui/Skeleton";

type Period = "1d" | "1w" | "1mo" | "6mo" | "1y" | "5y";

interface ChartPoint {
  date: string;    // formatted label for X-axis
  close: number;
  volume: number;
  rawDate: string; // original date string from backend
}

const PERIODS: { id: Period; label: string }[] = [
  { id: "1d",  label: "1D"  },
  { id: "1w",  label: "5D"  },
  { id: "1mo", label: "1M"  },
  { id: "6mo", label: "6M"  },
  { id: "1y",  label: "1Y"  },
  { id: "5y",  label: "Max" },
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
      {priceEntry?.value != null && (
        <div className="font-mono font-bold text-white text-sm">
          ₹{Number(priceEntry.value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
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

// SVG badge rendered via ReferenceLine label at the right Y-axis edge
function CurrentPriceBadge({
  viewBox,
  color,
  price,
}: {
  viewBox?: { x: number; y: number; width: number; height: number };
  color: string;
  price: number;
}) {
  if (!viewBox) return null;
  const { x, y, width } = viewBox;
  const label = price.toFixed(2);
  const bw = Math.max(44, label.length * 6.5 + 10);
  const bh = 16;
  return (
    <g>
      <rect
        x={x + width + 2}
        y={y - bh / 2}
        width={bw}
        height={bh}
        rx={3}
        fill={color}
        fillOpacity={0.9}
      />
      <text
        x={x + width + 2 + bw / 2}
        y={y + 5}
        textAnchor="middle"
        fill="white"
        fontSize={9}
        fontWeight={700}
        fontFamily="monospace"
      >
        {label}
      </text>
    </g>
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

  // Drag-to-select range state
  const [selStart, setSelStart] = useState<string | null>(null);
  const [selEnd,   setSelEnd]   = useState<string | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  // Ref avoids stale closure in onMouseMove during rapid drag
  const isSelectingRef = useRef(false);

  const handlePeriodChange = useCallback((p: Period) => {
    setPeriod(p);
    setSelStart(null);
    setSelEnd(null);
  }, []);

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

      // Fetch 1D first so initial render has data immediately
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
      const rest: Period[] = ["1w", "1mo", "6mo", "1y", "5y"];
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

      const missingLongPeriods = (["6mo", "1y", "5y"] as const).filter((p) => !updates[p]);
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

  const strokeColor = change == null ? "#71717a" : change >= 0 ? "#10b981" : "#ef4444";
  const gradientId  = `priceGrad_${symbol}`;

  const thinned = useMemo(() => {
    const maxPoints =
      period === "1d"  ? 800 :
      period === "1w"  ? 400 :
      period === "1mo" ? 280 :
      period === "1y"  ? 500 :
      period === "5y"  ? 600 :
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
  const lastPrice = chartData[chartData.length - 1]?.close ?? null;

  // Derive selection price-change info once selection is finalized
  const selInfo = useMemo(() => {
    if (!selStart || !selEnd) return null;
    const idxS = chartData.findIndex((p) => p.rawDate === selStart);
    const idxE = chartData.findIndex((p) => p.rawDate === selEnd);
    if (idxS < 0 || idxE < 0 || idxS === idxE) return null;
    const earlier = idxS < idxE ? chartData[idxS] : chartData[idxE];
    const later   = idxS < idxE ? chartData[idxE] : chartData[idxS];
    const priceChange = later.close - earlier.close;
    const pctChange   = (priceChange / earlier.close) * 100;
    return {
      priceChange,
      pctChange,
      startLabel: formatTooltipDate(earlier.rawDate, period),
      endLabel:   formatTooltipDate(later.rawDate, period),
    };
  }, [selStart, selEnd, chartData, period]);

  const selStartPoint = useMemo(
    () => chartData.find((p) => p.rawDate === selStart) ?? null,
    [selStart, chartData]
  );
  const selEndPoint = useMemo(
    () => chartData.find((p) => p.rawDate === selEnd) ?? null,
    [selEnd, chartData]
  );

  return (
    <div
      className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3 sm:p-5 flex flex-col overflow-hidden
        [&_*]:outline-none [&_.recharts-wrapper]:outline-none [&_.recharts-surface]:outline-none"
      style={{ userSelect: "none" }}
    >
      {/* Period tabs */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
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
              onClick={() => handlePeriodChange(p.id)}
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

      {/* Selection info bar — shown after drag is released */}
      {selInfo && !isSelecting && (
        <div
          className={`flex items-center gap-2 mb-2 px-3 py-2 rounded-lg text-xs border
            ${selInfo.priceChange >= 0
              ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-400"
              : "bg-red-500/10 border-red-500/25 text-red-400"
            }`}
        >
          <span className="font-mono font-bold text-sm">
            {selInfo.priceChange >= 0 ? "+" : ""}
            {selInfo.priceChange.toFixed(2)}{" "}
            ({selInfo.pctChange >= 0 ? "+" : ""}{selInfo.pctChange.toFixed(2)}%)
            {selInfo.priceChange >= 0 ? " ↑" : " ↓"}
          </span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-400 truncate">
            {selInfo.startLabel} – {selInfo.endLabel}
          </span>
          <button
            onClick={() => { setSelStart(null); setSelEnd(null); }}
            className="ml-auto text-zinc-600 hover:text-zinc-300 transition-colors text-base leading-none"
          >
            ×
          </button>
        </div>
      )}

      {/* Chart body */}
      <div ref={chartBodyRef} className="h-[clamp(270px,48vw,390px)] sm:h-[350px] lg:h-[390px] min-h-[270px]">
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
        <ComposedChart
          width={chartSize.width}
          height={chartSize.height}
          data={chartData}
          margin={{ top: 8, right: 2, left: 0, bottom: 6 }}
          onMouseDown={(e) => {
            const label = (e as { activeLabel?: string })?.activeLabel;
            if (label) {
              setSelStart(label);
              setSelEnd(label);
              setIsSelecting(true);
              isSelectingRef.current = true;
            }
          }}
          onMouseMove={(e) => {
            if (!isSelectingRef.current) return;
            const label = (e as { activeLabel?: string })?.activeLabel;
            if (label) setSelEnd(label);
          }}
          onMouseUp={() => {
            setIsSelecting(false);
            isSelectingRef.current = false;
          }}
          onMouseLeave={() => {
            if (isSelectingRef.current) {
              setIsSelecting(false);
              isSelectingRef.current = false;
            }
          }}
          onDoubleClick={() => {
            setSelStart(null);
            setSelEnd(null);
          }}
        >
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
              width={56}
              tickMargin={2}
              tickFormatter={formatPriceTick}
              tickCount={6}
              domain={["auto", "auto"]}
            />

            <Tooltip
              content={<CustomTooltip period={period} />}
              cursor={
                isSelecting
                  ? { stroke: "transparent" }
                  : { stroke: "#3f3f46", strokeWidth: 1, strokeDasharray: "4 3" }
              }
            />

            {/* Drag-to-select overlay */}
            {selStart && selEnd && selStart !== selEnd && (
              <ReferenceArea
                yAxisId="price"
                x1={selStart}
                x2={selEnd}
                fill={strokeColor}
                fillOpacity={0.12}
                stroke={strokeColor}
                strokeOpacity={0.3}
              />
            )}

            {/* Current price dashed line + badge */}
            {lastPrice != null && (
              <ReferenceLine
                yAxisId="price"
                y={lastPrice}
                stroke={strokeColor}
                strokeDasharray="3 2"
                strokeOpacity={0.45}
                label={{
                  content: (props: unknown) => {
                    const lp = props as { viewBox?: { x: number; y: number; width: number; height: number } };
                    return (
                      <CurrentPriceBadge
                        viewBox={lp.viewBox}
                        color={strokeColor}
                        price={lastPrice}
                      />
                    );
                  },
                }}
              />
            )}

            {hasVolume && (
              <Bar
                yAxisId="volume"
                dataKey="volume"
                fill="#2563eb"
                fillOpacity={0.35}
                barSize={period === "1d" ? 1 : period === "1w" ? 3 : period === "1mo" ? 4 : 2}
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
              activeDot={isSelecting ? false : { r: 4, fill: strokeColor, strokeWidth: 0 }}
              isAnimationActive={false}
            />

            {/* Selection endpoint dots — shown only after drag is released */}
            {!isSelecting && selStart && selStartPoint && (
              <ReferenceDot
                yAxisId="price"
                x={selStart}
                y={selStartPoint.close}
                r={4}
                fill="white"
                strokeWidth={0}
              />
            )}
            {!isSelecting && selEnd && selEndPoint && selEnd !== selStart && (
              <ReferenceDot
                yAxisId="price"
                x={selEnd}
                y={selEndPoint.close}
                r={4}
                fill="white"
                strokeWidth={0}
              />
            )}
          </ComposedChart>
      )}
      </div>
    </div>
  );
}
