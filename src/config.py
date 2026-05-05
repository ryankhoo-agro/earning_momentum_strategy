"""
Central config — all thresholds, paths, and rate limits live here.
No magic numbers elsewhere in the codebase.
"""

from pathlib import Path

# ── Directories ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# ── Backtest window ───────────────────────────────────────────────────────────
BACKTEST_START = "2015-01-01"
# End date: None means most recent available; set explicitly to pin a window.
BACKTEST_END: str | None = None

# ── Strategy parameters ───────────────────────────────────────────────────────
HOLDING_PERIODS: list[int] = [1, 2, 3, 4, 5]
DEFAULT_GAP_THRESHOLD_PCT: float = 2.0       # flat-% mode default
DEFAULT_ZSCORE_THRESHOLD: float = 1.5        # z-score mode default
DEFAULT_TRANSACTION_COST_BPS: float = 5.0    # round-trip basis points

# ── Data sources ──────────────────────────────────────────────────────────────
SP500_MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv"
)

# ── Finnhub ───────────────────────────────────────────────────────────────────
FINNHUB_RATE_LIMIT: int = 60   # calls per minute (free tier)
