"use client";

// InfoTooltip — hover (i) icon with plain-English explanation

import { Info } from "lucide-react";

interface InfoTooltipProps {
  content: string;
}

export function InfoTooltip({ content }: InfoTooltipProps) {
  return (
    <span className="relative group inline-flex items-center ml-1 align-middle">
      <Info className="w-3 h-3 text-zinc-600 cursor-help" />
      <span
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-52 px-3 py-2
          text-xs text-zinc-200 bg-zinc-800 border border-zinc-700 rounded-xl
          opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity
          duration-150 z-50 leading-relaxed shadow-2xl shadow-black/60"
      >
        {content}
        {/* Arrow */}
        <span className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-zinc-700" />
      </span>
    </span>
  );
}
