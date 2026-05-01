import { Metadata } from 'next';
import { fetchKnowledgeGraph } from '@/lib/knowledge-graph';
import KnowledgeGraphFallback from '@/components/stock/KnowledgeGraphFallback';
import StockNavbar from '@/components/stock/StockNavbar';

interface PageProps {
  params: Promise<{ symbol: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { symbol } = await params;
  return {
    title: `${symbol.toUpperCase()} Knowledge Graph — Stocxi`,
    description: `Knowledge graph for ${symbol.toUpperCase()} stock analysis`,
  };
}

export default async function KnowledgeGraphPage({ params }: PageProps) {
  const { symbol } = await params;
  const upper = symbol.toUpperCase();
  
  const kgData = await fetchKnowledgeGraph(upper);

  return (
    <div className="min-h-screen bg-black">
      <StockNavbar symbol={upper} companyName="" />
      
      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-8">
        <KnowledgeGraphFallback
          symbol={upper}
          data={kgData}
        />
      </main>
    </div>
  );
}