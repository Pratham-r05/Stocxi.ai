"""
graph/ — Knowledge graph construction and 3D visualization layer.

Modules:
  knowledge_graph.py         — builds graph dict, renders 3D HTML, serializes for LLM.
  hfbp.py                    — Horizon-Aware Forward-Backward Propagation algorithm.
  builder.py                 — HFBP-typed edge construction with conditional logic.
  stocxi_knowledge_graph.py  — Full StocxiKnowledgeGraph orchestration class.
  scorer.py                  — Relevance scoring (weight × confidence × recency).
  store.py                   — Postgres read/write for nodes and edges.
"""
from .builder import Edge, HFBPRelation, build_edges, EDGE_WEIGHT_PRIORS, EDGE_MODIFIERS
from .hfbp import HFBPGraph
from .knowledge_graph import build_graph, render_3d_html, serialize_for_llm, to_graphxr_data
from .stocxi_knowledge_graph import StocxiKnowledgeGraph

__all__ = [
    # Legacy
    "build_graph",
    "render_3d_html",
    "serialize_for_llm",
    "to_graphxr_data",
    # HFBP
    "Edge",
    "HFBPRelation",
    "build_edges",
    "EDGE_WEIGHT_PRIORS",
    "EDGE_MODIFIERS",
    "HFBPGraph",
    "StocxiKnowledgeGraph",
]
