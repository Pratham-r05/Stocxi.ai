"""
fetch_premierene.py — Fetch all 7 component data for PREMIERENE and write to premierene_data.json.

Premier Energies Ltd — NSE: PREMIERENE (solar panels / EPC / renewable energy, listed 2024)

Run:
  cd stocxi
  python -m backend.tests.research.fetch_premierene
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from backend.schemas.messages import UserProfile, Horizon, Risk

SYMBOL  = "PREMIERENE"
AS_OF   = date.today()
PROFILE = UserProfile(horizon=Horizon.short, risk=Risk.moderate)
OUT     = os.path.join(os.path.dirname(__file__), "premierene_data.json")


def _ser(obj):
    """JSON serializer for dates/datetimes and pydantic models."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


async def main() -> None:
    output: dict = {
        "symbol":     SYMBOL,
        "as_of":      AS_OF.isoformat(),
        "fetched_at": datetime.now().isoformat(),
        "components": {}
    }

    # ── 1. Price ──────────────────────────────────────────────────────────────
    print("Fetching price...", flush=True)
    try:
        from backend.services.price_service import get_price
        nodes = await get_price(SYMBOL, AS_OF, PROFILE)
        output["components"]["price"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}  [{n.source}]")
    except Exception as e:
        output["components"]["price"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 2. OHLCV ─────────────────────────────────────────────────────────────
    print("Fetching OHLCV...", flush=True)
    try:
        from backend.services.ohlcv_service import get_ohlcv
        df = await get_ohlcv(SYMBOL, AS_OF)
        tail = df.tail(30).reset_index()
        output["components"]["ohlcv"] = {
            "total_rows": len(df),
            "columns":    list(df.columns),
            "date_range": {
                "from": str(df.index[0].date()) if not df.empty else None,
                "to":   str(df.index[-1].date()) if not df.empty else None,
            },
            "latest_30_rows": [
                {
                    "date":   str(row["date"].date()) if hasattr(row.get("date"), "date") else str(row.get("date", row.index if hasattr(row, "index") else "")),
                    "open":   round(float(row["Open"]),  2),
                    "high":   round(float(row["High"]),  2),
                    "low":    round(float(row["Low"]),   2),
                    "close":  round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                }
                for _, row in tail.iterrows()
            ],
        }
        print(f"  ✓ {len(df)} rows  {df.index[0].date()} → {df.index[-1].date()}")
    except Exception as e:
        output["components"]["ohlcv"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 3. Key Ratios ─────────────────────────────────────────────────────────
    print("Fetching ratios...", flush=True)
    try:
        from backend.services.ratios_service import get_ratios
        nodes = await get_ratios(SYMBOL, AS_OF, PROFILE)
        output["components"]["key_ratios"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}  [{n.signal.value}]")
    except Exception as e:
        output["components"]["key_ratios"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 4. Financial Statements ───────────────────────────────────────────────
    print("Fetching financials...", flush=True)
    try:
        from backend.services.financials_service import get_financials
        nodes = await get_financials(SYMBOL, AS_OF, PROFILE)
        output["components"]["financial_statements"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}  [{n.signal.value}]")
    except Exception as e:
        output["components"]["financial_statements"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 5. Shareholding ───────────────────────────────────────────────────────
    print("Fetching shareholding...", flush=True)
    try:
        from backend.services.shareholding_service import get_shareholding
        nodes = await get_shareholding(SYMBOL, AS_OF, PROFILE)
        output["components"]["shareholding"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}  [{n.signal.value}]")
    except Exception as e:
        output["components"]["shareholding"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 6. Technical Indicators ───────────────────────────────────────────────
    print("Fetching technicals...", flush=True)
    try:
        from backend.services.technicals_service import get_technicals
        nodes = await get_technicals(SYMBOL, as_of_date=AS_OF, profile=PROFILE)
        output["components"]["technicals"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}  [{n.signal.value}]")
    except Exception as e:
        output["components"]["technicals"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── 7. Announcements ──────────────────────────────────────────────────────
    print("Fetching announcements...", flush=True)
    try:
        from backend.services.announcements_service import get_announcements
        nodes = await get_announcements(SYMBOL, AS_OF, PROFILE)
        output["components"]["announcements"] = {
            "node_count": len(nodes),
            "nodes": [n.model_dump() for n in nodes],
        }
        for n in nodes:
            print(f"  ✓ {n.name}: {n.value}")
    except Exception as e:
        output["components"]["announcements"] = {"error": str(e)}
        print(f"  ✗ {e}")

    # ── Write JSON ────────────────────────────────────────────────────────────
    with open(OUT, "w") as f:
        json.dump(output, f, indent=2, default=_ser)

    total = sum(
        v.get("node_count", 0)
        for v in output["components"].values()
        if isinstance(v, dict)
    )
    print(f"\nDone. {total} total nodes → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
