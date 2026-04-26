"""
test_screener_reliability.py — Screener.in reliability test across 10 random stocks.

Tests every data category Stocxi depends on:
  1. P/E ratio, ROE, ROCE, Book Value, EPS  (top-ratios)
  2. Quarterly P&L
  3. Annual P&L
  4. Balance Sheet
  5. Cash Flow
  6. Shareholding
  7. MF Holdings

Stocks: mix of large-cap, mid-cap, small-cap, PSU, NBFC across sectors.
Run: conda run -n datatest python test_screener_reliability.py
"""

import time
import requests
from bs4 import BeautifulSoup
import re
import random

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# 10 random stocks — varied sectors + caps
STOCKS = [
    ("RELIANCE",     "reliance-industries"),
    ("HDFCBANK",     "hdfc-bank"),
    ("INFY",         "infosys"),
    ("TATAMOTORS",   "tata-motors"),
    ("SUNPHARMA",    "sun-pharmaceutical-industries"),
    ("IRCTC",        "irctc"),
    ("ZOMATO",       "zomato"),
    ("COALINDIA",    "coal-india"),
    ("BAJFINANCE",   "bajaj-finance"),
    ("DMART",        "avenue-supermarts"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TIMEOUT = 15

CATEGORIES = [
    "pe_ratio", "roe", "roce", "book_value", "eps",
    "quarterly_results", "annual_results",
    "balance_sheet", "cash_flow",
    "shareholding", "mf_holdings",
]


def fetch_soup(symbol_slug: str) -> tuple[BeautifulSoup | None, str | None]:
    """Try consolidated then screener URL. Returns (soup, used_url)."""
    urls = [
        f"https://www.screener.in/company/{symbol_slug}/consolidated/",
        f"https://www.screener.in/company/{symbol_slug}/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.text) > 5000:
                return BeautifulSoup(r.text, "html.parser"), url
        except Exception as e:
            pass
    return None, None


def parse_top_ratios(soup) -> dict:
    result = {k: None for k in ["pe_ratio", "roe", "roce", "book_value", "eps"]}
    try:
        ul = soup.find("ul", {"id": "top-ratios"})
        if not ul:
            return result
        for li in ul.find_all("li"):
            name_el  = li.find("span", class_="name")
            value_el = li.find("span", class_="nowrap value") or li.find("span", class_="value")
            if not name_el or not value_el:
                continue
            name = name_el.get_text(strip=True).lower()
            raw  = value_el.get_text(strip=True).replace(",", "")
            m = re.search(r"[-+]?\d+\.?\d*", raw)
            val = float(m.group()) if m else None
            if "stock p/e" in name or ("p/e" in name and "stock" in name):
                result["pe_ratio"] = val
            elif "book value" in name:
                result["book_value"] = val
            elif "eps" in name:
                result["eps"] = val
            elif "roce" in name:
                result["roce"] = val
            elif "roe" in name:
                result["roe"] = val
    except Exception:
        pass
    return result


def parse_table(soup, section_id: str) -> dict:
    try:
        table = soup.find("section", {"id": section_id})
        if not table:
            table = soup.find(id=section_id)
        if not table:
            return {}
        tbl = table.find("table")
        if not tbl:
            return {}
        rows = tbl.find_all("tr")
        if not rows:
            return {}
        return {"rows": len(rows), "ok": True}
    except Exception:
        return {}


def parse_mf_holdings(soup) -> dict:
    try:
        company_id = None
        root = soup.find(attrs={"data-company-id": True})
        if root:
            company_id = root.get("data-company-id")
        if not company_id:
            m = re.search(r'data-company-id="(\d+)"', str(soup))
            if m:
                company_id = m.group(1)
        if not company_id:
            return {"ok": False, "reason": "no company_id"}

        api_url = f"https://www.screener.in/api/3/{company_id}/investors/domestic_institutions/quarterly/"
        r = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "reason": f"HTTP {r.status_code}"}

        data = r.json()
        mf_count = sum(
            1 for k in data if isinstance(k, str) and "mutual fund" in k.lower()
        )
        return {"ok": mf_count > 0, "mf_funds": mf_count, "total_investors": len(data)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*65}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*65}{RESET}")


def ok(label, note=""):
    note_str = f"  {YELLOW}({note}){RESET}" if note else ""
    print(f"    {GREEN}✓{RESET} {label}{note_str}")


def fail(label, note=""):
    note_str = f"  {RED}({note}){RESET}" if note else ""
    print(f"    {RED}✗{RESET} {label}{note_str}")


# ── Master results tracker ────────────────────────────────────────────────────
# per_stock[symbol][category] = True/False
per_stock: dict[str, dict[str, bool]] = {}
fetch_ok:  dict[str, bool] = {}

section("Screener.in — 10 Stock Reliability Test")
print(f"  Testing {len(STOCKS)} stocks × {len(CATEGORIES)} data categories\n")

for symbol, slug in STOCKS:
    print(f"\n  {BOLD}[{symbol}]{RESET}  ({slug})")
    per_stock[symbol] = {}

    soup, used_url = fetch_soup(slug)
    if soup is None:
        print(f"    {RED}✗ PAGE FETCH FAILED — skipping all categories{RESET}")
        fetch_ok[symbol] = False
        for cat in CATEGORIES:
            per_stock[symbol][cat] = False
        continue

    fetch_ok[symbol] = True
    print(f"    {GREEN}✓ page fetched{RESET}  {YELLOW}({used_url}){RESET}")

    # ── 1-5: Top ratios ───────────────────────────────────────────────────────
    ratios = parse_top_ratios(soup)
    for field in ["pe_ratio", "roe", "roce", "book_value", "eps"]:
        val = ratios.get(field)
        if val is not None:
            ok(field, str(val))
            per_stock[symbol][field] = True
        else:
            fail(field, "None")
            per_stock[symbol][field] = False

    # ── 6: Quarterly results ──────────────────────────────────────────────────
    q = parse_table(soup, "quarters")
    if q.get("ok"):
        ok("quarterly_results", f"{q['rows']} rows")
        per_stock[symbol]["quarterly_results"] = True
    else:
        fail("quarterly_results", "table missing")
        per_stock[symbol]["quarterly_results"] = False

    # ── 7: Annual results ─────────────────────────────────────────────────────
    a = parse_table(soup, "profit-loss")
    if a.get("ok"):
        ok("annual_results", f"{a['rows']} rows")
        per_stock[symbol]["annual_results"] = True
    else:
        fail("annual_results", "table missing")
        per_stock[symbol]["annual_results"] = False

    # ── 8: Balance sheet ──────────────────────────────────────────────────────
    b = parse_table(soup, "balance-sheet")
    if b.get("ok"):
        ok("balance_sheet", f"{b['rows']} rows")
        per_stock[symbol]["balance_sheet"] = True
    else:
        fail("balance_sheet", "table missing")
        per_stock[symbol]["balance_sheet"] = False

    # ── 9: Cash flow ──────────────────────────────────────────────────────────
    c = parse_table(soup, "cash-flow")
    if c.get("ok"):
        ok("cash_flow", f"{c['rows']} rows")
        per_stock[symbol]["cash_flow"] = True
    else:
        fail("cash_flow", "table missing")
        per_stock[symbol]["cash_flow"] = False

    # ── 10: Shareholding ──────────────────────────────────────────────────────
    sh = parse_table(soup, "shareholding")
    if sh.get("ok"):
        ok("shareholding", f"{sh['rows']} rows")
        per_stock[symbol]["shareholding"] = True
    else:
        fail("shareholding", "table missing")
        per_stock[symbol]["shareholding"] = False

    # ── 11: MF holdings (separate API call) ───────────────────────────────────
    mf = parse_mf_holdings(soup)
    if mf.get("ok"):
        ok("mf_holdings", f"{mf['mf_funds']} MF funds / {mf['total_investors']} investors")
        per_stock[symbol]["mf_holdings"] = True
    else:
        fail("mf_holdings", mf.get("reason", "failed"))
        per_stock[symbol]["mf_holdings"] = False

    time.sleep(1.5)   # be polite to Screener


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY — Per-Category Success Rate")

col_w = 22
sym_w = 14

header = f"  {'Category':<{col_w}}" + "".join(f"{s:<{sym_w}}" for s, _ in STOCKS)
print(header)
print(f"  {'─'*col_w}" + ("─"*sym_w)*len(STOCKS))

cat_pass = {cat: 0 for cat in CATEGORIES}

for cat in CATEGORIES:
    row = f"  {cat:<{col_w}}"
    for symbol, _ in STOCKS:
        v = per_stock.get(symbol, {}).get(cat, False)
        if v:
            cat_pass[cat] += 1
            row += f"{GREEN}✓{RESET}{'':<{sym_w-1}}"
        else:
            row += f"{RED}✗{RESET}{'':<{sym_w-1}}"
    pct = int(100 * cat_pass[cat] / len(STOCKS))
    bar = "█" * (pct // 10)
    color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
    row += f"  {color}{pct:3d}% {bar}{RESET}"
    print(row)

# Overall probability
section("OVERALL PROBABILITY OF SUCCESS")

total_checks = len(STOCKS) * len(CATEGORIES)
total_pass   = sum(cat_pass.values())
overall_pct  = 100 * total_pass / total_checks

print(f"\n  Stocks tested     : {len(STOCKS)}")
print(f"  Categories tested : {len(CATEGORIES)}")
print(f"  Total checks      : {total_checks}")
print(f"  Passed            : {GREEN}{total_pass}{RESET}")
print(f"  Failed            : {RED}{total_checks - total_pass}{RESET}")
print(f"\n  {BOLD}Overall success rate: ", end="")
color = GREEN if overall_pct >= 80 else YELLOW if overall_pct >= 60 else RED
print(f"{color}{overall_pct:.1f}%{RESET}\n")

print(f"  {BOLD}Per-category breakdown:{RESET}")
for cat, passed in sorted(cat_pass.items(), key=lambda x: x[1], reverse=True):
    pct = 100 * passed / len(STOCKS)
    color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
    bar = "█" * int(pct // 10)
    print(f"    {cat:<22} {color}{passed}/{len(STOCKS)}  {pct:.0f}%  {bar}{RESET}")

print()
