import SearchBar from "@/components/home/SearchBar";
import TrendingChips from "@/components/home/TrendingChips";

export default function Home() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4">
      {/* Main content column */}
      <div className="w-full max-w-lg space-y-8">
        {/* Logo area */}
        <div className="space-y-2 text-center">
          <h1 className="text-5xl font-bold tracking-tight">
            <span className="bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
              Stocxi
            </span>
          </h1>
          <p className="text-base text-zinc-400">
            AI-powered analysis for Indian stocks — fundamentals, technicals &amp; sentiment.
          </p>
        </div>

        {/* Search bar */}
        <SearchBar />

        {/* Trending chips */}
        <TrendingChips />
      </div>

      {/* Footer */}
      <p className="absolute bottom-6 left-0 right-0 text-center text-xs text-zinc-600">
        Not financial advice. Data for educational purposes only.
      </p>
    </div>
  );
}
