"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type MarketTickerItem = {
  id: string;
  label: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  currency: string;
};

type MarketTickerResponse = {
  items: MarketTickerItem[];
  updatedAt: string;
  marketOpen: boolean;
};

function isIndianMarketOpen(now = new Date()): boolean {
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;

  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const openMinutes = 9 * 60 + 15;
  const closeMinutes = 15 * 60 + 30;
  return minutes >= openMinutes && minutes <= closeMinutes;
}

function formatPrice(value: number, currency: string): string {
  if (currency === "INR") {
    return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  }
  if (currency === "USD") {
    return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  }
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export default function MarketTickerBar() {
  const [items, setItems] = useState<MarketTickerItem[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [isMarketOpen, setIsMarketOpen] = useState(false);

  const loadTicker = useCallback(async () => {
    try {
      const res = await fetch("/api/market-ticker", { cache: "no-store" });
      if (!res.ok) return;

      const data = (await res.json()) as MarketTickerResponse;
      setItems(Array.isArray(data.items) ? data.items : []);
      setIsMarketOpen(Boolean(data.marketOpen));
    } catch {
      setIsMarketOpen(isIndianMarketOpen());
    }
  }, []);

  useEffect(() => {
    let timer: number | null = null;
    let active = true;

    const loop = async () => {
      await loadTicker();
      if (!active) return;

      const delay = isIndianMarketOpen() ? 15_000 : 120_000;
      timer = window.setTimeout(loop, delay);
    };

    void loop();

    return () => {
      active = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [loadTicker]);

  const marqueeItems = useMemo(() => {
    if (!items.length) return [];
    return [...items, ...items];
  }, [items]);

  const animationDuration = Math.max(28, items.length * 6);

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-3 z-40 flex justify-center px-2 sm:px-4">
      <div
        className="pointer-events-auto market-ticker-shell w-full max-w-[1150px]"
        onPointerDown={() => setIsPaused(true)}
        onPointerUp={() => setIsPaused(false)}
        onPointerCancel={() => setIsPaused(false)}
        onPointerLeave={() => setIsPaused(false)}
      >
        <div className="flex items-center justify-between gap-3 border-b border-zinc-700/40 px-3 py-2 text-[11px] text-zinc-400 sm:px-4">
          <span className="uppercase tracking-[0.12em] text-zinc-300">Live Market Tape</span>
          <span className={isMarketOpen ? "text-emerald-300" : "text-amber-300"}>
            {isMarketOpen ? "Market Open • Live updates" : "Market Closed • Slow updates"}
          </span>
        </div>

        <div className="overflow-hidden px-2 py-2 sm:px-3">
          {!marqueeItems.length ? (
            <div className="px-2 py-2 text-sm text-zinc-400">Loading market data...</div>
          ) : (
            <div
              className={`market-marquee-track ${isPaused ? "paused" : ""}`}
              style={{ animationDuration: `${animationDuration}s` }}
            >
              {marqueeItems.map((item, idx) => {
                const up = item.change >= 0;
                return (
                  <div
                    key={`${item.id}-${idx}`}
                    className="mx-1.5 inline-flex items-center gap-2 rounded-full border border-zinc-700/50 bg-zinc-900/55 px-3 py-1.5 text-xs whitespace-nowrap"
                  >
                    <span className="font-semibold text-zinc-200">{item.label}</span>
                    <span className="text-zinc-100">{formatPrice(item.price, item.currency)}</span>
                    <span className={up ? "text-emerald-400" : "text-red-400"}>
                      {up ? "+" : ""}
                      {item.changePercent.toFixed(2)}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="px-3 pb-2 text-[11px] text-zinc-500 sm:px-4">Hold anywhere on the bar to pause, release to resume.</div>
      </div>
    </div>
  );
}
