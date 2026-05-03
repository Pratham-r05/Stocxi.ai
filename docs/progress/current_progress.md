What was fixed:
  What was fixed:

  ┌───────────────────────────┬────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┬────────────────────────────┐

  ┌───────────────────────────┬────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┬────────────────────────────┐
  │            Bug            │                           Root Cause                           │                           Fix                           │            File            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ D/E 20× wrong (32.08 →    │ _extract_series("equity") matched "Equity Capital" (₹13 Cr     │ Compute Net Worth = share_capital + reserves separately │ financials_service.py      │
  │ 1.54)                     │ share capital) instead of Net Worth (₹271 Cr)                  │                                                         │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ PE/EPS wrong (16.87/3.37  │ BSE consolidated used when only ConPE present, ConROE and      │ Require ≥2 of {ConPE, ConROE, ConPB} to be non-null     │ bse_client.py              │
  │ → 26.83/2.12)             │ ConPB both null — incomplete consolidated data                 │ before using consolidated                               │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ Sector "diversified" for  │ Hardcoded _SECTOR_MAP defaulted to "diversified" for any stock │ Live fetch from NSE/BSE equityMetaInfo — NSE gives      │ fetch_phase1_data.py       │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ Sector "diversified" for  │ Hardcoded _SECTOR_MAP defaulted to "diversified" for any stock │ Live fetch from NSE/BSE equityMetaInfo — NSE gives      │ fetch_phase1_data.py       │
  │ unknown stocks            │  not in the 25-stock map                                       │ "Seafood", BSE gives "Fast Moving Consumer Goods"       │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ Market cap from wrong     │ fetch_trading_stats searched MarketCap key — BSE actually      │ Added MktCapFull as primary key, also inject BSE market │ bse_client.py,             │
  │ field                     │ returns MktCapFull                                             │  cap into ratios pipeline                               │ ratios_service.py          │
  └───────────────────────────┴────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────┴────────────────────────────┘

  Also added nse_client.fetch_meta_info() as a new function for industry/sector lookup from NSE directly.

✻ Baked for 11m 52s
          print(f'D/E ratio: {de_ratio}  (verified real value: ~1.53)')

      asyncio.run(test_de())
      " 2>&1)
  ⎿  Borrowings: 417.0 Cr
     Share Capital: 13.0 Cr
     Reserves: 258.0 Cr
     Net Worth (equity): 271.0 Cr
     D/E ratio: 1.54  (verified real value: ~1.53)

⏺ All 4 fixes are confirmed working. Here's the summary:

  ---
  What was fixed:

  ┌───────────────────────────┬────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┬────────────────────────────┐
  │            Bug            │                           Root Cause                           │                           Fix                           │            File            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ D/E 20× wrong (32.08 →    │ _extract_series("equity") matched "Equity Capital" (₹13 Cr     │ Compute Net Worth = share_capital + reserves separately │ financials_service.py      │
  │ 1.54)                     │ share capital) instead of Net Worth (₹271 Cr)                  │                                                         │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ PE/EPS wrong (16.87/3.37  │ BSE consolidated used when only ConPE present, ConROE and      │ Require ≥2 of {ConPE, ConROE, ConPB} to be non-null     │ bse_client.py              │
  │ → 26.83/2.12)             │ ConPB both null — incomplete consolidated data                 │ before using consolidated                               │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ Sector "diversified" for  │ Hardcoded _SECTOR_MAP defaulted to "diversified" for any stock │ Live fetch from NSE/BSE equityMetaInfo — NSE gives      │ fetch_phase1_data.py       │
  │ unknown stocks            │  not in the 25-stock map                                       │ "Seafood", BSE gives "Fast Moving Consumer Goods"       │                            │
  ├───────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────┤
  │ Market cap from wrong     │ fetch_trading_stats searched MarketCap key — BSE actually      │ Added MktCapFull as primary key, also inject BSE market │ bse_client.py,             │
  │ field                     │ returns MktCapFull                                             │  cap into ratios pipeline                               │ ratios_service.py          │
  └───────────────────────────┴────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────┴────────────────────────────┘

  Also added nse_client.fetch_meta_info() as a new function for industry/sector lookup from NSE directly.

✻ Baked for 11m 52s

※ recap: Fixed 4 data accuracy bugs in the fundamentals pipeline — wrong D/E ratio, PE/EPS, sector classification, and market cap all now sourced from live NSE/BSE APIs. Next: re-run
  fetch_phase1_data.py on COASTCORP to verify the corrected data end-to-end. (disable recaps in /config)





  Bug fixes applied:                            
                                                                                                                                               
  1. HBLENGINE ROE — Corrected 40.1% → 20.09% in data/HBLENGINE_data.md                                                                      
  2. News labels outside nodes — News/announcement node labels now truncated to 25 chars ("News 1: Reliance Industri…") in render_html(). Full 
  headline is stored in full_label and shown in the side panel + search.                                                                       
  3. Tooltip HTML as raw text — Replaced HTML-tagged tooltip with plain text joined by \n. Newer vis-network treats title strings as text (XSS 
  protection), so <b> was showing literally. Now shows clean plain-text on hover.                                                              
  4. Cross-category edges — relates_to edges now rendered in purple (#a855f7, opacity 0.55, width 2) vs structural belongs_to in blue          
  (#3b82f6). Physics tweaked: centralGravity 0.005→0.02, springConstant 0.08→0.12, springLength 120→100 — clusters will pull toward each other 
  now.                                                                                                                                         
  5. Zoom label visibility — Added nodes.scaling.label with drawThreshold: 3 so labels stay visible at more zoom levels instead of disappearing
   early.                                                                                                                                      
  6. Side panel — Now shows: signal badge pill (Bullish/Bearish/Neutral/Mixed), node type, full news headline, value, analysis context, metric
  row (connections/structural/semantic counts), edge type breakdown with colored dots, and neighbor list with edge type indicators (blue dot = 
  structural, purple = semantic).   