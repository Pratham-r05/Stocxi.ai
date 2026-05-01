"""
knowledge_graph_service.py — Transform analysis data into knowledge graph structure.

Node hierarchy:
  - HEAD NODES (5): fundamental, technical_indicator, announcement, news, financial
  - CHILD NODES: Dynamic based on available data - each data point
  - VERDICT NODES (5): verdict_fundamental, verdict_technical, verdict_announcement, verdict_news, verdict_financial

Edge types:
  - belongs_to: child → head
  - informs: head → verdict
  - cross_category: head ↔ head (CONFIRMS, CONTRADICTS, AMPLIFIES)
  - cross_verdict: verdict ↔ verdict (AGREES, DISAGREES)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def categorize_node(node: dict[str, Any]) -> tuple[str | None, str]:
    """Categorize a node into head category + node type.
    
    Returns: (head_key, node_type)
    """
    key = node.get("key", "")
    category = node.get("category", "")
    
    if category == "technical" or any(t in key for t in ["SMA", "EMA", "RSI", "MACD", "ADX", "BB", "VWAP", "OBV", "CCI", "Stochastic"]):
        return "technical_indicator", "child"
    elif category == "fundamental" or any(t in key for t in ["PE", "ROE", "ROCE", "PB", "EPS", "Book_Value", "Debt", "Margin"]):
        return "fundamental", "child"
    elif category == "financial" or any(t in key for t in ["Revenue", "Profit", "Cash", "Asset", "Liability", "Holding", "Quarterly", "Annual"]):
        return "financial", "child"
    elif category == "news":
        return "news", "child"
    elif category == "announcement" or category == "announce":
        return "announcement", "child"
    else:
        return None, "unknown"


def extract_performance(node: dict[str, Any]) -> str:
    """Extract performance indicator: positive, negative, or neutral."""
    signal = node.get("signal", "")
    verdict = node.get("verdict", "")
    value = node.get("value", "")
    
    if signal in ["bullish", "positive"] or verdict in ["bullish", "positive"]:
        return "positive"
    elif signal in ["bearish", "negative"] or verdict in ["bearish", "negative"]:
        return "negative"
    else:
        return "neutral"


def build_knowledge_graph(analysis_data: dict[str, Any]) -> dict[str, Any]:
    """Transform analysis response into knowledge graph format."""
    
    nodes = []
    edges = []
    
    # HEAD NODE DEFINITIONS
    HEAD_NODES = [
        {"id": "fundamental", "label": "Fundamental", "type": "head", "color": "#FFFFFF"},
        {"id": "technical_indicator", "label": "Technical Indicator", "type": "head", "color": "#FFFFFF"},
        {"id": "financial", "label": "Financial", "type": "head", "color": "#FFFFFF"},
        {"id": "announcement", "label": "Announcement", "type": "head", "color": "#FFFFFF"},
        {"id": "news", "label": "News", "type": "head", "color": "#FFFFFF"},
    ]
    VERDICT_NODES = [
        {"id": "verdict_fundamental", "label": "Verdict Fundamental", "type": "verdict", "color": "#A855F7"},
        {"id": "verdict_technical", "label": "Verdict Technical", "type": "verdict", "color": "#A855F7"},
        {"id": "verdict_financial", "label": "Verdict Financial", "type": "verdict", "color": "#A855F7"},
        {"id": "verdict_announcement", "label": "Verdict Announcement", "type": "verdict", "color": "#A855F7"},
        {"id": "verdict_news", "label": "Verdict News", "type": "verdict", "color": "#A855F7"},
    ]
    
    # Add head nodes
    for node in HEAD_NODES:
        nodes.append({
            "id": node["id"],
            "key": node["id"],
            "label": node["label"],
            "value": node["label"],
            "context": f"Analysis category: {node['label']}",
            "performance": "neutral",
            "nodeType": "head",
            "color": node["color"]
        })
    
    # Add verdict nodes
    for node in VERDICT_NODES:
        nodes.append({
            "id": node["id"],
            "key": node["id"],
            "label": node["label"],
            "value": node["label"],
            "context": f"AI verdict for: {node['label'].replace('Verdict ', '')}",
            "performance": "neutral",
            "nodeType": "verdict",
            "color": node["color"]
        })
    
    # Process data points from analysis
    processed_categories = set()
    category_data = {
        "fundamental": analysis_data.get("fundamentals", analysis_data.get("fundamental", {})),
        "technical_indicator": analysis_data.get("technicals", analysis_data.get("technical_indicator", {})),
        "financial": analysis_data.get("financials", analysis_data.get("financial", {})),
        "announcement": analysis_data.get("announcements", analysis_data.get("announcement", {})),
        "news": analysis_data.get("news", analysis_data.get("news", [])),
    }
    
    # Map category to verdict node
    category_to_verdict = {
        "fundamental": "verdict_fundamental",
        "technical_indicator": "verdict_technical",
        "financial": "verdict_financial",
        "announcement": "verdict_announcement",
        "news": "verdict_news",
    }
    
    for category, data in category_data.items():
        if not data:
            continue
            
        head_id = category
        
        # Handle different data formats
        if isinstance(data, dict):
            items = data.items()
        elif isinstance(data, list):
            items = [(i.get("key", f"item_{i}"), i) for i in data]
        else:
            continue
            
        for key, value_data in items:
            if isinstance(value_data, dict):
                node_key = value_data.get("key", key)
                node_value = value_data.get("value", value_data.get("value", str(value_data)))
                node_context = value_data.get("context", value_data.get("description", ""))
                performance = value_data.get("performance", extract_performance(value_data))
            else:
                node_key = key
                node_value = str(value_data)
                node_context = ""
                performance = "neutral"
            
            # Skip if already added as head
            if node_key in [n["id"] for n in nodes]:
                continue
                
            child_id = f"{head_id}_{node_key}"
            
            nodes.append({
                "id": child_id,
                "key": node_key,
                "label": node_key,
                "value": node_value,
                "context": node_context,
                "performance": performance,
                "nodeType": "child",
                "color": "#6B7280"
            })
            
            # Edge: child → head (belongs_to)
            edges.append({
                "source": child_id,
                "target": head_id,
                "relation": "belongs_to",
                "label": "belongs_to"
            })
    
    # Add edges: head → verdict (informs)
    for category, verdict_id in category_to_verdict.items():
        if category in category_data and category_data[category]:
            edges.append({
                "source": category,
                "target": verdict_id,
                "relation": "informs",
                "label": "informs"
            })
    
    # Get verdicts from analysis
    verdicts = analysis_data.get("verdicts", {})
    
    # Add cross-category edges based on analysis verdicts/agreements
    agreements = analysis_data.get("agreements", [])
    for agreement in agreements if isinstance(agreements, list) else []:
        if isinstance(agreement, dict):
            source = agreement.get("source")
            target = agreement.get("target")
            relation = agreement.get("relation", "CONFIRMS")
            if source and target:
                edges.append({
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "label": relation
                })
    
    contradictions = analysis_data.get("contradictions", [])
    for contr in contradictions if isinstance(contradictions, list) else []:
        if isinstance(contr, dict):
            source = contr.get("source")
            target = contr.get("target")
            if source and target:
                edges.append({
                    "source": source,
                    "target": target,
                    "relation": "CONTRADICTS",
                    "label": "CONTRADICTS"
                })
    
    # Add edges between verdict nodes (agreements/disagreements)
    verdict_ids = [v["id"] for v in VERDICT_NODES]
    for i, v1 in enumerate(verdict_ids):
        for v2 in verdict_ids[i+1:]:
            # Add cross_verdict edge - simple correlation
            edges.append({
                "source": v1,
                "target": v2,
                "relation": "cross_verdict",
                "label": "correlates"
            })
    
    return {
        "nodes": nodes,
        "edges": edges,
        "headNodes": [n["id"] for n in HEAD_NODES],
        "verdictNodes": [n["id"] for n in VERDICT_NODES]
    }