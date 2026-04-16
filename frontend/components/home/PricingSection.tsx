"use client";

// PricingSection — Free / Pro / Max plans

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Check, Lock } from "lucide-react";
import Link from "next/link";

const freeFeatures = [
  "Full stock overview — price, fundamentals",
  "Technical indicators with tooltips",
  "BSE corporate announcements",
  "Recent news headlines",
  "BUY / HOLD / AVOID signal",
  "3 total stock analyses",
];

const proFeatures = [
  "Everything in Free",
  "Unlimited stock analyses",
  "Deep AI analysis across 3 risk levels",
  "Social sentiment — Reddit & Twitter",
  "7-day sentiment trend chart",
  "Price history chart (1M, 3M, 6M, 1Y)",
  "Quarterly & annual financial tables",
  "Priority analysis refresh",
];

const maxFeatures = [
  "Everything in Pro",
  "Mutual fund analysis",
  "Advanced fund filters & comparison",
  "Portfolio overlap detection",
  "Risk-adjusted fund scoring",
  "All premium features unlocked",
];

interface PricingCardProps {
  plan: string;
  price: string;
  period?: string;
  features: string[];
  highlighted?: boolean;
  comingSoon?: boolean;
  cta: React.ReactNode;
  badge?: string;
  delay: number;
}

function PricingCard({
  plan,
  price,
  period,
  features,
  highlighted,
  comingSoon,
  cta,
  badge,
  delay,
}: PricingCardProps) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 28 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, delay, ease: "easeOut" as const }}
      className={`relative rounded-2xl p-8 flex flex-col gap-6 ${
        highlighted
          ? "border border-zinc-600 bg-zinc-900"
          : comingSoon
          ? "border border-zinc-800/60 bg-zinc-900/20 opacity-70"
          : "border border-zinc-800 bg-zinc-900/40"
      }`}
    >
      {badge && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-white text-zinc-950 text-xs font-bold px-3 py-1 rounded-full tracking-wide">
            {badge}
          </span>
        </div>
      )}

      {comingSoon && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-zinc-700 text-zinc-300 text-xs font-bold px-3 py-1 rounded-full tracking-wide flex items-center gap-1.5">
            <Lock className="w-3 h-3" /> COMING SOON
          </span>
        </div>
      )}

      <div>
        <div className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-2">{plan}</div>
        <div className="flex items-end gap-1">
          <span className="text-5xl font-black tracking-tighter text-white">{price}</span>
          {period && <span className="text-zinc-500 text-sm mb-2">{period}</span>}
        </div>
      </div>

      <ul className="space-y-3 flex-1">
        {features.map((f, i) => (
          <li key={i} className={`flex items-start gap-2.5 text-sm ${comingSoon ? "text-zinc-600" : "text-zinc-400"}`}>
            <Check className={`w-4 h-4 mt-0.5 shrink-0 ${comingSoon ? "text-zinc-700" : "text-zinc-300"}`} />
            {f}
          </li>
        ))}
      </ul>

      {cta}
    </motion.div>
  );
}

export default function PricingSection() {
  return (
    <section className="py-24 border-t border-zinc-800/50">
      <div className="max-w-5xl mx-auto px-6">
        <div className="text-center mb-16">
          <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 block">
            Pricing
          </span>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white mb-4">
            Simple, honest pricing.
          </h2>
          <p className="text-zinc-500">Start free. Upgrade when you need more.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Free */}
          <PricingCard
            plan="Free"
            price="₹0"
            features={freeFeatures}
            delay={0}
            cta={
              <Link
                href="/"
                className="w-full block text-center rounded-xl py-3 text-sm font-semibold border border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-white transition-colors"
              >
                Start Free →
              </Link>
            }
          />

          {/* Pro */}
          <PricingCard
            plan="Pro"
            price="₹199"
            period="/ month"
            features={proFeatures}
            highlighted
            badge="MOST POPULAR"
            delay={0.1}
            cta={
              <button
                disabled
                className="w-full rounded-xl py-3 text-sm font-semibold bg-white text-zinc-950 opacity-50 cursor-not-allowed"
              >
                Coming Soon
              </button>
            }
          />

          {/* Max */}
          <PricingCard
            plan="Max"
            price="₹499"
            period="/ month"
            features={maxFeatures}
            comingSoon
            delay={0.2}
            cta={
              <button
                disabled
                className="w-full rounded-xl py-3 text-sm font-semibold border border-zinc-800 text-zinc-600 cursor-not-allowed"
              >
                Coming Soon
              </button>
            }
          />
        </div>

        <p className="mt-8 text-center text-xs text-zinc-700">
          Free plan gives you 3 analyses to try. Paid plans launch soon — early users get priority access.
        </p>
      </div>
    </section>
  );
}
