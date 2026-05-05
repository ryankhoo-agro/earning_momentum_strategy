"""
Earnings calendar fetch from Finnhub with BMO/AMC tagging.

Why Finnhub and not yfinance: yfinance earnings dates have active GitHub issues
documenting date misalignment. Finnhub's /calendar/earnings endpoint includes an
`hour` field ('bmo', 'amc', 'dmh') which is required for correct entry-day logic.

Caveat: free tier is rate-limited to 60 calls/min. Every call hits local parquet
cache first; the API is only hit on first run or when cache is explicitly cleared.
"""

import logging

import pandas as pd

from src.config import DATA_RAW_DIR, FINNHUB_RATE_LIMIT

logger = logging.getLogger(__name__)


def fetch_earnings_calendar(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """
    Return earnings events for `tickers` in [start, end] with BMO/AMC flag.

    Respects FINNHUB_RATE_LIMIT. Caches results under data/raw/.
    Logs every ticker that returns no data.
    """
    raise NotImplementedError


def tag_bmo_amc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each earnings row as 'bmo', 'amc', or 'dmh' (during market hours).

    dmh rows are flagged and excluded from signal generation — they cannot be
    mapped to a clean overnight gap.
    """
    raise NotImplementedError
