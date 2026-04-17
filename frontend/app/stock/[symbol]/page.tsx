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
import StockSectionTabs from "@/components/stock/StockSectionTabs";
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

  const pageSections = [
    { id: "overview", label: "Overview" },
    { id: "key-fundamentals", label: "Key Fundamentals" },
    { id: "ai-analysis", label: "AI Analysis" },
    { id: "technical-indicators", label: "Technical Indicators" },
    { id: "bse-announcements", label: "BSE Announcements" },
    { id: "recent-news", label: "News" },
    { id: "financials", label: "Financials" },
  ];

  return (
    <div className="min-h-screen bg-black overflow-x-hidden">
      <StockNavbar symbol={upper} companyName={data.company_name} />

      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-8 space-y-5 overflow-x-hidden">
        <StockSectionTabs sections={pageSections} />

        {/* Header: company name, price, change */}
        <section id="overview" className="scroll-mt-32">
          <StockHeader
            symbol={upper}
            companyName={data.company_name}
            logoUrl={data.logo_url}
            exchange={data.exchange}
            sector={data.sector}
            price={data.price}
            change={data.change}
            changePercent={data.change_percent}
            open={data.open}
            dayHigh={data.day_high}
            dayLow={data.day_low}
          />
        </section>

        {/* Quick stats bar */}
        <section className="scroll-mt-32">
          <TopStatsBar
            marketCap={data.market_cap}
            peRatio={data.pe_ratio}
            volume={data.volume}
            dayHigh={data.day_high}
            dayLow={data.day_low}
            week52High={data.week_52_high}
            week52Low={data.week_52_low}
          />
        </section>

        {/* Chart + Key Fundamentals side by side */}
        <div className="flex flex-col lg:flex-row gap-5">
          <div id="price-chart" className="flex-1 min-w-0 scroll-mt-32">
            <PriceChart symbol={upper} defaultChangePercent={data.change_percent} />
          </div>
          <div id="key-fundamentals" className="lg:w-72 shrink-0 scroll-mt-32">
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
        <section id="ai-analysis" className="scroll-mt-32">
          <AIAnalysisPanel symbol={upper} />
        </section>

        {/* Technical Indicators */}
        <section id="technical-indicators" className="scroll-mt-32">
          <TechnicalsSection
            technicals={data.technicals}
            currentVolume={data.volume}
          />
        </section>

        {/* News, Announcements */}
        <div className="space-y-5">
          <section id="bse-announcements" className="scroll-mt-32">
            <AnnouncementsSection symbol={upper} />
          </section>
          <section id="recent-news" className="scroll-mt-32">
            <NewsSection symbol={upper} />
          </section>
        </div>

        {/* Financials */}
        <section id="financials" className="scroll-mt-32">
          <FinancialsSection symbol={upper} />
        </section>

        <footer className="text-center text-xs text-zinc-700 py-4">
          Data sourced from NSEPython, Screener.in, and public social media.
          Not financial advice. Always do your own research.
        </footer>
      </main>
    </div>
  );
}
