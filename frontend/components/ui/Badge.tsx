type Signal = string | null | undefined;

function getSignalClasses(signal: Signal): string {
  const s = (signal ?? "").toLowerCase();
  if (s === "buy" || s === "bullish" || s === "strong" || s === "positive") {
    return "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
  }
  if (s === "avoid" || s === "bearish" || s === "weak" || s === "negative") {
    return "bg-red-500/15 text-red-400 border border-red-500/30";
  }
  if (s === "hold" || s === "mixed" || s === "neutral") {
    return "bg-zinc-700/50 text-zinc-300 border border-zinc-600/30";
  }
  return "bg-zinc-800/50 text-zinc-500 border border-zinc-700/30";
}

interface BadgeProps {
  signal: Signal;
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export default function Badge({ signal, label, size = "sm", className = "" }: BadgeProps) {
  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-3 py-1 text-sm",
    lg: "px-4 py-1.5 text-base font-bold",
  }[size];
  return (
    <span className={`inline-flex items-center rounded-full font-semibold ${sizeClasses} ${getSignalClasses(signal)} ${className}`}>
      {label ?? signal ?? "—"}
    </span>
  );
}
