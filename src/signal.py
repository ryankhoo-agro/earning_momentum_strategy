"""
Gap calculation and threshold logic.

The overnight earnings gap is defined as:
    gap = (open_t - close_{t-1}) / close_{t-1}

where t is the first trading session in which the market can react:
  - BMO: t = the announcement date itself (market hasn't opened yet)
  - AMC: t = the next trading day after the announcement date

Both cases use the same formula. The session tag is preserved so the owner
can disaggregate BMO vs AMC drift patterns downstream.

Two threshold modes:
  - Flat %: buy if gap > X%. Simple, but biased toward high-vol names and
    high-vol periods (tech earnings season amplifies gap sizes).
  - Cross-sectional z-score: deferred until the dataset is split.

Master output: data/processed/signals.csv — only rows with complete
price and earnings data on both sides of the join.
"""

import logging

import numpy as np
import pandas as pd

from src.config import DATA_PROCESSED_DIR

logger = logging.getLogger(__name__)

SIGNALS_CSV = DATA_PROCESSED_DIR / "signals.csv"


def compute_gaps(earnings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    Attach the overnight gap to each earnings event and write the master CSV.

    Filters out 'unknown' session rows (no clean gap can be defined without
    knowing announcement timing). Drops any event where either side of the
    price join is missing — no imputation, no forward-fill.

    Returns the master DataFrame and saves it to data/processed/signals.csv.
    """
    # ── 1. Drop unknowns ──────────────────────────────────────────────────────
    known = earnings[earnings["session"].isin(["bmo", "amc"])].copy()
    dropped = len(earnings) - len(known)
    if dropped:
        logger.info("Dropped %d unknown-session rows from earnings", dropped)

    # ── 2. Build wide price tables ────────────────────────────────────────────
    # prices: DatetimeIndex('date', tz-naive) + columns [ticker, Open, Close]
    prices_reset = prices.reset_index()
    open_wide = prices_reset.pivot(index="date", columns="ticker", values="Open")
    close_wide = prices_reset.pivot(index="date", columns="ticker", values="Close")

    # Previous trading day's close: shift by 1 row within the sorted date index.
    prev_close = close_wide.shift(1)

    trading_dates = open_wide.index.values  # tz-naive numpy datetime64 array

    # ── 3. Compute reaction_date for every event ──────────────────────────────
    # Normalise earnings timestamps to tz-naive calendar dates for searchsorted.
    norm_dates = (
        known["earnings_date"]
        .dt.normalize()
        .dt.tz_localize(None)
        .values.astype("datetime64[ns]")
    )

    bmo_mask = (known["session"] == "bmo").values

    # BMO: first trading day >= announcement date  → searchsorted side='left'
    # AMC: first trading day >  announcement date  → searchsorted side='right'
    idx_left = np.searchsorted(trading_dates, norm_dates, side="left")
    idx_right = np.searchsorted(trading_dates, norm_dates, side="right")
    reaction_idx = np.where(bmo_mask, idx_left, idx_right)

    in_bounds = reaction_idx < len(trading_dates)
    capped = np.minimum(reaction_idx, len(trading_dates) - 1)
    reaction_dates = np.where(in_bounds, trading_dates[capped], np.datetime64("NaT"))

    known = known.copy()
    known["reaction_date"] = pd.to_datetime(reaction_dates)

    out_of_range = known["reaction_date"].isna().sum()
    if out_of_range:
        logger.info(
            "Dropped %d events with no trading day on/after announcement date",
            out_of_range,
        )
    known = known.dropna(subset=["reaction_date"])

    # ── 4. Vectorised price lookup via long-format merge ──────────────────────
    open_long = (
        open_wide.stack(future_stack=True)
        .rename("open_t")
        .reset_index()
        .rename(columns={"date": "reaction_date"})
    )
    prev_close_long = (
        prev_close.stack(future_stack=True)
        .rename("prev_close")
        .reset_index()
        .rename(columns={"date": "reaction_date"})
    )

    result = known.merge(open_long, on=["reaction_date", "ticker"], how="inner")
    result = result.merge(prev_close_long, on=["reaction_date", "ticker"], how="inner")

    before = len(result)
    result = result.dropna(subset=["open_t", "prev_close"])
    after = len(result)
    if before - after:
        logger.info(
            "Dropped %d events with NaN open_t or prev_close after price join",
            before - after,
        )

    # ── 5. Gap calculation ────────────────────────────────────────────────────
    result["gap"] = (result["open_t"] - result["prev_close"]) / result["prev_close"]

    # ── 6. Save master CSV ────────────────────────────────────────────────────
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    col_order = [
        "ticker", "earnings_date", "session", "friday_amc",
        "reaction_date", "prev_close", "open_t", "gap",
        "eps_estimate", "reported_eps", "surprise_pct",
    ]
    out_cols = [c for c in col_order if c in result.columns]
    result[out_cols].to_csv(SIGNALS_CSV, index=False)

    logger.info(
        "signals.csv: %d events, %d tickers — saved to %s",
        len(result),
        result["ticker"].nunique(),
        SIGNALS_CSV,
    )
    return result[out_cols]


def apply_flat_threshold(gaps: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    """Return rows where gap exceeds `threshold_pct` (e.g., 2.0 means 2%)."""
    threshold = threshold_pct / 100.0
    signal = gaps[gaps["gap"] > threshold].copy()
    logger.info(
        "Flat threshold %.1f%%: %d / %d events pass (%.1f%%)",
        threshold_pct,
        len(signal),
        len(gaps),
        100 * len(signal) / len(gaps) if len(gaps) else 0,
    )
    return signal


def apply_zscore_threshold(
    gaps: pd.DataFrame,
    threshold_z: float,
    train_mean: float,
    train_std: float,
) -> pd.DataFrame:
    """
    Apply a static z-score threshold using training-period statistics.

    Cutoff = train_mean + threshold_z * train_std.

    The training stats must be precomputed via backtest.calibrate_zscore_threshold
    to prevent look-ahead: the holdout set must never touch the calibration step.
    """
    cutoff = train_mean + threshold_z * train_std
    signal = gaps[gaps["gap"] > cutoff].copy()
    logger.info(
        "Z-score threshold z=%.2f (cutoff=%.4f): %d / %d events pass (%.1f%%)",
        threshold_z,
        cutoff,
        len(signal),
        len(gaps),
        100 * len(signal) / len(gaps) if len(gaps) else 0,
    )
    return signal
