import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { fetchStockOverview } from "@/lib/api";
import StockHeader from "@/components/stock/StockHeader";
import QuickStatsGrid from "@/components/stock/QuickStatsGrid";
import TechnicalsSection from "@/components/stock/TechnicalsSection";
import AIAnalysisPanel from "@/components/stock/AIAnalysisPanel";
import SentimentSection from "@/components/sentiment/SentimentSection";
import NewsSection from "@/components/stock/NewsSection";
import AnnouncementsSection from "@/components/stock/AnnouncementsSection";
import FinancialsSection from "@/components/stock/FinancialsSection";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} — Stocxi`,
    description: `AI stock analysis for ${symbol.toUpperCase()}`,
  };
}

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const upper = symbol.toUpperCase();
  const data = await fetchStockOverview(upper);
  if (!data) notFound();

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Top navbar: back arrow + Stocxi logo */}
      <nav className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-40">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center gap-3">
          <Link href="/" className="text-zinc-400 hover:text-zinc-100 transition-colors text-sm flex items-center gap-1.5">
            ← Back
          </Link>
          <span className="text-zinc-700">|</span>
          <Link href="/" className="font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent text-sm">
            Stocxi
          </Link>
        </div>
      </nav>

      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 space-y-8">
        {/* Stock Header */}
        <StockHeader
          symbol={upper}
          companyName={data.company_name}
          exchange={data.exchange}
          sector={data.sector}
          price={data.price}
          change={data.change}
          changePercent={data.change_percent}
          open={data.open}
          dayHigh={data.day_high}
          dayLow={data.day_low}
        />

        {/* Quick Stats */}
        <QuickStatsGrid
          marketCap={data.market_cap}
          peRatio={data.pe_ratio}
          week52High={data.week_52_high}
          week52Low={data.week_52_low}
          roe={data.roe}
          roce={data.roce}
          bookValue={data.book_value}
          dividendYield={data.dividend_yield}
        />

        {/* AI Analysis Panel — client, handles own fetch */}
        <AIAnalysisPanel symbol={upper} />

        {/* Technicals — uses server-fetched data passed as prop */}
        <TechnicalsSection technicals={data.technicals} />

        {/* Sentiment Section — client, handles own fetch */}
        <SentimentSection symbol={upper} />

        {/* News Section — client, handles own fetch */}
        <NewsSection symbol={upper} />

        {/* Announcements Section — client, handles own fetch */}
        <AnnouncementsSection symbol={upper} />

        {/* Financials Section — client, handles own fetch */}
        <FinancialsSection symbol={upper} />

        <footer className="text-center text-xs text-zinc-600 py-4">
          Data sourced from NSEPython, Screener.in, and public social media.
          Not financial advice. Always do your own research.
        </footer>
      </div>
    </div>
  );
}
