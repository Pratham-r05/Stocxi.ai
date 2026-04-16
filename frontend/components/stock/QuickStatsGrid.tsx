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

interface StatCardProps {
  label: string;
  value: string;
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className="text-sm font-semibold text-zinc-100">{value}</div>
    </div>
  );
}

function formatMarketCap(value: number | null): string {
  if (value === null) return "—";
  // Show in Cr if < 1T, else in B
  const crore = value / 1e7;
  if (crore >= 1000) {
    return `₹${(value / 1e9).toFixed(1)}B`;
  }
  return `₹${crore.toFixed(0)}Cr`;
}

function formatPrice(value: number | null): string {
  if (value === null) return "—";
  return `₹${value.toLocaleString("en-IN")}`;
}

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return `${value.toFixed(2)}%`;
}

function formatPE(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(2);
}

export default function QuickStatsGrid({
  marketCap,
  peRatio,
  week52High,
  week52Low,
  roe,
  roce,
  bookValue,
  dividendYield,
}: QuickStatsGridProps) {
  const stats: StatCardProps[] = [
    { label: "Market Cap", value: formatMarketCap(marketCap) },
    { label: "P/E Ratio", value: formatPE(peRatio) },
    { label: "52W High", value: formatPrice(week52High) },
    { label: "52W Low", value: formatPrice(week52Low) },
    { label: "ROE", value: formatPercent(roe) },
    { label: "ROCE", value: formatPercent(roce) },
    { label: "Book Value", value: bookValue !== null ? `₹${bookValue.toLocaleString("en-IN")}` : "—" },
    { label: "Div Yield", value: formatPercent(dividendYield) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <StatCard key={stat.label} label={stat.label} value={stat.value} />
      ))}
    </div>
  );
}
