"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

const STOCK_POOL = [
  "RELIANCE",
  "TCS",
  "INFY",
  "HDFCBANK",
  "WIPRO",
  "ITC",
  "ADANIPOWER",
  "PAYTM",
  "SBIN",
  "ICICIBANK",
  "LT",
  "MARUTI",
  "BHARTIARTL",
  "HINDUNILVR",
  "BAJFINANCE",
  "TMPV",
  "SUNPHARMA",
  "AXISBANK",
  "M&M",
  "NTPC",
  "POWERGRID",
  "ULTRACEMCO",
  "TITAN",
  "ASIANPAINT",
  "COALINDIA",
  "ONGC",
  "HCLTECH",
  "TECHM",
];

const VISIBLE_CHIPS = 8;
const ROTATE_INTERVAL_MS = 60_000;
const INITIAL_SYMBOLS = STOCK_POOL.slice(0, VISIBLE_CHIPS);

function getRandomSymbols(pool: string[], count: number): string[] {
  const shuffled = [...pool];
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, Math.min(count, shuffled.length));
}

export default function TrendingChips() {
  const router = useRouter();
  const [loadingSymbol, setLoadingSymbol] = useState<string | null>(null);
  const [symbols, setSymbols] = useState<string[]>(INITIAL_SYMBOLS);

  useEffect(() => {
    setSymbols(getRandomSymbols(STOCK_POOL, VISIBLE_CHIPS));

    const timer = window.setInterval(() => {
      setSymbols(getRandomSymbols(STOCK_POOL, VISIBLE_CHIPS));
    }, ROTATE_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const go = (symbol: string) => {
    setLoadingSymbol(symbol);
    router.push(`/stock/${symbol}`);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="shrink-0 text-xs font-medium text-zinc-500">Trending:</span>
      {symbols.map((symbol) => {
        const isLoading = loadingSymbol === symbol;
        return (
          <button
            key={symbol}
            onClick={() => go(symbol)}
            disabled={loadingSymbol !== null}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
              isLoading
                ? "border-zinc-500 bg-zinc-800 text-zinc-100"
                : "border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-600 hover:text-zinc-100"
            }`}
          >
            {isLoading && <Loader2 className="w-3 h-3 animate-spin" />}
            {symbol}
          </button>
        );
      })}
    </div>
  );
}
