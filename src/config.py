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
# Hold-out period starts here; everything before is used only for calibration.
TEST_START: str = "2022-01-01"

# ── Strategy parameters ───────────────────────────────────────────────────────
HOLDING_PERIODS: list[int] = [1, 2, 3, 4, 5]
DEFAULT_GAP_THRESHOLD_PCT: float = 2.0       # flat-% mode default
DEFAULT_ZSCORE_THRESHOLD: float = 1.5        # z-score mode default
DEFAULT_TRANSACTION_COST_BPS: float = 5.0    # round-trip basis points
DEFAULT_SLIPPAGE_BPS: float = 2.5            # round-trip basis points

# ── Data sources ──────────────────────────────────────────────────────────────
SP500_MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv"
)
SP500_CSV_FILENAME = "S&P 500 Historical Components & Changes (01-17-2026).csv"
SP500_CSV_PATH = DATA_RAW_DIR / SP500_CSV_FILENAME

# ── Rate limiting / fetching ──────────────────────────────────────────────────
# Delay between yfinance batch calls to avoid triggering rate limits.
RATE_LIMIT_DELAY_S: float = 1.0
# Number of tickers per yf.download() batch call.
PRICE_BATCH_SIZE: int = 50
# Max earnings records to request per ticker (~60 covers 15 years of quarterlies).
EARNINGS_LIMIT: int = 60
