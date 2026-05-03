import { Metadata } from 'next';
import StockNavbar from '@/components/stock/StockNavbar';
import KnowledgeGraphClient from '@/components/stock/KnowledgeGraphClient';

interface PageProps {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ horizon?: string; risk?: string; sector?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} Knowledge Graph — Stocxi`,
    description: `Interactive knowledge graph for ${symbol.toUpperCase()} stock analysis`,
  };
}

export default async function KnowledgeGraphPage({ params, searchParams }: PageProps) {
  const { symbol } = await params;
  const sp = await searchParams;
  const upper = symbol.toUpperCase();
  const horizon = (["short", "medium", "long"].includes(sp.horizon ?? "")
    ? sp.horizon! : "short") as "short" | "medium" | "long";
  const risk = (["conservative", "moderate", "aggressive"].includes(sp.risk ?? "")
    ? sp.risk! : "moderate") as "conservative" | "moderate" | "aggressive";
  const analysisParams = new URLSearchParams({ horizon, risk });
  if (sp.sector) analysisParams.set("sector", sp.sector);
  
  const graphUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/knowledge-graph/${upper}`;

  return (
    <div className="min-h-screen bg-black overflow-hidden flex flex-col">
      <StockNavbar
        symbol={upper}
        companyName=""
        downloadType="graph"
        backHref={`/stock/${upper}/analysis?${analysisParams.toString()}`}
      />
      
      <main className="flex-1 w-full bg-black relative">
        <KnowledgeGraphClient symbol={upper} graphUrl={graphUrl} />
      </main>
    </div>
  );
}
