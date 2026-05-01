"use client";

// StockNavbar — sticky glass navbar for stock analysis page

import { useSession } from "next-auth/react";
import Link from "next/link";
import { ChevronLeft, Network } from "lucide-react";
import DownloadReportButton from "@/components/stock/DownloadReportButton";

interface StockNavbarProps {
  symbol: string;
  companyName: string;
}

export default function StockNavbar({ symbol, companyName }: StockNavbarProps) {
  const { data: session } = useSession();

  // Shorten company name for display
  const shortName = companyName.length > 28 ? companyName.slice(0, 28) + "…" : companyName;

  // Get initials from session for avatar
  const initials = session?.user?.name
    ? session.user.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : null;

  return (
    <nav className="sticky top-0 z-50 glass border-b border-zinc-800/50">
      <div className="max-w-6xl mx-auto px-3 sm:px-6 h-14 flex items-center justify-between gap-2">
        {/* Left: back */}
        <Link
          href="/"
          className="flex items-center gap-1 text-zinc-400 hover:text-white transition-colors text-sm font-medium shrink-0"
        >
          <ChevronLeft className="w-4 h-4" />
          <span className="hidden sm:inline">Back</span>
        </Link>

        {/* Center: symbol + name */}
        <div className="flex items-center gap-2 text-sm min-w-0 flex-1 justify-center">
          <span className="font-bold text-white shrink-0">{symbol}</span>
          <span className="text-zinc-600 hidden sm:block">·</span>
          <span className="text-zinc-500 hidden sm:block truncate max-w-[200px]">{shortName}</span>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-3 shrink-0">
          <Link
            href={`/stock/${symbol}/knowledge`}
            className="flex items-center gap-1.5 text-zinc-400 hover:text-white transition-colors text-sm"
            title="Knowledge Graph"
          >
            <Network className="w-4 h-4" />
            <span className="hidden sm:inline">Graph</span>
          </Link>
          <DownloadReportButton symbol={symbol} />
          {initials ? (
            <div className="w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs font-bold text-zinc-300 shrink-0">
              {initials}
            </div>
          ) : (
            <Link href="/login" className="text-sm text-zinc-500 hover:text-white transition-colors shrink-0">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
