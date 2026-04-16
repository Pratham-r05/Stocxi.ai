// LandingFooter — minimal, monochrome

export default function LandingFooter() {
  return (
    <footer className="border-t border-zinc-800/50 py-10">
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-lg font-black tracking-tighter text-white">Stocxi</span>
          <span className="text-zinc-700 hidden sm:block">·</span>
          <span className="text-xs text-zinc-600">AI-powered stock analysis for Indian markets</span>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-4 text-xs text-zinc-700">
          <span>Not financial advice. For educational use only.</span>
          <span className="hidden sm:block">·</span>
          <span>© 2025 Stocxi</span>
        </div>
      </div>
    </footer>
  );
}
