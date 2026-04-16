"use client";

// ProblemSection — "Most people look at a stock and see noise."

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

// Fake data grid to visualise information overload
const fakeMetrics = [
  ["EBITDA", "12,430 Cr", "↑ 4.2%"],
  ["D/E Ratio", "0.34", "Stable"],
  ["RSI(14)", "67.2", "Overbought"],
  ["MACD", "-2.41", "Bearish"],
  ["PEG Ratio", "1.82", "Fair"],
  ["ADX", "28.9", "Strong"],
  ["Beta", "0.91", "Low"],
  ["EV/EBITDA", "14.3x", "—"],
  ["Promoter %", "52.11", "↓ 0.3"],
  ["FII %", "21.3", "↑ 2.1"],
  ["Pledged", "1.2%", "Low"],
  ["BB Upper", "3,940", "Near"],
];

export default function ProblemSection() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="py-24 px-6 overflow-hidden">
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          {/* Left — text */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, ease: "easeOut" as const }}
          >
            <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-4 block">
              The Problem
            </span>
            <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white leading-[1.05] mb-6">
              Most people look at a stock
              <br />
              <span className="text-zinc-500">and see noise.</span>
            </h2>
            <p className="text-zinc-400 text-lg leading-relaxed mb-4">
              Earnings. PE ratio. MACD. Bollinger Bands. RSI. Promoter holding. ROCE. EV/EBITDA.
            </p>
            <p className="text-zinc-500 text-base leading-relaxed">
              It&apos;s too much. And none of it directly tells you{" "}
              <span className="text-white">whether to buy</span> — especially if you&apos;re not a
              finance professional.
            </p>
          </motion.div>

          {/* Right — info overload graphic */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.15, ease: "easeOut" as const }}
            className="relative"
          >
            <div className="relative rounded-2xl border border-zinc-800 bg-zinc-900 p-5 overflow-hidden">
              {/* Fake terminal header */}
              <div className="flex items-center gap-1.5 mb-4">
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <span className="ml-2 text-xs text-zinc-600 font-mono">RELIANCE.NS — Analysis</span>
              </div>

              {/* Overloaded data grid */}
              <div className="grid grid-cols-3 gap-1.5 font-mono text-xs">
                {fakeMetrics.map(([label, val, note], i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-zinc-800/60 border border-zinc-700/40 p-2"
                  >
                    <div className="text-zinc-600 text-[10px] mb-0.5 truncate">{label}</div>
                    <div className="text-zinc-300 font-semibold truncate">{val}</div>
                    <div className="text-zinc-600 text-[10px] truncate">{note}</div>
                  </div>
                ))}
              </div>

              {/* Confused overlay annotation */}
              <div className="absolute bottom-4 right-4 bg-black/90 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-400 max-w-[140px] text-center shadow-xl">
                😵 <br />
                <span className="text-zinc-500">What does this even mean?</span>
              </div>

              {/* Right fade */}
              <div className="absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-black to-transparent pointer-events-none" />
              {/* Bottom fade */}
              <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black to-transparent pointer-events-none" />
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
