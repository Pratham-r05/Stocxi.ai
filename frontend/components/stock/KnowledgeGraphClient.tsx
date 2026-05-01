'use client';

import { useEffect, useRef, useState, useCallback, Suspense } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
import * as THREE from 'three';

interface KGNode {
  id: string;
  key: string;
  label: string;
  value: string;
  context: string;
  performance: 'positive' | 'negative' | 'neutral';
  nodeType: 'head' | 'child' | 'verdict';
  color: string;
}

interface KGEdge {
  source: string;
  target: string;
  relation: string;
  label: string;
}

interface KnowledgeGraphData {
  nodes: KGNode[];
  edges: KGEdge[];
  headNodes: string[];
  verdictNodes: string[];
}

interface KnowledgeGraphClientProps {
  symbol: string;
  data: KnowledgeGraphData | null;
}

const NODE_COLORS = {
  head: '#FFFFFF',
  child: '#6B7280',
  verdict: '#A855F7',
};

const PERFORMANCE_COLORS = {
  positive: '#00FF88',
  negative: '#FF3355',
  neutral: '#B8C4D0',
};

const EDGE_COLORS: Record<string, string> = {
  belongs_to: 'rgba(255,255,255,0.25)',
  informs: 'rgba(255,255,255,0.4)',
  CONFIRMS: '#00FF88',
  CONTRADICTS: '#FF3355',
  AMPLIFIES: '#00FFCC',
  cross_verdict: 'rgba(255,255,255,0.12)',
};

function NodeMesh({ 
  node, 
  position, 
  onHover,
}: { 
  node: KGNode;
  position: [number, number, number];
  onHover: (node: KGNode | null) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const isHead = node.nodeType === 'head';
  const isVerdict = node.nodeType === 'verdict';
  
  const radius = isHead ? 0.7 : isVerdict ? 0.45 : 0.28;
  const color = NODE_COLORS[node.nodeType as keyof typeof NODE_COLORS] || node.color;
  
  useFrame((state) => {
    if (meshRef.current && isHead) {
      meshRef.current.rotation.x += 0.003;
      meshRef.current.rotation.y += 0.003;
    }
  });

  return (
    <group position={position}>
      <mesh
        ref={meshRef}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(node);
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHover(null);
        }}
      >
        {isHead || isVerdict ? (
          <sphereGeometry args={[radius, 32, 32]} />
        ) : (
          <boxGeometry args={[radius, radius, radius]} />
        )}
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.15}
          transparent
          opacity={0.9}
          roughness={0.3}
          metalness={0.2}
        />
      </mesh>
      {isHead && (
        <Text
          position={[0, radius + 0.4, 0]}
          fontSize={0.22}
          color="#FFFFFF"
          anchorX="center"
          anchorY="middle"
        >
          {node.label}
        </Text>
      )}
    </group>
  );
}

function EdgeLine({ 
  start, 
  end, 
  relation 
}: { 
  start: [number, number, number]; 
  end: [number, number, number];
  relation: string;
}) {
  const color = EDGE_COLORS[relation] || 'rgba(255,255,255,0.15)';
  const width = relation === 'belongs_to' ? 0.4 : relation === 'informs' ? 0.6 : 1;
  
  return (
    <Line
      points={[start, end]}
      color={color}
      lineWidth={width}
      transparent
      opacity={0.4}
    />
  );
}

function KnowledgeGraphScene({ 
  data, 
  onNodeHover 
}: { 
  data: KnowledgeGraphData;
  onNodeHover: (node: KGNode | null) => void;
}) {
  const controlsRef = useRef<any>(null);
  const [hoveredNode, setHoveredNode] = useState<KGNode | null>(null);
  const nodePositions = useRef<Map<string, [number, number, number]>>(new Map());
  
  useEffect(() => {
    if (!data || !data.nodes.length) return;
    
    const positions = new Map<string, [number, number, number]>();
    const headNodes = data.nodes.filter(n => n.nodeType === 'head');
    const verdictNodes = data.nodes.filter(n => n.nodeType === 'verdict');
    const childNodes = data.nodes.filter(n => n.nodeType === 'child');
    
    const headCount = headNodes.length;
    const verdictCount = verdictNodes.length;
    
    headNodes.forEach((node, i) => {
      const angle = (i / headCount) * Math.PI * 2;
      positions.set(node.id, [
        Math.cos(angle) * 7,
        2.5,
        Math.sin(angle) * 7
      ]);
    });
    
    verdictNodes.forEach((node, i) => {
      const angle = (i / verdictCount) * Math.PI * 2;
      positions.set(node.id, [
        Math.cos(angle) * 7,
        -3.5,
        Math.sin(angle) * 7
      ]);
    });
    
    childNodes.forEach((node, i) => {
      const parentEdge = data.edges.find(e => e.target === node.id);
      const parentPos = parentEdge ? positions.get(parentEdge.source) : [0, 0, 0];
      const categoryIndex = headNodes.findIndex(h => h.id === parentEdge?.source);
      const angle = categoryIndex >= 0 ? (categoryIndex / headCount) * Math.PI * 2 : 0;
      const spread = 2.8;
      const layer = Math.floor(i / 8);
      const offset = (i % 8) * 0.4;
      
      positions.set(node.id, [
        parentPos[0] + Math.cos(angle + offset) * spread,
        parentPos[1] + 1.2 + layer * 0.6,
        parentPos[2] + Math.sin(angle + offset) * spread
      ]);
    });
    
    nodePositions.current = positions;
  }, [data]);

  const handleHover = useCallback((node: KGNode | null) => {
    setHoveredNode(node);
    onNodeHover(node);
  }, [onNodeHover]);

  if (!data || !data.nodes.length) {
    return (
      <mesh>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshStandardMaterial color="#333333" />
      </mesh>
    );
  }

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      <pointLight position={[-10, 5, -10]} intensity={0.4} color="#A855F7" />
      <pointLight position={[0, -10, 0]} intensity={0.3} />
      
      {data.nodes.map((node) => {
        const pos = nodePositions.current.get(node.id);
        if (!pos) return null;
        
        return (
          <NodeMesh
            key={node.id}
            node={node}
            position={pos}
            onHover={handleHover}
          />
        );
      })}
      
      {data.edges.map((edge, i) => {
        const start = nodePositions.current.get(edge.source);
        const end = nodePositions.current.get(edge.target);
        if (!start || !end) return null;
        
        return (
          <EdgeLine
            key={`${edge.source}-${edge.target}-${i}`}
            start={start}
            end={end}
            relation={edge.relation}
          />
        );
      })}
      
      <OrbitControls
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={4}
        maxDistance={25}
        autoRotate={false}
        dampingFactor={0.05}
      />
    </>
  );
}

function TooltipPanel({ node }: { node: KGNode | null }) {
  if (!node) return null;
  
  const perfColor = PERFORMANCE_COLORS[node.performance];
  
  return (
    <div className="fixed bottom-6 left-6 bg-zinc-900/95 border border-zinc-700 rounded-lg p-4 min-w-[260px] backdrop-blur-sm shadow-xl">
      <div className="flex items-center justify-between mb-2">
        <span className="text-white font-semibold text-sm">{node.label}</span>
        <span 
          className="px-2 py-0.5 text-xs rounded-full font-medium"
          style={{ backgroundColor: perfColor, color: '#000' }}
        >
          {node.performance}
        </span>
      </div>
      <div className="text-zinc-400 text-xs mb-1">
        <span className="text-zinc-500">Value: </span>
        <span className="text-white">{node.value}</span>
      </div>
      {node.context && (
        <div className="text-zinc-500 text-xs mt-2 line-clamp-2">
          {node.context}
        </div>
      )}
      <div className="text-zinc-600 text-xs mt-2">
        Type: {node.nodeType}
      </div>
    </div>
  );
}

function ControlPanel({ 
  onReset, 
}: { 
  onReset: () => void;
}) {
  return (
    <div className="fixed top-4 left-4 bg-zinc-900/90 border border-zinc-700 rounded-lg p-3 space-y-2 z-50">
      <button
        onClick={onReset}
        className="w-full px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs rounded transition-colors"
      >
        Reset View
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-zinc-800 border-t-white rounded-full animate-spin" />
        <div className="text-zinc-500 text-sm">Loading knowledge graph...</div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black">
      <div className="text-zinc-500 text-sm">No data available</div>
    </div>
  );
}

export default function KnowledgeGraphClient({ 
  symbol, 
  data, 
}: KnowledgeGraphClientProps) {
  const [hoveredNode, setHoveredNode] = useState<KGNode | null>(null);
  const controlsRef = useRef<any>(null);

  const handleNodeHover = useCallback((node: KGNode | null) => {
    setHoveredNode(node);
  }, []);

  const handleReset = useCallback(() => {
    if (controlsRef.current) {
      controlsRef.current.reset();
    }
  }, []);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 'r' || e.key === 'R') {
        handleReset();
      }
    };
    window.addEventListener('keypress', handleKeyPress);
    return () => window.removeEventListener('keypress', handleKeyPress);
  }, [handleReset]);

  if (!data || !data.nodes.length) {
    return <EmptyState />;
  }

  return (
    <div className="relative w-full h-[600px] bg-[#0A0A0A] rounded-lg overflow-hidden border border-zinc-800">
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4">
        <h2 className="text-white text-lg font-semibold">Knowledge Graph</h2>
        <span className="text-zinc-500">|</span>
        <span className="text-zinc-400 text-sm font-mono">{symbol}</span>
      </div>
      
      <Canvas
        camera={{ position: [0, 5, 18], fov: 50 }}
        style={{ background: '#0A0A0A' }}
      >
        <Suspense fallback={null}>
          <KnowledgeGraphScene data={data} onNodeHover={handleNodeHover} />
        </Suspense>
      </Canvas>
      
      <ControlPanel onReset={handleReset} />
      <TooltipPanel node={hoveredNode} />
      
      <div className="absolute bottom-4 right-4 flex gap-3 text-xs text-zinc-600">
        <span>Scroll to zoom</span>
        <span>•</span>
        <span>Drag to rotate</span>
        <span>•</span>
        <span>R to reset</span>
      </div>
    </div>
  );
}