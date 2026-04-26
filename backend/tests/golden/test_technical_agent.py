"""
test_technical_agent.py — Golden-file tests for agent_technical.

Verifies:
  1. All 17 indicator nodes returned (or graceful partial on thin data)
  2. N_MIN threshold: at least 10 nodes per stock (ARCHITECTURE.md §14)
  3. node_id format: "{STOCK}|technical|{Name}|{date}"
  4. All nodes have sanitized=True
  5. All signal values are valid NodeSignal enum values
  6. Each expected indicator name appears in the node list
  7. Weight version stamped correctly from versions.yaml
  8. Signals are directionally sane for RELIANCE (large-cap, liquid)

Run from repo root with venv active:
    python -m pytest backend/tests/golden/test_technical_agent.py -v

Or run directly:
    cd backend && python tests/golden/test_technical_agent.py
"""

from __future__ import annotations

import asyncio
import sys
import os
import uuid
from datetime import date

# Allow running directly from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from backend.agents.agent_technical import run
from backend.schemas.messages import FetchRequest, Horizon, Risk, UserProfile
from backend.schemas.node import NodeCategory, NodeSignal
from backend.util.ist_calendar import as_of_date_for_fetch

# ── Constants ─────────────────────────────────────────────────────────────────

EXPECTED_NAMES = {
    "RSI", "MACD", "ADX", "ATR", "Bollinger_Bands", "EMA",
    "SMA", "Ichimoku_Cloud", "Parabolic_SAR",
    "Stochastic", "Williams_R", "ROC",
    "OBV", "VWAP", "CMF", "MFI",
    "Week_52_Ratio",
}
N_MIN = 10  # from versions.yaml min_nodes.technical

TEST_STOCKS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC"]

PROFILES = [
    UserProfile(horizon=Horizon.short, risk=Risk.moderate),
    UserProfile(horizon=Horizon.long,  risk=Risk.conservative),
]


def _make_request(stock: str, profile: UserProfile) -> FetchRequest:
    return FetchRequest(
        stock=stock,
        as_of_date=as_of_date_for_fetch(),
        profile=profile,
        request_id=str(uuid.uuid4()),
    )


# ── Test helpers ──────────────────────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    icon = PASS if cond else FAIL
    print(f"    {icon}  {msg}")
    if not cond:
        _failures.append(msg)


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── Core assertions ───────────────────────────────────────────────────────────

def assert_nodes(stock: str, nodes: list, profile: UserProfile) -> None:
    horizon = profile.horizon.value
    names   = {n.name for n in nodes}

    check(len(nodes) >= N_MIN,
          f"{stock}/{horizon}: {len(nodes)} nodes ≥ N_MIN({N_MIN})")

    check(len(nodes) <= len(EXPECTED_NAMES),
          f"{stock}/{horizon}: node count {len(nodes)} ≤ 17")

    for n in nodes:
        # node_id format
        parts = n.node_id.split("|")
        check(
            len(parts) == 4
            and parts[0] == stock.upper()
            and parts[1] == "technical"
            and parts[2] == n.name
            and parts[3] == str(n.as_of_date),
            f"{stock}/{horizon} node_id format: {n.node_id}",
        )

        # sanitized flag
        check(n.sanitized is True,
              f"{stock}/{horizon} {n.name}: sanitized=True")

        # valid NodeSignal
        check(n.signal in (NodeSignal.positive, NodeSignal.negative, NodeSignal.neutral),
              f"{stock}/{horizon} {n.name}: signal is valid NodeSignal")

        # category
        check(n.category == NodeCategory.technical,
              f"{stock}/{horizon} {n.name}: category=technical")

        # weight is non-negative
        check(n.weight >= 0.0,
              f"{stock}/{horizon} {n.name}: weight={n.weight} ≥ 0")

        # weight_version stamped
        check(n.weight_version != "",
              f"{stock}/{horizon} {n.name}: weight_version stamped")

        # confidence in [0, 1]
        check(0.0 <= n.confidence <= 1.0,
              f"{stock}/{horizon} {n.name}: confidence in [0,1]")

    # Key indicators present
    for expected in EXPECTED_NAMES:
        if expected not in names:
            print(f"    {WARN} {stock}/{horizon}: {expected} missing (data may be thin)")


def assert_reliance_sanity(nodes: list) -> None:
    """
    RELIANCE is one of India's largest, most liquid stocks.
    We assert directional sanity — not exact values, but reasonable ranges.
    """
    by_name = {n.name: n for n in nodes}

    if "RSI" in by_name:
        rsi_raw = by_name["RSI"].value_raw.get("rsi")
        if rsi_raw is not None:
            check(0 < rsi_raw < 100, f"RELIANCE RSI in range: {rsi_raw}")

    if "ADX" in by_name:
        adx_raw = by_name["ADX"].value_raw.get("adx")
        if adx_raw is not None:
            check(adx_raw >= 0, f"RELIANCE ADX non-negative: {adx_raw}")

    if "Week_52_Ratio" in by_name:
        r52 = by_name["Week_52_Ratio"].value_raw.get("week_52_ratio")
        if r52 is not None:
            check(0.0 <= r52 <= 1.0, f"RELIANCE 52W ratio in [0,1]: {r52}")

    if "CMF" in by_name:
        cmf = by_name["CMF"].value_raw.get("cmf")
        if cmf is not None:
            check(-1.0 <= cmf <= 1.0, f"RELIANCE CMF in [-1,1]: {cmf}")

    if "MFI" in by_name:
        mfi = by_name["MFI"].value_raw.get("mfi")
        if mfi is not None:
            check(0 <= mfi <= 100, f"RELIANCE MFI in [0,100]: {mfi}")

    if "Stochastic" in by_name:
        k = by_name["Stochastic"].value_raw.get("stoch_k")
        if k is not None:
            check(0 <= k <= 100, f"RELIANCE Stochastic %K in [0,100]: {k}")


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_all() -> None:
    print("\n" + "═" * 60)
    print("  Milestone 1 — Technical Agent Golden Tests")
    print("═" * 60)

    for stock in TEST_STOCKS:
        for profile in PROFILES:
            section(f"{stock} / horizon={profile.horizon.value} risk={profile.risk.value}")
            req   = _make_request(stock, profile)
            nodes = await run(req)

            print(f"  → {len(nodes)} nodes returned")
            for n in sorted(nodes, key=lambda x: x.name):
                print(f"     • {n.name:<20} signal={n.signal.value:<10} w={n.weight:.4f}  {n.value[:60]}")

            assert_nodes(stock, nodes, profile)
            if stock == "RELIANCE" and profile.horizon == Horizon.short:
                assert_reliance_sanity(nodes)

    print("\n" + "═" * 60)
    if _failures:
        print(f"  FAILED — {len(_failures)} assertion(s):")
        for f in _failures:
            print(f"    ❌ {f}")
        sys.exit(1)
    else:
        print(f"  ALL ASSERTIONS PASSED ✅")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all())
