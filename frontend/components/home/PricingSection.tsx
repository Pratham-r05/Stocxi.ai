"use client";

// PricingSection — $10 Basic / $25 Pro

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Check } from "lucide-react";
import { signIn } from "next-auth/react";

const basicFeatures = [
  "Full stock overview — price, fundamentals",
  "Technical indicators with plain-English tooltips",
  "BSE corporate announcements",
  "Recent news headlines",
  "BUY / HOLD / AVOID signal (standard)",
  "Quarterly & annual financial tables",
];

const proFeatures = [
  "Everything in Basic",
  "Deep AI analysis across 3 risk levels",
  "Social sentiment — Reddit & Twitter",
  "7-day sentiment trend chart",
  "Price history chart (1M, 3M, 6M, 1Y)",
  "Priority analysis refresh",
];

function PricingCard({
  plan,
  price,
  features,
  highlighted,
  delay,
}: {
  plan: string;
  price: string;
  features: string[];
  highlighted?: boolean;
  delay: number;
}) {
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
          : "border border-zinc-800 bg-zinc-900/40"
      }`}
    >
      {highlighted && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-white text-zinc-950 text-xs font-bold px-3 py-1 rounded-full tracking-wide">
            MOST POPULAR
          </span>
        </div>
      )}

      <div>
        <div className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-2">{plan}</div>
        <div className="flex items-end gap-1">
          <span className="text-5xl font-black tracking-tighter text-white">{price}</span>
          <span className="text-zinc-500 text-sm mb-2">/ month</span>
        </div>
      </div>

      <ul className="space-y-3 flex-1">
        {features.map((f, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-zinc-400">
            <Check className="w-4 h-4 text-zinc-300 mt-0.5 shrink-0" />
            {f}
          </li>
        ))}
      </ul>

      <button
        onClick={() => signIn("google", { callbackUrl: "/" })}
        className={`w-full rounded-xl py-3 text-sm font-semibold transition-colors ${
          highlighted
            ? "bg-white text-zinc-950 hover:bg-zinc-100"
            : "border border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-white"
        }`}
      >
        Get Started →
      </button>
    </motion.div>
  );
}

export default function PricingSection() {
  return (
    <section className="py-24 border-t border-zinc-800/50">
      <div className="max-w-4xl mx-auto px-6">
        <div className="text-center mb-16">
          <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 block">
            Pricing
          </span>
          <h2 className="text-4xl sm:text-5xl font-black tracking-tighter text-white mb-4">
            Simple, honest pricing.
          </h2>
          <p className="text-zinc-500">Pick the plan that fits how deep you want to go.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <PricingCard
            plan="Basic"
            price="$10"
            features={basicFeatures}
            highlighted
            delay={0}
          />
          <PricingCard
            plan="Pro"
            price="$25"
            features={proFeatures}
            delay={0.1}
          />
        </div>

        <p className="mt-8 text-center text-xs text-zinc-700">
          Payment integration coming soon. Plans shown are indicative — early users get free access.
        </p>
      </div>
    </section>
  );
}
