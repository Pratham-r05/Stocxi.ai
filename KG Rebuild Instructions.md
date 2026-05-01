# STOCXI — Knowledge Graph Rebuild Instructions for Claude
> ⚠️ READ THIS ENTIRE FILE BEFORE TAKING ANY ACTION. DO NOT SKIP SECTIONS.
> These instructions exist because a previous AI session (OpenCode + Claude) corrupted the knowledge graph by overwriting a nearly-correct file. This must not happen again.

---

## CONTEXT

- **Project path:** `~/Documents/Placement-Prep/10.Projects/stocxi`
- **Data fetch script:** `fetch_phase1_data.py`
- **Graph tool:** `graphify` (generates `.html` knowledge graph from `.md` files)
- **Data lives in:** `data/` folder as per-stock `.json` files (e.g. `RELIANCE_data.json`)
- **Graphify output folder:** `graphify-out/`

---

## ❌ WHAT WENT WRONG LAST TIME — DO NOT REPEAT

1. A previous session built an almost-correct knowledge graph using graphify
2. Another AI session (OpenCode) then made changes and **corrupted** the graph file
3. Claude picked up that corrupted file as the source of truth and **overwrote the correct graph** with the corrupted version
4. Claude also generated multiple leftover files (`build_kg.py`, `generate_graph.py`, `HANDOFF_KG_DEBUG.xml`, etc.) that created confusion

**Root cause:** Claude got confused by too many graph-related files in the root and used the wrong one.

---

## TASK 1 — CLEANUP (DO THIS FIRST, NOTHING ELSE)

### Step 1A: Delete these files from project root

Run the following commands one by one. Confirm each file exists before deleting.

```bash
cd ~/Documents/Placement-Prep/10.Projects/stocxi

# Old/corrupted graph files
rm -f knowledge_g.md
rm -f build_kg.py
rm -f generate_graph.py
rm -f HANDOFF_KG_DEBUG.xml
rm -f SESSION_SUMMARY_KG_REBUILD.md
rm -f NEW_PROGRESS.md
rm -f test_force_layout.py
rm -f test_kg_node.js
rm -f "Indian Stock Market API Response (1).json"
rm -f 00_kg_shorthand_book.md
rm -f vertex_credentials.json
```

> ⚠️ If unsure about any file — ASK the user before deleting. Never delete silently.

### Step 1B: Delete old graph weight/output folders

```bash
rm -rf graph_weights/
rm -rf graphify-out/
```

> `graphify-out/` will be regenerated fresh. Deleting it removes old corrupted outputs.

### Step 1C: DO NOT DELETE — PROTECTED FILES

```
fetch_phase1_data.py       ← data fetcher, NEVER touch
data/                      ← all stock JSON files, NEVER touch
CLAUDE.md                  ← project instructions
CLAUDE_DESIGN.md           ← design context
ARCHITECTURE.md            ← system architecture
PLAN.md                    ← project plan
README.md                  ← project readme
SCALE.md                   ← scaling notes
AGENTS.md                  ← agent definitions
backend/                   ← application backend
frontend/                  ← application frontend
config/                    ← configuration
docs/                      ← documentation
reports/                   ← reports folder
```

## important point to note
Do not need to read any entire file for reading anything first fetch what u need to read and use grep and ripgrep for searching 
do not waste token on unnecessary things
once everything thing done crete a new knowledgegraph__.md file and updata what u done

### Step 1D: Verify cleanup

```bash
ls -la ~/Documents/Placement-Prep/10.Projects/stocxi
```

Confirm only the protected files and folders remain. Show output to user before proceeding.

---

## TASK 2 — PLAN FOR KNOWLEDGE GRAPH BUILD

Before writing any code, present this plan to the user and get explicit approval.

### Graph Build Plan

```
# Step 1 — Fetch data + generate .md
conda run -n stocxi python fetch_phase1_data.py RELIANCE long
         ↓
  RELIANCE_knowledge.md  (saved in project root)
         ↓
# Step 2 — Build graph from .md
conda run -n stocxi python build_knowledge_graph.py RELIANCE long
         ↓
  graphify-out/RELIANCE/[DATE].html
```

### Script to create: `build_knowledge_graph.py`

This is the ONLY graph building script. It must:
# Step 1 — Fetch data + generate .md (only if not already fetched)
conda run -n stocxi python fetch_phase1_data.py RELIANCE long

# Step 2 — Build graph directly from the .md
graphify RELIANCE_knowledge.md

**Do NOT create any other graph-related scripts.**

---

## TASK 3 — DATA VALIDATION BEFORE BUILDING

Before building any graph, validate that the fetched data exists and is complete.

# Check .md file was created and is non-empty
ls -lh {STOCK}_knowledge.md

# Check it has actual content
wc -l {STOCK}_knowledge.md

# Preview first 30 lines to confirm structure
head -30 {STOCK}_knowledge.md

**make sure all data point exist in knowledge graph that is available in that stock .md file

---

## TASK 4 — NODE MAPPING (Data → Graph Nodes)

Every data point that EXISTS in the `.md` file must appear as a node in the knowledge graph. Do not skip available data.

### Mapping rules:

| Section in .md file | Node type in graph | Required? |
|---|---|---|
| `## Fundamental` | Fundamental node | Yes if present |
| `## Technical` | Technical node | Yes if present |
| `## News` | News node (one per article) | Yes if present |
| `## Announcements` | Announcement node | Yes if present |
| `## Financial` | Financial node | Yes if present |

**If a section is missing from `.md` → it is OK to skip that node.**
**If a section EXISTS in `.md` → it MUST have a corresponding node. No exceptions.**

---

## TASK 5 — NODE CONTENT REQUIREMENTS

Each node type must contain specific fields. Follow this exactly:

### Fundamental Nodes
```
- value: the raw metric value (e.g. P/E: 24.5)
- summary: 1-2 line interpretation
- sentiment: BULLISH / BEARISH / NEUTRAL
```

### Technical Nodes
```
- value: the raw indicator value (e.g. RSI: 62)
- summary: 1-2 line interpretation
- sentiment: BULLISH / BEARISH / NEUTRAL
```

### Announcement Nodes
```
- context_summary: gemini will fetch data from announancement and generate 2 line summary
- sentiment: BULLISH / BEARISH / NEUTRAL
```

### News Nodes
```
- summary: gemini will summarize the news article and most important 4-5 line summary will be stored
- sentiment: BULLISH / BEARISH / NEUTRAL
```

### Financial Nodes
```
- value: the raw financial figure
- performance_summary: comparison of recent value vs previous YoY data (e.g. "Revenue grew 18% YoY from ₹X to ₹Y") for every data point in that are availble in balance sheet, p&l, cash flow, quarterly result, annual result, shareholding
```

---

## TASK 6 — TERMINAL COMMAND TO BUILD GRAPH

The graph must be buildable from terminal with a single command:

```bash
# Fetch data (if not already fetched)
conda run -n stocxi python fetch_phase1_data.py RELIANCE long

# Build knowledge graph
conda run -n stocxi python build_knowledge_graph.py RELIANCE long
```

`build_knowledge_graph.py` must:
1. Read `data/RELIANCE_data.json`
2. Generate `data/RELIANCE_knowledge.md` with all nodes per Task 4 & 6
3. Run graphify on that `.md` file
4. Save output to `graphify-out/RELIANCE/`

The `.md` file is the intermediate artifact — graphify uses it to generate the final `.html` graph.

---

## GOLDEN RULES — CLAUDE MUST FOLLOW ALWAYS

1. **Never overwrite** `data/[STOCK]_knowledge.md` without showing the user a diff first
2. **Never create** multiple graph builder scripts — only `build_knowledge_graph.py` is allowed
3. **Never delete** anything in the `data/` folder
4. **Never assume** a file is corrupted — ask the user
5. **Always show** file contents before editing
6. **Always confirm** cleanup step output before moving to graph building
7. If confused about which file is the correct version — **STOP AND ASK**

---

## SESSION CHECKLIST

Before starting each session, Claude must confirm:

- [ ] Cleanup done? (`ls` output shown to user)
- [ ] Only `build_knowledge_graph.py` exists for graph building?
- [ ] Data validated for target stock?
- [ ] Node mapping reviewed against Task 4?
- [ ] Node content follows Task 6 format?
- [ ] Terminal command tested end-to-end?

---

*This file is the single source of truth for the KG rebuild. If any other file contradicts this — follow THIS file.*
