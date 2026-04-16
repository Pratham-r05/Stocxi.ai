// StockHeader — company name, price, day range — monochrome visual upgrade

import { Building2, Tag } from "lucide-react";

interface StockHeaderProps {
  symbol: string;
  companyName: string;
  exchange: string | null;
  sector: string | null;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  open: number | null;
  dayHigh: number | null;
  dayLow: number | null;
}


export default function StockHeader({
  symbol,
  companyName,
  exchange,
  sector,
  price,
  change,
  changePercent,
}: StockHeaderProps) {
  const isPositive = change !== null && change >= 0;
  const isNegative = change !== null && change < 0;
  const changeArrow = isPositive ? "▲" : isNegative ? "▼" : null;
  const changeColor = isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-zinc-400";
  const changeBg = isPositive ? "bg-emerald-500/10" : isNegative ? "bg-red-500/10" : "bg-zinc-800/50";

  return (
    <div className="space-y-4">
      {/* Row 1: Company name + Price */}
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white leading-tight">
          {companyName}
        </h1>
        <div className="text-right shrink-0">
          <div className="text-4xl font-black font-mono text-white tracking-tight">
            {price !== null ? `₹${price.toLocaleString("en-IN")}` : "—"}
          </div>
          {changeArrow && change !== null && changePercent !== null && (
            <div className={`inline-flex items-center gap-1 mt-1.5 text-sm font-semibold px-2.5 py-0.5 rounded-full ${changeColor} ${changeBg}`}>
              <span>{changeArrow}</span>
              <span>₹{Math.abs(change).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span>({Math.abs(changePercent).toFixed(2)}%)</span>
            </div>
          )}
        </div>
      </div>

      {/* Row 2: Symbol + Exchange + Sector chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-800/60 px-2.5 py-1 text-xs font-bold text-zinc-200 tracking-wide">
          {symbol}
        </span>
        {exchange && (
          <span className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800/60 px-2.5 py-1 text-xs font-medium text-zinc-400">
            <Building2 className="w-3 h-3" />
            {exchange}
          </span>
        )}
        {sector && (
          <span className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800/60 px-2.5 py-1 text-xs font-medium text-zinc-400">
            <Tag className="w-3 h-3" />
            {sector}
          </span>
        )}
      </div>

    </div>
  );
}
