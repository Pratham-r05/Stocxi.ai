"use client";

// AnnouncementsSection — BSE corporate announcements

import { useEffect, useState } from "react";
import { fetchAnnouncements } from "@/lib/api";
import type { Announcement } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";

interface AnnouncementsSectionProps {
  symbol: string;
}

export default function AnnouncementsSection({ symbol }: AnnouncementsSectionProps) {
  const [items, setItems] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnnouncements(symbol).then((data) => {
      setItems(data?.announcements ?? []);
      setLoading(false);
    });
  }, [symbol]);

  return (
    <section>
      <SectionHeader title="BSE Announcements" />

      {loading && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="px-4 py-3 border-b border-zinc-800 last:border-b-0">
              <Skeleton className="h-4 w-3/4 mb-1.5" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center text-zinc-500 text-sm">
          No recent announcements found for {symbol}
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
          {items.slice(0, 10).map((item, i) => (
            <div
              key={i}
              className="px-4 py-3 border-b border-zinc-800 last:border-b-0 flex items-start justify-between gap-3 hover:bg-zinc-800/30 transition-colors"
            >
              <div className="min-w-0 flex-1">
                <p className="text-zinc-200 text-sm font-medium truncate">
                  {item.subject || item.title || "No subject"}
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">{item.date}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {item.category && (
                  <span className="rounded-full bg-zinc-700/60 px-2 py-0.5 text-xs text-zinc-400">
                    {item.category}
                  </span>
                )}
                {item.pdf_url && (
                  <a
                    href={item.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs px-2 py-1 transition-colors"
                  >
                    PDF ↗
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
