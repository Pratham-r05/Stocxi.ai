"use client";

// Landing navbar — glass, sticky, auth state aware

import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import { motion } from "framer-motion";

export default function LandingNavbar() {
  const { data: session } = useSession();

  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="fixed top-0 inset-x-0 z-50 glass border-b border-zinc-800/40"
    >
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="text-xl font-black tracking-tighter text-white select-none">
          Stocxi
        </Link>

        {/* Right side */}
        <div className="flex items-center gap-3">
          {session ? (
            <Link
              href="/stock/TCS"
              className="text-sm font-medium text-zinc-300 hover:text-white transition-colors"
            >
              Dashboard →
            </Link>
          ) : (
            <>
              <button
                onClick={() => signIn("google", { callbackUrl: "/" })}
                className="text-sm font-medium text-zinc-400 hover:text-white transition-colors"
              >
                Sign in
              </button>
              <button
                onClick={() => signIn("google", { callbackUrl: "/" })}
                className="text-sm font-semibold bg-white text-zinc-950 rounded-lg px-4 py-1.5 hover:bg-zinc-100 transition-colors"
              >
                Get Started
              </button>
            </>
          )}
        </div>
      </div>
    </motion.header>
  );
}
