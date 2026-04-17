"use client";

import { useEffect, useRef } from "react";
import { useSession } from "next-auth/react";

export default function TrackStockSearch({ symbol }: { symbol: string }) {
  const { data: session, status } = useSession();
  const lastSentSymbol = useRef<string | null>(null);

  useEffect(() => {
    if (status !== "authenticated" || !session?.user?.email) return;

    const normalizedSymbol = symbol.trim().toUpperCase();
    if (!normalizedSymbol) return;

    if (lastSentSymbol.current === normalizedSymbol) return;
    lastSentSymbol.current = normalizedSymbol;

    void fetch("/api/user/stock-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: normalizedSymbol }),
      keepalive: true,
    });
  }, [session?.user?.email, status, symbol]);

  return null;
}
