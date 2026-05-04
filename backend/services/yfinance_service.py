"""
yfinance_service.py — Price + fundamental data for Indian stocks.

Why we stopped using yfinance for quotes:
  Yahoo Finance IP-blocks the crumb endpoint (/v1/test/getcrumb) during
  heavy testing. All quoteSummary calls fail with 429 even with retries.

New stack:
  Primary  → nsepython.nse_eq(symbol)
             Hits NSE India's public API directly — no Yahoo, no rate limits.
             Works for all NSE-listed stocks (most Indian large/mid caps).

  Fallback → Direct httpx GET to Yahoo Finance chart API
             /v8/finance/chart/{symbol}.BO — chart endpoint does NOT need crumb.
             Used only for BSE-only stocks not listed on NSE.

  yfinance → Still kept in requirements for technicals_service.py which
             downloads historical OHLCV via yf.download() (different endpoint).
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── NSE primary: nsepython ─────────────────────────────────────────────────────
def _safe_int(v) -> int | None:
    """Parse volume/count from NSE — may arrive as int, float, or comma-formatted string."""
    if v is None:
        return None
    try:
        return int(str(v).replace(",", "").split(".")[0])
    except Exception:
        return None


def _fetch_from_nse(symbol: str) -> dict:
    """
    Sync — run in thread pool.
    nsepython.nse_eq() calls NSE India's public quote API directly.
    Returns structured data or raises on failure.
    """
    # Import here so startup doesn't fail if package has issues
    from nsepython import nse_eq  # type: ignore

    symbol = symbol.upper().strip()
    raw = nse_eq(symbol)  # raises if symbol not found on NSE

    price_info  = raw.get("priceInfo", {})
    metadata    = raw.get("metadata", {})
    info        = raw.get("info", {})          # NSE also puts companyName here
    trade_info  = raw.get("tradeInfo", {})
    pre_open    = raw.get("preOpenMarket", {})
    sec_info    = raw.get("securityInfo", {})
    intraday    = price_info.get("intraDayHighLow", {})
    week_hl     = price_info.get("weekHighLow", {})

    price = price_info.get("lastPrice") or price_info.get("close")
    if not price or float(price) <= 0:
        raise ValueError(f"NSE returned no price for {symbol}")

    previous_close = price_info.get("previousClose") or price
    change         = price_info.get("change", round(float(price) - float(previous_close), 2))
    change_pct     = price_info.get("pChange", 0.0)

    # Market cap from tradeInfo (in crores) → convert to absolute value
    market_cap_cr = trade_info.get("totalMarketCap")
    market_cap = int(market_cap_cr * 1e7) if market_cap_cr else None  # crores → rupees

    # Company name: metadata.companyName exists but can return ticker for some stocks.
    # Try info.companyName as a second source before falling back to symbol.
    company_name = (
        metadata.get("companyName") or
        info.get("companyName") or
        symbol
    )

    return {
        "exchange":        "NSE",
        "company_name":    company_name,
        "industry":        metadata.get("industry"),
        "sector":          None,  # NSE API doesn't give sector; screener.in does
        "price":           round(float(price), 2),
        "previous_close":  round(float(previous_close), 2),
        "change":          round(float(change), 2),
        "change_percent":  round(float(change_pct), 2),
        "open":            price_info.get("open"),
        "day_high":        intraday.get("max"),
        "day_low":         intraday.get("min"),
        "week_52_high":    week_hl.get("max"),
        "week_52_low":     week_hl.get("min"),
        "volume":          _safe_int(
                               trade_info.get("totalTradedVolume") or
                               trade_info.get("totalTradedQty") or
                               pre_open.get("totalTradedVolume")
                           ),
        "market_cap":      market_cap,
        # fundamentals NSE doesn't expose via this endpoint:
        "pe_ratio":        None,
        "pb_ratio":        None,
        "eps":             None,
        "dividend_yield":  None,
        "beta":            None,
        "description":     None,
        "website":         None,
        "employees":       None,
    }


# ── BSE fallback: Yahoo chart API (no crumb needed) ───────────────────────────
async def _fetch_from_yahoo_chart(symbol: str) -> dict:
    """
    Async httpx call to Yahoo Finance chart endpoint.
    /v8/finance/chart/ does NOT require a crumb — different auth flow.
    Used as fallback for BSE-only stocks.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.yahoo.com",
        "Accept": "application/json",
    }

    for suffix, exchange in [(".NS", "NSE"), (".BO", "BSE")]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            result = (data.get("chart") or {}).get("result") or []
            if not result:
                continue

            meta  = result[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            if not price or float(price) <= 0:
                continue

            prev  = meta.get("previousClose") or price
            logger.info(f"Yahoo chart API: got price for {symbol} on {exchange}")
            return {
                "exchange":        exchange,
                "company_name":    meta.get("shortName") or symbol,
                "industry":        None,
                "sector":          None,
                "price":           round(float(price), 2),
                "previous_close":  round(float(prev), 2),
                "change":          round(float(price) - float(prev), 2),
                "change_percent":  round(((float(price) - float(prev)) / float(prev)) * 100, 2),
                "open":            meta.get("regularMarketOpen"),
                "day_high":        meta.get("regularMarketDayHigh"),
                "day_low":         meta.get("regularMarketDayLow"),
                "week_52_high":    meta.get("fiftyTwoWeekHigh"),
                "week_52_low":     meta.get("fiftyTwoWeekLow"),
                "volume":          meta.get("regularMarketVolume"),
                "market_cap":      meta.get("marketCap"),
                "pe_ratio":        None,
                "pb_ratio":        None,
                "eps":             None,
                "dividend_yield":  None,
                "beta":            None,
                "description":     None,
                "website":         None,
                "employees":       None,
            }
        except Exception as e:
            logger.warning(f"Yahoo chart fallback failed for {symbol}{suffix}: {e}")
            continue

    raise ValueError(f"Symbol '{symbol}' not found on NSE or BSE")


def _fetch_nse_intraday_1d(symbol: str) -> list[dict]:
    """
    Fetch today's intraday chart data from NSE's own chart API via nsepython session.
    Returns [{date: 'YYYY-MM-DD HH:MM', close, volume?}] in IST.
    NSE returns [[timestamp_ms, price, volume?], ...] in grapthData key.
    """
    from nsepython import nsefetch  # type: ignore
    from datetime import timezone, timedelta

    IST = timezone(timedelta(hours=5, minutes=30))
    url = f"https://www.nseindia.com/api/chart-databyindex?index={symbol}&indices=false"
    try:
        data = nsefetch(url)
        graph_data = data.get("grapthData") or []
        if not graph_data:
            return []
        result = []
        for point in graph_data:
            if len(point) < 2:
                continue
            ts_ms, price = point[0], point[1]
            if price is None:
                continue
            dt = datetime.fromtimestamp(float(ts_ms) / 1000, tz=IST)
            entry = {
                "date":  dt.strftime("%Y-%m-%d %H:%M"),
                "close": round(float(price), 2),
            }
            if len(point) >= 3 and point[2] is not None:
                try:
                    vol = int(float(point[2]))
                    if vol > 0:
                        entry["volume"] = vol
                except Exception:
                    pass
            result.append(entry)
        logger.info(f"NSE intraday 1D: {len(result)} points for {symbol}")
        return result
    except Exception as e:
        logger.warning(f"NSE intraday 1D failed for {symbol}: {e}")
        return []


def _fetch_nse_historical_week(symbol: str) -> list[dict]:
    """
    Fetch last 7 calendar days of daily OHLCV from NSE historical API.
    Returns [{date: 'YYYY-MM-DD', close, volume}].
    NSE historical endpoint: /api/historical/cm/equity?symbol=X&series[]=EQ&from=DD-MM-YYYY&to=DD-MM-YYYY
    """
    from nsepython import nsefetch  # type: ignore
    from datetime import date, timedelta

    end   = date.today()
    start = end - timedelta(days=14)  # buffer for weekends/holidays
    url = (
        f"https://www.nseindia.com/api/historical/cm/equity"
        f"?symbol={symbol}&series[]=EQ"
        f"&from={start.strftime('%d-%m-%Y')}&to={end.strftime('%d-%m-%Y')}"
    )
    try:
        data = nsefetch(url)
        rows = data.get("data") or []
        if not rows:
            return []
        result = []
        for row in rows:
            date_str = (row.get("CH_TIMESTAMP") or row.get("mTIMESTAMP") or "")[:10]
            close    = row.get("CH_CLOSING_PRICE") or row.get("CH_LAST_TRADED_PRICE")
            volume   = row.get("CH_TOT_TRADED_QTY")
            if not date_str or close is None:
                continue
            entry: dict = {"date": date_str, "close": round(float(close), 2)}
            if volume:
                try:
                    entry["volume"] = int(float(volume))
                except Exception:
                    pass
            result.append(entry)
        result.sort(key=lambda x: x["date"])
        # Last 7 trading days
        result = result[-7:]
        logger.info(f"NSE historical 1W: {len(result)} points for {symbol}")
        return result
    except Exception as e:
        logger.warning(f"NSE historical 1W failed for {symbol}: {e}")
        return []


async def get_history(symbol: str, period: str = "1y") -> dict:
    """
    Async entry point — returns OHLCV history for charting.
    Supports intraday (1d/1w) and daily periods.
    Returns {date, close, volume} per point. Never raises.
    """
    import yfinance as yf
    import pandas as pd
    from datetime import date, datetime, timedelta, timezone

    symbol = symbol.upper().strip()
    valid_periods = {"1d", "1w", "1mo", "3mo", "6mo", "1y", "2y", "5y"}
    if period not in valid_periods:
        period = "1y"

    # Map period → (source range, source interval)
    _yf_map = {
        "1d":  ("1d",  "1m"),
        "1w":  ("5d",  "60m"),
        "1mo": ("1mo", "60m"),
        "3mo": ("3mo", "1d"),
        "6mo": ("6mo", "1d"),
        "1y":  ("1y",  "1d"),
        "2y":  ("2y",  "1d"),
        "5y":  ("5y",  "1d"),
    }
    yf_period, yf_interval = _yf_map[period]
    is_intraday = period in {"1d", "1w", "1mo"}

    def _bucket_minutes_for_period() -> int:
        """Return output bucket size in minutes for each chart period."""
        if period == "1d":
            return 1
        if period == "1w":
            return 60
        if period == "1mo":
            return 720
        return 0

    def _aggregate_intraday_points(points: list[dict]) -> list[dict]:
        """Aggregate intraday points by configured bucket size and sum traded volume."""
        bucket_minutes = _bucket_minutes_for_period()
        if bucket_minutes <= 1 or not points:
            return points

        intraday_points = [p for p in points if len(str(p.get("date", ""))) > 10]
        if not intraday_points:
            return points

        buckets: dict[str, dict] = {}

        for p in intraday_points:
            date_str = str(p.get("date", ""))
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            except Exception:
                continue

            total_minutes = dt.hour * 60 + dt.minute
            bucket_start_minutes = (total_minutes // bucket_minutes) * bucket_minutes
            bucket_hour = bucket_start_minutes // 60
            bucket_minute = bucket_start_minutes % 60
            bucket_dt = dt.replace(hour=bucket_hour, minute=bucket_minute, second=0, microsecond=0)
            bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M")

            close_val = p.get("close")
            if close_val is None:
                continue

            entry = buckets.get(bucket_key)
            if entry is None:
                entry = {"date": bucket_key, "close": round(float(close_val), 2)}
                buckets[bucket_key] = entry
            else:
                entry["close"] = round(float(close_val), 2)

            volume_val = p.get("volume")
            if volume_val is not None:
                try:
                    vol_int = int(float(volume_val))
                    if vol_int > 0:
                        entry["volume"] = int(entry.get("volume", 0)) + vol_int
                except Exception:
                    pass

        if not buckets:
            return points

        return sorted(buckets.values(), key=lambda x: x["date"])

    def _extract_ohlcv(df: pd.DataFrame) -> list[dict]:
        """Normalize dataframe and extract [{date, close, volume?}] safely."""
        try:
            if df is None or df.empty:
                return []

            if isinstance(df.columns, pd.MultiIndex):
                df = df.copy()
                df.columns = df.columns.get_level_values(0)

            close_col = None
            for candidate in ["Close", "Adj Close", "close", "CLOSE"]:
                if candidate in df.columns:
                    close_col = candidate
                    break
            if close_col is None:
                for c in df.columns:
                    if str(c).strip().lower() in {"close", "adj close"}:
                        close_col = c
                        break
            if close_col is None:
                return []

            vol_col = None
            for candidate in ["Volume", "volume", "VOLUME"]:
                if candidate in df.columns:
                    vol_col = candidate
                    break

            close_series = df[close_col].squeeze()
            if isinstance(close_series, pd.DataFrame):
                close_series = close_series.iloc[:, 0]

            result = []
            for dt, val in close_series.items():
                if pd.notna(val):
                    if is_intraday and hasattr(dt, "strftime"):
                        dt_str = dt.strftime("%Y-%m-%d %H:%M")
                    elif hasattr(dt, "strftime"):
                        dt_str = dt.strftime("%Y-%m-%d")
                    else:
                        dt_str = str(dt)[:16]

                    entry: dict = {"date": dt_str, "close": round(float(val), 2)}

                    if vol_col is not None:
                        try:
                            vol_val = df[vol_col].loc[dt]
                            if isinstance(vol_val, pd.Series):
                                vol_val = vol_val.iloc[0]
                            if pd.notna(vol_val) and float(vol_val) > 0:
                                entry["volume"] = int(float(vol_val))
                        except Exception:
                            pass

                    result.append(entry)
            return result
        except Exception as e:
            logger.warning(f"OHLCV extraction failed for {symbol}: {e}")
            return []

    def _download_from_yahoo_intraday_chart() -> list[dict]:
        """Fetch true intraday candles from Yahoo chart API without crumb auth."""
        if not is_intraday:
            return []

        if period == "1d":
            # range=1d returns 0 points when market is closed; use 5d+5m and filter to last trading day
            range_param, interval_param = ("5d", "5m")
        elif period == "1w":
            range_param, interval_param = ("5d", "60m")
        else:
            range_param, interval_param = ("1mo", "60m")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://finance.yahoo.com",
            "Accept": "application/json",
        }
        IST = timezone(timedelta(hours=5, minutes=30))

        for suffix in [".NS", ".BO"]:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}"
            try:
                with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                    resp = client.get(
                        url,
                        headers=headers,
                        params={
                            "range": range_param,
                            "interval": interval_param,
                            "includePrePost": "false",
                            "events": "div,splits",
                        },
                    )
                    resp.raise_for_status()
                    payload = resp.json()

                results = (payload.get("chart") or {}).get("result") or []
                if not results:
                    continue

                result0 = results[0] or {}
                timestamps = result0.get("timestamp") or []
                quote_list = ((result0.get("indicators") or {}).get("quote") or [{}])
                quote0 = quote_list[0] if quote_list else {}
                closes = quote0.get("close") or []
                volumes = quote0.get("volume") or []

                if not timestamps or not closes:
                    continue

                out: list[dict] = []
                for i, ts in enumerate(timestamps):
                    if i >= len(closes):
                        break
                    close_val = closes[i]
                    if close_val is None:
                        continue

                    try:
                        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST)
                    except Exception:
                        continue

                    entry: dict = {
                        "date": dt.strftime("%Y-%m-%d %H:%M"),
                        "close": round(float(close_val), 2),
                    }

                    if i < len(volumes) and volumes[i] is not None:
                        try:
                            vol_int = int(float(volumes[i]))
                            if vol_int > 0:
                                entry["volume"] = vol_int
                        except Exception:
                            pass

                    out.append(entry)

                if out and period == "1d":
                    # Filter to last trading day only
                    last_day = sorted({p["date"][:10] for p in out})[-1]
                    out = [p for p in out if p["date"].startswith(last_day)]

                if out:
                    logger.info(f"Yahoo intraday chart: {len(out)} points for {symbol}{suffix} period={period}")
                    return out
            except Exception as e:
                logger.warning(f"Yahoo intraday chart failed for {symbol}{suffix} period={period}: {e}")

        return []

    def _download_from_yahoo_daily_chart() -> list[dict]:
        """Fetch daily candles from Yahoo chart API without crumb auth."""
        if is_intraday:
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://finance.yahoo.com",
            "Accept": "application/json",
        }
        IST = timezone(timedelta(hours=5, minutes=30))

        for suffix in [".NS", ".BO"]:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}"
            try:
                with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                    resp = client.get(
                        url,
                        headers=headers,
                        params={
                            "range": yf_period,
                            "interval": "1d",
                            "includePrePost": "false",
                            "events": "div,splits",
                        },
                    )
                    resp.raise_for_status()
                    payload = resp.json()

                results = (payload.get("chart") or {}).get("result") or []
                if not results:
                    continue

                result0 = results[0] or {}
                timestamps = result0.get("timestamp") or []
                quote_list = ((result0.get("indicators") or {}).get("quote") or [{}])
                quote0 = quote_list[0] if quote_list else {}
                closes = quote0.get("close") or []
                volumes = quote0.get("volume") or []

                if not timestamps or not closes:
                    continue

                out: list[dict] = []
                for i, ts in enumerate(timestamps):
                    if i >= len(closes):
                        break
                    close_val = closes[i]
                    if close_val is None:
                        continue

                    try:
                        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST)
                    except Exception:
                        continue

                    entry: dict = {
                        "date": dt.strftime("%Y-%m-%d"),
                        "close": round(float(close_val), 2),
                    }

                    if i < len(volumes) and volumes[i] is not None:
                        try:
                            vol_int = int(float(volumes[i]))
                            if vol_int > 0:
                                entry["volume"] = vol_int
                        except Exception:
                            pass

                    out.append(entry)

                if out:
                    logger.info(f"Yahoo daily chart: {len(out)} points for {symbol}{suffix} period={period}")
                    return out
            except Exception as e:
                logger.warning(f"Yahoo daily chart failed for {symbol}{suffix} period={period}: {e}")

        return []

    def _download_from_yfinance() -> list[dict]:
        """Download history from Yahoo chart endpoint for NSE/BSE variants."""
        for suffix in [".NS", ".BO"]:
            try:
                df = yf.download(
                    f"{symbol}{suffix}",
                    period=yf_period,
                    interval=yf_interval,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                    group_by="column",
                )
                points = _extract_ohlcv(df)
                if points:
                    return points
            except Exception as e:
                logger.warning(f"History yfinance failed for {symbol}{suffix}: {e}")
        return []

    def _download_from_jugaad() -> list[dict]:
        """Fallback to NSE historical candles; works for all periods (daily resolution for intraday)."""
        try:
            from jugaad_data.nse import stock_df  # type: ignore
        except Exception as e:
            logger.warning(f"jugaad-data import failed for history {symbol}: {e}")
            return []

        try:
            lookback_days = {
                "1d": 15, "1w": 25,
                "1mo": 45, "3mo": 120, "6mo": 220,
                "1y": 420, "2y": 820, "5y": 2050,
            }.get(period, 420)
            # For intraday periods, cap output to recent trading days
            max_pts = {"1d": 5, "1w": 7}.get(period, None)

            end = date.today()
            start = end - timedelta(days=lookback_days)
            df = stock_df(symbol=symbol, from_date=start, to_date=end, series="EQ")
            if df is None or df.empty:
                return []

            date_col = next((c for c in ["DATE", "Date", "date"] if c in df.columns), None)
            close_col = next((c for c in ["CLOSE", "Close", "close"] if c in df.columns), None)
            vol_col = next((c for c in ["VOLUME", "Volume", "volume", "TOTTRDQTY"] if c in df.columns), None)

            if date_col is None or close_col is None:
                return []

            cols = [date_col, close_col] + ([vol_col] if vol_col else [])
            tmp = df[cols].copy()
            tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp = tmp.dropna(subset=[date_col, close_col]).sort_values(by=date_col)

            out = []
            for _, row in tmp.iterrows():
                entry: dict = {
                    "date": row[date_col].strftime("%Y-%m-%d"),
                    "close": round(float(row[close_col]), 2),
                }
                if vol_col and pd.notna(row.get(vol_col)):
                    try:
                        entry["volume"] = int(float(row[vol_col]))
                    except Exception:
                        pass
                out.append(entry)
            return out[-max_pts:] if max_pts else out
        except Exception as e:
            logger.warning(f"History jugaad fallback failed for {symbol}: {e}")
            return []

    def _download() -> list[dict]:
        try:
            # For 1D: NSE native minute series first.
            if period == "1d":
                points = _fetch_nse_intraday_1d(symbol)
                if points:
                    return points

            # For 1D/1W/1M: enforce intraday source + bucketed output, no daily downgrade.
            if period in {"1d", "1w", "1mo"}:
                points = _download_from_yahoo_intraday_chart()
                if points:
                    return _aggregate_intraday_points(points)

                points = _download_from_yfinance()
                if points:
                    return _aggregate_intraday_points(points)

                logger.warning(f"Intraday history unavailable for {symbol} period={period}; returning empty set")
                return []

            # Remaining daily periods: direct Yahoo chart first, then yfinance, then NSE historical.
            points = _download_from_yahoo_daily_chart()
            if points:
                return points

            points = _download_from_yfinance()
            if points:
                return points
            points = _download_from_jugaad()
            if points:
                return points
            return []
        except Exception as e:
            logger.warning(f"History download failed for {symbol}: {e}")
            return []

    try:
        loop = asyncio.get_running_loop()
        closes = await loop.run_in_executor(None, _download)
    except Exception as e:
        logger.warning(f"get_history executor failed for {symbol}: {e}")
        closes = []

    return {"symbol": symbol, "period": period, "closes": closes}


def _fetch_from_groww(symbol: str) -> dict:
    """
    Fetch live quote from Groww Trade API.
    Returns normalised price dict or raises on failure.
    """
    try:
        from fetchers.groww_client import get_quote
    except ModuleNotFoundError:
        from fetchers.groww_client import get_quote

    q = get_quote(symbol)
    if not q or not q.get("last_price"):
        raise ValueError(f"Groww returned no price for {symbol}")

    price = float(q["last_price"])
    prev  = float(q.get("prev_close") or price)
    return {
        "exchange":       "NSE",
        "company_name":   symbol,
        "industry":       None,
        "sector":         None,
        "price":          round(price, 2),
        "previous_close": round(prev, 2),
        "change":         round(price - prev, 2),
        "change_percent": round(((price - prev) / prev) * 100, 2) if prev else 0.0,
        "open":           q.get("open"),
        "day_high":       q.get("high"),
        "day_low":        q.get("low"),
        "week_52_high":   q.get("week_52_high"),
        "week_52_low":    q.get("week_52_low"),
        "volume":         q.get("volume"),
        "market_cap":     None,   # Groww quote doesn't expose market cap
        "pe_ratio":       None,
        "pb_ratio":       None,
        "eps":            None,
        "dividend_yield": None,
        "beta":           None,
        "description":    None,
        "website":        None,
        "employees":      None,
    }


async def get_price_and_fundamentals(symbol: str) -> dict:
    """
    Async entry point for all services.
    Flow:
      1. NseIndiaApi (nse_client.fetch_quote) — primary, uses BennyThadikaran/NseIndiaApi git repo
      2. nsepython nse_eq() fallback — older lib, missing market cap
      3. Groww Trade API — reliable for BSE stocks
      4. Yahoo chart API — last resort

    The result always has the same keys — some may be None if source
    doesn't provide them (frontend shows "—" for null fields).
    """
    from fetchers.nse_client import fetch_quote as nse_fetch_quote

    symbol = symbol.upper().strip()

    # Stage 1: NseIndiaApi (BennyThadikaran/NseIndiaApi git repo) — accurate, full data
    try:
        q = await nse_fetch_quote(symbol)
        market_cap = int(q["market_cap_cr"] * 1e7) if q.get("market_cap_cr") else None
        # Volume from trade info falls back to pre-open if trade session not started
        volume = q.get("volume")
        data = {
            "symbol":        symbol,
            "exchange":      "NSE",
            "company_name":  q.get("company_name") or symbol,
            "sector":        q.get("sector"),
            "industry":      q.get("industry"),
            "price":         q["close"],
            "previous_close": q.get("previous_close"),
            "change":        q.get("change"),
            "change_percent": q.get("change_pct"),
            "open":          q.get("open"),
            "day_high":      q.get("high"),
            "day_low":       q.get("low"),
            "week_52_high":  q.get("week_high_52"),
            "week_52_low":   q.get("week_low_52"),
            "volume":        volume,
            "market_cap":    market_cap,
            "pe_ratio":      None,
            "pb_ratio":      None,
            "eps":           None,
            "dividend_yield": None,
            "beta":          None,
            "description":   None,
            "website":       None,
            "employees":     None,
        }
        logger.info(f"Quote source: NseIndiaApi for {symbol}")
        return data
    except Exception as e:
        logger.warning(f"NseIndiaApi failed for {symbol}: {e}. Trying nsepython...")

    # Stage 2: nsepython nse_eq() (older lib, no market cap)
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch_from_nse, symbol)
        data["symbol"] = symbol
        logger.info(f"Quote source: nsepython for {symbol}")
        return data
    except Exception as e:
        logger.warning(f"nsepython failed for {symbol}: {e}. Trying Groww...")

    # Stage 3: Groww Trade API
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch_from_groww, symbol)
        data["symbol"] = symbol
        logger.info(f"Quote source: Groww for {symbol}")
        return data
    except Exception as e:
        logger.warning(f"Groww quote failed for {symbol}: {e}. Trying Yahoo chart...")

    # Stage 4: Yahoo chart API (BSE fallback)
    data = await _fetch_from_yahoo_chart(symbol)
    data["symbol"] = symbol
    return data
