// QuickStatsGrid — 8 key metrics with icon labels and hover

import { TrendingUp, TrendingDown, BarChart2, ArrowUpCircle, ArrowDownCircle, Percent, BookOpen, DollarSign } from "lucide-react";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

interface QuickStatsGridProps {
  marketCap: number | null;
  peRatio: number | null;
  week52High: number | null;
  week52Low: number | null;
  roe: number | null;
  roce: number | null;
  bookValue: number | null;
  dividendYield: number | null;
}

function StatCard({
  label,
  value,
  tooltip,
  Icon,
}: {
  label: string;
  value: string;
  tooltip: string;
  Icon: React.FC<{ className?: string }>;
}) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 transition-colors">
      <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-2">
        <Icon className="w-3 h-3" />
        <span className="inline-flex items-center">
          {label}
          <InfoTooltip content={tooltip} />
        </span>
      </div>
      <div className="text-sm font-semibold font-mono text-zinc-100">{value}</div>
    </div>
  );
}

function formatMarketCap(v: number | null): string {
  if (v == null) return "—";
  const cr = v / 1e7;
  return cr >= 1000 ? `₹${(v / 1e9).toFixed(1)}B` : `₹${cr.toFixed(0)}Cr`;
}

function formatPrice(v: number | null): string {
  if (v == null) return "—";
  return `₹${v.toLocaleString("en-IN")}`;
}

function formatPercent(v: number | null): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

function formatPE(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(2);
}

export default function QuickStatsGrid({ marketCap, peRatio, week52High, week52Low, roe, roce, bookValue, dividendYield }: QuickStatsGridProps) {
  const stats = [
    {
      label: "Market Cap",
      value: formatMarketCap(marketCap),
      tooltip: "Total company size in the market. Bigger market cap usually means more stable; smaller can mean higher growth but higher risk.",
      Icon: TrendingUp,
    },
    {
      label: "P/E Ratio",
      value: formatPE(peRatio),
      tooltip: "Price divided by earnings. Lower than peers can mean undervalued; very high can mean expensive unless growth is strong.",
      Icon: BarChart2,
    },
    {
      label: "52W High",
      value: formatPrice(week52High),
      tooltip: "Highest price in the last 52 weeks. If current price is near this, momentum is strong but upside may be limited.",
      Icon: ArrowUpCircle,
    },
    {
      label: "52W Low",
      value: formatPrice(week52Low),
      tooltip: "Lowest price in the last 52 weeks. If current price is near this, stock may be weak or could be a value opportunity.",
      Icon: ArrowDownCircle,
    },
    {
      label: "ROE",
      value: formatPercent(roe),
      tooltip: "Return on Equity: profit generated from shareholders' money. Higher and consistent ROE is generally better.",
      Icon: Percent,
    },
    {
      label: "ROCE",
      value: formatPercent(roce),
      tooltip: "Return on Capital Employed: efficiency of total capital use. Compare with competitors; higher usually means better operations.",
      Icon: TrendingDown,
    },
    {
      label: "Book Value",
      value: bookValue != null ? `₹${bookValue.toLocaleString("en-IN")}` : "—",
      tooltip: "Net asset value per share. If price is far above book value, valuation may depend more on growth expectations.",
      Icon: BookOpen,
    },
    {
      label: "Div Yield",
      value: formatPercent(dividendYield),
      tooltip: "Annual dividend return as a percentage of price. Higher yield is good for income, but check if dividends are sustainable.",
      Icon: DollarSign,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {stats.map((s) => (
        <StatCard key={s.label} label={s.label} value={s.value} tooltip={s.tooltip} Icon={s.Icon} />
      ))}
    </div>
  );
}
