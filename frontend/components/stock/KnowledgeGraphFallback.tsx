'use client';

import { useState, useEffect } from 'react';

interface KGNode {
  id: string;
  key: string;
  label: string;
  value: string;
  context: string;
  performance: string;
  nodeType: string;
  color: string;
}

interface KnowledgeGraphData {
  nodes: KGNode[];
  edges: { source: string; target: string; relation: string }[];
}

export default function KnowledgeGraphFallback({ 
  symbol, 
  data 
}: { 
  symbol: string;
  data: KnowledgeGraphData | null;
}) {
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [viewMode, setViewMode] = useState<'3d' | 'list'>('list');

  if (!data) {
    return (
      <div className="flex items-center justify-center h-[600px] bg-[#0A0A0A] text-zinc-500">
        No data available
      </div>
    );
  }

  const headNodes = data.nodes.filter(n => n.nodeType === 'head');
  const verdictNodes = data.nodes.filter(n => n.nodeType === 'verdict');
  const childNodes = data.nodes.filter(n => n.nodeType === 'child');

  const getPerformanceColor = (perf: string) => {
    switch(perf) {
      case 'positive': return 'text-[#00FF88]';
      case 'negative': return 'text-[#FF3355]';
      default: return 'text-[#B8C4D0]';
    }
  };

  const getNodeColor = (type: string) => {
    switch(type) {
      case 'head': return 'bg-white text-black';
      case 'verdict': return 'bg-[#A855F7] text-white';
      default: return 'bg-[#6B7280] text-white';
    }
  };

  return (
    <div className="relative w-full h-[600px] bg-[#0A0A0A] rounded-lg overflow-hidden border border-zinc-800">
      {/* Header */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4">
        <h2 className="text-white text-lg font-semibold">Knowledge Graph</h2>
        <span className="text-zinc-500">|</span>
        <span className="text-zinc-400 text-sm font-mono">{symbol}</span>
      </div>

      {/* View Toggle */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <button
          onClick={() => setViewMode('list')}
          className={`px-3 py-1 text-xs rounded ${
            viewMode === 'list' ? 'bg-zinc-700 text-white' : 'bg-zinc-800 text-zinc-400'
          }`}
        >
          List
        </button>
        <button
          onClick={() => setViewMode('3d')}
          className={`px-3 py-1 text-xs rounded ${
            viewMode === '3d' ? 'bg-zinc-700 text-white' : 'bg-zinc-800 text-zinc-400'
          }`}
          disabled
        >
          3D (WebGL issue)
        </button>
      </div>

      <div className="pt-16 h-full overflow-auto p-4">
        {/* Head Nodes */}
        <div className="mb-6">
          <h3 className="text-xs text-zinc-500 uppercase mb-2">Head Nodes (White)</h3>
          <div className="flex flex-wrap gap-2">
            {headNodes.map(node => (
              <button
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className="px-3 py-2 bg-white text-black text-sm rounded-full hover:bg-zinc-200 transition-colors"
              >
                {node.label}
              </button>
            ))}
          </div>
        </div>

        {/* Verdict Nodes */}
        <div className="mb-6">
          <h3 className="text-xs text-zinc-500 uppercase mb-2">Verdict Nodes (Purple)</h3>
          <div className="flex flex-wrap gap-2">
            {verdictNodes.map(node => (
              <button
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className="px-3 py-2 bg-[#A855F7] text-white text-sm rounded-full hover:bg-[#9333EA] transition-colors"
              >
                {node.label}
              </button>
            ))}
          </div>
        </div>

        {/* Child Nodes */}
        <div className="mb-6">
          <h3 className="text-xs text-zinc-500 uppercase mb-2">
            Child Nodes (Gray) — {childNodes.length} data points
          </h3>
          <div className="flex flex-wrap gap-1 max-h-[250px] overflow-auto">
            {childNodes.map(node => (
              <button
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className={`px-2 py-1 text-xs rounded ${getNodeColor(node.nodeType)} hover:opacity-80 transition-opacity`}
              >
                {node.key}
              </button>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="text-xs text-zinc-600">
          Total Nodes: {data.nodes.length} | Total Edges: {data.edges.length}
        </div>
      </div>

      {/* Tooltip Panel */}
      {selectedNode && (
        <div className="absolute bottom-4 left-4 bg-zinc-900/95 border border-zinc-700 rounded-lg p-4 min-w-[240px]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-white font-semibold text-sm">{selectedNode.label}</span>
            <span 
              className={`px-2 py-0.5 text-xs rounded-full ${getPerformanceColor(selectedNode.performance)}`}
              style={{ backgroundColor: selectedNode.performance === 'positive' ? '#00FF88' : selectedNode.performance === 'negative' ? '#FF3355' : '#333', color: selectedNode.performance === 'neutral' ? '#B8C4D0' : '#000' }}
            >
              {selectedNode.performance}
            </span>
          </div>
          <div className="text-zinc-400 text-xs">
            <span className="text-zinc-500">Value: </span>
            <span className="text-white">{selectedNode.value}</span>
          </div>
          {selectedNode.context && (
            <div className="text-zinc-500 text-xs mt-2">{selectedNode.context}</div>
          )}
          <div className="text-zinc-600 text-xs mt-2">Type: {selectedNode.nodeType}</div>
          <button 
            onClick={() => setSelectedNode(null)}
            className="text-zinc-500 text-xs mt-2 hover:text-white"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}