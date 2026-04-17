"use client";

import { useMemo, useState } from "react";
import { fetchSentiment } from "@/lib/api";
import type { SentimentData, SentimentPost } from "@/lib/types";
import { ExternalLink, MessageSquareText, X as CloseIcon } from "lucide-react";
import Image from "next/image";

type SourceTab = "twitter" | "reddit";

function formatWhen(iso: string | undefined): string {
  if (!iso) return "Unknown time";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function Spinner() {
  return (
    <span
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-500 border-t-zinc-100"
      aria-hidden="true"
    />
  );
}

function SourcePill({
  id,
  active,
  label,
  onClick,
}: {
  id: SourceTab;
  active: boolean;
  label: string;
  onClick: (id: SourceTab) => void;
}) {
  return (
    <button
      onClick={() => onClick(id)}
      className={[
        "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
        active
          ? "bg-zinc-200 text-zinc-900 border-zinc-200"
          : "bg-zinc-900 text-zinc-400 border-zinc-700 hover:text-zinc-200 hover:border-zinc-500",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function PostCard({ post }: { post: SentimentPost }) {
  const text = post.text?.trim() || post.title?.trim() || "Untitled mention";
  const score = typeof post.score === "number" ? post.score : null;
  const scoreClass = score == null ? "text-zinc-500" : score > 0.1 ? "text-emerald-400" : score < -0.1 ? "text-red-400" : "text-zinc-400";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3 space-y-2">
      <p className="text-sm text-zinc-200 leading-relaxed">{text}</p>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-zinc-500">{formatWhen(post.created_at)}</span>
        <div className="flex items-center gap-2">
          {score != null && (
            <span className={scoreClass}>Score {score.toFixed(2)}</span>
          )}
          {post.url ? (
            <a
              href={post.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-zinc-300 hover:text-white"
            >
              Visit
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function SocialBuzzLauncher({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [activeTab, setActiveTab] = useState<SourceTab>("twitter");
  const [data, setData] = useState<SentimentData | null>(null);
  const [lastSymbol, setLastSymbol] = useState<string | null>(null);

  const currentPosts = useMemo(() => {
    if (!data) return [] as SentimentPost[];
    return activeTab === "twitter" ? data.twitter.posts : data.reddit.posts;
  }, [data, activeTab]);

  const load = async (force = false) => {
    if (!force && data && lastSymbol === symbol) return;
    const minLoaderMs = 1200;
    const startedAt = Date.now();
    setLoading(true);
    setFailed(false);
    const result = await fetchSentiment(symbol, true);
    const spent = Date.now() - startedAt;
    if (spent < minLoaderMs) {
      await new Promise((resolve) => setTimeout(resolve, minLoaderMs - spent));
    }
    if (result) {
      setData(result);
      setLastSymbol(symbol);
    } else {
      setFailed(true);
      setData(null);
    }
    setLoading(false);
  };

  const openWithFetch = async () => {
    setOpen(true);
    await load(true);
  };

  return (
    <>
      <button
        onClick={openWithFetch}
        className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 px-2.5 py-2 text-xs font-medium text-zinc-200 transition-colors"
        title="Open X and Reddit buzz"
      >
        <Image
          src="/social-buzz-default.svg"
          alt="Social buzz"
          width={18}
          height={18}
          className="h-[18px] w-[18px] rounded"
        />
        <span className="hidden sm:inline">X/Reddit Buzz</span>
        {loading ? <Spinner /> : <MessageSquareText className="h-3.5 w-3.5" />}
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70" onClick={() => setOpen(false)} />

          <div className="relative z-10 w-full max-w-2xl rounded-2xl border border-zinc-700 bg-zinc-900 shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div>
                <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-[0.12em]">Social Buzz</h3>
                <p className="text-xs text-zinc-500 mt-1">{symbol} discussions from X and Reddit</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 p-2 text-zinc-300"
                aria-label="Close"
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            </div>

            <div className="px-5 py-4">
              <div className="flex items-center gap-2 mb-4">
                <SourcePill id="twitter" label="X" active={activeTab === "twitter"} onClick={setActiveTab} />
                <SourcePill id="reddit" label="Reddit" active={activeTab === "reddit"} onClick={setActiveTab} />
                <button
                  onClick={() => load(true)}
                  className="ml-auto text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Refresh
                </button>
              </div>

              {loading ? (
                <div className="h-44 flex items-center justify-center gap-2 text-sm text-zinc-400">
                  <Spinner />
                  Fetching social mentions...
                </div>
              ) : failed ? (
                <div className="rounded-xl border border-red-900/60 bg-red-950/20 p-5 text-center text-sm text-red-300 space-y-3">
                  <p>Unable to fetch X/Reddit mentions right now.</p>
                  <button
                    onClick={() => load(true)}
                    className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
                  >
                    Retry
                  </button>
                </div>
              ) : currentPosts.length === 0 ? (
                <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-5 text-center text-sm text-zinc-400 space-y-1">
                  <p>No one is talking about this stock right now.</p>
                  <p className="text-xs text-zinc-500">If this looks wrong, try Refresh to run a fresh search.</p>
                </div>
              ) : (
                <div className="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
                  {currentPosts.slice(0, 12).map((post, idx) => (
                    <PostCard key={`${post.url ?? "post"}-${idx}`} post={post} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
