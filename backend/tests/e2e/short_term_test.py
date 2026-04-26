"""
short_term_test.py — End-to-end deep analysis for SHORT-TERM investors.

Time Horizon: 1 Day to 3 Months
Stocks     : BAJAJFINSV, NESTLEIND, TATACHEM

Run with:
  conda run -n stocxi python backend/tests/e2e/short_term_test.py

Output:
  backend/tests/e2e/results/short_term_analysis_<TIMESTAMP>.txt
"""

from analysis_runner import run_full_test

# ── Stock selection — Short Term (1 Day – 3 Months) ──────────────────────────
# Sectors: NBFC (Bajaj Finserv), FMCG/Packaged Foods (Nestle India),
#          Speciality Chemicals (Tata Chemicals)
STOCKS        = ["BAJAJFINSV", "NESTLEIND", "TATACHEM"]
TIME_HORIZON  = "short_term"
HORIZON_LABEL = "Short Term (1 Day – 3 Months)"

if __name__ == "__main__":
    run_full_test(
        stocks=STOCKS,
        time_horizon=TIME_HORIZON,
        horizon_label=HORIZON_LABEL,
    )
