"""
Point-in-time S&P 500 membership via local CSV snapshot.

Why this matters: using today's constituents to backtest 2015 data introduces
survivorship bias — you'd only hold names that survived to today. Point-in-time
membership bounds that bias by giving us the actual constituents at each date.
Caveat: the CSV source is approximate; it is not CRSP-grade.

Date format in the CSV is D/M/YYYY (day-first). Rows with day > 12 confirm this.
"""

import logging

import pandas as pd

from src.config import DATA_RAW_DIR, SP500_CSV_PATH, SP500_MEMBERSHIP_URL

logger = logging.getLogger(__name__)

_TABLE_CACHE: pd.DataFrame | None = None


def load_membership_table() -> pd.DataFrame:
    """
    Load point-in-time membership from the local CSV snapshot.

    Falls back to downloading from fja05680/sp500 on GitHub if the local file
    is absent. Returns a DataFrame with columns:
      - date (datetime64): snapshot date
      - tickers (list[str]): S&P 500 members on that date
    """
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE

    if SP500_CSV_PATH.exists():
        logger.info("Loading membership table from %s", SP500_CSV_PATH)
        df_raw = pd.read_csv(SP500_CSV_PATH)
    else:
        logger.warning(
            "Local CSV not found at %s — downloading from %s",
            SP500_CSV_PATH,
            SP500_MEMBERSHIP_URL,
        )
        df_raw = pd.read_csv(SP500_MEMBERSHIP_URL)

    df_raw["date"] = pd.to_datetime(df_raw["date"], dayfirst=True)
    df_raw["tickers"] = df_raw["tickers"].str.split(",")
    df_raw = df_raw.sort_values("date").reset_index(drop=True)

    _TABLE_CACHE = df_raw
    return _TABLE_CACHE


def get_universe(as_of_date: str) -> list[str]:
    """Return tickers that were S&P 500 members on `as_of_date` (YYYY-MM-DD).

    Uses the most recent snapshot on or before as_of_date. Returns an empty
    list and logs a warning if no snapshot predates the requested date.
    """
    dt = pd.Timestamp(as_of_date)
    df = load_membership_table()
    past = df[df["date"] <= dt]
    if past.empty:
        logger.warning("No membership snapshot on or before %s", as_of_date)
        return []
    tickers: list[str] = past.iloc[-1]["tickers"]
    return tickers


def get_all_tickers_in_window(start: str, end: str) -> list[str]:
    """Return every unique ticker that appeared in the S&P 500 between start and end.

    Includes the snapshot immediately before start so that stocks already in the
    index at the start of the window are not excluded. The union covers all
    membership changes throughout the window, giving the full point-in-time
    universe needed to download prices and earnings data without look-ahead.
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    df = load_membership_table()

    pre_start = df[df["date"] <= start_dt].tail(1)
    in_window = df[(df["date"] > start_dt) & (df["date"] <= end_dt)]
    combined = pd.concat([pre_start, in_window], ignore_index=True)

    if combined.empty:
        logger.warning("No membership data in window %s – %s", start, end)
        return []

    all_tickers: set[str] = set()
    for row_tickers in combined["tickers"]:
        all_tickers.update(t.strip() for t in row_tickers if t.strip())

    result = sorted(all_tickers)
    logger.info(
        "Universe: %d unique tickers appeared between %s and %s",
        len(result),
        start,
        end,
    )
    return result
