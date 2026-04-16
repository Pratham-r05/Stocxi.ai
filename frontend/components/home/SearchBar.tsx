"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
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
    debounceRef.current = setTimeout(() => {
      runSearch(query);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  // Click-outside to close
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
      if (activeIndex >= 0 && results[activeIndex]) {
        selectResult(results[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  }

  const showDropdown = isOpen && query.length >= 2;

  return (
    <div ref={containerRef} className="relative w-full">
      {/* Input */}
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-zinc-500">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
        </span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (query.length >= 2 && (results.length > 0 || hasSearched)) {
              setIsOpen(true);
            }
          }}
          placeholder="Search stocks — RELIANCE, TCS, INFY…"
          className="w-full rounded-xl border border-zinc-800 bg-zinc-900 py-3.5 pl-11 pr-12 text-zinc-100 placeholder-zinc-500 outline-none transition-colors focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600"
          autoComplete="off"
          spellCheck={false}
        />
        {/* Loading indicator */}
        {isLoading && (
          <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center">
            <svg
              className="h-4 w-4 animate-spin text-zinc-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </span>
        )}
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-xl">
          {results.length > 0 ? (
            <ul role="listbox">
              {results.map((result, idx) => (
                <li
                  key={result.symbol}
                  role="option"
                  aria-selected={idx === activeIndex}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onMouseDown={(e) => {
                    // Prevent blur before click registers
                    e.preventDefault();
                    selectResult(result);
                  }}
                  className={`flex cursor-pointer items-center justify-between px-4 py-3 transition-colors ${
                    idx === activeIndex ? "bg-zinc-800" : "hover:bg-zinc-800/60"
                  }`}
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate font-medium text-zinc-100">{result.symbol}</span>
                    <span className="truncate text-sm text-zinc-400">{result.name}</span>
                  </div>
                  <span className="ml-3 shrink-0 rounded-full bg-zinc-700 px-2 py-0.5 text-xs text-zinc-300">
                    {result.exchange}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            hasSearched && (
              <div className="px-4 py-3 text-sm text-zinc-500">
                No results for &ldquo;{query}&rdquo;
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
