import Badge from "@/components/ui/Badge";
import SectionHeader from "@/components/ui/SectionHeader";

interface TechnicalsSectionProps {
  technicals: {
    rsi: number | null;
    rsi_signal: string;
    macd: number | null;
    macd_signal: string;
    adx: number | null;
    adx_signal: string;
    atr: number | null;
    bb_upper: number | null;
    bb_lower: number | null;
    bb_signal: string;
    ema_20: number | null;
    ema_50: number | null;
    ema_200: number | null;
    ema_signal: string;
    volume_sma_20: number | null;
    overall_signal: string;
  };
}

function IndicatorCard({
  label,
  value,
  signal,
  size = "sm",
  className = "",
  children,
}: {
  label: string;
  value?: string | null;
  signal: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900 p-4 ${className}`}>
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      {value != null && (
        <p className="font-mono text-sm text-zinc-200 mb-2">{value}</p>
      )}
      <Badge signal={signal} size={size} />
      {children}
    </div>
  );
}

function RSIBar({ rsi }: { rsi: number }) {
  // Clamp rsi to 0-100 range for safety
  const clamped = Math.min(100, Math.max(0, rsi));
  const pct = clamped; // 0-100 directly maps to 0%-100%

  return (
    <div className="mt-3 relative h-1.5 rounded-full overflow-hidden flex">
      {/* Zone 0-30: red */}
      <div className="h-full bg-red-500/60" style={{ width: "30%" }} />
      {/* Zone 30-70: zinc */}
      <div className="h-full bg-zinc-500/60" style={{ width: "40%" }} />
      {/* Zone 70-100: emerald */}
      <div className="h-full bg-emerald-500/60" style={{ width: "30%" }} />
      {/* Marker */}
      <span
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-3 rounded-full bg-white shadow"
        style={{ left: `${pct}%` }}
      />
    </div>
  );
}

export default function TechnicalsSection({ technicals }: TechnicalsSectionProps) {
  const {
    rsi, rsi_signal,
    macd, macd_signal,
    adx, adx_signal,
    ema_signal,
    bb_signal,
    overall_signal,
  } = technicals;

  const fmt = (n: number | null, decimals = 2) =>
    n != null ? n.toFixed(decimals) : null;

  return (
    <section>
      <SectionHeader title="Technical Indicators" />
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">

        {/* RSI(14) */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-1">RSI (14)</p>
          {rsi != null && (
            <p className="font-mono text-sm text-zinc-200 mb-2">{fmt(rsi)}</p>
          )}
          <Badge signal={rsi_signal} size="sm" />
          {rsi != null && <RSIBar rsi={rsi} />}
        </div>

        {/* MACD */}
        <IndicatorCard
          label="MACD"
          value={fmt(macd)}
          signal={macd_signal}
        />

        {/* ADX(14) */}
        <IndicatorCard
          label="ADX (14)"
          value={fmt(adx)}
          signal={adx_signal}
        />

        {/* EMA Signal */}
        <IndicatorCard
          label="EMA Signal"
          signal={ema_signal}
        />

        {/* BB Signal */}
        <IndicatorCard
          label="BB Signal"
          signal={bb_signal}
        />

        {/* Overall — spans 2 cols on mobile, 1 on sm+ */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 col-span-2 sm:col-span-1">
          <p className="text-xs text-zinc-500 mb-2">Overall Signal</p>
          <Badge signal={overall_signal} size="md" />
        </div>

      </div>
    </section>
  );
}
