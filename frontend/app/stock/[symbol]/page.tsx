import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchStockOverview } from "@/lib/api";
import StockNavbar from "@/components/stock/StockNavbar";
import StockHeader from "@/components/stock/StockHeader";
import TopStatsBar from "@/components/stock/TopStatsBar";
import PriceChart from "@/components/stock/PriceChart";
import KeyFundamentals from "@/components/stock/KeyFundamentals";
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
    <div className="min-h-screen bg-black">
      <StockNavbar symbol={upper} companyName={data.company_name} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-5">
        {/* Header: company name, price, change */}
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

        {/* Quick stats bar */}
        <TopStatsBar
          marketCap={data.market_cap}
          peRatio={data.pe_ratio}
          volume={data.volume}
          dayHigh={data.day_high}
          dayLow={data.day_low}
          week52High={data.week_52_high}
          week52Low={data.week_52_low}
        />

        {/* Chart + Key Fundamentals side by side */}
        <div className="flex flex-col lg:flex-row gap-5">
          <div className="flex-1 min-w-0">
            <PriceChart symbol={upper} defaultChangePercent={data.change_percent} />
          </div>
          <div className="lg:w-72 shrink-0">
            <KeyFundamentals
              marketCap={data.market_cap}
              volume={data.volume}
              eps={data.eps}
              peRatio={data.pe_ratio}
              pbRatio={data.pb_ratio}
              bookValue={data.book_value}
              faceValue={data.face_value}
              dividendYield={data.dividend_yield}
              industry={data.industry}
              sector={data.sector}
              roe={data.roe}
              roce={data.roce}
            />
          </div>
        </div>

        {/* AI Analysis */}
        <AIAnalysisPanel symbol={upper} />

        {/* Technical Indicators */}
        <TechnicalsSection
          technicals={data.technicals}
          currentVolume={data.volume}
        />

        {/* Social, News, Announcements */}
        <div className="space-y-5">
          <SentimentSection symbol={upper} />
          <AnnouncementsSection symbol={upper} />
          <NewsSection symbol={upper} />
        </div>

        {/* Financials */}
        <FinancialsSection symbol={upper} />

        <footer className="text-center text-xs text-zinc-700 py-4">
          Data sourced from NSEPython, Screener.in, and public social media.
          Not financial advice. Always do your own research.
        </footer>
      </main>
    </div>
  );
}
