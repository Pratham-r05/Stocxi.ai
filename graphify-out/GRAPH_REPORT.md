# Graph Report - data  (2026-05-01)

## Corpus Check
- 1 files · ~5,223 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 123 nodes · 197 edges · 8 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Valuation & Profitability|Valuation & Profitability]]
- [[_COMMUNITY_Market & Technical Signals|Market & Technical Signals]]
- [[_COMMUNITY_Balance Sheet Assets|Balance Sheet Assets]]
- [[_COMMUNITY_Quarterly Performance|Quarterly Performance]]
- [[_COMMUNITY_Profit & Loss|Profit & Loss]]
- [[_COMMUNITY_Board Announcements|Board Announcements]]
- [[_COMMUNITY_Shareholding Structure|Shareholding Structure]]
- [[_COMMUNITY_Cash Flow|Cash Flow]]

## God Nodes (most connected - your core abstractions)
1. `Fundamentals` - 39 edges
2. `Technical Indicators` - 20 edges
3. `Profit and Loss` - 15 edges
4. `Balance Sheet` - 13 edges
5. `RPOWER` - 12 edges
6. `Quarterly Results` - 12 edges
7. `Announcements` - 12 edges
8. `Net Profit Annual` - 10 edges
9. `EPS` - 9 edges
10. `Debt to Equity` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Fundamentals` --conceptually_related_to--> `Technical Indicators`  [INFERRED]
  data/RPOWER_data.md → data/RPOWER_data.md  _Bridges community 0 → community 1_
- `Balance Sheet` --references--> `ROE`  [INFERRED]
  data/RPOWER_data.md → data/RPOWER_data.md  _Bridges community 2 → community 0_
- `Profit and Loss` --references--> `EPS`  [INFERRED]
  data/RPOWER_data.md → data/RPOWER_data.md  _Bridges community 4 → community 0_
- `Cash Flow` --conceptually_related_to--> `Net Profit Annual`  [INFERRED]
  data/RPOWER_data.md → data/RPOWER_data.md  _Bridges community 7 → community 0_
- `Shareholding Pattern` --conceptually_related_to--> `OBV`  [INFERRED]
  data/RPOWER_data.md → data/RPOWER_data.md  _Bridges community 6 → community 1_

## Communities

### Community 0 - "Valuation & Profitability"
Cohesion: 0.14
Nodes (26): Reserves (Balance Sheet), Fundamentals, EBITDA Margin, EBITDA TTM, EPS, EPS Annual, Expenses Annual, Expenses Quarterly (+18 more)

### Community 1 - "Market & Technical Signals"
Cohesion: 0.1
Nodes (25): Market Context, News, Technical Indicators, Market Regime, Long-Term Horizon, News: Stock Drop on Volume Surge, RPOWER, Diversified Sector (+17 more)

### Community 2 - "Balance Sheet Assets"
Cohesion: 0.18
Nodes (18): Borrowings (Balance Sheet), CWIP, Equity Capital, Fixed Assets, Investments, Other Assets, Other Liabilities, Total Assets (Balance Sheet) (+10 more)

### Community 3 - "Quarterly Performance"
Cohesion: 0.14
Nodes (14): Quarterly Results, Net Profit Quarterly, Revenue Quarterly, Quarterly Depreciation, Quarterly EPS, Quarterly Expenses, Quarterly Interest, Quarterly Net Profit (+6 more)

### Community 4 - "Profit & Loss"
Cohesion: 0.18
Nodes (11): Profit and Loss, Depreciation, Dividend Payout %, Expenses (P&L), Interest (P&L), Operating Profit (P&L), OPM % (P&L), Other Income (+3 more)

### Community 5 - "Board Announcements"
Cohesion: 0.18
Nodes (11): Announcement: Board Meeting Fund Raising July, Announcement: Board Meeting FY25 Results, Announcement: Board Meeting Q1 Results, Announcement: Board Meeting Q2 + Fund Raising, Announcement: Board Meeting Q3 Results, Announcement: FY25 Financial Results, Announcement: Q1 Financial Results, Announcement: Q3 Financial Results (+3 more)

### Community 6 - "Shareholding Structure"
Cohesion: 0.22
Nodes (9): Shareholding Pattern, Promoter Holding, Public Retail Holding, DIIs Holding, FIIs Holding, Government Holding, No. of Shareholders, Promoters Holding (+1 more)

### Community 7 - "Cash Flow"
Cohesion: 0.22
Nodes (9): Cash From Financing Activity, Cash From Investing Activity, Cash From Operating Activity, CFO/OP Ratio, Free Cash Flow (Cash Flow), Net Cash Flow, Cash Flow, Cash From Financing (+1 more)

## Knowledge Gaps
- **58 isolated node(s):** `Diversified Sector`, `Long-Term Horizon`, `Revenue TTM`, `PAT Growth YoY`, `Expenses Quarterly` (+53 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RPOWER` connect `Market & Technical Signals` to `Valuation & Profitability`, `Balance Sheet Assets`, `Quarterly Performance`, `Profit & Loss`, `Board Announcements`, `Shareholding Structure`, `Cash Flow`?**
  _High betweenness centrality (0.483) - this node is a cross-community bridge._
- **Why does `Fundamentals` connect `Valuation & Profitability` to `Market & Technical Signals`, `Balance Sheet Assets`, `Quarterly Performance`, `Shareholding Structure`, `Cash Flow`?**
  _High betweenness centrality (0.453) - this node is a cross-community bridge._
- **Why does `Technical Indicators` connect `Market & Technical Signals` to `Valuation & Profitability`?**
  _High betweenness centrality (0.249) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Fundamentals` (e.g. with `Technical Indicators` and `Market Context`) actually correct?**
  _`Fundamentals` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Technical Indicators` (e.g. with `Fundamentals` and `Market Context`) actually correct?**
  _`Technical Indicators` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Profit and Loss` (e.g. with `EPS` and `PAT TTM`) actually correct?**
  _`Profit and Loss` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Balance Sheet` (e.g. with `Debt to Equity` and `ROE`) actually correct?**
  _`Balance Sheet` has 2 INFERRED edges - model-reasoned connections that need verification._