# Stocxi Backend — Testing Questions for VSCode

> Paste each question into VSCode Copilot / Cursor / Claude Code.
> Run from: `/Users/prathamraj/Documents/Placement-Prep/10.Projects/stocxi/backend`
> Server must be running: `uvicorn main:app --reload --port 8000`

---

## Current Verified Status (2026-04-14)

Tested against fresh backend instances on `http://127.0.0.1:8001` through `http://127.0.0.1:8010`.

### ✅ Working

- Health endpoint returns `status`, `version`, and `redis` (`connected`).
- Stock overview works for RELIANCE/TCS/INFY/HDFCBANK with valid price + technicals.
- RELIANCE overview has full company name (`Reliance Industries Limited`).
- RELIANCE overview has non-null `pe_ratio` and `market_cap` (from Screener ratios).
- Invalid symbol endpoint returns HTTP 404 with `detail`.
- Financials endpoint returns quarterly + annual + balance sheet + cash flow + shareholding.
- News endpoint returns valid article objects; `?limit=3` behaves correctly.
- Search endpoint returns valid symbol lists for `REL`, `TAT`, `HDFC` (including RELIANCE and HDFCBANK).
- AI analysis endpoint returns 200 with structured response and no `error` key.
- Invalid AI risk level (`extreme`) returns 422 (no 500 crash).
- Redis cache hit latency observed around `0.24s-0.25s` on localhost.
- Concurrent requests (5 parallel stock calls) return 200 without crashes.
- Full INFY flow (search → overview → financials → news → analysis) returns all 200.
- Screener timeout chaos test (Step 16) passes: with `_TIMEOUT=0.001`, endpoint returned graceful 404 (no 500 crash), then timeout was reverted.
- Announcements endpoint now returns populated entries (NSE source) for tested symbols like RELIANCE/TCS/INFY.
- AI risk profile behavior verified on fresh symbols (example: HEROMOTOCO produced low=HOLD, medium=BUY, high=BUY).
- Mutual fund holdings extraction is fixed via Screener investor API and returns rows for symbols with available MF data (confirmed: RELIANCE, INFY).
- Financials response now includes `mf_holdings_source_status` + `mf_holdings_note` for explicit frontend messaging.

### ⚠️ Partially Working / Notes

- `mf_holdings` can be empty for some symbols (e.g., TCS, HDFCBANK) when Screener investor drilldown has no mutual-fund rows for that company.
- Same verdict across all risk levels may still occur for some symbols when the underlying data strongly points in one direction.
- Occasional AI provider malformed JSON may still happen upstream; service now retries this case before returning fallback.

### ❌ Not Verified Yet

- None in this pass.

---

## 1. Health Check

**Question to ask VSCode AI:**
> Run `curl http://localhost:8000/health` and confirm the server is running and Redis is connected.

**Expected result:**
```json
{ "status": "ok", "version": "1.0.0", "redis": "connected" }
```

---

## 2. Stock Overview — Price + Fundamentals + Technicals

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE` and check:
> - price is a number (not null)
> - week_52_high and week_52_low are numbers
> - change_percent is a number
> - technicals.rsi is a number between 0-100
> - technicals.overall_signal is one of: Bullish, Bearish, Neutral, Mixed
> - pe_ratio is NOT null (should come from screener #top-ratios)
> - market_cap is NOT null
> - company_name is "Reliance Industries Limited" NOT "RELIANCE"

**Expected issues to catch:**
- `company_name` returning ticker symbol instead of full name
- `pe_ratio` and `market_cap` still null (screener ratios not merging)

---

## 3. Stock Overview — Different Symbols

**Question:**
> Run these three curls and confirm all return valid price data:
> ```
> curl http://localhost:8000/api/v1/stock/TCS
> curl http://localhost:8000/api/v1/stock/INFY
> curl http://localhost:8000/api/v1/stock/HDFCBANK
> ```
> For each: price > 0, technicals present, no 500 errors.

---

## 4. Invalid Symbol — Must Return 404

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/INVALIDSYMBOLXYZ` and confirm:
> - HTTP status is 404 (not 500)
> - Response has a `detail` field explaining symbol not found

---

## 5. Financials — Quarterly P&L

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE/financials` and check:
> - `quarterly_results.headers` has at least 4 date columns (e.g. "Mar 2024", "Jun 2024")
> - `quarterly_results.rows` has at least 8 rows (Revenue, Expenses, EBITDA, Net Profit etc.)
> - `balance_sheet.rows` has at least 5 rows
> - `cash_flow.rows` has at least 3 rows
> - `shareholding.rows` has at least 4 rows (Promoter, FII, DII, Public)

---

## 6. Financials — Annual P&L (if implemented)

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE/financials` and check:
> - Response contains `annual_results` key
> - `annual_results.headers` has year columns (e.g. "2020", "2021", "2022")
> - `annual_results.rows` has Revenue and Net Profit rows

---

## 7. MF Holdings (if implemented)

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE/financials` and check:
> - Response contains `mf_holdings` key
> - Response contains `mf_holdings_source_status` (`available` or `not_available`)
> - Response contains `mf_holdings_note` (human-readable explanation)
> - For RELIANCE/INFY, `mf_holdings.rows` has at least 1 mutual fund entry
> - For some symbols, empty rows are acceptable if Screener has no MF investor rows
> - Each row has a fund name and holding percentage

---

## 8. News Headlines

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE/news` and check:
> - `count` is between 1 and 10
> - Each article has: `title`, `link`, `published`, `source`
> - `title` is not empty or "None"
> - `link` starts with "http"

---

## 9. News — Limit Parameter

**Question:**
> Run `curl "http://localhost:8000/api/v1/stock/TCS/news?limit=3"` and confirm:
> - `count` is 3 or less
> - `articles` array has exactly 3 items

---

## 10. Announcements (if implemented)

**Question:**
> Run `curl http://localhost:8000/api/v1/stock/RELIANCE/announcements` and check:
> - Returns a list of announcements from NSE corporate announcements source
> - Empty list is acceptable when source has no recent entries for a symbol
> - Each returned item has `title`/`subject`, `date`, and `category`
> - No 500 error

---

## 11. Search Autocomplete

**Question:**
> Run these and confirm results:
> ```
> curl "http://localhost:8000/api/v1/search?q=REL"
> curl "http://localhost:8000/api/v1/search?q=TAT"
> curl "http://localhost:8000/api/v1/search?q=HDFC"
> ```
> Each should return a list of matching stock symbols/names.
> "REL" should include RELIANCE. "HDFC" should include HDFCBANK and HDFCLIFE.

---

## 12. AI Analysis — Medium Risk

**Question:**
> Run `curl "http://localhost:8000/api/v1/analysis/RELIANCE?risk_level=medium"` and check:
> - `final_verdict` is one of: BUY, HOLD, AVOID
> - `fundamentals.verdict` is one of: Strong, Weak, Neutral
> - `technicals.verdict` is one of: Bullish, Bearish, Mixed
> - `news.verdict` is one of: Positive, Negative, Neutral
> - `plain_english` is a non-empty string (3+ sentences)
> - `disclaimer` field is present
> - `risk_match` is true or false (boolean)
> - No `error` key in response

---

## 13. AI Analysis — All Risk Levels

**Question:**
> Run all three and confirm different responses:
> ```
> curl "http://localhost:8000/api/v1/analysis/TCS?risk_level=low"
> curl "http://localhost:8000/api/v1/analysis/TCS?risk_level=medium"
> curl "http://localhost:8000/api/v1/analysis/TCS?risk_level=high"
> ```
> The `plain_english` field should mention different risk considerations.
> All three should complete without error.

---

## 14. AI Analysis — Invalid Risk Level

**Question:**
> Run `curl "http://localhost:8000/api/v1/analysis/RELIANCE?risk_level=extreme"` and confirm:
> - Either returns 422 validation error OR defaults to "medium"
> - Does NOT return 500

---

## 15. Redis Caching — Verify Speed

**Question:**
> Run the same endpoint twice and measure response time:
> ```
> time curl http://localhost:8000/api/v1/stock/RELIANCE
> time curl http://localhost:8000/api/v1/stock/RELIANCE
> ```
> First call: 3-8 seconds (cold fetch)
> Second call: under ~300ms on localhost (cache hit)
> If second call is still slow, Redis caching is broken.

---

## 16. Screener Timeout Graceful Handling

**Question:**
> Temporarily set `_TIMEOUT = 0.001` in `screener_service.py`, restart server, run:
> `curl http://localhost:8000/api/v1/stock/RELIANCE/financials`
> Confirm: returns 404 or empty financials — NOT a 500 crash.
> Revert the timeout after testing.

---

## 17. Concurrent Requests (Stress Test)

**Question:**
> Run 5 simultaneous requests:
> ```bash
> for i in 1 2 3 4 5; do
>   curl http://localhost:8000/api/v1/stock/TCS &
> done
> wait
> ```
> All 5 should return 200. No crashes, no race conditions.

---

## 18. Full End-to-End Flow

**Question:**
> Simulate what the frontend does for a user searching "INFY":
> 1. `curl "http://localhost:8000/api/v1/search?q=INFY"` → find the symbol
> 2. `curl http://localhost:8000/api/v1/stock/INFY` → get overview
> 3. `curl http://localhost:8000/api/v1/stock/INFY/financials` → get financials
> 4. `curl http://localhost:8000/api/v1/stock/INFY/news` → get news
> 5. `curl "http://localhost:8000/api/v1/analysis/INFY?risk_level=medium"` → get AI verdict
>
> All 5 must return 200 with valid data. This is the complete user journey.

---

## Known Issues to Verify Fixed

| Issue | Test | Pass condition |
|---|---|---|
| company_name returns ticker | Step 2 above | Returns "Reliance Industries Limited" not "RELIANCE" |
| PE ratio null | Step 2 above | pe_ratio is a number |
| Market cap null | Step 2 above | market_cap is a number |
| Sector null | Step 2 above | sector is a string (may still be null — acceptable) |
| yfinance 429 | Any stock endpoint | No 429 errors in logs |
| Screener timeout crash | Step 16 above | Returns gracefully, no 500 |
