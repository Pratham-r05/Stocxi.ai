"""
medium_term_test.py — End-to-end deep analysis for MEDIUM-TERM investors.

Time Horizon: 3 Months to 1 Year
Stocks     : MOTHERSON, PAGEIND, PIIND

Run with:
  conda run -n stocxi python backend/tests/e2e/medium_term_test.py

Output:
  backend/tests/e2e/results/medium_term_analysis_<TIMESTAMP>.txt
"""

from analysis_runner import run_full_test

# ── Stock selection — Medium Term (3 Months – 1 Year) ────────────────────────
# Sectors: Auto Ancillary (Motherson Sumi/Samvardhana),
#          Consumer Discretionary (Page Industries — Jockey licensee),
#          Agro/Speciality Chemicals (P.I. Industries)
STOCKS        = ["MOTHERSON", "PAGEIND", "PIIND"]
TIME_HORIZON  = "medium_term"
HORIZON_LABEL = "Medium Term (3 Months – 1 Year)"

if __name__ == "__main__":
    run_full_test(
        stocks=STOCKS,
        time_horizon=TIME_HORIZON,
        horizon_label=HORIZON_LABEL,
    )
