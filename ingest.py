"""
One-shot data ingestion: prices + earnings for the 2015-2025 S&P 500 universe.

Run once to populate data/raw/prices/ and data/raw/earnings/.
Subsequent dashboard runs read from cache without hitting the network.
"""

import logging
import sys
from pathlib import Path

# Ensure src/ is importable when run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import BACKTEST_START
from src.earnings import fetch_earnings_calendar
from src.prices import fetch_prices
from src.universe import get_all_tickers_in_window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

START = BACKTEST_START     # 2015-01-01
END = "2025-01-01"


def main() -> None:
    logger.info("=== Ingestion start ===")

    logger.info("Step 1/3 — resolving universe")
    tickers = get_all_tickers_in_window(START, END)
    logger.info("Universe: %d tickers", len(tickers))

    logger.info("Step 2/3 — fetching prices (batched, fast)")
    # ^GSPC appended as benchmark; not a strategy ticker, but needed by the equity curve tab.
    prices = fetch_prices(list(tickers) + ["^GSPC"], start=START, end=END)
    logger.info(
        "Prices done: %d rows, %d tickers",
        len(prices),
        prices["ticker"].nunique() if not prices.empty else 0,
    )

    logger.info("Step 3/3 — fetching earnings calendar (per-ticker, ~10-20 min)")
    earnings = fetch_earnings_calendar(tickers, start=START, end=END)
    logger.info(
        "Earnings done: %d events, %d tickers",
        len(earnings),
        earnings["ticker"].nunique() if not earnings.empty else 0,
    )

    logger.info("=== Ingestion complete ===")


if __name__ == "__main__":
    main()
