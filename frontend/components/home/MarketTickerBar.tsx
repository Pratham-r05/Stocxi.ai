"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Space_Grotesk } from "next/font/google";

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

const tickerFont = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

function isIndianMarketOpen(now = new Date()): boolean {
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;

  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const openMinutes = 9 * 60 + 15;
  const closeMinutes = 15 * 60 + 30;
  return minutes >= openMinutes && minutes <= closeMinutes;
}

function formatPrice(value: number | null | undefined, currency: string): string {
  if (value == null) return "—";
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
  const [hasAttemptedLoad, setHasAttemptedLoad] = useState(false);

  const loadTicker = useCallback(async () => {
    try {
      const res = await fetch("/api/market-ticker", { cache: "no-store" });
      if (!res.ok) {
        setHasAttemptedLoad(true);
        return;
      }

      const data = (await res.json()) as MarketTickerResponse;
      const nextItems = Array.isArray(data.items) ? data.items : [];
      if (nextItems.length > 0) {
        setItems(nextItems);
      }
      setIsMarketOpen(Boolean(data.marketOpen));
      setHasAttemptedLoad(true);
    } catch {
      setIsMarketOpen(isIndianMarketOpen());
      setHasAttemptedLoad(true);
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
    <div className="relative z-40 px-3 pt-[calc(3.5rem+env(safe-area-inset-top)+0.75rem)] sm:px-6 sm:pt-16">
      <div
        className={`relative mx-auto w-full max-w-6xl overflow-hidden ${tickerFont.className}`}
        onPointerDown={() => setIsPaused(true)}
        onPointerUp={() => setIsPaused(false)}
        onPointerCancel={() => setIsPaused(false)}
        onPointerLeave={() => setIsPaused(false)}
      >
        <div className="market-ticker-fade-left" aria-hidden="true" />
        <div className="market-ticker-fade-right" aria-hidden="true" />

        <div className="relative z-[2] overflow-hidden px-6 py-2 sm:px-10">
          {!marqueeItems.length && !hasAttemptedLoad ? (
            <div className="px-2 py-2 text-sm text-zinc-400">Loading market data...</div>
          ) : !marqueeItems.length ? (
            <div className="px-2 py-2 text-sm text-zinc-400">
              Market data is temporarily unavailable.
            </div>
          ) : (
            <div
              className={`market-marquee-track ${isPaused ? "paused" : ""}`}
              style={{ animationDuration: `${animationDuration}s` }}
            >
              <span className="w-4 shrink-0 sm:w-8" aria-hidden="true" />
              {marqueeItems.map((item, idx) => {
                const up = item.change >= 0;
                return (
                  <div
                    key={`${item.id}-${idx}`}
                    className="mx-4 inline-flex items-center gap-2.5 whitespace-nowrap py-1 text-xs sm:mx-5 sm:text-sm"
                  >
                    <span className="font-semibold tracking-wide text-white/95 drop-shadow-[0_1px_2px_rgba(0,0,0,0.7)]">
                      {item.label}
                    </span>
                    <span className={`${up ? "text-emerald-400" : "text-rose-400"} font-bold drop-shadow-[0_1px_2px_rgba(0,0,0,0.7)]`}>
                      {formatPrice(item.price, item.currency)}
                    </span>
                    <span className={up ? "text-emerald-300/95" : "text-rose-300/95"}>
                      ({item.changePercent != null ? `${up ? "+" : ""}${item.changePercent.toFixed(2)}%` : "—"})
                    </span>
                    <span className="text-zinc-700/80">•</span>
                  </div>
                );
              })}
              <span className="w-4 shrink-0 sm:w-8" aria-hidden="true" />
            </div>
          )}
        </div>

        <div className="sr-only">
          {isMarketOpen ? "Market open with live updates" : "Market closed with delayed updates"}
        </div>
      </div>
    </div>
  );
}
