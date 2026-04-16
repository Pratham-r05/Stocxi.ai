// KeyFundamentals — sidebar panel with key financial metrics

interface KeyFundamentalsProps {
  marketCap: number | null;
  volume: number | null;
  eps: number | null;
  peRatio: number | null;
  pbRatio: number | null;
  bookValue: number | null;
  dividendYield: number | null;
  industry: string | null;
  sector: string | null;
  roe: number | null;
  roce: number | null;
  faceValue: number | null;
}

function fmtMarketCap(v: number | null): string {
  if (v === null) return "—";
  const cr = v / 1e7;
  if (cr >= 1_00_000) return `₹${(cr / 1_00_000).toFixed(2)}L Cr`;
  return `₹${cr.toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
}

function fmtNum(v: number | null, suffix = "", decimals = 2): string {
  if (v === null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: decimals }) + suffix;
}

function Row({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-zinc-800/70 last:border-0 gap-3">
      <span className="text-xs text-zinc-500 shrink-0">{label}</span>
      <span
        className={`text-xs font-medium text-right truncate max-w-[180px] ${
          highlight ? "text-blue-400 font-semibold" : "text-zinc-200"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function fmtVolume(v: number | null): string {
  if (v === null) return "—";
  if (v >= 1_00_00_000) return `${(v / 1_00_00_000).toFixed(2)} Cr`;
  if (v >= 1_00_000)    return `${(v / 1_00_000).toFixed(2)} L`;
  return v.toLocaleString("en-IN");
}

export default function KeyFundamentals({
  marketCap,
  volume,
  eps,
  peRatio,
  pbRatio,
  bookValue,
  dividendYield,
  industry,
  sector,
  roe,
  roce,
  faceValue,
}: KeyFundamentalsProps) {
  const rows = [
    { label: "Market Cap",       value: fmtMarketCap(marketCap) },
    { label: "Volume",           value: fmtVolume(volume) },
    { label: "EPS",              value: eps !== null ? `₹${fmtNum(eps)}` : "—" },
    { label: "PE Ratio",         value: peRatio !== null ? peRatio.toFixed(2) : "—" },
    { label: "PB Ratio",         value: pbRatio !== null ? pbRatio.toFixed(2) : "—" },
    { label: "Book Value",       value: bookValue !== null ? `₹${fmtNum(bookValue)}` : "—" },
    { label: "Face Value",       value: faceValue !== null ? `₹${fmtNum(faceValue)}` : "—" },
    { label: "Dividend Yield",   value: dividendYield !== null ? `${dividendYield.toFixed(2)} %` : "—" },
    { label: "Return on Equity", value: roe !== null ? `${fmtNum(roe)} %` : "—" },
    { label: "ROCE",             value: roce !== null ? `${fmtNum(roce)} %` : "—" },
    { label: "Industry",         value: industry ?? "—", highlight: !!industry },
    { label: "Sector",           value: sector ?? "—",   highlight: !!sector },
  ];

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 h-full">
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
        Key Fundamentals
      </h3>
      <div>
        {rows.map((r) => (
          <Row key={r.label} label={r.label} value={r.value} highlight={r.highlight} />
        ))}
      </div>
    </div>
  );
}
