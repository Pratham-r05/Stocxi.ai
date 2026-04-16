"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import { searchSymbols } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

export default function SearchBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [hasSearched, setHasSearched] = useState(false);
  const [focused, setFocused] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      setIsOpen(false);
      setHasSearched(false);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setHasSearched(false);
    const data = await searchSymbols(q);
    setResults(data);
    setHasSearched(true);
    setIsLoading(false);
    setIsOpen(true);
    setActiveIndex(-1);
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, runSearch]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function selectResult(result: SearchResult) {
    setIsOpen(false);
    setQuery("");
    router.push(`/stock/${result.symbol}`);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => Math.max(prev - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && results[activeIndex]) selectResult(results[activeIndex]);
    } else if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  }

  const showDropdown = isOpen && query.length >= 2;

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        className={`relative rounded-xl transition-all duration-200 ${
          focused ? "glow-white" : ""
        }`}
      >
        <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-zinc-500">
          <Search className="w-4.5 h-4.5" size={18} />
        </span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            setFocused(true);
            if (query.length >= 2 && (results.length > 0 || hasSearched)) setIsOpen(true);
          }}
          onBlur={() => setFocused(false)}
          placeholder="Search stocks — RELIANCE, TCS, INFY…"
          className="w-full rounded-xl border border-zinc-800 bg-zinc-900 py-4 pl-11 pr-16 text-zinc-100 placeholder-zinc-500 outline-none transition-colors focus:border-zinc-600 focus:ring-1 focus:ring-white/10 text-base"
          autoComplete="off"
          spellCheck={false}
        />
        {/* Right side: loading or ⌘K hint */}
        <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center gap-1">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
          ) : (
            <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-500 font-mono">
              ⌘K
            </kbd>
          )}
        </span>
      </div>

      {showDropdown && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl shadow-black/50">
          {results.length > 0 ? (
            <ul role="listbox">
              {results.map((result, idx) => (
                <li
                  key={result.symbol}
                  role="option"
                  aria-selected={idx === activeIndex}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onMouseDown={(e) => { e.preventDefault(); selectResult(result); }}
                  className={`flex cursor-pointer items-center justify-between px-4 py-3 transition-colors border-b border-zinc-800/50 last:border-b-0 ${
                    idx === activeIndex ? "bg-zinc-800" : "hover:bg-zinc-800/50"
                  }`}
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="font-semibold text-white text-sm">{result.symbol}</span>
                    <span className="truncate text-xs text-zinc-500 mt-0.5">{result.name}</span>
                  </div>
                  <span className="ml-3 shrink-0 rounded border border-zinc-700 bg-zinc-800/50 px-2 py-0.5 text-xs text-zinc-400">
                    {result.exchange}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            hasSearched && (
              <div className="px-4 py-4 text-sm text-zinc-500">
                No results for &ldquo;{query}&rdquo;
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
