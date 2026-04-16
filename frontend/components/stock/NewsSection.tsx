"use client";

// NewsSection — recent news headlines with icons polish

import { useEffect, useState } from "react";
import { fetchNews } from "@/lib/api";
import type { NewsArticle } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import { ExternalLink, Clock } from "lucide-react";

interface NewsSectionProps {
  symbol: string;
}

function timeAgo(published: string): string {
  try {
    const diff = Date.now() - new Date(published).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "Just now";
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
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
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <Skeleton className="h-4 w-4/5 mb-2" />
              <Skeleton className="h-3 w-28" />
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
              className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 hover:shadow-lg hover:shadow-black/30 transition-all"
            >
              <a
                href={article.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-100 font-medium text-sm hover:text-white transition-colors leading-snug flex items-start gap-1.5 group"
              >
                <span className="flex-1">{article.title}</span>
                <ExternalLink className="w-3.5 h-3.5 shrink-0 mt-0.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
              </a>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-xs text-zinc-500 font-medium">{article.source}</span>
                <span className="text-zinc-700">·</span>
                <span className="flex items-center gap-1 text-xs text-zinc-600">
                  <Clock className="w-3 h-3" />
                  {timeAgo(article.published)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
