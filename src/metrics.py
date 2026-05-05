"""
Performance and risk metrics computed from trade-level P&L.

All functions are pure — no I/O, no side effects. Input is a DataFrame of
trade returns; output is a scalar or Series.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe. Uses realised returns, not excess — no risk-free rate
    subtracted in v1 (document this in the dashboard)."""
    raise NotImplementedError


def max_drawdown(equity_curve: pd.Series) -> float:
    """Peak-to-trough drawdown as a negative fraction."""
    raise NotImplementedError


def hit_rate(trade_returns: pd.Series) -> float:
    """Fraction of trades with positive return."""
    raise NotImplementedError


def decay_curve(sweep_results: dict[int, pd.DataFrame]) -> pd.Series:
    """Mean trade return at each holding period N. The headline PEAD plot."""
    raise NotImplementedError


def turnover(signals: pd.DataFrame, holding_period: int) -> float:
    """Average fraction of portfolio turned over per day."""
    raise NotImplementedError
