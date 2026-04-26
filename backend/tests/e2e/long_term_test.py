"""
long_term_test.py — End-to-end deep analysis for LONG-TERM investors.

Time Horizon: 1 Year to 3 Years
Stocks     : MPHASIS, ALKYLAMINE, KANSAINER, EIDPARRY

Run with:
  conda run -n stocxi python backend/tests/e2e/long_term_test.py

Output:
  backend/tests/e2e/results/long_term_analysis_<TIMESTAMP>.txt
"""

from analysis_runner import run_full_test

# ── Stock selection — Long Term (1 Year – 3 Years) ────────────────────────────
# Sectors: IT Midcap (Mphasis — DXC subsidiary),
#          Speciality Chemicals (Alkyl Amines Chemicals),
#          Decorative Paints (Kansai Nerolac),
#          Sugar & Distillery (EID Parry — Murugappa Group)
STOCKS        = ["MPHASIS", "ALKYLAMINE", "KANSAINER", "EIDPARRY"]
TIME_HORIZON  = "long_term"
HORIZON_LABEL = "Long Term (1 Year – 3 Years)"

if __name__ == "__main__":
    run_full_test(
        stocks=STOCKS,
        time_horizon=TIME_HORIZON,
        horizon_label=HORIZON_LABEL,
    )
