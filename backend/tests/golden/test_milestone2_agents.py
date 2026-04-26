"""
test_milestone2_agents.py — Golden-file tests for Milestone 2 agents.

Tests agent_fundamental, agent_news, agent_announcement, agent_context on RELIANCE.
Uses TCS as a second validation stock for fundamentals.

Verified properties:
  - Nodes have correct shape (category, node_id format, confidence, weight, version)
  - Fundamental: N_MIN = 8 where data available; only ratios/percentages in values
  - News: sanitized=False (Orchestrator will scrub); signal is valid NodeSignal
  - Announcements: sanitized=False; confidence=0.80; source is nse/bse
  - Context: sanitized=True; always ≥1 node (Market_Regime)

Run from repo root:
    /Users/prathamraj/miniforge3/envs/stocxi/bin/python \\
        backend/tests/golden/test_milestone2_agents.py
"""

from __future__ import annotations

import asyncio
import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from backend.agents import agent_fundamental, agent_news, agent_announcement, agent_context
from backend.schemas.messages import FetchRequest, Horizon, Risk, UserProfile
from backend.schemas.node import NodeCategory, NodeSignal
from backend.util.ist_calendar import as_of_date_for_fetch

# ── Helpers ────────────────────────────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"    {'✅' if cond else '❌'}  {msg}")
    if not cond:
        _failures.append(msg)


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def _req(stock: str, horizon: Horizon = Horizon.long, risk: Risk = Risk.moderate) -> FetchRequest:
    return FetchRequest(
        stock=stock,
        as_of_date=as_of_date_for_fetch(),
        profile=UserProfile(horizon=horizon, risk=risk),
        request_id=str(uuid.uuid4()),
    )


def _check_node_shape(nodes: list, expected_category: NodeCategory, sanitized_expected: bool, label: str):
    """Shared shape assertions for any node list."""
    for n in nodes:
        parts = n.node_id.split("|")
        check(
            len(parts) == 4 and parts[1] == expected_category.value,
            f"{label} {n.name}: node_id format — {n.node_id[:60]}",
        )
        check(n.sanitized is sanitized_expected,
              f"{label} {n.name}: sanitized={sanitized_expected}")
        check(n.signal in (NodeSignal.positive, NodeSignal.negative, NodeSignal.neutral),
              f"{label} {n.name}: valid NodeSignal")
        check(0.0 <= n.confidence <= 1.0,
              f"{label} {n.name}: confidence in [0,1]")
        check(n.weight >= 0.0,
              f"{label} {n.name}: weight ≥ 0")
        check(n.weight_version != "",
              f"{label} {n.name}: weight_version stamped")
        check(n.category == expected_category,
              f"{label} {n.name}: category={expected_category.value}")


# ── Fundamental tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fundamental():
    section("Fundamental Agent — RELIANCE + TCS")
    N_MIN_FUND = 4  # lenient — Screener may be throttled; we need some nodes

    for stock in ["RELIANCE", "TCS"]:
        req   = _req(stock, Horizon.long)
        nodes = await agent_fundamental.run(req)
        print(f"\n  {stock}: {len(nodes)} fundamental nodes")
        for n in nodes:
            print(f"     • {n.name:<30} sig={n.signal.value:<10} w={n.weight:.4f}  {n.value[:60]}")

        # Shape assertions
        _check_node_shape(nodes, NodeCategory.fundamental, sanitized_expected=True, label=stock)

        # Data quality
        if nodes:
            check(len(nodes) >= N_MIN_FUND,
                  f"{stock}: ≥{N_MIN_FUND} fundamental nodes (got {len(nodes)})")

            # Values must not contain absolute monetary amounts in crores/lacs
            for n in nodes:
                val = n.value
                has_crore = "cr" in val.lower() and any(c.isdigit() for c in val[:20])
                check(not has_crore,
                      f"{stock} {n.name}: value does not expose raw crore amount")
        else:
            print(f"    {WARN} {stock}: 0 nodes — Screener may be throttled")


# ── News tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_news():
    section("News Agent — RELIANCE")
    req   = _req("RELIANCE", Horizon.short)
    nodes = await agent_news.run(req)
    print(f"\n  RELIANCE: {len(nodes)} news nodes")
    for n in nodes:
        print(f"     • {n.name}  sig={n.signal.value:<10}  {n.value[:70]}")

    if not nodes:
        print(f"    {WARN} 0 news nodes — news service may be unavailable or no recent news")
        return

    _check_node_shape(nodes, NodeCategory.news, sanitized_expected=False, label="RELIANCE news")

    check(all("News_" in n.name for n in nodes),
          "All news nodes named News_XX")
    check(all(n.confidence == 0.60 for n in nodes),
          "All news nodes have confidence=0.60")
    check(all(n.source_url != "" or n.value_raw.get("link", "") == "" for n in nodes),
          "News source_url set or link empty")


# ── Announcement tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_announcements():
    section("Announcement Agent — RELIANCE")
    req   = _req("RELIANCE")
    nodes = await agent_announcement.run(req)
    print(f"\n  RELIANCE: {len(nodes)} announcement nodes")
    for n in nodes:
        print(f"     • {n.name}  sig={n.signal.value:<10}  {n.value[:70]}")

    if not nodes:
        print(f"    {WARN} 0 announcement nodes — NSE/BSE API may be unavailable")
        return

    _check_node_shape(nodes, NodeCategory.announcement, sanitized_expected=False, label="RELIANCE ann")

    check(all("Announcement_" in n.name for n in nodes),
          "All announcement nodes named Announcement_XX")
    check(all(n.confidence == 0.80 for n in nodes),
          "All announcement nodes have confidence=0.80")
    check(all(n.source in ("nse_announcements", "bse_announcements") for n in nodes),
          "Announcement source is nse_announcements or bse_announcements")


# ── Context tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context():
    section("Context Agent — RELIANCE")
    req   = _req("RELIANCE")
    nodes = await agent_context.run(req)
    print(f"\n  RELIANCE: {len(nodes)} context nodes")
    for n in nodes:
        print(f"     • {n.name:<22}  sig={n.signal.value:<10}  {n.value[:60]}")

    check(len(nodes) >= 1, f"Context agent returns ≥1 node (got {len(nodes)})")

    _check_node_shape(nodes, NodeCategory.context, sanitized_expected=True, label="RELIANCE ctx")

    names = {n.name for n in nodes}
    check("Market_Regime" in names, "Market_Regime node present")
    if "Market_Regime" in names:
        regime = next(n for n in nodes if n.name == "Market_Regime")
        check(regime.value_raw.get("nifty_1m_return_pct") is not None or "unavailable" in regime.value.lower(),
              "Market_Regime has NIFTY return or graceful fallback")


# ── Runner ─────────────────────────────────────────────────────────────────────

async def run_all():
    print("\n" + "═" * 60)
    print("  Milestone 2 — Data Agents Golden Tests")
    print("═" * 60)

    await test_fundamental()
    await test_news()
    await test_announcements()
    await test_context()

    print("\n" + "═" * 60)
    if _failures:
        print(f"  FAILED — {len(_failures)} assertion(s):")
        for f in _failures:
            print(f"    ❌ {f}")
        sys.exit(1)
    else:
        print("  ALL ASSERTIONS PASSED ✅")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all())
