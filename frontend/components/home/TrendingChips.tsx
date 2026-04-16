"use client";

import { useRouter } from "next/navigation";

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

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="shrink-0 text-xs font-medium text-zinc-500">Trending:</span>
      {TRENDING.map((symbol) => (
        <button
          key={symbol}
          onClick={() => router.push(`/stock/${symbol}`)}
          className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs font-medium text-zinc-300 transition-colors hover:border-zinc-600 hover:text-zinc-100"
        >
          {symbol}
        </button>
      ))}
    </div>
  );
}
