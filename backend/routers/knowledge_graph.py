"""
knowledge_graph.py — Knowledge graph API endpoint.

Returns analysis data transformed into knowledge graph format:
- 5 head nodes (fundamental, technical_indicator, financial, announcement, news)
- Dynamic child nodes based on available data
- 5 verdict nodes
- All edges connecting them
"""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from services.knowledge_graph_service import build_knowledge_graph
from services.yfinance_service import get_price_and_fundamentals
from services.technicals_service import calculate_technicals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Knowledge Graph"])


async def fetch_all_data(symbol: str) -> dict:
    """Fetch all analysis data for a symbol."""
    price_data = await get_price_and_fundamentals(symbol)
    technicals = await calculate_technicals(symbol)
    
    as_of_date = date.today() - timedelta(days=1)
    
    financials = {}
    announcements = {}
    
    return {
        "fundamentals": price_data,
        "technicals": technicals,
        "financials": financials,
        "announcements": announcements,
    }


@router.get("/knowledge-graph/{symbol}")
async def get_knowledge_graph(symbol: str):
    """Get knowledge graph for a stock symbol."""
    try:
        analysis_data = await fetch_all_data(symbol.upper())
        
        if not analysis_data:
            raise HTTPException(status_code=404, detail=f"No analysis data found for {symbol}")
        
        kg_data = build_knowledge_graph(analysis_data)
        
        return JSONResponse(content=kg_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building knowledge graph for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build knowledge graph: {str(e)}")