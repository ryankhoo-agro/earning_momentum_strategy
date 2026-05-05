"""
Sanity checks and diagnostic panels. Must pass before any equity curve is shown.

Checks (from planning_brief.md §8):
1. Average 1-day return for positive-gap stocks is positive.
2. ~125 earnings events per quarter for S&P 500 universe.
3. BMO/AMC split is not ~50/50 random.
4. Spot-check: 10 random events match a public source (manual + automated).

Failing any check raises a DataQualityError so the dashboard surfaces it
explicitly rather than silently displaying bad results.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when a sanity check fails. Blocks downstream computation."""


def check_positive_gap_drift(trade_returns: pd.DataFrame) -> None:
    """Sanity check 1: mean 1-day return on positive-gap names must be > 0."""
    raise NotImplementedError


def check_earnings_count(earnings: pd.DataFrame) -> None:
    """Sanity check 2: ~125 events per quarter. Logs actual counts."""
    raise NotImplementedError


def check_bmo_amc_split(earnings: pd.DataFrame) -> None:
    """Sanity check 3: BMO/AMC split must not be ~50/50."""
    raise NotImplementedError


def gap_distribution(signals: pd.DataFrame) -> pd.DataFrame:
    """Return gap distribution statistics for the distribution panel."""
    raise NotImplementedError


def sector_distribution(signals: pd.DataFrame, sector_map: pd.Series) -> pd.DataFrame:
    """Return triggered-name counts by sector for the distribution panel."""
    raise NotImplementedError
