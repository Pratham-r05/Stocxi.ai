import type {
  SearchResult, StockOverview, AIAnalysis, Financials,
  NewsResponse, AnnouncementsResponse, SentimentData, HistoryData,
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

export async function fetchFinancials(symbol: string): Promise<Financials | null> {
  return apiFetch<Financials>(`/api/v1/stock/${symbol}/financials`);
}

export async function fetchNews(symbol: string): Promise<NewsResponse | null> {
  return apiFetch<NewsResponse>(`/api/v1/stock/${symbol}/news?limit=10`);
}

export async function fetchAnnouncements(symbol: string): Promise<AnnouncementsResponse | null> {
  return apiFetch<AnnouncementsResponse>(`/api/v1/stock/${symbol}/announcements?limit=10`);
}

export async function fetchSentiment(symbol: string): Promise<SentimentData | null> {
  return apiFetch<SentimentData>(`/api/v1/stock/${symbol}/sentiment`);
}

export async function fetchHistory(
  symbol: string,
  period: "1mo" | "3mo" | "6mo" | "1y" = "1y"
): Promise<HistoryData | null> {
  return apiFetch<HistoryData>(`/api/v1/stock/${symbol}/history?period=${period}`);
}
