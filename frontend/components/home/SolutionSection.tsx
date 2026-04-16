"use client";

// SolutionSection — 3 alternating feature blocks showing what Stocxi does

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Brain, BarChart2, MessageSquare, TrendingUp, CheckCircle } from "lucide-react";

function Block({
  eyebrow,
  heading,
  sub,
  body,
  graphic,
  reverse = false,
  index,
}: {
  eyebrow: string;
  heading: string;
  sub: string;
  body: string;
  graphic: React.ReactNode;
  reverse?: boolean;
  index: number;
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <div ref={ref} className="py-20">
      <div className={`max-w-6xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 items-center ${reverse ? "lg:[&>*:first-child]:order-2" : ""}`}>
        {/* Text */}
        <motion.div
          initial={{ opacity: 0, x: reverse ? 30 : -30 }}
          animate={inView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.6, delay: index * 0.05, ease: "easeOut" as const }}
        >
          <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 block">
            {eyebrow}
          </span>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white leading-[1.05] mb-2">
            {heading}
          </h2>
          <p className="text-zinc-500 text-xl font-semibold mb-5 tracking-tight">{sub}</p>
          <p className="text-zinc-400 text-base leading-relaxed">{body}</p>
        </motion.div>

        {/* Graphic */}
        <motion.div
          initial={{ opacity: 0, x: reverse ? -30 : 30 }}
          animate={inView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.6, delay: index * 0.05 + 0.12, ease: "easeOut" as const }}
        >
          {graphic}
        </motion.div>
      </div>
    </div>
  );
}

// Mock AI verdict card
function AIVerdictGraphic() {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-zinc-400 text-sm font-medium">
          <Brain className="w-4 h-4" /> AI Analysis
        </div>
        <span className="text-xs text-zinc-600">Medium Risk</span>
      </div>
      <div className="flex flex-col items-center py-4 gap-3">
        <span className="text-xs uppercase tracking-widest text-zinc-500">Final Verdict</span>
        <span className="text-4xl font-black tracking-tighter text-white bg-emerald-500/10 border border-emerald-500/20 px-6 py-2 rounded-xl glow-signal-buy">
          BUY
        </span>
      </div>
      <p className="text-zinc-400 text-sm leading-relaxed border-t border-zinc-800 pt-4">
        Strong fundamentals with ROCE above 20%. Technically bullish with RSI at 58. Social
        sentiment positive across Reddit and Twitter.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {["Fundamentals", "Technicals", "News", "Sentiment"].map((f) => (
          <div key={f} className="rounded-lg bg-zinc-800/50 border border-zinc-700/30 px-3 py-2">
            <div className="text-xs text-zinc-600 mb-1">{f}</div>
            <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> Positive
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Mock technicals card with tooltip
function TechnicalsGraphic() {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 space-y-3">
      <div className="flex items-center gap-2 text-zinc-400 text-sm font-medium mb-2">
        <BarChart2 className="w-4 h-4" /> Technical Indicators
      </div>
      {[
        { label: "RSI (14)", value: "67.2", signal: "Bullish", hint: "67.2 — approaching overbought. Watch for reversal above 70." },
        { label: "MACD", value: "+1.24", signal: "Bullish", hint: "MACD line above signal. Momentum is positive." },
        { label: "ADX", value: "31.4", signal: "Strong", hint: "Above 25. A strong uptrend is in place." },
        { label: "EMA Signal", value: "—", signal: "Above EMA", hint: "Price is trading above its 20-day EMA — uptrend." },
      ].map((ind, i) => (
        <div key={i} className="flex items-center justify-between rounded-lg bg-zinc-800/50 border border-zinc-700/30 px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-zinc-300">{ind.label}</span>
            <span className="w-3.5 h-3.5 rounded-full border border-zinc-600 text-zinc-600 flex items-center justify-center text-[9px] cursor-help">i</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-zinc-400">{ind.value}</span>
            <span className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">{ind.signal}</span>
          </div>
        </div>
      ))}
      {/* Tooltip callout */}
      <div className="mt-2 rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-xs text-zinc-400">
        <span className="text-zinc-300 font-medium">ⓘ RSI explained: </span>
        Measures overbought/oversold levels. Above 70 = possibly overbought.
      </div>
    </div>
  );
}

// Mock sentiment donut (pure SVG)
function SentimentGraphic() {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 space-y-4">
      <div className="flex items-center gap-2 text-zinc-400 text-sm font-medium">
        <MessageSquare className="w-4 h-4" /> Social Sentiment
      </div>
      <div className="flex flex-col items-center gap-4">
        {/* SVG donut */}
        <svg viewBox="0 0 120 120" className="w-28 h-28">
          <circle cx="60" cy="60" r="44" fill="none" stroke="#27272a" strokeWidth="16" />
          <circle
            cx="60" cy="60" r="44" fill="none"
            stroke="#d4d4d8" strokeWidth="16"
            strokeDasharray="165 111"
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
          />
          <circle
            cx="60" cy="60" r="44" fill="none"
            stroke="#52525b" strokeWidth="16"
            strokeDasharray="111 165"
            strokeLinecap="round"
            strokeDashoffset="-165"
            transform="rotate(-90 60 60)"
          />
          <text x="60" y="56" textAnchor="middle" className="font-mono" fill="#ffffff" fontSize="12" fontWeight="bold">+0.42</text>
          <text x="60" y="70" textAnchor="middle" fill="#71717a" fontSize="8">combined</text>
        </svg>
        <div className="flex items-center gap-6 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-zinc-300 inline-block" />Reddit</span>
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-zinc-600 inline-block" />Twitter/X</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-zinc-800/50 border border-zinc-700/30 p-3">
          <div className="text-xs text-orange-400 font-semibold mb-1">r/ Reddit</div>
          <div className="text-xs text-zinc-400">Bullish discussion, strong buying interest noted.</div>
        </div>
        <div className="rounded-xl bg-zinc-800/50 border border-zinc-700/30 p-3">
          <div className="text-xs text-sky-400 font-semibold mb-1">𝕏 Twitter</div>
          <div className="text-xs text-zinc-400">Positive sentiment, trend continues upward.</div>
        </div>
      </div>
    </div>
  );
}

export default function SolutionSection() {
  return (
    <section className="border-t border-zinc-800/50">
      <div className="max-w-6xl mx-auto px-6 pt-20 text-center">
        <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 block">
          The Solution
        </span>
        <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white leading-[1.05]">
          Everything you need.
          <br />
          <span className="text-zinc-500">Nothing you don&apos;t.</span>
        </h2>
      </div>

      <Block
        index={0}
        eyebrow="AI Verdict"
        heading="One clear answer."
        sub="Not 20 metrics. One verdict."
        body="Claude AI reads fundamentals, technicals, and news sentiment to give you a single BUY, HOLD, or AVOID. With a plain-English explanation you can actually understand."
        graphic={<AIVerdictGraphic />}
      />

      <Block
        index={1}
        reverse
        eyebrow="Technical Analysis"
        heading="Technicals, explained for humans."
        sub="Every indicator has a tooltip."
        body="RSI, MACD, Bollinger Bands — each comes with a plain-English explanation. Hover the ⓘ to understand what any number means and why it matters. No finance degree required."
        graphic={<TechnicalsGraphic />}
      />

      <Block
        index={2}
        eyebrow="Social Sentiment"
        heading="Know what the crowd thinks."
        sub="Before you decide."
        body="Reddit and Twitter posts about any stock, scored daily by AI. See if retail investors are bullish or bearish — and track how mood has shifted over the last 7 days."
        graphic={<SentimentGraphic />}
      />
    </section>
  );
}
