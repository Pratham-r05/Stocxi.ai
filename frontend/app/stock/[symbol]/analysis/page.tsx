// Analysis page — AI-powered stock analysis via the simplified Gemini pipeline.
// URL: /stock/SYMBOL/analysis?horizon=short&risk=moderate

import type { Metadata } from "next";
import StockNavbar from "@/components/stock/StockNavbar";
import AnalysisClient from "@/components/stock/AnalysisClient";

interface PageProps {
  params:       Promise<{ symbol: string }>;
  searchParams: Promise<{ horizon?: string; risk?: string; sector?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} AI Analysis — Stocxi`,
    description: `AI-powered stock analysis for ${symbol.toUpperCase()}`,
  };
}

export default async function AnalysisPage({ params, searchParams }: PageProps) {
  const { symbol } = await params;
  const sp         = await searchParams;

  const upper   = symbol.toUpperCase();
  const horizon = (["short", "medium", "long"].includes(sp.horizon ?? "")
    ? sp.horizon! : "short") as "short" | "medium" | "long";
  const risk    = (["conservative", "moderate", "aggressive"].includes(sp.risk ?? "")
    ? sp.risk! : "moderate") as "conservative" | "moderate" | "aggressive";
  const sector  = sp.sector ?? "";

  return (
    <div className="min-h-screen bg-black overflow-x-hidden">
      <StockNavbar
        symbol={upper}
        companyName=""
        horizon={horizon}
        risk={risk}
      />
      <main className="max-w-5xl mx-auto px-3 sm:px-6 py-8">
        {/* AnalysisClient fetches client-side so the page loads instantly */}
        <AnalysisClient symbol={upper} horizon={horizon} risk={risk} sector={sector} />
      </main>
    </div>
  );
}
