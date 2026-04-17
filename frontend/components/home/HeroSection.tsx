"use client";

// Hero — "We built an AI that reads stocks so you don't have to."

import { motion } from "framer-motion";
import Link from "next/link";
import SearchBar from "./SearchBar";
import TrendingChips from "./TrendingChips";

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
};
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: "easeOut" as const } },
};

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-20 overflow-hidden">
      {/* Radial top glow */}
      <div className="hero-glow absolute inset-x-0 top-0 h-[500px]" />

      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="relative z-10 w-full max-w-2xl flex flex-col items-center text-center"
      >
        {/* Badge */}
        <motion.div variants={item}>
          <span className="inline-flex items-center gap-1.5 border border-zinc-700/60 bg-zinc-900/60 text-zinc-400 text-xs px-3 py-1.5 rounded-full mb-8 tracking-wide">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            Built for Indian Markets · NSE &amp; BSE
          </span>
        </motion.div>

        {/* Headline */}
        <motion.h1 variants={item} className="text-5xl sm:text-7xl font-black tracking-tighter leading-[0.9] mb-2">
          <span className="text-white">Markets, decoded.</span>
          <br />
          <span className="text-white">Decisions, clarified.</span>
        </motion.h1>
        <motion.h1 variants={item} className="text-5xl sm:text-7xl font-black tracking-tighter leading-[0.9] text-zinc-500 mb-8">
          Stocxi reads. You decide.
        </motion.h1>

        {/* Sub */}
        <motion.p variants={item} className="text-zinc-400 text-lg leading-relaxed max-w-lg mb-10">
          One AI. One verdict —{" "}
          <span className="text-white font-semibold">BUY</span>,{" "}
          <span className="text-zinc-300 font-semibold">HOLD</span>, or{" "}
          <span className="text-white font-semibold">AVOID</span>. Crunched from fundamentals, technicals,
          and the pulse of the internet.
        </motion.p>

        {/* Search */}
        <motion.div variants={item} className="w-full max-w-xl mb-4">
          <SearchBar />
        </motion.div>

        {/* Trending */}
        <motion.div variants={item} className="w-full max-w-xl">
          <TrendingChips />
        </motion.div>

        {/* CTA */}
        <motion.div variants={item} className="mt-10 flex items-center gap-4">
          <Link
            href="#how-it-works"
            className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            See how it works ↓
          </Link>
        </motion.div>
      </motion.div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-black to-transparent pointer-events-none" />
    </section>
  );
}
