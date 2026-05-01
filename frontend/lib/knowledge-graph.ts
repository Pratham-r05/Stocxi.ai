import { KnowledgeGraphData } from '@/components/stock/KnowledgeGraph';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchKnowledgeGraph(symbol: string): Promise<KnowledgeGraphData | null> {
  const url = `${API_BASE}/api/v1/knowledge-graph/${encodeURIComponent(symbol)}`;
  
  const response = await fetch(url, {
    cache: 'no-store',
  });
  
  if (!response.ok) {
    console.error('Knowledge graph fetch failed:', response.status);
    return null;
  }
  
  const data = await response.json();
  return data as KnowledgeGraphData;
}