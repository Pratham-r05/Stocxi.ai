"use client";

// AnnouncementsSection — corporate announcements with Gemini-generated summaries

import { useEffect, useState } from "react";
import { fetchAnnouncements, announcementPdfProxyUrl } from "@/lib/api";
import type { Announcement } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import { Clock, ExternalLink } from "lucide-react";

function timeAgo(date: string): string {
  try {
    const diff = Date.now() - new Date(date).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "Just now";
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  } catch {
    return date;
  }
}

function AnnouncementRow({ item }: { item: Announcement }) {
  const summary  = (item.summary || item.subject || item.title || "").trim();
  const pdfUrl = item.pdf_url || "";
  const filingUrl = item.filing_url || "";
  const hasPdf = !!pdfUrl;
  // PDF links go through the backend proxy so NSE/BSE auth/bot-blocking is handled
  const linkUrl = hasPdf ? announcementPdfProxyUrl(pdfUrl) : filingUrl;
  const linkLabel = hasPdf ? "PDF" : filingUrl ? "Filing" : "";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 hover:shadow-lg hover:shadow-black/30 transition-all">
      <div className="flex items-start gap-2">
        <p className="flex-1 text-zinc-100 font-medium text-sm leading-snug">
          {summary || "Corporate announcement"}
        </p>
        {linkUrl && (
          <a
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open ${linkLabel}`}
            className="shrink-0 mt-0.5 text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 mt-1.5">
        <span className="text-xs text-zinc-500 font-medium">{item.source || item.category || "exchange_filing"}</span>
        {item.category && (
          <>
            <span className="text-zinc-700">·</span>
            <span className="text-xs text-zinc-600">{item.category}</span>
          </>
        )}
        {linkLabel && (
          <>
            <span className="text-zinc-700">·</span>
            <span className="text-xs text-zinc-600">{linkLabel}</span>
          </>
        )}
        <span className="text-zinc-700">·</span>
        <span className="flex items-center gap-1 text-xs text-zinc-600">
          <Clock className="w-3 h-3" />
          {timeAgo(item.date)}
        </span>
        <span className="text-zinc-700">·</span>
        <span className="text-xs text-zinc-600">{item.date}</span>
      </div>

      {item.subject && item.subject !== summary && (
        <div className="mt-1.5 text-xs text-zinc-600 line-clamp-1">
          {item.subject}
        </div>
      )}
    </div>
  );
}

interface AnnouncementsSectionProps {
  symbol: string;
}

export default function AnnouncementsSection({ symbol }: AnnouncementsSectionProps) {
  const [items, setItems] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setFailed(false);
      const data = await fetchAnnouncements(symbol);
      if (!active) return;
      if (data == null) {
        setItems([]);
        setFailed(true);
      } else {
        setItems(data.announcements ?? []);
      }
      setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [symbol, reloadToken]);

  return (
    <section>
      <SectionHeader title="Announcements" />

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

      {!loading && failed && (
        <div className="rounded-xl border border-red-900/60 bg-red-950/20 p-6 text-center text-red-300 text-sm space-y-3">
          <p>Unable to load announcements right now. Check backend connection and try again.</p>
          <button
            onClick={() => setReloadToken((t) => t + 1)}
            className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !failed && items.length === 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center text-zinc-500 text-sm">
          No recent announcements found for {symbol}
        </div>
      )}

      {!loading && !failed && items.length > 0 && (
        <div className="space-y-2">
          {items.slice(0, 10).map((item, i) => (
            <AnnouncementRow key={i} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
