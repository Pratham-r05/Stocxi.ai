'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Text, Line, Html } from '@react-three/drei';
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

interface KnowledgeGraphProps {
  symbol: string;
  data: KnowledgeGraphData | null;
  loading?: boolean;
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
  belongs_to: 'rgba(255,255,255,0.22)',
  informs: 'rgba(255,255,255,0.35)',
  CONFIRMS: '#00FF88',
  CONTRADICTS: '#FF3355',
  AMPLIFIES: '#00FFCC',
  cross_verdict: 'rgba(255,255,255,0.10)',
};

function NodeMesh({ 
  node, 
  position, 
  onHover,
  isHovered,
}: { 
  node: KGNode;
  position: [number, number, number];
  onHover: (node: KGNode | null) => void;
  isHovered: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const isHead = node.nodeType === 'head';
  const isVerdict = node.nodeType === 'verdict';
  
  const radius = isHead ? 0.8 : isVerdict ? 0.5 : 0.3;
  const color = NODE_COLORS[node.nodeType as keyof typeof NODE_COLORS] || node.color;
  
  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.rotation.x += 0.005;
      meshRef.current.rotation.y += 0.005;
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
          emissive={isHovered ? color : '#000000'}
          emissiveIntensity={isHovered ? 0.5 : 0}
          transparent
          opacity={0.9}
          wireframe={false}
        />
      </mesh>
      <Text
        position={[0, isHead || isVerdict ? radius + 0.5 : radius + 0.3, 0]}
        fontSize={0.25}
        color={color}
        anchorX="center"
        anchorY="middle"
        maxWidth={2}
      >
        {node.label}
      </Text>
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
  
  return (
    <Line
      points={[start, end]}
      color={color}
      lineWidth={relation === 'belongs_to' ? 0.5 : 1}
      transparent
      opacity={0.3}
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
        Math.cos(angle) * 6,
        2,
        Math.sin(angle) * 6
      ]);
    });
    
    verdictNodes.forEach((node, i) => {
      const angle = (i / verdictCount) * Math.PI * 2;
      positions.set(node.id, [
        Math.cos(angle) * 6,
        -3,
        Math.sin(angle) * 6
      ]);
    });
    
    childNodes.forEach((node, i) => {
      const parentEdge = data.edges.find(e => e.target === node.id);
      const resolvedPos = parentEdge ? positions.get(parentEdge.source) : undefined;
      const parentPos: [number, number, number] = resolvedPos ?? [0, 0, 0];
      const categoryIndex = headNodes.findIndex(h => h.id === parentEdge?.source);
      const angle = categoryIndex >= 0 ? (categoryIndex / headCount) * Math.PI * 2 : 0;
      const spread = 2.5;

      positions.set(node.id, [
        parentPos[0] + Math.cos(angle + (i * 0.3)) * spread,
        parentPos[1] + 1 + (i % 3) * 0.5,
        parentPos[2] + Math.sin(angle + (i * 0.3)) * spread
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
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      <pointLight position={[-10, -10, -10]} intensity={0.5} />
      
      {data.nodes.map((node) => {
        const pos = nodePositions.current.get(node.id);
        if (!pos) return null;
        
        return (
          <NodeMesh
            key={node.id}
            node={node}
            position={pos}
            onHover={handleHover}
            isHovered={hoveredNode?.id === node.id}
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
        minDistance={3}
        maxDistance={30}
        autoRotate={false}
      />
    </>
  );
}

function TooltipPanel({ node }: { node: KGNode | null }) {
  if (!node) return null;
  
  const perfColor = PERFORMANCE_COLORS[node.performance];
  
  return (
    <div className="absolute bottom-4 left-4 bg-zinc-900/95 border border-zinc-700 rounded-lg p-4 min-w-[280px] backdrop-blur-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-white font-semibold text-sm">{node.label}</span>
        <span 
          className="px-2 py-0.5 text-xs rounded-full"
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
        <div className="text-zinc-500 text-xs mt-2">
          {node.context}
        </div>
      )}
      <div className="text-zinc-600 text-xs mt-2">
        Type: {node.nodeType} | ID: {node.id}
      </div>
    </div>
  );
}

function ControlPanel({ 
  onReset, 
  onToggle3D 
}: { 
  onReset: () => void;
  onToggle3D: () => void;
}) {
  return (
    <div className="absolute top-4 left-4 bg-zinc-900/90 border border-zinc-700 rounded-lg p-3 space-y-2">
      <button
        onClick={onReset}
        className="w-full px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs rounded transition-colors"
      >
        Reset View
      </button>
      <button
        onClick={onToggle3D}
        className="w-full px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs rounded transition-colors"
      >
        Toggle 3D
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black">
      <div className="text-zinc-500 text-sm">Loading knowledge graph...</div>
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

export default function KnowledgeGraph({ 
  symbol, 
  data, 
  loading = false 
}: KnowledgeGraphProps) {
  const [hoveredNode, setHoveredNode] = useState<KGNode | null>(null);
  const [is3D, setIs3D] = useState(true);
  const controlsRef = useRef<any>(null);

  const handleNodeHover = useCallback((node: KGNode | null) => {
    setHoveredNode(node);
  }, []);

  const handleReset = useCallback(() => {
    if (controlsRef.current) {
      controlsRef.current.reset();
    }
  }, []);

  const handleToggle3D = useCallback(() => {
    setIs3D(prev => !prev);
  }, []);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 't' || e.key === 'T') {
        setIs3D(prev => !prev);
      }
    };
    window.addEventListener('keypress', handleKeyPress);
    return () => window.removeEventListener('keypress', handleKeyPress);
  }, []);

  if (loading) {
    return <LoadingState />;
  }

  if (!data || !data.nodes.length) {
    return <EmptyState />;
  }

  return (
    <div className="relative w-full h-[600px] bg-[#0A0A0A] rounded-lg overflow-hidden">
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4">
        <h2 className="text-white text-lg font-semibold">Knowledge Graph</h2>
        <span className="text-zinc-500">|</span>
        <span className="text-zinc-400 text-sm">{symbol}</span>
      </div>
      
      <Canvas
        camera={{ position: [0, 5, 15], fov: 60 }}
        style={{ background: '#0A0A0A', outline: 'none' }}
      >
        <KnowledgeGraphScene data={data} onNodeHover={handleNodeHover} />
      </Canvas>
      
      <ControlPanel onReset={handleReset} onToggle3D={handleToggle3D} />
      <TooltipPanel node={hoveredNode} />
      
      <div className="absolute bottom-4 right-4 flex gap-2 text-xs text-zinc-600">
        <span>2-finger zoom</span>
        <span>•</span>
        <span>drag to rotate</span>
        <span>•</span>
        <span>T for 3D mode</span>
      </div>
    </div>
  );
}

export type { KnowledgeGraphData, KGNode, KGEdge };