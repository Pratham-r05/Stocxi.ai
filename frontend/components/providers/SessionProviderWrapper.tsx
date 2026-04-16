"use client";

// Thin client wrapper so layout.tsx (server) can include SessionProvider
import { SessionProvider } from "next-auth/react";

export function SessionProviderWrapper({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
