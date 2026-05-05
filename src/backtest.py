"""
Entry/exit, holding-period sweep, and P&L computation.

Fixed-notional, calendar-time portfolio: each triggered event gets one unit
of notional. The portfolio's daily return is the equal-weighted average of all
currently active positions' mark-to-market returns. Days with no open positions
contribute zero. This matches the standard calendar-time approach in PEAD
literature (Bernard & Thomas 1989) and is consistent with equal-sizing every
trade — because each trade is the same size, averaging is correct.

Entry modes:
  'open'  — buy at open_t on reaction_date. The overnight gap has already
             occurred; this captures the intraday continuation and subsequent
             day-to-day drift.
  'close' — buy at close on reaction_date. Forfeits the gap and intraday
             move; captures only subsequent day-to-day drift from day 1 onward.
             Requires one additional trading day of price data per trade.

Costs (round-trip, deducted from each trade's last holding day):
  cost_bps     — commissions and fees
  slippage_bps — bid-ask spread / execution quality degradation
  Both are in basis points, round-trip (entry + exit combined).
"""

import logging

import numpy as np
import pandas as pd

from src.config import DEFAULT_SLIPPAGE_BPS, DEFAULT_TRANSACTION_COST_BPS, TEST_START

logger = logging.getLogger(__name__)


def split_signals(
    signals: pd.DataFrame, test_start: str = TEST_START
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split signals into train and holdout sets by reaction_date.

    Train: reaction_date < test_start  — used only for threshold calibration.
    Test:  reaction_date >= test_start — the out-of-sample equity curve window.
    """
    dates = pd.to_datetime(signals["reaction_date"]).dt.normalize()
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    cutoff = pd.Timestamp(test_start)
    train = signals[dates < cutoff].copy()
    test = signals[dates >= cutoff].copy()
    logger.info(
        "Train/test split at %s: %d train events, %d test events",
        test_start,
        len(train),
        len(test),
    )
    return train, test


def calibrate_zscore_threshold(
    train_signals: pd.DataFrame, z: float
) -> dict[str, float]:
    """
    Compute gap distribution statistics on the training set and derive a
    static gap cutoff = mean + z * std.

    Static (not rolling) to avoid look-ahead from the holdout period. The
    user picks z on distributional grounds — e.g., to target the top quartile
    of earnings gaps — not by optimising any return metric on the training set.

    Returns a dict with keys: mean, std, z, cutoff (all in decimal, not %).
    """
    gaps = train_signals["gap"].dropna()
    if gaps.empty:
        logger.warning("calibrate_zscore_threshold: train_signals has no gap data")
        return {"mean": 0.0, "std": 1.0, "z": z, "cutoff": z}
    mean_gap = float(gaps.mean())
    std_gap = float(gaps.std())
    cutoff = mean_gap + z * std_gap
    pct_passing = float((gaps > cutoff).mean()) * 100
    logger.info(
        "Z-score calibration: n=%d, mean=%.4f, std=%.4f, z=%.2f → cutoff=%.4f (%.1f%% of train pass)",
        len(gaps),
        mean_gap,
        std_gap,
        z,
        cutoff,
        pct_passing,
    )
    return {"mean": mean_gap, "std": std_gap, "z": z, "cutoff": cutoff}


def run_backtest(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    holding_period: int,
    entry_mode: str = "open",
    cost_bps: float = DEFAULT_TRANSACTION_COST_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    Build a calendar-time equity curve and trade log from filtered signals.

    signals should already be filtered to the desired threshold and holdout
    window. prices must cover the full holding window for every event in signals.

    Returns
    -------
    equity_curve : pd.Series
        Date-indexed cumulative portfolio value, starting at 1.0 on the first
        reaction_date. Days with no open positions compound at 0% (flat).
    trade_log : pd.DataFrame
        One row per completed trade with entry/exit dates, prices, and returns.
    """
    if signals.empty:
        logger.warning("run_backtest: signals is empty — returning flat equity curve")
        return pd.Series(dtype=float, name="equity"), pd.DataFrame()

    # ── 1. Build close matrix ─────────────────────────────────────────────────
    prices_reset = prices.reset_index()
    prices_reset["date"] = pd.to_datetime(prices_reset["date"])
    if prices_reset["date"].dt.tz is not None:
        prices_reset["date"] = prices_reset["date"].dt.tz_localize(None)

    close_wide = (
        prices_reset.pivot(index="date", columns="ticker", values="Close")
        .sort_index()
    )

    signals = signals.copy()
    signals["reaction_date"] = pd.to_datetime(signals["reaction_date"]).dt.normalize()
    if signals["reaction_date"].dt.tz is not None:
        signals["reaction_date"] = signals["reaction_date"].dt.tz_localize(None)

    round_trip_cost = (cost_bps + slippage_bps) / 10_000.0
    # close entry needs one extra close: closes[0] = reaction_date close (entry price)
    closes_needed = holding_period + (1 if entry_mode == "close" else 0)

    trade_records: list[dict] = []
    daily_rows: list[dict] = []
    skipped = 0
    trade_id = 0

    # ── 2. Per-trade daily mark-to-market returns ─────────────────────────────
    for _, row in signals.iterrows():
        ticker = row["ticker"]
        reaction_date = row["reaction_date"]
        open_t = float(row["open_t"])

        if ticker not in close_wide.columns:
            skipped += 1
            continue

        col = close_wide[ticker].dropna()
        if reaction_date not in col.index:
            skipped += 1
            continue

        pos = col.index.get_loc(reaction_date)
        if pos + closes_needed > len(col):
            skipped += 1
            continue

        closes = col.iloc[pos : pos + closes_needed].values
        dates_window = col.index[pos : pos + closes_needed]

        if np.any(np.isnan(closes)) or np.isnan(open_t):
            skipped += 1
            continue

        if entry_mode == "open":
            # active days: reaction_date … reaction_date + (N-1) trading days
            active_dates = dates_window
            entry_price = open_t
            exit_price = float(closes[-1])
            daily_rets: list[float] = [float((closes[0] - open_t) / open_t)]
            for k in range(1, holding_period):
                daily_rets.append(float((closes[k] - closes[k - 1]) / closes[k - 1]))
        else:  # close
            # active days: reaction_date+1 … reaction_date + N trading days
            # closes[0] = close on reaction_date (entry); closes[1..N] = exit path
            active_dates = dates_window[1:]
            entry_price = float(closes[0])
            exit_price = float(closes[-1])
            daily_rets = [
                float((closes[k + 1] - closes[k]) / closes[k])
                for k in range(holding_period)
            ]

        # Round-trip cost charged on exit (last active day)
        daily_rets[-1] -= round_trip_cost
        gross_return = (exit_price - entry_price) / entry_price
        net_return = gross_return - round_trip_cost

        trade_records.append(
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "reaction_date": reaction_date,
                "entry_date": active_dates[0],
                "exit_date": active_dates[-1],
                "session": row.get("session"),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "net_return": net_return,
            }
        )
        for date, ret in zip(active_dates, daily_rets):
            daily_rows.append({"trade_id": trade_id, "date": date, "ret": ret})

        trade_id += 1

    if skipped:
        logger.info("run_backtest: skipped %d events (incomplete price window)", skipped)

    trade_log = pd.DataFrame(trade_records)

    if not daily_rows:
        logger.warning("run_backtest: no trades generated")
        return pd.Series(dtype=float, name="equity"), trade_log

    # ── 3. Calendar-time portfolio returns ────────────────────────────────────
    daily_df = pd.DataFrame(daily_rows)
    # Wide matrix: rows = dates, cols = trade_ids, values = daily MTM return.
    # NaN means that trade was not active on that date; mean(skipna) handles it.
    matrix = daily_df.pivot(index="date", columns="trade_id", values="ret")
    portfolio_returns = matrix.mean(axis=1)

    # Reindex to all trading dates from first reaction_date onward, filling
    # days with no active positions with 0 (strategy sits flat)
    first_date = signals["reaction_date"].min()
    all_dates = close_wide.index[close_wide.index >= first_date]
    portfolio_returns = portfolio_returns.reindex(all_dates, fill_value=0.0)

    # ── 4. Equity curve (cumulative product, starts at 1.0) ───────────────────
    equity_curve = (1.0 + portfolio_returns).cumprod()
    equity_curve.name = "equity"

    return equity_curve, trade_log
