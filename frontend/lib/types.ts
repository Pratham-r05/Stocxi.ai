// Search
export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
}

// Technicals
export interface Technicals {
  rsi: number | null;
  rsi_signal: string;
  macd: number | null;
  macd_signal: string;
  adx: number | null;
  adx_signal: string;
  atr: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bb_signal: string;
  ema_20: number | null;
  ema_50: number | null;
  ema_200: number | null;
  ema_signal: string;
  volume_sma_20: number | null;
  overall_signal: string;
}

// Sentiment
export interface SentimentPost {
  title?: string;
  text?: string;
  score?: number;
  url?: string;
  created_at?: string;
}
export interface SentimentSource {
  posts: SentimentPost[];
  summary: string;
  structured_summary?: {
    overall_view: string;
    investor_takeaway: string;
    key_themes: string[];
    bullish_points: string[];
    risk_points: string[];
    key_discussions: string[];
  };
  sentiment: string;
  sentiment_score: number;
  signal: "BUY" | "HOLD" | "AVOID";
  source: string;
  fetched_at: string;
}
export interface SentimentChartPoint {
  date: string;
  reddit_score: number;
  twitter_score: number;
}
export interface SentimentData {
  reddit: SentimentSource;
  twitter: SentimentSource;
  combined_signal: "BUY" | "HOLD" | "AVOID";
  combined_sentiment_score: number;
  chart_data: SentimentChartPoint[];
}

// Stock Overview
export interface StockOverview {
  symbol: string;
  company_name: string;
  company_website: string | null;
  logo_url: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  day_high: number | null;
  day_low: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  volume: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  book_value: number | null;
  eps: number | null;
  dividend_yield: number | null;
  beta: number | null;
  roce: number | null;
  roe: number | null;
  face_value: number | null;
  technicals: Technicals;
  sentiment: SentimentData | null;
}

// AI Analysis
export interface AIVerdict {
  verdict: string;
  summary: string;
}
export interface AIAnalysis {
  symbol: string;
  company_name: string;
  risk_level: string;
  final_verdict: "BUY" | "HOLD" | "AVOID";
  plain_english: string;
  fundamentals: AIVerdict;
  technicals: AIVerdict;
  news: AIVerdict;
  social: AIVerdict;
  risk_match: boolean;
  overall_technical_signal: string;
  current_price: number | null;
  change_percent: number | null;
  generated_at: string;
  disclaimer: string;
}

// Financials
export interface FinancialTable {
  columns?: string[];
  headers?: string[];
  rows: { label: string; values: (number | string | null)[] }[];
}
export interface Financials {
  symbol: string;
  quarterly_results: FinancialTable | null;
  annual_results: FinancialTable | null;
  balance_sheet: FinancialTable | null;
  cash_flow: FinancialTable | null;
  shareholding: FinancialTable | null;
  mf_holdings: FinancialTable | null;
}

// News
export interface NewsArticle {
  title: string;
  link: string;
  published: string;
  source: string;
}
export interface NewsResponse {
  symbol: string;
  count: number;
  articles: NewsArticle[];
}

// Price History
export interface HistoryPoint {
  date: string;
  close: number;
  volume?: number;
}
export interface HistoryData {
  symbol: string;
  period: string;
  closes: HistoryPoint[];
}

// Announcements
export interface Announcement {
  subject: string;
  title?: string;
  date: string;
  category: string;
  pdf_url: string | null;
}
export interface AnnouncementsResponse {
  symbol: string;
  count: number;
  announcements: Announcement[];
}
