import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchStockOverview } from "@/lib/api";
import StockNavbar from "@/components/stock/StockNavbar";
import StockHeader from "@/components/stock/StockHeader";
import TopStatsBar from "@/components/stock/TopStatsBar";
import PriceChart from "@/components/stock/PriceChart";
import KeyFundamentals from "@/components/stock/KeyFundamentals";
import TechnicalsSection from "@/components/stock/TechnicalsSection";
import StockSectionTabs from "@/components/stock/StockSectionTabs";
import AIAnalysisLauncher from "@/components/stock/AIAnalysisLauncher";
import TrackStockSearch from "@/components/stock/TrackStockSearch";
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
    { id: "technical-indicators", label: "Technical Indicators" },
    { id: "announcements", label: "Announcements" },
    { id: "recent-news", label: "News" },
    { id: "financials", label: "Financials" },
  ];

  return (
    <div className="min-h-screen bg-black overflow-x-hidden">
      <StockNavbar symbol={upper} companyName={data.company_name} />

      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-8 space-y-5 overflow-x-hidden">
        <TrackStockSearch symbol={upper} />

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
            pbRatio={data.pb_ratio}
            volume={data.volume}
            open={data.open}
            previousClose={data.previous_close}
            week52High={data.week_52_high}
            week52Low={data.week_52_low}
          />
        </section>

        {/* Section tabs + AI Analysis launcher beside Financials */}
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <StockSectionTabs sections={pageSections} />
          </div>
          <div className="shrink-0">
            <AIAnalysisLauncher symbol={upper} sector={data.sector ?? ""} />
          </div>
        </div>

        {/* Chart + Key Fundamentals side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] gap-3 items-start">
          <div id="price-chart" className="flex-1 min-w-0 scroll-mt-32">
            <PriceChart symbol={upper} defaultChangePercent={data.change_percent} />
          </div>
          <div id="key-fundamentals" className="scroll-mt-32">
            <KeyFundamentals
              eps={data.eps}
              bookValue={data.book_value}
              faceValue={data.face_value}
              dividendYield={data.dividend_yield}
              roe={data.roe}
              roce={data.roce}
              operatingMargin={data.operating_margin}
              netProfitMargin={data.net_profit_margin}
              debtToEquity={data.debt_to_equity}
              currentRatio={data.current_ratio}
              peRatio={data.pe_ratio}
              pbRatio={data.pb_ratio}
              marketCap={data.market_cap}
              beta={data.beta}
              industry={data.industry}
              sector={data.sector}
            />
          </div>
        </div>

        {/* Technical Indicators */}
        <section id="technical-indicators" className="scroll-mt-32">
          <TechnicalsSection
            technicals={data.technicals}
            currentVolume={data.volume}
          />
        </section>

        {/* News, Announcements */}
        <div className="space-y-5">
          <section id="announcements" className="scroll-mt-32">
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
