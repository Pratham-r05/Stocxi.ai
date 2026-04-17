"use client";

// StockNavbar — sticky glass navbar for stock analysis page

import { useSession } from "next-auth/react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
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
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        {/* Left: back */}
        <Link
          href="/"
          className="flex items-center gap-1 text-zinc-400 hover:text-white transition-colors text-sm font-medium"
        >
          <ChevronLeft className="w-4 h-4" />
          Back
        </Link>

        {/* Center: symbol + name */}
        <div className="flex items-center gap-2 text-sm">
          <span className="font-bold text-white">{symbol}</span>
          <span className="text-zinc-600 hidden sm:block">·</span>
          <span className="text-zinc-500 hidden sm:block truncate max-w-[200px]">{shortName}</span>
        </div>

        {/* Right: report action + avatar/sign in */}
        <div className="flex items-center gap-2.5">
          <DownloadReportButton symbol={symbol} />
          {initials ? (
            <div className="w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs font-bold text-zinc-300">
              {initials}
            </div>
          ) : (
            <Link href="/login" className="text-sm text-zinc-500 hover:text-white transition-colors">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
