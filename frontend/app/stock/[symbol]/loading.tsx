// Loading UI for /stock/[symbol] — shown automatically by Next.js during server fetch

export default function StockLoading() {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-6">
      <div className="flex flex-col items-center gap-6">
        {/* Animated ring loader */}
        <div className="relative w-20 h-20">
          <div className="absolute inset-0 rounded-full border-2 border-zinc-800" />
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-white border-r-white/60 animate-spin" />
          <div className="absolute inset-2 rounded-full border-2 border-transparent border-b-zinc-500 border-l-zinc-500 animate-spin [animation-direction:reverse] [animation-duration:1.5s]" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
          </div>
        </div>

        {/* Text */}
        <div className="flex flex-col items-center gap-1.5">
          <p className="text-sm font-semibold text-zinc-200 tracking-wide">
            Fetching stock data
          </p>
          <p className="text-xs text-zinc-500">
            Loading prices, fundamentals, and AI insights…
          </p>
        </div>

        {/* Shimmer dots */}
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-600 animate-bounce [animation-delay:-0.3s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:-0.15s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-bounce" />
        </div>
      </div>
    </div>
  );
}
