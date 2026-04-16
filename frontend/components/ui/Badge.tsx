// Badge — signal-aware with glow for BUY/AVOID

type Signal = string | null | undefined;

function getSignalClasses(signal: Signal): { classes: string; style: React.CSSProperties } {
  const s = (signal ?? "").toLowerCase();
  if (s === "buy" || s === "bullish" || s === "strong" || s === "positive") {
    return {
      classes: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
      style: { boxShadow: "0 0 10px rgba(52,211,153,0.28)" },
    };
  }
  if (s === "avoid" || s === "bearish" || s === "weak" || s === "negative") {
    return {
      classes: "bg-red-500/15 text-red-400 border border-red-500/30",
      style: { boxShadow: "0 0 8px rgba(248,113,113,0.22)" },
    };
  }
  if (s === "hold" || s === "mixed" || s === "neutral") {
    return {
      classes: "bg-zinc-700/50 text-zinc-300 border border-zinc-600/30",
      style: {},
    };
  }
  return {
    classes: "bg-zinc-800/50 text-zinc-500 border border-zinc-700/30",
    style: {},
  };
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

  const { classes, style } = getSignalClasses(signal);

  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold ${sizeClasses} ${classes} ${className}`}
      style={style}
    >
      {label ?? signal ?? "—"}
    </span>
  );
}
