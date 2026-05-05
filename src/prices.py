"""
Daily OHLC fetch and caching via yfinance.

Why yfinance for prices but not earnings: yfinance OHLC data is reliable enough
for daily backtesting. Its earnings date fields are not — see earnings.py.

Caveat: yfinance has no delisted-stock prices. Stocks removed from the S&P 500
that were subsequently delisted will have partial or missing price histories.
Survivorship bias is partially mitigated by point-in-time membership but not
eliminated. Every missing ticker is logged so the user can audit the gap.
"""

import logging

import pandas as pd

from src.config import BACKTEST_END, BACKTEST_START, DATA_RAW_DIR

logger = logging.getLogger(__name__)


def fetch_prices(tickers: list[str], start: str = BACKTEST_START, end: str | None = BACKTEST_END) -> pd.DataFrame:
    """
    Return daily OHLC for `tickers` over [start, end].

    Hits local parquet cache first. Fetches from yfinance only for tickers/date
    ranges not yet cached. Logs any tickers with no data returned.
    """
    raise NotImplementedError
