import type {
  SearchResult, StockOverview, AIAnalysis, Financials,
  NewsResponse, AnnouncementsResponse, SentimentData, HistoryData,
  V2AnalysisResult,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

export async function searchSymbols(query: string): Promise<SearchResult[]> {
  const data = await apiFetch<{ results: SearchResult[] }>(
    `/api/v1/search?q=${encodeURIComponent(query)}&limit=10`
  );
  return data?.results ?? [];
}

export async function fetchStockOverview(symbol: string): Promise<StockOverview | null> {
  return apiFetch<StockOverview>(`/api/v1/stock/${symbol}`);
}

export async function fetchAIAnalysis(
  symbol: string,
  riskLevel: "low" | "medium" | "high" = "medium"
): Promise<AIAnalysis | null> {
  return apiFetch<AIAnalysis>(`/api/v1/analysis/${symbol}?risk_level=${riskLevel}`);
}

export async function fetchAIAnalysisV2(
  symbol: string,
  horizon: "short" | "medium" | "long" = "short",
  risk: "conservative" | "moderate" | "aggressive" = "moderate",
  sector = ""
): Promise<V2AnalysisResult | null> {
  const params = new URLSearchParams({ horizon, risk });
  if (sector) params.set("sector", sector);
  return apiFetch<V2AnalysisResult>(`/api/v2/analysis/${symbol}?${params.toString()}`);
}

export interface SimpleAnalysisResult {
  symbol: string;
  horizon: string;
  level: string;
  generated_on: string;
  cached: boolean;
  analysis_html: string;
  kg_html: string;
}

export async function fetchSimpleAnalysis(
  symbol: string,
  horizon: "short" | "medium" | "long",
  risk: "conservative" | "moderate" | "aggressive",
): Promise<SimpleAnalysisResult | null> {
  const params = new URLSearchParams({ horizon, risk });
  try {
    const res = await fetch(
      `${BASE}/api/v2/analysis/${symbol}/generate?${params.toString()}`,
      { cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json() as Promise<SimpleAnalysisResult>;
  } catch {
    return null;
  }
}

export async function fetchAIAnalysisV2Report(
  symbol: string,
  horizon: "short" | "medium" | "long" = "short",
  risk: "conservative" | "moderate" | "aggressive" = "moderate",
  sector = "",
  tier: "orbiter" | "stellar" | "apex" = "stellar"
): Promise<Blob | null> {
  const params = new URLSearchParams({ horizon, risk, tier });
  if (sector) params.set("sector", sector);
  try {
    const res = await fetch(`${BASE}/api/v2/analysis/${symbol}/report?${params.toString()}`);
    if (!res.ok) return null;
    return res.blob();
  } catch {
    return null;
  }
}

export async function fetchFinancials(symbol: string): Promise<Financials | null> {
  return apiFetch<Financials>(`/api/v1/stock/${symbol}/financials`);
}

export async function fetchNews(symbol: string): Promise<NewsResponse | null> {
  return apiFetch<NewsResponse>(`/api/v1/stock/${symbol}/news?limit=10`);
}

export async function fetchAnnouncements(symbol: string): Promise<AnnouncementsResponse | null> {
  try {
    const res = await fetch(
      `${BASE}/api/v1/stock/${symbol}/announcements?limit=10`,
      { cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json() as Promise<AnnouncementsResponse>;
  } catch {
    return null;
  }
}

export async function fetchSentiment(symbol: string, forceRefresh = false): Promise<SentimentData | null> {
  const qp = forceRefresh ? "?refresh=true" : "";
  return apiFetch<SentimentData>(`/api/v1/stock/${symbol}/sentiment${qp}`);
}

export async function fetchHistory(
  symbol: string,
  period: "1d" | "1w" | "1mo" | "3mo" | "6mo" | "1y" | "2y" | "5y" = "1y"
): Promise<HistoryData | null> {
  return apiFetch<HistoryData>(`/api/v1/stock/${symbol}/history?period=${period}`);
}
