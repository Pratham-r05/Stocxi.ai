"""Test full news pipeline: gnews -> LLM summary -> Node format."""
import asyncio
import sys
import json
from datetime import date

sys.path.insert(0, ".")

from agents.agent_news import news_agent
from schemas.messages import FetchRequest, UserProfile


async def main():
    # Test with 3 stocks
    for stock in ["HDFCBANK", "TCS", "RELIANCE"]:
        print(f"\n{'='*70}")
        print(f"  {stock} — Full Pipeline Test")
        print(f"{'='*70}\n")

        request = FetchRequest(
            stock=stock,
            as_of_date=date(2026, 4, 27),
            profile=UserProfile(horizon="short", risk="moderate"),
            request_id=f"test-{stock}",
        )

        result = await news_agent.fetch(request)

        if hasattr(result, "reason"):
            print(f"  FetchFailure: {result.reason} — {result.error}")
            continue

        nodes = result
        print(f"  Got {len(nodes)} nodes\n")

        for node in nodes[:5]:
            print(f"  Node: {node.name}")
            print(f"  Source: {node.source} (confidence: {node.confidence})")
            print(f"  Signal: {node.signal.value} | Weight: {node.weight}")
            print(f"  Horizon: {node.horizon_relevance.value}")
            print(f"  Date: {node.as_of_date}")
            print(f"  Value:")
            for line in node.value.split("\n"):
                print(f"    {line}")
            raw = node.value_raw
            print(f"  value_raw keys: {list(raw.keys())}")
            if raw.get("llm_summary"):
                print(f"  LLM Summary: {raw['llm_summary'][:150]}...")
            print()


if __name__ == "__main__":
    asyncio.run(main())
