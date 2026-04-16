"use client";

// NewsSection — fetches and displays recent news headlines

import { useEffect, useState } from "react";
import { fetchNews } from "@/lib/api";
import type { NewsArticle } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";

interface NewsSectionProps {
  symbol: string;
}

function timeAgo(published: string): string {
  try {
    const date = new Date(published);
    const diff = Date.now() - date.getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "Just now";
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return published;
  }
}

export default function NewsSection({ symbol }: NewsSectionProps) {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchNews(symbol).then((data) => {
      setArticles(data?.articles ?? []);
      setLoading(false);
    });
  }, [symbol]);

  return (
    <section>
      <SectionHeader title="Recent News" />

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <Skeleton className="h-4 w-4/5 mb-2" />
              <Skeleton className="h-3 w-32" />
            </div>
          ))}
        </div>
      )}

      {!loading && articles.length === 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center text-zinc-500 text-sm">
          No recent news found for {symbol}
        </div>
      )}

      {!loading && articles.length > 0 && (
        <div className="space-y-2">
          {articles.slice(0, 10).map((article, i) => (
            <div
              key={i}
              className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 transition-colors"
            >
              <a
                href={article.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-100 font-medium text-sm hover:text-violet-400 transition-colors leading-snug block"
              >
                {article.title}
              </a>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-xs text-zinc-500 font-medium">{article.source}</span>
                <span className="text-zinc-700">·</span>
                <span className="text-xs text-zinc-600">{timeAgo(article.published)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
