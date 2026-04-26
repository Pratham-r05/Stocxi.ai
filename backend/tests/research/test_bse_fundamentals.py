"""
test_bse_fundamentals.py — Test BSE.resultsSnapshot() + BSE.equityMetaInfo()
for P/E, EPS, ROE, ROCE, Book Value across 10 stocks.

Run: conda run -n datatest python test_bse_fundamentals.py
"""

import time
import json
from bse import BSE

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

STOCKS = [
    ("RELIANCE",   "500325"),
    ("HDFCBANK",   "500180"),
    ("INFY",       "500209"),
    ("TATAMOTORS", "500570"),
    ("SUNPHARMA",  "524715"),
    ("IRCTC",      "542830"),
    ("ZOMATO",     "543320"),
    ("COALINDIA",  "533278"),
    ("BAJFINANCE", "500034"),
    ("DMART",      "540376"),
]

FIELDS = ["pe_ratio", "eps", "roe", "roce", "book_value", "pb_ratio", "opm", "npm"]

def section(t):
    print(f"\n{BOLD}{CYAN}{'─'*65}{RESET}\n{BOLD}{CYAN}  {t}{RESET}\n{BOLD}{CYAN}{'─'*65}{RESET}")

def ok(label, note=""):
    print(f"    {GREEN}✓{RESET} {label:<16} {YELLOW}{note}{RESET}")

def fail(label, note=""):
    print(f"    {RED}✗{RESET} {label:<16} {RED}{note}{RESET}")

def safe_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "", "-", "N/A") else None
    except Exception:
        return None


def extract_from_metainfo(data: dict, price: float | None = None) -> dict:
    """
    Pull all fundamentals from equityMetaInfo.
    Actual BSE field names (confirmed from live response):
      PE, EPS, ConEPS, ROE, ConROE, PB, OPM, NPM
    ROCE is NOT available from BSE — noted as N/A.
    Book Value = Price / PB (calculated).
    """
    result = {f: None for f in FIELDS}
    if not data or not isinstance(data, dict):
        return result

    result["pe_ratio"]  = safe_float(data.get("PE") or data.get("ConPE"))
    # Prefer consolidated EPS over standalone
    result["eps"]       = safe_float(data.get("ConEPS") or data.get("EPS"))
    result["roe"]       = safe_float(data.get("ConROE") or data.get("ROE"))
    result["pb_ratio"]  = safe_float(data.get("PB"))
    result["opm"]       = safe_float(data.get("OPM"))
    result["npm"]       = safe_float(data.get("NPM"))
    # Book Value = Price / P/B ratio
    pb = safe_float(data.get("PB"))
    if pb and pb > 0 and price and price > 0:
        result["book_value"] = round(price / pb, 2)
    # ROCE — not available in BSE equityMetaInfo or getScripTradingStats
    result["roce"] = None

    return result


def extract_eps_from_snapshot(data: dict) -> float | None:
    """
    Pull EPS from resultsSnapshot results_in_crores.data rows as fallback.
    Structure: {"fields": ["title","Mar-26",...], "data": [["EPS","5.48",...], ...]}
    """
    if not data or not isinstance(data, dict):
        return None
    try:
        block = data.get("results_in_crores") or {}
        if isinstance(block, str):
            import ast
            block = ast.literal_eval(block)
        rows = block.get("data", [])
        for row in rows:
            if row and str(row[0]).strip().upper() == "EPS":
                # last column is full-year value
                for v in reversed(row[1:]):
                    f = safe_float(v)
                    if f is not None:
                        return f
    except Exception:
        pass
    return None


section("BSE Fundamentals — 10 Stock Test")
print(f"  Using: BSE.resultsSnapshot() + BSE.equityMetaInfo()\n")

per_stock = {}

with BSE(download_folder="/tmp") as bse:
    for symbol, bse_code in STOCKS:
        print(f"\n  {BOLD}[{symbol}]{RESET}  BSE:{bse_code}")
        per_stock[symbol] = {f: None for f in FIELDS}

        # ── Step 1: quote (need price for Book Value calc) ────────────────────
        price = None
        try:
            q = bse.quote(bse_code)
            raw_price = q.get("CurrentValue") or q.get("Last") or q.get("LTP")
            price = safe_float(raw_price)
        except Exception:
            pass

        # ── Step 2: equityMetaInfo (primary source for all ratios) ───────────
        meta_data = {}
        try:
            meta_data = bse.equityMetaInfo(bse_code)
            ok("equityMetaInfo", f"PE={meta_data.get('PE')}  EPS={meta_data.get('ConEPS') or meta_data.get('EPS')}  ROE={meta_data.get('ConROE') or meta_data.get('ROE')}  PB={meta_data.get('PB')}")
        except Exception as e:
            fail("equityMetaInfo", str(e))

        # ── Step 3: resultsSnapshot (EPS fallback) ────────────────────────────
        snapshot_data = {}
        try:
            snapshot_data = bse.resultsSnapshot(scripcode=bse_code)
        except Exception:
            pass

        # ── Extract all fields ────────────────────────────────────────────────
        extracted = extract_from_metainfo(meta_data, price)

        # EPS fallback from snapshot if meta gave None
        if extracted["eps"] is None:
            extracted["eps"] = extract_eps_from_snapshot(snapshot_data)

        for field in FIELDS:
            per_stock[symbol][field] = extracted.get(field)

        # Print field results
        print(f"    {'─'*40}")
        for field in FIELDS:
            val = per_stock[symbol][field]
            if val is not None:
                ok(field, str(val))
            else:
                fail(field, "None — not in BSE API" if field == "roce" else "None")

        time.sleep(0.8)

# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY — Per-Field Success Rate")

col_w = 14
sym_w = 13

header = f"  {'Field':<{col_w}}" + "".join(f"{s:<{sym_w}}" for s, _ in STOCKS)
print(header)
print(f"  {'─'*col_w}" + "─"*sym_w*len(STOCKS))

field_pass = {f: 0 for f in FIELDS}

for field in FIELDS:
    row = f"  {field:<{col_w}}"
    for symbol, _ in STOCKS:
        val = per_stock[symbol].get(field)
        if val is not None:
            field_pass[field] += 1
            row += f"{GREEN}✓{RESET}{'':<{sym_w-1}}"
        else:
            row += f"{RED}✗{RESET}{'':<{sym_w-1}}"
    pct = int(100 * field_pass[field] / len(STOCKS))
    color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
    bar = "█" * (pct // 10)
    row += f"  {color}{pct:3d}%  {bar}{RESET}"
    print(row)

total_checks = len(STOCKS) * len(FIELDS)
total_pass   = sum(field_pass.values())
overall_pct  = 100 * total_pass / total_checks

print(f"\n  Total checks : {total_checks}")
print(f"  Passed       : {GREEN}{total_pass}{RESET}")
print(f"  Failed       : {RED}{total_checks - total_pass}{RESET}")
color = GREEN if overall_pct >= 80 else YELLOW if overall_pct >= 60 else RED
print(f"\n  {BOLD}Overall success rate: {color}{overall_pct:.1f}%{RESET}\n")

# Also show actual values table
section("ACTUAL VALUES TABLE")
print(f"  {'Symbol':<14}", end="")
for f in FIELDS:
    print(f"{f:<16}", end="")
print()
print(f"  {'─'*14}" + "─"*16*len(FIELDS))
for symbol, _ in STOCKS:
    print(f"  {symbol:<14}", end="")
    for f in FIELDS:
        val = per_stock[symbol].get(f)
        disp = f"{val:.2f}" if val is not None else "N/A"
        color = GREEN if val is not None else RED
        print(f"{color}{disp:<16}{RESET}", end="")
    print()
print()
