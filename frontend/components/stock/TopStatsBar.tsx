// TopStatsBar — horizontal key metrics bar: Market Cap | PE | Volume | Day H-L | 52W H-L

interface TopStatsBarProps {
  marketCap: number | null;
  peRatio: number | null;
  volume: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  week52High: number | null;
  week52Low: number | null;
}

function fmtMarketCap(v: number | null): string {
  if (v === null) return "—";
  const cr = v / 1e7; // rupees → crores
  if (cr >= 1_00_000) return `₹${(cr / 1_00_000).toFixed(2)}L Cr`;
  return `₹${cr.toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
}

function fmtNum(v: number | null, decimals = 2): string {
  if (v === null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: decimals });
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 sm:px-4 py-2 min-w-[110px] sm:min-w-0">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium whitespace-nowrap">
        {label}
      </span>
      <span className="text-sm font-semibold font-mono text-zinc-100 whitespace-nowrap">
        {value}
      </span>
    </div>
  );
}

export default function TopStatsBar({
  marketCap,
  peRatio,
  volume,
  dayHigh,
  dayLow,
  week52High,
  week52Low,
}: TopStatsBarProps) {
  const dayRange =
    dayHigh !== null && dayLow !== null
      ? `${fmtNum(dayHigh)} – ${fmtNum(dayLow)}`
      : "—";
  const weekRange =
    week52High !== null && week52Low !== null
      ? `${fmtNum(week52High)} – ${fmtNum(week52Low)}`
      : "—";

  const stats = [
    { label: "Market Cap",     value: fmtMarketCap(marketCap) },
    { label: "PE Ratio",       value: peRatio !== null ? peRatio.toFixed(2) : "—" },
    { label: "Volume",         value: fmtNum(volume, 0) },
    { label: "Day High – Low", value: dayRange },
    { label: "52W High – Low", value: weekRange },
  ];

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
      <div className="flex items-stretch divide-x divide-zinc-800 min-w-max">
        {stats.map((s) => (
          <StatItem key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
    </div>
  );
}
