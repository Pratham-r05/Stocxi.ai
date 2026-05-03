"use client";

// TechnicalsSection — 10 professional indicator cards with category badges and (i) tooltips

import { motion, type Variants } from "framer-motion";
import Badge from "@/components/ui/Badge";
import SectionHeader from "@/components/ui/SectionHeader";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

interface TechnicalsSectionProps {
  technicals: {
    rsi: number | null;
    rsi_signal: string | null;
    macd: number | null;
    macd_signal_line: number | null;
    macd_signal: string | null;
    adx: number | null;
    adx_signal: string | null;
    atr: number | null;
    bb_upper: number | null;
    bb_lower: number | null;
    bb_signal: string | null;
    ema_20: number | null;
    ema_50: number | null;
    ema_200: number | null;
    ema_signal: string | null;
    stoch_k: number | null;
    stoch_d: number | null;
    stoch_signal: string | null;
    vwap: number | null;
    vwap_signal: string | null;
    volume_sma_20: number | null;
    overall_signal: string | null;
  };
  currentVolume?: number | null;
}

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};
const cardAnim: Variants = {
  hidden: { opacity: 0, y: 14 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

const CATEGORY_COLORS: Record<string, string> = {
  "Trend":     "bg-blue-500/15 text-blue-400 border-blue-500/25",
  "Momentum":  "bg-amber-500/15 text-amber-400 border-amber-500/25",
  "Volume":    "bg-orange-500/15 text-orange-400 border-orange-500/25",
  "Structure": "bg-purple-500/15 text-purple-400 border-purple-500/25",
  "Volatility":"bg-pink-500/15 text-pink-400 border-pink-500/25",
  "Breadth":   "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  "Pattern":   "bg-zinc-600/40 text-zinc-400 border-zinc-600/40",
};

function CategoryBadge({ category }: { category: string }) {
  const cls = CATEGORY_COLORS[category] ?? "bg-zinc-700/40 text-zinc-400 border-zinc-600/30";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}>
      {category}
    </span>
  );
}

function RuleBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3 rounded-lg bg-zinc-800/60 border border-zinc-700/50 px-3 py-2">
      <p className="text-[11px] text-zinc-400 leading-relaxed">{children}</p>
    </div>
  );
}

function RSIBar({ rsi }: { rsi: number }) {
  const clamped = Math.min(100, Math.max(0, rsi));
  return (
    <div className="mt-3 relative h-1.5 rounded-full overflow-hidden flex">
      <div className="h-full bg-emerald-500/50" style={{ width: "30%" }} />
      <div className="h-full bg-zinc-500/30" style={{ width: "40%" }} />
      <div className="h-full bg-red-500/50"   style={{ width: "30%" }} />
      <span
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-3 rounded-full bg-white shadow-md"
        style={{ left: `${clamped}%` }}
      />
    </div>
  );
}

function signalSummary(
  signal: string | null | undefined,
  bullish: string,
  neutral: string,
  bearish: string,
) {
  const s = (signal ?? "").toLowerCase();
  if (["bullish", "buy", "strong", "positive"].includes(s)) return bullish;
  if (["bearish", "avoid", "weak", "negative"].includes(s)) return bearish;
  return neutral;
}

function explainRsi(rsi: number | null) {
  if (rsi == null) return "RSI data is not available right now, so momentum cannot be judged from this indicator.";
  if (rsi >= 70) return "Momentum is very hot. The stock can still rise, but fresh entries carry higher pullback risk.";
  if (rsi <= 30) return "Momentum is deeply sold off. This zone often attracts bounce trades, but trend confirmation is important.";
  if (rsi >= 60) return "Momentum is healthy and in favor of buyers, without being in extreme overbought territory.";
  if (rsi <= 40) return "Momentum is on the weaker side. Buyers are not fully in control yet.";
  return "Momentum is balanced. The market is neither overheated nor oversold.";
}

function explainAdx(adx: number | null) {
  if (adx == null) return "ADX data is unavailable, so trend strength cannot be confirmed from this card.";
  if (adx >= 25) return "Trend strength is strong. Direction should be taken from other indicators like EMA or MACD.";
  if (adx >= 20) return "Trend strength is building, but not yet decisive.";
  return "Trend is weak or sideways. Breakouts are less reliable in this zone.";
}

function explainAtr(atr: number | null) {
  if (atr == null) return "ATR data is unavailable, so daily risk range cannot be estimated from this card.";
  return `Typical daily movement is around Rs ${atr.toFixed(2)}. Use this as a practical stop-loss distance guide.`;
}

export default function TechnicalsSection({
  technicals,
  currentVolume,
}: TechnicalsSectionProps) {
  const {
    rsi, rsi_signal,
    macd, macd_signal_line, macd_signal,
    adx, adx_signal,
    atr,
    bb_upper, bb_lower, bb_signal,
    ema_20, ema_50, ema_200, ema_signal,
    stoch_k, stoch_d, stoch_signal,
    vwap, vwap_signal,
    volume_sma_20,
    overall_signal,
  } = technicals;

  const fmt = (n: number | null, d = 2) => (n != null ? n.toFixed(d) : "N/A");

  // Volume ratio vs 20-day SMA
  const volRatio =
    currentVolume && volume_sma_20 && volume_sma_20 > 0
      ? (currentVolume / volume_sma_20).toFixed(2)
      : null;
  const volSignal =
    volRatio == null ? "Neutral"
    : parseFloat(volRatio) >= 1.5 ? "Bullish"
    : parseFloat(volRatio) < 0.7  ? "Bearish"
    : "Neutral";
  const volRatioNum = volRatio != null ? parseFloat(volRatio) : null;

  const indicators = [
    {
      num: "01",
      category: "Trend",
      title: "Price vs Moving Averages",
      tooltip: "EMA 20/50/200 show short, medium, and long-term trend. Price above all 3 EMAs = strong uptrend. Below all 3 = downtrend.",
      signal: ema_signal,
      value: ema_20 != null ? (
        <span className="font-mono text-xs text-zinc-300">
          20: {fmt(ema_20)} · 50: {fmt(ema_50)} · 200: {fmt(ema_200)}
        </span>
      ) : null,
      description: "Is the stock above its 20-day, 50-day, and 200-day EMA? The 200 DMA is the single most-watched line on NSE/BSE screens.",
      beginnerSummary: signalSummary(
        ema_signal,
        "Trend structure is healthy: buyers are likely in control across short and long timeframes.",
        "Trend is mixed: some moving averages may support price, but the setup is not fully aligned.",
        "Trend structure is weak: price is likely losing support from key moving averages."
      ),
      rule: "Price above 200 DMA = long-term uptrend. Stay away if price is below all three EMAs.",
    },
    {
      num: "02",
      category: "Momentum",
      title: "RSI (Relative Strength Index)",
      tooltip: "14-period RSI tells you if the stock is overbought (>70) or oversold (<30). Most Indian traders use this daily.",
      signal: rsi_signal,
      value: rsi != null ? (
        <>
          <span className="font-mono text-sm text-zinc-200">{fmt(rsi, 1)}</span>
          <RSIBar rsi={rsi} />
        </>
      ) : null,
      description: "14-period RSI measures momentum. Above 70 = overbought (may reverse). Below 30 = oversold (may bounce).",
      beginnerSummary: explainRsi(rsi),
      rule: "Sweet spot: RSI 40–65 for fresh entries. RSI above 80 = likely near-term reversal risk.",
    },
    {
      num: "03",
      category: "Volume",
      title: "Volume Confirmation",
      tooltip: "Price moves with high volume are genuine; low-volume breakouts on NSE often fail. Compare today's volume to the 20-day average.",
      signal: volSignal,
      value: (
        <div className="space-y-0.5">
          {volume_sma_20 != null && (
            <span className="font-mono text-xs text-zinc-300">
              SMA-20: {volume_sma_20.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
          )}
          {volRatio != null && (
            <div className="font-mono text-xs text-zinc-400">Ratio: {volRatio}×</div>
          )}
        </div>
      ),
      description: "Price moves with high volume are genuine; low-volume breakouts on NSE often fail. Compare today's volume to the 20-day average.",
      beginnerSummary:
        volRatioNum == null
          ? "Volume context is incomplete right now, so treat breakouts with caution."
          : volRatioNum >= 1.5
            ? "Participation is strong: this move has crowd support and is more likely to sustain."
            : volRatioNum < 0.7
              ? "Participation is weak: the move can fade quickly without stronger volume confirmation."
              : "Participation is normal: wait for price and volume to expand together for higher conviction.",
      rule: "Breakout volume should be ≥ 1.5× the 20-day average. Avoid low-volume pumps.",
    },
    {
      num: "04",
      category: "Structure",
      title: "Support & Resistance Levels",
      tooltip: "Bollinger Bands identify dynamic support/resistance. Price near upper band = resistance. Near lower band = support.",
      signal: bb_signal,
      value: bb_upper != null ? (
        <span className="font-mono text-xs text-zinc-300">
          Upper: {fmt(bb_upper)} · Lower: {fmt(bb_lower)}
        </span>
      ) : null,
      description: "Bollinger Bands show dynamic support/resistance. Key price levels where the stock has historically reversed or consolidated.",
      beginnerSummary: signalSummary(
        bb_signal,
        "Price behavior is favoring a support-side bounce or steady upward structure inside the band range.",
        "Price is inside expected band range, which usually means consolidation rather than a strong directional move.",
        "Price action is likely under pressure near resistance or showing weak structure."
      ),
      rule: "Never buy right into strong overhead resistance. Buy near support with a tight stop below.",
    },
    {
      num: "05",
      category: "Momentum",
      title: "MACD (Crossover & Histogram)",
      tooltip: "MACD line crossing above the signal line = bullish momentum. The histogram shows momentum strength — shrinking bars = weakening trend.",
      signal: macd_signal,
      value: macd != null ? (
        <div className="space-y-0.5">
          <span className="font-mono text-sm text-zinc-200">MACD: {fmt(macd, 3)}</span>
          {macd_signal_line != null && (
            <div className="font-mono text-xs text-zinc-400">Signal Line: {fmt(macd_signal_line, 3)}</div>
          )}
        </div>
      ) : null,
      description: "MACD line crossing above the signal line = bullish momentum. Histogram shows momentum strength — shrinking bars = weakening trend.",
      beginnerSummary: signalSummary(
        macd_signal,
        "Momentum is improving and buyers are gaining follow-through.",
        "Momentum is indecisive: trend continuation needs confirmation from price or volume.",
        "Momentum is fading and downside pressure is building."
      ),
      rule: "Look for MACD bullish crossover above the zero line for high-conviction entries.",
    },
    {
      num: "06",
      category: "Volatility",
      title: "ATR (Average True Range)",
      tooltip: "ATR measures how much a stock moves per day on average. Critical for sizing your position and placing stop-losses — especially for F&O stocks.",
      signal: atr != null ? (atr > 0 ? "Neutral" : "Neutral") : "Neutral",
      value: atr != null ? (
        <span className="font-mono text-sm text-zinc-200">₹{fmt(atr)}</span>
      ) : null,
      description: "ATR measures how much a stock moves per day on average. Critical for sizing your position and placing stop-losses — especially for F&O stocks.",
      beginnerSummary: explainAtr(atr),
      rule: "Set stop-loss at 1–1.5× ATR from entry. Don't risk more than 1–2% of capital per trade.",
    },
    {
      num: "07",
      category: "Breadth",
      title: "ADX — Trend Strength",
      tooltip: "ADX measures how strong the current trend is — not its direction. Above 25 = strong trend. Below 20 = weak or sideways.",
      signal: adx_signal,
      value: adx != null ? (
        <span className="font-mono text-sm text-zinc-200">{fmt(adx, 1)}</span>
      ) : null,
      description: "ADX measures the strength of a trend regardless of direction. A rising ADX above 25 confirms the trend is gathering momentum.",
      beginnerSummary: explainAdx(adx),
      rule: "ADX > 25 = trending — trade with the trend. ADX < 20 = range-bound — consider range strategies.",
    },
    {
      num: "08",
      category: "Momentum",
      title: "Stochastic Oscillator",
      tooltip: "Stochastic %K and %D lines show overbought/oversold conditions. Both above 80 = overbought. Both below 20 = oversold. %K crossing %D is a trade signal.",
      signal: stoch_signal,
      value: stoch_k != null ? (
        <div className="space-y-0.5">
          <span className="font-mono text-sm text-zinc-200">%K: {fmt(stoch_k, 1)}</span>
          {stoch_d != null && (
            <div className="font-mono text-xs text-zinc-400">%D: {fmt(stoch_d, 1)}</div>
          )}
        </div>
      ) : null,
      description: "Stochastic compares current closing price to the price range over a lookback period. Popular with swing traders on NSE.",
      beginnerSummary: stoch_k == null
        ? "Stochastic data is unavailable right now."
        : stoch_k >= 80
          ? "Momentum is in overbought territory — avoid chasing the move; wait for a pullback before entering."
          : stoch_k <= 20
            ? "Momentum is in oversold territory — potential for a bounce, but confirm with price action first."
            : "Momentum is in a neutral zone — neither stretched to the upside nor the downside.",
      rule: "Buy when %K crosses above %D below 20. Avoid when both lines are above 80.",
    },
    {
      num: "09",
      category: "Trend",
      title: "VWAP (Volume-Weighted Average Price)",
      tooltip: "VWAP is the average price weighted by volume. Institutional traders use it as a benchmark — price above VWAP is bullish intraday.",
      signal: vwap_signal,
      value: vwap != null ? (
        <span className="font-mono text-sm text-zinc-200">₹{fmt(vwap, 2)}</span>
      ) : null,
      description: "VWAP combines price and volume data. Institutions benchmark orders against VWAP — sustained price above VWAP signals buying pressure.",
      beginnerSummary: vwap == null
        ? "VWAP data is unavailable. This indicator needs intraday OHLCV data."
        : (vwap_signal ?? "neutral").toLowerCase() === "bullish"
          ? "Price is above VWAP — institutional buying pressure is likely favoring the upside."
          : "Price is below VWAP — institutional activity is likely on the sell side; caution advised.",
      rule: "For intraday: buy pullbacks to VWAP in an uptrend. Don't short a stock that keeps bouncing at VWAP.",
    },
    {
      num: "10",
      category: "Structure",
      title: "Overall Technical Signal",
      tooltip: "A combined signal using RSI, MACD, and EMA to give one overall technical verdict for this stock.",
      signal: overall_signal,
      value: null,
      description: "Combines RSI momentum, MACD crossover, and EMA trend alignment to give a consolidated view of the stock's technical health.",
      beginnerSummary: signalSummary(
        overall_signal,
        "Most major technical components are aligned in favor of upside continuation.",
        "Signals are mixed. Wait for clearer alignment before taking aggressive positions.",
        "Several technical components are warning of weakness; protect capital first."
      ),
      rule: "Use as a starting filter — a Bullish signal with high-volume confirmation and trend support is the strongest setup.",
    },
  ];

  return (
    <section>
      <SectionHeader title="Technical Indicators" />
      <div className="mb-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-3 py-2.5">
        <p className="text-[10px] uppercase tracking-wide text-cyan-300/80 font-semibold">Beginner Quick Read</p>
        <p className="mt-1 text-xs text-zinc-300 leading-relaxed">
          Start with the signal badge, then read the <span className="text-zinc-100 font-medium">What this means now</span> note.
          Use the <span className="text-zinc-100 font-medium">Learn</span> button to understand each indicator in plain language.
        </p>
      </div>
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 gap-3"
      >
        {indicators.map((ind) => (
          <motion.div
            key={ind.num}
            variants={cardAnim}
            className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 transition-colors"
          >
            {/* Top row: category badge + number */}
            <div className="flex items-center justify-between mb-2">
              <CategoryBadge category={ind.category} />
              <span className="text-zinc-700 text-xs font-bold font-mono">{ind.num}</span>
            </div>

            {/* Title with (i) */}
            <div className="flex items-center gap-1 mb-2">
              <h4 className="text-sm font-semibold text-zinc-100">{ind.title}</h4>
              <InfoTooltip
                title="Beginner explanation"
                label="Learn"
                content={ind.tooltip}
              />
            </div>

            {/* Live value */}
            {ind.value && <div className="mb-2">{ind.value}</div>}

            {/* Signal badge */}
            <Badge signal={ind.signal} size="sm" />

            {/* Description */}
            <p className="mt-2.5 text-[11px] text-zinc-500 leading-relaxed">
              {ind.description}
            </p>

            <div className="mt-2.5 rounded-lg border border-zinc-700/50 bg-zinc-800/45 px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-zinc-400">What this means now</p>
              <p className="mt-1 text-xs text-zinc-200 leading-relaxed">{ind.beginnerSummary}</p>
            </div>

            {/* Rule box */}
            <RuleBox>
              <span className="font-semibold text-zinc-300">Rule: </span>
              {ind.rule}
            </RuleBox>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
