"""
Earnings calendar fetch via yfinance Ticker.get_earnings_dates().

Why yfinance: used for lack of a better free alternative. Treat dates as
approximate — spot-check against public sources before trusting any signal.

Caching: every fetch writes to data/raw/earnings/<TICKER>.parquet. Re-runs
read from cache without hitting the network.

BMO/AMC classification uses the timezone-aware timestamp yfinance returns:
  - time < 09:30 ET  → BMO (pre-market announcement)
  - time >= 16:00 ET → AMC (after-hours announcement)
  - anything else    → unknown (logged and excluded from signal generation)

Friday AMC releases receive weekend digestion time before the gap opens on
Monday. These are flagged via the 'friday_amc' column rather than excluded,
so the owner can decide how to treat them.

Intraday releases (09:30–16:00) are tagged 'unknown' and excluded — they
cannot be mapped to a clean overnight gap without intraday data.
"""

import logging
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from src.config import DATA_RAW_DIR, EARNINGS_LIMIT, RATE_LIMIT_DELAY_S

logger = logging.getLogger(__name__)

_EARNINGS_DIR: Path = DATA_RAW_DIR / "earnings"
_ET = ZoneInfo("America/New_York")

# Market session boundaries in ET
_MARKET_OPEN_HOUR = 9
_MARKET_OPEN_MINUTE = 30
_MARKET_CLOSE_HOUR = 16


def _cache_path(ticker: str) -> Path:
    return _EARNINGS_DIR / f"{ticker}.parquet"


def _load_from_cache(ticker: str) -> pd.DataFrame | None:
    path = _cache_path(ticker)
    if path.exists():
        return pd.read_parquet(path)
    return None


def _save_to_cache(ticker: str, df: pd.DataFrame) -> None:
    _EARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_cache_path(ticker))


def fetch_earnings_calendar(
    tickers: list[str], start: str, end: str
) -> pd.DataFrame:
    """
    Return earnings events for `tickers` in [start, end].

    Hits per-ticker parquet cache first. Fetches from yfinance only on cache
    miss, sleeping RATE_LIMIT_DELAY_S between each ticker to avoid throttling.
    Logs every ticker that returns no data.

    Returns a DataFrame with columns:
      ticker, earnings_date (datetime, tz-aware ET), session (bmo/amc/unknown),
      friday_amc (bool), eps_estimate, reported_eps, surprise_pct.
    """
    start_dt = pd.Timestamp(start, tz=_ET)
    end_dt = pd.Timestamp(end, tz=_ET)

    frames: list[pd.DataFrame] = []
    to_fetch: list[str] = []

    for ticker in tickers:
        df = _load_from_cache(ticker)
        if df is not None:
            frames.append(df)
        else:
            to_fetch.append(ticker)

    if to_fetch:
        logger.info(
            "Cache miss for %d tickers — fetching earnings from yfinance", len(to_fetch)
        )
        for i, ticker in enumerate(to_fetch):
            df = _fetch_one(ticker)
            if df is not None:
                frames.append(df)
            if i < len(to_fetch) - 1:
                time.sleep(RATE_LIMIT_DELAY_S)

    if not frames:
        logger.warning("fetch_earnings_calendar returned no data for any ticker")
        return pd.DataFrame(
            columns=[
                "ticker",
                "earnings_date",
                "session",
                "friday_amc",
                "eps_estimate",
                "reported_eps",
                "surprise_pct",
            ]
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = tag_bmo_amc(combined)

    # Filter to requested window
    mask = (combined["earnings_date"] >= start_dt) & (
        combined["earnings_date"] <= end_dt
    )
    windowed = combined[mask].copy().reset_index(drop=True)

    logger.info(
        "%d earnings events in window %s – %s", len(windowed), start, end
    )
    return windowed


def _fetch_one(ticker: str) -> pd.DataFrame | None:
    """Fetch earnings dates for a single ticker, cache, and return a tidy DataFrame."""
    try:
        raw = yf.Ticker(ticker).get_earnings_dates(limit=EARNINGS_LIMIT)
    except Exception as exc:
        logger.warning("yfinance error fetching earnings for %s: %s", ticker, exc)
        return None

    if raw is None or raw.empty:
        logger.warning("No earnings data returned for %s", ticker)
        return None

    df = raw.reset_index()
    df.columns = df.columns.str.strip()

    # Normalise column names — yfinance field names can vary across versions.
    rename_map = {
        "Earnings Date": "earnings_date",
        "EPS Estimate": "eps_estimate",
        "Reported EPS": "reported_eps",
        "Surprise(%)": "surprise_pct",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    df["ticker"] = ticker

    # Keep only the columns we care about; tolerate missing optional columns.
    keep = ["ticker", "earnings_date", "eps_estimate", "reported_eps", "surprise_pct"]
    df = df[[c for c in keep if c in df.columns]]

    _save_to_cache(ticker, df)
    return df


def tag_bmo_amc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each row as 'bmo', 'amc', or 'unknown' using the earnings timestamp.

    Rows tagged 'unknown' are logged and excluded from signal generation —
    they cannot be mapped to a clean overnight gap without knowing announcement
    timing. Friday AMC events are flagged separately; they receive weekend
    digestion time and should be handled intentionally, not silently.
    """
    if "earnings_date" not in df.columns:
        raise ValueError("DataFrame must have an 'earnings_date' column")

    dates = pd.to_datetime(df["earnings_date"])

    # Ensure timezone-aware in ET
    if dates.dt.tz is None:
        dates = dates.dt.tz_localize(_ET)
    else:
        dates = dates.dt.tz_convert(_ET)

    hour = dates.dt.hour
    minute = dates.dt.minute

    before_open = (hour < _MARKET_OPEN_HOUR) | (
        (hour == _MARKET_OPEN_HOUR) & (minute < _MARKET_OPEN_MINUTE)
    )
    after_close = hour >= _MARKET_CLOSE_HOUR

    session = pd.Series("unknown", index=df.index)
    session[before_open] = "bmo"
    session[after_close] = "amc"

    unknown_count = (session == "unknown").sum()
    if unknown_count:
        logger.info(
            "%d earnings rows have ambiguous timing — tagged 'unknown' and excluded "
            "from signal generation",
            unknown_count,
        )

    df = df.copy()
    df["session"] = session
    df["earnings_date"] = dates  # store tz-aware

    # Flag Friday AMC so the owner can decide how to handle weekend digestion.
    friday_amc = (dates.dt.dayofweek == 4) & (session == "amc")
    df["friday_amc"] = friday_amc

    return df
