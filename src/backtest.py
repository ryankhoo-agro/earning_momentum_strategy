"""
Entry/exit logic and holding-period sweep.

Entry: open of t+1 (post-announcement open).
Exit: close of t+N, where N in {1, 2, 3, 4, 5}.
Sizing: equal-weight across all triggered names on a given entry date.
Costs: flat round-trip bps applied at entry.

No leverage, no shorting in v1. See docs/v2_ideas.md for deferred extensions.
"""

import logging

import pandas as pd

from src.config import DEFAULT_TRANSACTION_COST_BPS, HOLDING_PERIODS

logger = logging.getLogger(__name__)


def run_backtest(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    holding_period: int,
    transaction_cost_bps: float = DEFAULT_TRANSACTION_COST_BPS,
) -> pd.DataFrame:
    """
    Return trade-level P&L for a single holding period.

    Must be deterministic: identical inputs → identical outputs.
    """
    raise NotImplementedError


def sweep_holding_periods(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    holding_periods: list[int] = HOLDING_PERIODS,
    transaction_cost_bps: float = DEFAULT_TRANSACTION_COST_BPS,
) -> dict[int, pd.DataFrame]:
    """Run backtest for each holding period and return results keyed by N."""
    raise NotImplementedError
