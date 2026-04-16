# PROGRESS.md — Sentiment Component Build Tracker

Last updated: 2026-04-16

---

## Status

| Agent | Task | Status | Files Changed |
|---|---|---|---|
| 1 | Setup files | ✅ Done | CLAUDE.md, PROGRESS.md (created) |
| 2 | Tool selection + .env spec | ✅ Done | PROGRESS.md, config.py, .env.example |
| 3 | sentiment_service.py | ✅ Done | backend/services/sentiment_service.py |
| 4 | Router integration | ✅ Done | backend/routers/stock.py |
| 5 | AI prompt extension | ✅ Done | backend/services/ai_service.py |
| 6 | Requirements + smoke test | ✅ Done | backend/requirements.txt |

---

## Decisions Log

### Agent 2 — Tool Selection

**Reddit:** `rdt-cli` (system CLI, no app credentials)
- Install: `pipx install rdt-cli`
- Called via subprocess: `rdt search "{symbol} NSE stock" --limit 25 --json`
- No credentials required in .env — rdt handles auth/guest access itself
- Why: Same tool used by /reddit slash command in Claude Code. No credentials needed.

**Twitter/X:** `twitter-cli` (system CLI, no app credentials)
- Install: `pipx install twitter-cli`
- Called via subprocess: `twitter search "{symbol} NSE stock" -n 25 --json`
- No credentials required in .env — twitter-cli uses cookie-based auth already configured
- Why: Same tool used by /x slash command in Claude Code. Consistent with project's no-credential approach.

**Sentiment:** `vaderSentiment==3.3.2`
- pip: `pip install vaderSentiment==3.3.2`
- No API key required — fully offline
- Why: Confirmed working, pip-installable, designed for social media text, fast

**No .env changes needed** — all data fetching is via CLI tools, zero credentials in the app.

**Risk Table:**
| Risk | Mitigation |
|---|---|
| CLI not in PATH | _find_cli() checks PATH, ~/.local/bin, /opt/homebrew/bin |
| CLI returns error/empty | _run_cli() retries 3x, returns None → fallback dict |
| CLI timeout | 20s timeout per attempt, 3 attempts total |
| Twitter search flaky | Fallback query with just symbol if complex query fails |
| Company name lookup fails (yfinance 429) | Falls back to symbol-only query, never raises |
| vaderSentiment returns NaN | Guarded with `compound != compound` check, defaults to 0.0 |
| Any exception in gather | return_exceptions=True, each source processed independently |

---

## Known Issues
_(agents append here when they hit problems)_
