// KeyFundamentals — sidebar panel with unique financial metrics not shown in the top bar

interface KeyFundamentalsProps {
  eps: number | null;
  bookValue: number | null;
  faceValue: number | null;
  dividendYield: number | null;
  roe: number | null;
  roce: number | null;
  operatingMargin: number | null;
  netProfitMargin: number | null;
  debtToEquity: number | null;
  currentRatio: number | null;
  peRatio: number | null;
  pbRatio: number | null;
  marketCap: number | null;
  beta: number | null;
  industry: string | null;
  sector: string | null;
}

function fmtNum(v: number | null, suffix = "", decimals = 2): string {
  if (v == null) return "";
  return v.toLocaleString("en-IN", { maximumFractionDigits: decimals }) + suffix;
}

function fmtMarketCap(v: number | null): string {
  if (v == null) return "";
  const cr = v / 1e7;
  if (cr >= 100000) return `₹${(cr / 100000).toFixed(2)}L Cr`;
  if (cr >= 1000) return `₹${(cr / 1000).toFixed(2)}K Cr`;
  return `₹${cr.toFixed(0)} Cr`;
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

export default function KeyFundamentals({
  eps,
  bookValue,
  faceValue,
  dividendYield,
  roe,
  roce,
  operatingMargin,
  netProfitMargin,
  marketCap,
  industry,
  sector,
}: KeyFundamentalsProps) {
  const rows = [
    { label: "EPS",              value: eps != null ? `₹${fmtNum(eps)}` : "" },
    { label: "Book Value",       value: bookValue != null ? `₹${fmtNum(bookValue)}` : "" },
    { label: "Face Value",       value: faceValue != null ? `₹${fmtNum(faceValue)}` : "" },
    { label: "Dividend Yield",   value: dividendYield != null ? `${dividendYield.toFixed(2)} %` : "" },
    { label: "Return on Equity", value: roe != null ? `${fmtNum(roe)} %` : "" },
    { label: "ROCE",             value: roce != null ? `${fmtNum(roce)} %` : "" },
    { label: "Operating Margin", value: operatingMargin != null ? `${fmtNum(operatingMargin)} %` : "" },
    { label: "Net Profit Margin", value: netProfitMargin != null ? `${fmtNum(netProfitMargin)} %` : "" },
    { label: "Market Cap",       value: fmtMarketCap(marketCap) },
    { label: "Industry",         value: industry ?? "", highlight: !!industry },
    { label: "Sector",           value: sector ?? "",   highlight: !!sector },
  ].filter((row) => row.value);

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 h-fit">
      <div className="mb-3 flex items-center gap-2.5">
        <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-[0.12em] leading-none">
          Key Fundamentals
        </h3>
        <div className="h-px flex-1 bg-gradient-to-r from-zinc-600/70 to-transparent" />
      </div>
      <div>
        {rows.map((r) => (
          <Row key={r.label} label={r.label} value={r.value} highlight={r.highlight} />
        ))}
      </div>
    </div>
  );
}
