import { Metadata } from 'next';
import { fetchKnowledgeGraph } from '@/lib/knowledge-graph';
import KnowledgeGraphFallback from '@/components/stock/KnowledgeGraphFallback';
import StockNavbar from '@/components/stock/StockNavbar';

interface PageProps {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ horizon?: string; risk?: string; sector?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} Knowledge Graph — Stocxi`,
    description: `Knowledge graph for ${symbol.toUpperCase()} stock analysis`,
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
  
  const kgData = await fetchKnowledgeGraph(upper);

  return (
    <div className="min-h-screen bg-black">
      <StockNavbar
        symbol={upper}
        companyName=""
        downloadType="graph"
        backHref={`/stock/${upper}/analysis?${analysisParams.toString()}`}
      />
      
      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-8">
        <KnowledgeGraphFallback
          symbol={upper}
          data={kgData}
        />
      </main>
    </div>
  );
}
