import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchStockOverview } from "@/lib/api";
import StockNavbar from "@/components/stock/StockNavbar";
import StockHeader from "@/components/stock/StockHeader";
import QuickStatsGrid from "@/components/stock/QuickStatsGrid";
import TechnicalsSection from "@/components/stock/TechnicalsSection";
import AIAnalysisPanel from "@/components/stock/AIAnalysisPanel";
import SentimentSection from "@/components/sentiment/SentimentSection";
import NewsSection from "@/components/stock/NewsSection";
import AnnouncementsSection from "@/components/stock/AnnouncementsSection";
import FinancialsSection from "@/components/stock/FinancialsSection";
import PriceChart from "@/components/stock/PriceChart";

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
    <div className="min-h-screen bg-black">
      <StockNavbar symbol={upper} companyName={data.company_name} />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-6">
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

        <PriceChart symbol={upper} />

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

        <AIAnalysisPanel symbol={upper} />

        <div className="space-y-6">
          <TechnicalsSection technicals={data.technicals} />
          <SentimentSection symbol={upper} />
          <AnnouncementsSection symbol={upper} />
          <NewsSection symbol={upper} />
        </div>

        <FinancialsSection symbol={upper} />

        <footer className="text-center text-xs text-zinc-700 py-4">
          Data sourced from NSEPython, Screener.in, and public social media.
          Not financial advice. Always do your own research.
        </footer>
      </main>
    </div>
  );
}
