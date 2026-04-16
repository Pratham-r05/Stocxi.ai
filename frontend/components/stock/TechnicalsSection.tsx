"use client";

// TechnicalsSection — with (i) tooltips and Framer Motion stagger

import { motion, type Variants } from "framer-motion";
import Badge from "@/components/ui/Badge";
import SectionHeader from "@/components/ui/SectionHeader";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

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

const INDICATOR_HELP: Record<string, string> = {
  rsi: "Measures if a stock is overbought or oversold. Above 70 = possibly overbought (may fall). Below 30 = possibly oversold (may rise).",
  macd: "Tracks momentum. When MACD crosses above the signal line, that's typically bullish. Below = bearish.",
  adx: "Measures how strong the current trend is — not its direction. Above 25 = strong trend. Below 20 = weak or sideways.",
  ema: "Exponential Moving Average. If price is above the EMA, the stock is in an uptrend. Below = downtrend.",
  overall: "A combined signal using all indicators above to give one overall technical verdict.",
};

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};
const cardAnim: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

function RSIBar({ rsi }: { rsi: number }) {
  const clamped = Math.min(100, Math.max(0, rsi));
  return (
    <div className="mt-3 relative h-1.5 rounded-full overflow-hidden flex">
      <div className="h-full bg-red-500/50" style={{ width: "30%" }} />
      <div className="h-full bg-zinc-500/40" style={{ width: "40%" }} />
      <div className="h-full bg-emerald-500/50" style={{ width: "30%" }} />
      <span
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-3 rounded-full bg-white shadow-md"
        style={{ left: `${clamped}%` }}
      />
    </div>
  );
}

export default function TechnicalsSection({ technicals }: TechnicalsSectionProps) {
  const { rsi, rsi_signal, macd, macd_signal, adx, adx_signal, ema_signal, overall_signal, ema_20, ema_50, ema_200 } = technicals;
  const fmt = (n: number | null, d = 2) => (n != null ? n.toFixed(d) : "N/A");

  return (
    <section>
      <SectionHeader title="Technical Indicators" />
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 gap-3"
      >
        {/* RSI */}
        <motion.div variants={cardAnim} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-1 flex items-center">
            RSI (14) <InfoTooltip content={INDICATOR_HELP.rsi} />
          </p>
          <p className="font-mono text-sm text-zinc-200 mb-2">{fmt(rsi)}</p>
          <Badge signal={rsi_signal} size="sm" />
          {rsi != null && <RSIBar rsi={rsi} />}
        </motion.div>

        {/* MACD */}
        <motion.div variants={cardAnim} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-1 flex items-center">
            MACD <InfoTooltip content={INDICATOR_HELP.macd} />
          </p>
          <p className="font-mono text-sm text-zinc-200 mb-2">{fmt(macd)}</p>
          <Badge signal={macd_signal} size="sm" />
        </motion.div>

        {/* ADX */}
        <motion.div variants={cardAnim} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-1 flex items-center">
            ADX (14) <InfoTooltip content={INDICATOR_HELP.adx} />
          </p>
          <p className="font-mono text-sm text-zinc-200 mb-2">{fmt(adx)}</p>
          <Badge signal={adx_signal} size="sm" />
        </motion.div>

        {/* EMA Trend */}
        <motion.div variants={cardAnim} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-1 flex items-center">
            EMA Trend <InfoTooltip content={INDICATOR_HELP.ema} />
          </p>
          <p className="font-mono text-xs text-zinc-300 mb-2">
            20: {fmt(ema_20)} | 50: {fmt(ema_50)} | 200: {fmt(ema_200)}
          </p>
          <Badge signal={ema_signal} size="sm" />
        </motion.div>

        {/* Overall */}
        <motion.div variants={cardAnim} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-xs text-zinc-500 mb-2 flex items-center">
            Overall Signal <InfoTooltip content={INDICATOR_HELP.overall} />
          </p>
          <Badge signal={overall_signal} size="md" />
        </motion.div>
      </motion.div>
    </section>
  );
}
