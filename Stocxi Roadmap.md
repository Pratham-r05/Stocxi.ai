# STOCXI — Development Roadmap
> Pratham's control. Step by step. No shortcuts.

---

## PHASE 1 — Data Fetching & Verification

**Goal:** For any given stock, trigger all data fetching functions, store everything in a single structured file, and visually verify correctness.

### What to build / fix:
- One master command / script that accepts a stock name/ticker as input
- Triggers every fetching function in sequence:
  - Fundamental data
  - Technical indicators
  - Announcements
  - News
  - Financial statements (Balance Sheet, P&L, Cash Flow, Quarterly, Annual, Shareholding)
- Stores all output in **one file per stock** (e.g., `RELIANCE_data.json` or `.md`)

### Expected output structure in the file:

| Section | What gets stored |
|---|---|
| **Fundamentals** | All key values + context summary + sentiment |
| **Technical Indicators** | All indicator values + context summary + sentiment |
| **Announcements** | Top 10 announcements + per-announcement summary + sentiment |
| **News** | Top 10 news items + per-news summary + sentiment |
| **Balance Sheet** | All values + YoY comparison for every field (up to 10 years if available) |
| **P&L** | All values + YoY comparison |
| **Cash Flow** | All values + YoY comparison |
| **Quarterly Results** | All values + QoQ and YoY comparison |
| **Annual Results** | All values + YoY comparison |
| **Shareholding Pattern** | All values + period-over-period comparison |

### Claude's role in Phase 1:
- Help execute the master fetch command
- Review the output file and flag any missing data, errors, or malformed sections
- Confirm every section is populated correctly before moving to Phase 2

### ✅ Phase 1 complete when:
- Any stock ticker entered → single file generated → all sections populated with values + summaries + comparisons

---

## PHASE 2 — Knowledge Graph (Fresh Build with Graphify)

**Goal:** Scrap the old knowledge graph. Build a new one from scratch using **Graphify**, driven entirely by the Phase 1 data file.

### What to build:
- Parse the Phase 1 output file for the stock
- Build a knowledge graph using Graphify where:
  - Each major data section = a node (Fundamentals, Technicals, Announcements, etc.)
  - Sub-fields and metrics = child nodes
  - Relationships between nodes are derived from the data (e.g., Revenue → Net Profit → EPS)
- **Node hover behavior:** When hovering over any stock node, show the actual data values inside the node tooltip/panel — not just labels

### Claude's role in Phase 2:
- Write the Graphify integration code from scratch
- Map Phase 1 data schema → graph node/edge structure
- Implement the hover-to-show-data feature
- Test graph rendering with at least one stock's data file

### ✅ Phase 2 complete when:
- Knowledge graph renders from Phase 1 file
- Hovering a node shows real data values
- Graph reflects actual stock data structure, not hardcoded placeholders

---

## PHASE 3 — Gemini Analysis Instruction File

**Goal:** Create a structured instruction file that tells Gemini exactly how to read and process the Phase 1 data file, based on the user's investment horizon.

### What to build:
- A `.txt` or `.md` instruction file passed to Gemini along with the Phase 1 data file
- Instructions cover:
  - How to read each section (Fundamentals, Technicals, Financials, etc.)
  - What signals to prioritize for each horizon
  - How to weigh sentiment, comparisons, and technical indicators together
  - How to handle missing or incomplete data sections

### Horizon-specific processing:
| Horizon | Key focus areas for Gemini |
|---|---|
| **Short Term** | Technicals, recent news, announcements, momentum indicators |
| **Medium Term** | Mix of technicals + fundamentals, quarterly trends, sector news |
| **Long Term** | Fundamentals, financial statement trends, shareholding patterns, valuation |

> ⚠️ **Pratham will provide the exact instruction file format later.** Claude will help draft and refine the instruction file once that format is shared.

### Claude's role in Phase 3:
- Help structure the instruction file once format is decided
- Ensure Gemini receives Phase 1 data + instruction file together in the correct invocation
- Validate that Gemini's response reflects the horizon correctly

### ✅ Phase 3 complete when:
- Gemini instruction file is finalized
- Gemini correctly reads Phase 1 data and produces horizon-aware analysis

---

## PHASE 4 — Output Generation

**Goal:** Generate a clean, structured, horizon-specific analysis output for the user.

### What to build:
- A separate output instruction file for Gemini (per horizon)
- Gemini uses Phase 3 analysis + output instruction to generate final report
- Output format differs by horizon:
  - **Short Term** — entry/exit signals, momentum, risk
  - **Medium Term** — trend analysis, earnings trajectory, sector positioning
  - **Long Term** — intrinsic value, financial health, growth story

> ⚠️ **Pratham will define the exact output instruction file format later.** Claude will help build and refine it once shared.

### Claude's role in Phase 4:
- Help draft output instruction files once format is decided
- Ensure output is clean, structured, and usable
- Validate output quality against Phase 1 data (no hallucinations, grounded in data)

### ✅ Phase 4 complete when:
- Any stock + any horizon → full analysis output generated
- Output is grounded in Phase 1 data, processed by Phase 3 Gemini instructions

---

## Current Status

| Phase | Status |
|---|---|
| Phase 1 — Data Fetch & Store | ✅ Complete — `fetch_phase1_data.py RELIANCE` → `data/RELIANCE_data.md` (77 nodes, all 10 sections populated) |
| Phase 2 — Knowledge Graph (Graphify) | 🔴 To be rebuilt from scratch |
| Phase 3 — Gemini Instruction File | ⏳ Waiting for Pratham's format |
| Phase 4 — Output Generation | ⏳ Waiting for Pratham's format |

---

## Immediate Next Step

**Execute Phase 1:**
1. Share the current fetch codebase / entry point
2. Run master fetch for one stock (e.g., RELIANCE or any test ticker)
3. Review the output file together
4. Fix any broken sections
5. Confirm Phase 1 is solid → move to Phase 2
