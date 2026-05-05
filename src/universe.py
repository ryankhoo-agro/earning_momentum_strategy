"""
Point-in-time S&P 500 membership via fja05680/sp500.

Why this matters: using today's constituents to backtest 2015 data introduces
survivorship bias — you'd only hold names that survived to today. Point-in-time
membership bounds that bias by giving us the actual constituents at each date.
Caveat: fja05680 is approximate; it is not CRSP-grade.
"""

import logging

import pandas as pd

from src.config import DATA_RAW_DIR, SP500_MEMBERSHIP_URL

logger = logging.getLogger(__name__)


def get_universe(as_of_date: str) -> list[str]:
    """Return tickers that were S&P 500 members on `as_of_date` (YYYY-MM-DD)."""
    raise NotImplementedError


def load_membership_table() -> pd.DataFrame:
    """Fetch or load cached point-in-time membership table from fja05680/sp500."""
    raise NotImplementedError
