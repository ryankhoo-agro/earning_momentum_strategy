"""
Gap calculation and threshold logic.

The overnight earnings gap is defined as:
    gap_i = (open_{t+1} - close_t) / close_t

where t is the last trading day before the announcement and t+1 is the first
trading day after. BMO/AMC timing determines the correct calendar mapping.

Two threshold modes:
- Flat %: buy if gap > X%. Simple, but biased toward high-vol names and
  high-vol periods (tech earnings season amplifies gap sizes).
- Cross-sectional z-score: buy if gap is in the top k-sigma of all gaps in a
  rolling pooling window. Adjusts for earnings-season regime without per-stock
  calibration. Pooling window is a modeling choice the owner must make.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_gaps(earnings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Attach overnight gap to each earnings event row."""
    raise NotImplementedError


def apply_flat_threshold(gaps: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    """Return rows where gap exceeds `threshold_pct` (e.g., 2.0 = 2%)."""
    raise NotImplementedError


def apply_zscore_threshold(gaps: pd.DataFrame, threshold_z: float, window_days: int) -> pd.DataFrame:
    """
    Return rows where gap z-score (within rolling `window_days` pool) exceeds
    `threshold_z`.

    Window choice is a modeling decision — see planning_brief.md §2.
    """
    raise NotImplementedError
