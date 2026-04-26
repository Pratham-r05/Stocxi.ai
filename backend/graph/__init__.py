"""
graph/ — Knowledge graph construction and 3D visualization layer.

Modules:
  knowledge_graph.py — builds a NetworkX graph from Nodes + AnalysisResult,
                       renders interactive 3D HTML via Plotly.
"""
from .knowledge_graph import build_graph, render_3d_html

__all__ = ["build_graph", "render_3d_html"]
