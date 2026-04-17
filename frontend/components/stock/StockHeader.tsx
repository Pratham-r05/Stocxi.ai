// StockHeader — company name, price, day range — monochrome visual upgrade

import { Building2, Tag } from "lucide-react";

interface StockHeaderProps {
  symbol: string;
  companyName: string;
  logoUrl?: string | null;
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
  logoUrl,
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
    <div className="space-y-3 sm:space-y-4">
      {/* Mobile: stack logo+name on top, price+change below. Desktop: side-by-side. */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4">
        {/* Logo + company name */}
        <div className="flex items-center gap-3 min-w-0 sm:flex-1">
          <div className="w-11 h-11 sm:w-16 sm:h-16 rounded-xl sm:rounded-2xl border border-zinc-700/80 bg-zinc-900 overflow-hidden shrink-0 flex items-center justify-center p-1.5">
            {logoUrl ? (
              <div className="w-full h-full rounded-lg sm:rounded-xl bg-white p-1">
                <img
                  src={logoUrl}
                  alt={`${companyName} logo`}
                  className="w-full h-full object-contain"
                  loading="eager"
                  referrerPolicy="no-referrer"
                />
              </div>
            ) : (
              <span className="text-sm sm:text-base font-bold text-zinc-300">{symbol.slice(0, 2)}</span>
            )}
          </div>
          <h1 className="text-base sm:text-3xl font-black tracking-tight text-white leading-tight truncate min-w-0 flex-1">
            {companyName}
          </h1>
        </div>

        {/* Price + change */}
        <div className="flex items-baseline sm:flex-col sm:items-end gap-2 sm:gap-0 min-w-0 sm:shrink-0">
          <div className="text-2xl sm:text-4xl font-black font-mono text-white tracking-tight whitespace-nowrap">
            {price !== null ? `₹${price.toLocaleString("en-IN")}` : "—"}
          </div>
          {changeArrow && change !== null && changePercent !== null && (
            <div className={`inline-flex items-center gap-1 sm:mt-1.5 text-xs sm:text-sm font-semibold px-2 sm:px-2.5 py-0.5 rounded-full whitespace-nowrap ${changeColor} ${changeBg}`}>
              <span>{changeArrow}</span>
              <span>₹{Math.abs(change).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span>({Math.abs(changePercent).toFixed(2)}%)</span>
            </div>
          )}
        </div>
      </div>

      {/* Symbol + Exchange + Sector chips */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <span className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-800/60 px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-bold text-zinc-200 tracking-wide">
          {symbol}
        </span>
        {exchange && (
          <span className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800/60 px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-medium text-zinc-400">
            <Building2 className="w-3 h-3" />
            {exchange}
          </span>
        )}
        {sector && (
          <span className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-800/60 px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-medium text-zinc-400 max-w-full truncate">
            <Tag className="w-3 h-3 shrink-0" />
            <span className="truncate">{sector}</span>
          </span>
        )}
      </div>

    </div>
  );
}
