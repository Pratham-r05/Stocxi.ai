"""
universe.py — NSE stock universe for backtesting.

100 NSE symbols drawn from Nifty 100 + Nifty Midcap, diversified across 11 sectors.
This universe is SURVIVORSHIP-BIASED: delisted stocks are not included because
a point-in-time delisting archive is unavailable. Any backtest results derived
from this universe MUST display SURVIVORSHIP_BIAS_DISCLAIMER.
"""

from __future__ import annotations

SURVIVORSHIP_BIAS_DISCLAIMER = (
    "Backtest results are derived from currently listed stocks only (survivorship bias). "
    "Stocks that were delisted or went bankrupt during the test period are excluded, "
    "which may overstate historical returns. These results are indicative only."
)

# fmt: off
UNIVERSE: list[str] = [
    # Banking & Finance (15)
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
    "BAJFINANCE", "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "ICICIGI",
    "SHRIRAMFIN", "CHOLAFIN", "MUTHOOTFIN", "PNBHOUSING", "CANFINHOME",

    # IT & Technology (12)
    "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM",
    "LTIM", "MPHASIS", "COFORGE", "PERSISTENT", "OFSS",
    "KPITTECH", "TATAELXSI",

    # Pharma & Healthcare (10)
    "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA",
    "LUPIN", "ALKEM", "TORNTPHARM", "IPCALAB", "GLENMARK",

    # FMCG (10)
    "ITC", "HINDUNILVR", "NESTLEIND", "BRITANNIA", "MARICO",
    "DABUR", "GODREJCP", "EMAMILTD", "COLPAL", "TATACONSUM",

    # Energy & Oil (8)
    "RELIANCE", "ONGC", "BPCL", "IOC", "HINDPETRO",
    "GAIL", "IGL", "PETRONET",

    # Automobiles (10)
    "MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO",
    "EICHERMOT", "TVSMOTOR", "ASHOKLEY", "TIINDIA", "BALKRISIND",

    # Infrastructure & Capital Goods (8)
    "LT", "NTPC", "POWERGRID", "BHEL", "ABB",
    "SIEMENS", "CUMMINSIND", "THERMAX",

    # Metals & Mining (8)
    "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "NATIONALUM",
    "SAIL", "NMDC", "COALINDIA",

    # Consumer Durables & Paints (8)
    "TITAN", "ASIANPAINT", "BERGER", "PIDILITE", "HAVELLS",
    "VOLTAS", "WHIRLPOOL", "CROMPTON",

    # Telecom & Media (4)
    "BHARTIARTL", "IDEA", "TATACOMM", "HFCL",

    # Diversified / Conglomerate (7)
    "ADANIENT", "ADANIPORTS", "ADANIGREEN", "TATAPOWER",
    "VEDANTALimited", "APLAPOLLO", "DLF",
]
# fmt: on


def get_universe() -> list[str]:
    """Return the full backtest stock universe."""
    return list(UNIVERSE)


def get_universe_by_sector() -> dict[str, list[str]]:
    """Return universe grouped by sector (used for sector-level metrics)."""
    return {
        "Banking & Finance": UNIVERSE[0:15],
        "IT & Technology":   UNIVERSE[15:27],
        "Pharma":            UNIVERSE[27:37],
        "FMCG":              UNIVERSE[37:47],
        "Energy & Oil":      UNIVERSE[47:55],
        "Automobiles":       UNIVERSE[55:65],
        "Infrastructure":    UNIVERSE[65:73],
        "Metals & Mining":   UNIVERSE[73:81],
        "Consumer Durables": UNIVERSE[81:89],
        "Telecom":           UNIVERSE[89:93],
        "Diversified":       UNIVERSE[93:100],
    }
