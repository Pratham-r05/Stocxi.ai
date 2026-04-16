"use client";

// HowItWorksSection — 3-step numbered flow

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Search, Brain, CheckCircle } from "lucide-react";

const steps = [
  {
    num: "01",
    Icon: Search,
    label: "Search any stock",
    body: "Type any NSE or BSE symbol. RELIANCE, TCS, HDFC — whatever you want to analyse.",
  },
  {
    num: "02",
    Icon: Brain,
    label: "AI analyses everything",
    body: "Our system reads fundamentals, calculates technicals, scans news, and checks social sentiment — in seconds.",
  },
  {
    num: "03",
    Icon: CheckCircle,
    label: "Get your verdict",
    body: "Receive a clear BUY, HOLD, or AVOID with a plain-English explanation tailored to your risk level.",
  },
];

export default function HowItWorksSection() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section id="how-it-works" ref={ref} className="py-24 border-t border-zinc-800/50">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16">
          <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 block">
            How It Works
          </span>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white">
            Three steps.
            <br />
            <span className="text-zinc-500">Thirty seconds.</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
          {/* Connecting dashes — desktop only */}
          <div className="hidden md:block absolute top-10 left-[38%] right-[38%] border-t border-dashed border-zinc-800" />

          {steps.map((step, i) => (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, y: 24 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: i * 0.12, ease: "easeOut" as const }}
              className="relative rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 flex flex-col gap-5"
            >
              {/* Number */}
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full border border-zinc-700 bg-zinc-800 flex items-center justify-center">
                  <step.Icon className="w-4 h-4 text-zinc-300" />
                </div>
                <span className="font-mono text-xs text-zinc-600 font-bold tracking-widest">{step.num}</span>
              </div>

              <div>
                <h3 className="text-lg font-bold text-white mb-2">{step.label}</h3>
                <p className="text-zinc-500 text-sm leading-relaxed">{step.body}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
