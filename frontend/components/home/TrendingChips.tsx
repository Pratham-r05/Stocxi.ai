"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

const TRENDING = [
  "RELIANCE",
  "TCS",
  "INFY",
  "HDFCBANK",
  "WIPRO",
  "ITC",
  "ADANIPOWER",
  "PAYTM",
];

export default function TrendingChips() {
  const router = useRouter();
  const [loadingSymbol, setLoadingSymbol] = useState<string | null>(null);

  const go = (symbol: string) => {
    setLoadingSymbol(symbol);
    router.push(`/stock/${symbol}`);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="shrink-0 text-xs font-medium text-zinc-500">Trending:</span>
      {TRENDING.map((symbol) => {
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
