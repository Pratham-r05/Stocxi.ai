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

function fmt(value: number | null): string {
  if (value === null) return "—";
  return value.toLocaleString("en-IN");
}

export default function StockHeader({
  symbol,
  companyName,
  exchange,
  sector,
  price,
  change,
  changePercent,
  open: _open,
  dayHigh,
  dayLow,
}: StockHeaderProps) {
  const isPositive = change !== null && change >= 0;
  const isNegative = change !== null && change < 0;

  const changeArrow = isPositive ? "▲" : isNegative ? "▼" : null;
  const changeColor = isPositive
    ? "text-emerald-400"
    : isNegative
    ? "text-red-400"
    : "text-zinc-400";

  const showDayRange =
    dayHigh !== null && dayLow !== null && price !== null && dayHigh !== dayLow;
  const dotPercent = showDayRange
    ? Math.min(
        100,
        Math.max(0, ((price! - dayLow!) / (dayHigh! - dayLow!)) * 100)
      )
    : 50;

  return (
    <div className="space-y-3">
      {/* Row 1: Company name + Price */}
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl font-bold text-zinc-50 leading-tight">
          {companyName}
        </h1>
        <div className="text-right shrink-0">
          <div className="text-3xl font-semibold text-zinc-50">
            {price !== null ? `₹${fmt(price)}` : "—"}
          </div>
          {changeArrow && change !== null && changePercent !== null && (
            <div className={`text-sm font-medium mt-0.5 ${changeColor}`}>
              {changeArrow} ₹{Math.abs(change).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{" "}
              ({Math.abs(changePercent).toFixed(2)}%)
            </div>
          )}
        </div>
      </div>

      {/* Row 2: Symbol + Exchange + Sector chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded-full bg-zinc-700 px-2.5 py-0.5 text-xs font-semibold text-zinc-200">
          {symbol}
        </span>
        {exchange && (
          <span className="inline-flex items-center rounded-full bg-zinc-700 px-2.5 py-0.5 text-xs font-semibold text-zinc-200">
            {exchange}
          </span>
        )}
        {sector && (
          <span className="inline-flex items-center rounded-full bg-zinc-700 px-2.5 py-0.5 text-xs font-semibold text-zinc-200">
            {sector}
          </span>
        )}
      </div>

      {/* Row 3: Day range bar */}
      {showDayRange && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>Day Range</span>
            <span>
              ₹{fmt(dayLow)} — ₹{fmt(dayHigh)}
            </span>
          </div>
          <div className="relative h-1.5 w-full rounded-full bg-zinc-700">
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-3 rounded-full bg-zinc-100 border-2 border-zinc-400 shadow"
              style={{ left: `${dotPercent}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span>₹{fmt(dayLow)}</span>
            <span className={`font-semibold ${changeColor}`}>
              ₹{fmt(price)}
            </span>
            <span>₹{fmt(dayHigh)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
