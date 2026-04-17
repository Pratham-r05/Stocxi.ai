"use client";

// InfoTooltip — hover (i) icon with plain-English explanation

import { Info } from "lucide-react";

interface InfoTooltipProps {
  content: string;
  title?: string;
  label?: string;
  className?: string;
}

export function InfoTooltip({ content, title, label, className = "" }: InfoTooltipProps) {
  const ariaLabel = title ? `${title}: ${content}` : content;
  const triggerClass = label
    ? "inline-flex items-center gap-1 rounded-md border border-zinc-700/60 bg-zinc-800/55 px-1.5 py-0.5 text-[10px] text-zinc-400"
    : "inline-flex items-center text-zinc-600";
  const tooltipWidthClass = label ? "w-64" : "w-52";

  return (
    <span className={`relative group inline-flex items-center ml-1 align-middle ${className}`}>
      <button
        type="button"
        aria-label={ariaLabel}
        className={`${triggerClass} transition-colors hover:text-zinc-200 hover:border-zinc-600 focus:outline-none focus:ring-2 focus:ring-zinc-500/50`}
      >
        <Info className="w-3 h-3" />
        {label ? <span className="font-medium">{label}</span> : null}
      </button>
      <span
        className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 ${tooltipWidthClass} px-3 py-2
          text-xs text-zinc-200 bg-zinc-800 border border-zinc-700 rounded-xl
          opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-events-none transition-opacity
          duration-150 z-50 leading-relaxed shadow-2xl shadow-black/60`}
      >
        {title ? <span className="block text-[10px] uppercase tracking-wide text-zinc-400 mb-1">{title}</span> : null}
        {content}
        {/* Arrow */}
        <span className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-zinc-700" />
      </span>
    </span>
  );
}
