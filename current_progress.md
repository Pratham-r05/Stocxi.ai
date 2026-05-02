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