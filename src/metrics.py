"""
Performance and risk metrics computed from trade-level P&L.

All functions are pure — no I/O, no side effects. Input is a DataFrame of
trade returns; output is a scalar or Series.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_drift_paths(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    max_hold: int = 5,
) -> pd.DataFrame:
    """
    Compute per-segment returns for each earnings event over a holding window.

    Return segments (6 total for max_hold=5):
      gap      : prev_close → open_t (overnight, already in signals)
      intraday : open_t → close_t on reaction day
      day2-5   : close-to-close for each subsequent trading day

    Events without a full max_hold price window are dropped and logged — yfinance
    has no delisted prices so this is expected for names removed from the S&P 500.

    Returns a DataFrame with columns:
      ticker, reaction_date, session, gap, intraday, day2, ..., day{max_hold+1}
    """
    seg_labels = ["gap", "intraday"] + [f"day{i+2}" for i in range(max_hold - 1)]

    # Build close_wide: index=date (tz-naive), columns=ticker
    prices_reset = prices.reset_index()
    prices_reset["date"] = pd.to_datetime(prices_reset["date"])
    if prices_reset["date"].dt.tz is not None:
        prices_reset["date"] = prices_reset["date"].dt.tz_localize(None)
    close_wide = prices_reset.pivot(index="date", columns="ticker", values="Close").sort_index()

    signals = signals.copy()
    signals["reaction_date"] = pd.to_datetime(signals["reaction_date"]).dt.normalize()
    if signals["reaction_date"].dt.tz is not None:
        signals["reaction_date"] = signals["reaction_date"].dt.tz_localize(None)

    records: list[dict] = []
    skipped = 0

    for _, row in signals.iterrows():
        ticker = row["ticker"]
        reaction_date = row["reaction_date"]

        if ticker not in close_wide.columns:
            skipped += 1
            continue

        col = close_wide[ticker].dropna()

        if reaction_date not in col.index:
            skipped += 1
            continue

        pos = col.index.get_loc(reaction_date)

        # Need max_hold closes starting at reaction_date
        if pos + max_hold > len(col):
            skipped += 1
            continue

        closes = col.iloc[pos : pos + max_hold].values
        open_t = float(row["open_t"])
        gap = float(row["gap"])

        if np.any(np.isnan(closes)) or np.isnan(open_t):
            skipped += 1
            continue

        intraday = (closes[0] - open_t) / open_t
        ctc = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, max_hold)]
        segs = [gap, intraday] + ctc

        records.append({
            "ticker": ticker,
            "reaction_date": reaction_date,
            "session": row.get("session"),
            **dict(zip(seg_labels, segs)),
        })

    if skipped:
        logger.info("compute_drift_paths: dropped %d events (incomplete price window)", skipped)

    return pd.DataFrame(records)


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe. Uses realised returns, not excess — no risk-free rate
    subtracted in v1 (document this in the dashboard). Includes 0-return days
    (days with no active positions), which is conservative but honest."""
    if len(returns) < 2 or returns.std() == 0:
        return float("nan")
    return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: pd.Series) -> float:
    """Peak-to-trough drawdown as a negative fraction (e.g., -0.15 = -15%)."""
    if equity_curve.empty:
        return float("nan")
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    return float(drawdown.min())


def hit_rate(trade_returns: pd.Series) -> float:
    """Fraction of trades with positive net return."""
    if trade_returns.empty:
        return float("nan")
    return float((trade_returns > 0).mean())


def decay_curve(sweep_results: dict[int, pd.DataFrame]) -> pd.Series:
    """Mean trade return at each holding period N. The headline PEAD plot."""
    raise NotImplementedError


def turnover(signals: pd.DataFrame, holding_period: int) -> float:
    """Average fraction of portfolio turned over per day."""
    raise NotImplementedError
