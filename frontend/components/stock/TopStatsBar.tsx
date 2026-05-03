// TopStatsBar — horizontal key metrics bar: Market Cap | PE | PB | Volume | Open–Close | 52W H-L

interface TopStatsBarProps {
  marketCap: number | null;
  peRatio: number | null;
  pbRatio: number | null;
  volume: number | null;
  open: number | null;
  previousClose: number | null;
  week52High: number | null;
  week52Low: number | null;
}

function fmtMarketCap(v: number | null): string {
  if (v == null) return "—";
  const cr = v / 1e7;
  if (cr >= 1_00_000) return `₹${(cr / 1_00_000).toFixed(2)}L Cr`;
  return `₹${cr.toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
}

function fmtVolume(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1_00_00_000) return `${(v / 1_00_00_000).toFixed(2)} Cr`;
  if (v >= 1_00_000) return `${(v / 1_00_000).toFixed(2)} L`;
  return v.toLocaleString("en-IN");
}

function fmtPrice(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-2.5 sm:px-3 py-1.5 min-w-[98px] sm:min-w-0">
      <span className="text-[9px] text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
        {label}
      </span>
      <span className="text-[13px] sm:text-sm font-semibold font-mono text-zinc-100 whitespace-nowrap">
        {value}
      </span>
    </div>
  );
}

export default function TopStatsBar({
  marketCap,
  peRatio,
  pbRatio,
  volume,
  open,
  previousClose,
  week52High,
  week52Low,
}: TopStatsBarProps) {
  const weekRange =
    week52High != null && week52Low != null
      ? `${fmtPrice(week52High)} – ${fmtPrice(week52Low)}`
      : "—";

  const openClose =
    open != null && previousClose != null
      ? `${fmtPrice(open)} · ${fmtPrice(previousClose)}`
      : open != null
        ? fmtPrice(open)
        : "—";

  const stats = [
    { label: "Market Cap",     value: fmtMarketCap(marketCap) },
    { label: "PE Ratio",       value: peRatio != null ? peRatio.toFixed(2) : "—" },
    { label: "PB Ratio",       value: pbRatio != null ? pbRatio.toFixed(2) : "—" },
    { label: "Volume",         value: fmtVolume(volume) },
    { label: "Open · Prev Close", value: openClose },
    { label: "52W High – Low", value: weekRange },
  ];

  return (
    <div className="inline-block max-w-full overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900 align-top [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
      <div className="flex items-stretch divide-x divide-zinc-800 min-w-max">
        {stats.map((s) => (
          <StatItem key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
    </div>
  );
}
