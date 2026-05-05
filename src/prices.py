"""
Daily OHLC fetch and caching via yfinance.

Why yfinance for prices: reliable enough for daily backtesting at no cost.
Caveat: yfinance has no delisted-stock prices. Stocks removed from the S&P 500
that were subsequently delisted will have partial or missing price histories.
Survivorship bias is partially mitigated by point-in-time membership but not
eliminated. Every missing ticker is logged so the user can audit the gap.

Cache layout: data/raw/prices/<TICKER>.parquet (per-ticker, DatetimeIndex).
Re-running the dashboard does not re-hit yfinance for already-cached tickers.
To refresh a ticker, delete its parquet file.
"""

import logging
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.config import (
    BACKTEST_END,
    BACKTEST_START,
    DATA_RAW_DIR,
    PRICE_BATCH_SIZE,
    RATE_LIMIT_DELAY_S,
)

logger = logging.getLogger(__name__)

_PRICES_DIR: Path = DATA_RAW_DIR / "prices"


def _cache_path(ticker: str) -> Path:
    return _PRICES_DIR / f"{ticker}.parquet"


def _load_from_cache(ticker: str) -> pd.DataFrame | None:
    path = _cache_path(ticker)
    if path.exists():
        return pd.read_parquet(path)
    return None


def _save_to_cache(ticker: str, df: pd.DataFrame) -> None:
    _PRICES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_cache_path(ticker))


def fetch_prices(
    tickers: list[str],
    start: str = BACKTEST_START,
    end: str | None = BACKTEST_END,
) -> pd.DataFrame:
    """
    Return daily Open/Close for `tickers` over [start, end].

    Hits per-ticker parquet cache first. Only fetches from yfinance on a cache
    miss. Results are batched to stay within yfinance's informal rate limits.
    Returns a long-format DataFrame with columns [ticker, Open, Close] and a
    DatetimeIndex named 'date'.
    """
    end_str = end or pd.Timestamp.today().normalize().strftime("%Y-%m-%d")

    cached: list[pd.DataFrame] = []
    to_fetch: list[str] = []

    for ticker in tickers:
        df = _load_from_cache(ticker)
        if df is not None:
            cached.append(df)
        else:
            to_fetch.append(ticker)

    if to_fetch:
        logger.info("Cache miss for %d tickers — fetching from yfinance", len(to_fetch))
        fetched = _batch_download(to_fetch, start, end_str)
        cached.extend(fetched)

    if not cached:
        logger.warning("fetch_prices returned no data for any ticker")
        return pd.DataFrame(columns=["ticker", "Open", "Close"])

    combined = pd.concat(cached)
    combined.index.name = "date"
    return combined.sort_index()


def _batch_download(tickers: list[str], start: str, end: str) -> list[pd.DataFrame]:
    """Download tickers in batches, sleeping between batches to respect rate limits."""
    frames: list[pd.DataFrame] = []
    batches = [
        tickers[i : i + PRICE_BATCH_SIZE]
        for i in range(0, len(tickers), PRICE_BATCH_SIZE)
    ]
    n_batches = len(batches)

    for idx, batch in enumerate(batches, start=1):
        logger.info(
            "Price batch %d/%d: downloading %d tickers", idx, n_batches, len(batch)
        )
        try:
            raw = yf.download(
                batch,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            logger.warning("Price batch %d/%d failed: %s", idx, n_batches, exc)
            _maybe_sleep(idx, n_batches)
            continue

        if raw.empty:
            logger.warning("Price batch %d/%d returned empty DataFrame", idx, n_batches)
            _maybe_sleep(idx, n_batches)
            continue

        frames.extend(_extract_batch(raw, batch))
        _maybe_sleep(idx, n_batches)

    return frames


def _extract_batch(raw: pd.DataFrame, batch: list[str]) -> list[pd.DataFrame]:
    """Pull per-ticker Open/Close from a yf.download() result and cache each."""
    frames: list[pd.DataFrame] = []

    # Single-ticker download has flat columns; multi-ticker has MultiIndex columns.
    single = len(batch) == 1

    for ticker in batch:
        try:
            if single:
                df = raw[["Open", "Close"]].copy()
            else:
                # MultiIndex columns: (field, ticker)
                df = raw[["Open", "Close"]].xs(ticker, axis=1, level=1).copy()

            df = df.dropna(how="all")
            if df.empty:
                logger.warning("No price data returned for %s", ticker)
                continue

            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            df["ticker"] = ticker
            _save_to_cache(ticker, df)
            frames.append(df)

        except KeyError:
            logger.warning("Ticker %s absent from yfinance download response", ticker)

    return frames


def _maybe_sleep(current_batch: int, total_batches: int) -> None:
    """Sleep between batches; skip after the last one."""
    if current_batch < total_batches:
        time.sleep(RATE_LIMIT_DELAY_S)
