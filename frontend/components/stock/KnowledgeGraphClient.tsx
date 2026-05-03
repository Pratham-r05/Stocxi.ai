"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

interface KnowledgeGraphClientProps {
  symbol: string;
  graphUrl: string;
}

export default function KnowledgeGraphClient({
  symbol,
  graphUrl,
}: KnowledgeGraphClientProps) {
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [html, setHtml] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadGraph() {
      setLoading(true);
      setFailed(false);
      setHtml("");

      try {
        const response = await fetch(graphUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = await response.text();
        if (cancelled) return;
        setHtml(body);
        setLoading(false);
      } catch {
        if (cancelled) return;
        setFailed(true);
        setLoading(false);
      }
    }

    void loadGraph();
    return () => {
      cancelled = true;
    };
  }, [graphUrl, reloadKey]);

  return (
    <div className="relative h-full min-h-[calc(100vh-72px)] bg-black">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black">
          <div className="flex items-center gap-3 text-sm text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            Building knowledge graph for {symbol}
          </div>
        </div>
      )}

      {failed && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black">
          <div className="max-w-sm rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-center">
            <AlertCircle className="mx-auto mb-3 h-6 w-6 text-zinc-500" />
            <p className="mb-4 text-sm text-zinc-400">
              Knowledge graph could not load.
            </p>
            <button
              onClick={() => {
                setFailed(false);
                setLoading(true);
                setReloadKey((value) => value + 1);
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry
            </button>
          </div>
        </div>
      )}

      {html && (
        <iframe
          key={reloadKey}
          srcDoc={html}
          className="absolute inset-0 h-full w-full border-0 outline-none focus:outline-none"
          sandbox="allow-scripts allow-same-origin"
          title={`${symbol} Knowledge Graph`}
        />
      )}
    </div>
  );
}
