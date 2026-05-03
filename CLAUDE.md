# CLAUDE.md — Agent Operating Manual for Stocxi

> Every AI coding agent MUST read this file first, every session, before any other action.
> If anything in this file conflicts with a user request, STOP and ask.
## hello world i want to say that the 
---

## 0. Python Environment (NON-NEGOTIABLE)

**Always use the `stocxi` conda environment. Never use `.venv312` or any other venv.**

| Action | Command |
|---|---|
| Run Python / scripts | `conda run -n stocxi python ...` |
| Run pytest | `conda run -n stocxi python -m pytest ...` |
| Install packages | `conda run -n stocxi pip install <pkg>` |
| Start FastAPI | `conda run -n stocxi uvicorn backend.main:app ...` |
| Any shell one-liner | prefix with `conda run -n stocxi` |

Path: `/Users/prathamraj/miniforge3/envs/stocxi`

This applies to every Bash tool call, every install, every test run, every server start — no exceptions.

---

## 1. What Stocxi Is

Stocxi is an AI stock analysis platform for Indian retail investors with no finance
background. A user searches any NSE/BSE stock and receives a transparent, evidence-backed
analysis built from a strict knowledge graph of approved data sources.

Legal posture: not a SEBI advisor — never says "buy"; only describes what signals have
historically implied.

- Live URL: https://stocxi.vercel.app
- Stage: MVP live. Building full analysis pipeline (see docs/architecture/PLAN.md for phases).
- Progress: see docs/progress/NEW_PROGRESS.md

---

## 2. Tech Stack (pinned)

| Layer | Tech | Version |
|---|---|---|
| Frontend | Next.js on Vercel | existing |
| Backend | FastAPI | 0.115.x |
| Python | CPython | 3.12 |
| DB | PostgreSQL (Supabase) | 16+ |
| Cache / Queue | Redis | 7+ |
| Task orchestration | Celery (or Prefect for DAGs) | latest stable |
| NSE data | BennyThadikaran/NseIndiaApi | latest |
| BSE data | BennyThadikaran/BseIndiaApi | latest |
| Price fallback | yfinance | latest |
| Financial statements | Screener.in scraper (recency-picked) | custom |
| News | RSS feeds from approved domains only | custom |
| Technical indicators | `ta` Python library on OHLCV | latest |
| LLM — dev | Gemini 2.5 Flash (free tier) | via Google AI Studio |
| LLM — prod primary | Gemini 2.5 Flash (paid, pinned) | pinned model id |
| LLM — prod deep | Claude Sonnet API | pinned model id |
| Charts | Matplotlib, Plotly | latest |
| PDF | WeasyPrint | latest |
| Hosting | Vercel (FE) + Railway / Render (BE) | — |

Model IDs, prompt versions, and weight-table versions are pinned in `config/versions.yaml`.
Every analysis logs the exact versions used.

---

## 3. Data Source Hierarchy

All sources defined in `config/sources.yaml`. Fetching from unlisted domains raises
`UnapprovedSourceError`.

| Priority | Confidence | Sources |
|---|---|---|
| L1 (exchange direct) | 1.00 | NSE API (NseIndiaApi), BSE API (BseIndiaApi) |
| L2 (verified scraper) | 0.85 | Screener.in (recency-picked consolidated/standalone) |
| L3 (aggregator) | 0.70 | yfinance (.NS → .BO → alt ticker) |
| L4 (fallback) | 0.50 | Google News RSS |

Waterfall pattern: try L1 first, fall to L2 on failure, etc. Every result stamped with
`source_id` and `confidence`.

---

## 4. Folder Structure

```
stocxi/
├── CLAUDE.md                  <- this file, agent entrypoint
├── docs/architecture/ARCHITECTURE.md            <- system architecture, data sources, node schema, knowledge graph
├── AGENTS.md                  <- multi-agent orchestration contract
├── docs/architecture/SCALE.md                   <- performance, caching, rate limits, cost
├── docs/architecture/PLAN.md                    <- phased build plan with checklist
├── docs/progress/NEW_PROGRESS.md            <- append-only session log + current state
├── README.md                  <- public project overview
├── config/
│   ├── versions.yaml          <- pinned model / prompt / weight / schema versions
│   ├── sources.yaml           <- approved data source URLs + priority + rate limits
│   ├── weights.yaml           <- signal weight table (node type -> weight)
│   ├── profiles.yaml          <- user profile -> category-weight map
│   ├── bse_codes.yaml         <- NSE symbol -> BSE scrip code mapping
│   └── alt_tickers.yaml       <- yfinance alternative tickers (ZOMATO->ETERNAL etc.)
├── backend/
│   ├── main.py                <- FastAPI app entry
│   ├── config.py              <- config loader (reads all yaml files)
│   ├── routers/               <- FastAPI route handlers
│   ├── agents/                <- orchestrator + specialist agents (see AGENTS.md)
│   ├── fetchers/              <- one client per data source, returns raw payload
│   ├── services/              <- business logic layer (waterfall pipelines)
│   ├── schemas/               <- pydantic models (Node, messages, API responses)
│   ├── graph/                 <- knowledge graph builder, edges, scoring, storage
│   ├── analysis/              <- prompt assembly, LLM call, verifier, formatter
│   ├── cache/                 <- Redis client, keys, TTLs, invalidation
│   ├── audit/                 <- per-analysis immutable audit log
│   ├── util/                  <- sanitizer, holiday calendar, IST helpers
│   ├── backtest/              <- point-in-time replay, metrics
│   ├── calibration/           <- weight refit + confidence calibration
│   └── tests/
│       ├── golden/            <- golden-file regression tests
│       ├── unit/
│       ├── integration/
│       └── research/          <- live data exploration tests
├── frontend/                  <- Next.js Vercel app
└── (conda env: stocxi)        <- Python 3.12 conda environment (miniforge3)
```

Every new module lives under the correct directory. No ad-hoc top-level files.

---

## 5. Code Quality Rules

### Mandatory
- **Docstrings** on every public function: what it does, params, return, raises.
- **Functions <= 50 lines.** Split longer ones. Exception: pure data/schema definitions.
- **File header comment** (one paragraph) explaining the module's role.
- **No hardcoded values.** URLs, weights, TTLs, model IDs, prompts — all from `config/` or env.
- **No secrets in code.** `.env` only, never committed. `.env.example` lists required keys.
- **Type hints on every function signature.**
- **Schema is pydantic, not ad-hoc dicts.** Raw dicts crossing module boundaries are banned.
- **Every external call** (HTTP, DB, LLM) wrapped in retry-aware client with timeout.

### Naming
- Files: `snake_case.py`
- Functions / variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Test files: `test_<module>.py`
- Agent modules: `agent_<domain>.py`

### Determinism (non-negotiable)
- LLM calls: `temperature=0`, pinned model id, pinned prompt version, pinned seed.
- Same input nodes + same config = identical output. Violation = bug.

### Security
- All node `value` fields sanitized before entering any LLM prompt.
- Stock/sector names anonymized (`STOCK_A`, `SECTOR_X`) in reasoning prompt.
- Every analysis claim must cite a `node_id`. Verifier strips uncited claims.
- Never use raw news HTML in prompts. See `backend/util/sanitizer.py`.

---

## 6. Pre-Task Checklist (every session)

Before touching any file, the agent MUST:

1. Read `docs/progress/NEW_PROGRESS.md` — current state, last session, known issues.
2. Read `docs/architecture/ARCHITECTURE.md` if touching: data sources, node schema, analysis protocol, weights, knowledge graph.
3. Read `AGENTS.md` if adding or modifying any agent.
4. Read `docs/architecture/SCALE.md` if touching fetchers, caches, queues, or LLM calls.
5. Read `docs/architecture/PLAN.md` to understand current phase and what's next.
6. If unsure whether a rule applies, ASK — do not guess.

---

## 7. Post-Task Checklist

After finishing any task, the agent MUST:

1. Update `docs/progress/NEW_PROGRESS.md`:
   - Append a Session Log entry (date, what was built, files touched, next steps).
   - Add any new blockers to known issues.
2. If architecture changed: update `docs/architecture/ARCHITECTURE.md` + log in docs/progress/NEW_PROGRESS.md.
3. If agent changed: update `AGENTS.md`.
4. If cache/scale changed: update `docs/architecture/SCALE.md`.
5. Check off completed items in `docs/architecture/PLAN.md`.
6. Bump version in `config/versions.yaml` if prompt, weight table, or model id changed.

---

## 8. Absolute Rules — NEVER BREAK

| # | Rule | Why |
|---|---|---|
| 1 | Never fetch from a source not in `config/sources.yaml`. | Data integrity is the product. |
| 2 | Never skip a docstring on a public function. | Future agents need context. |
| 3 | Never put an API key, token, or password in code. | Security. Rotate immediately if leaked. |
| 4 | Never modify a working module without reading it in full first. | Avoids destructive edits. |
| 5 | Never assume — state assumptions explicitly, raise for review. | Prevents silent drift. |
| 6 | Never let the LLM see the real stock name in reasoning phase. | Kills training-knowledge leakage. |
| 7 | Never ship an analysis claim without a `node_id` citation. | Anti-hallucination contract. |
| 8 | Never use `temperature > 0` or unpinned model id in production. | Determinism / legal. |
| 9 | Never skip the audit log write. | Reproducibility + legal. |
| 10 | Never hand-pick weights after v1. Refit from backtest only. | Empirical discipline. |
| 11 | Never use raw news HTML in LLM prompts unsanitized. | Prompt injection defense. |
| 12 | Never write "BUY", "SELL", "RECOMMEND", or "ADVICE" in output. | SEBI compliance. |
| 13 | Never backtest with data published after the test date. | Future leakage. |
| 14 | Never reconcile source conflicts silently. Log winner + loser. | Audit trail. |
| 15 | Never deploy prompt changes without golden-file suite. | Regression guard. |

---

## 9. Key Architecture References

| Topic | Where to look |
|---|---|
| Data sources, methods, fields, priorities | docs/architecture/ARCHITECTURE.md Section 3 |
| Node schema + data formats | docs/architecture/ARCHITECTURE.md Section 4 |
| Knowledge graph edges + scoring | docs/architecture/ARCHITECTURE.md Section 5 |
| 10-step analysis protocol | docs/architecture/ARCHITECTURE.md Section 6 |
| Agent contracts + waterfall details | AGENTS.md Sections 2.1-2.5 |
| Pipeline execution flow | AGENTS.md Section 10 |
| Cache keys, TTLs, rate limits | docs/architecture/SCALE.md Sections 2-4 |
| Build phases + current progress | docs/architecture/PLAN.md + docs/progress/NEW_PROGRESS.md |

---

## 10. Code Search & Bug-Fix Protocol (MANDATORY)

**NEVER read an entire file to find a bug or locate code. Always grep first.**

1. **Grep to locate** — find exact file + line number.
   ```
   Grep pattern="function_or_symbol" path="backend/" type="py"
   ```
2. **Read only the slice** — fetch just the relevant function.
   ```
   Read file_path="backend/agents/foo.py" offset=42 limit=35
   ```
3. **Fix in place** — `Edit` with narrowest unique `old_string`.
4. **No full-file reads** — banned unless file is < 50 lines or no grep hit exists.

---

*Authoritative file. Edits require explicit user approval.*
