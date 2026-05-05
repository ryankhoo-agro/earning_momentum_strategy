# Earnings Momentum Dashboard — Planning Brief

## 1. Project Goal

Build a Streamlit dashboard that backtests and visualizes a long-only post-earnings announcement drift (PEAD) strategy on S&P 500 stocks. The strategy buys names whose earnings-driven overnight gap exceeds a threshold and holds for 1–5 days. The dashboard must let the user vary the threshold and holding period interactively.

**This is a research/portfolio project, not a production trading system.** Honesty about limitations is a deliverable, not an afterthought.

---

## 2. Strategy Specification (v1)

**Universe:** S&P 500 constituents, point-in-time membership (no survivorship bias).

**Signal:** Overnight earnings gap, defined as:

```
gap_i = (open_{t+1} - close_{t}) / close_{t}
```

where `t` is the trading day immediately preceding the announcement and `t+1` is the first trading day after. Announcement timing (BMO/AMC) determines which calendar day maps to `t` and `t+1`.

**Threshold (two modes, toggle in dashboard):**
- **Flat percentage:** buy if `gap > X%` (single global threshold)
- **Cross-sectional z-score:** buy if `gap` is in the top k-σ of all earnings gaps in a rolling pooling window (e.g., same week or rolling 30 days). This adjusts for earnings-season volatility regimes without per-stock calibration.

**Entry:** Open of `t+1` (the post-announcement open).

**Holding period:** Sweep 1, 2, 3, 4, 5 trading days. Exit at close of `t+N`. Dashboard shows decay curve across all five.

**Position sizing:** Equal-weighted across all triggered names. No leverage, no shorting in v1.

**Costs:** Apply a flat per-trade cost (round-trip bps, e.g., 5–10 bps) as a dashboard parameter. Document that this excludes market impact.

**Backtest window:** 2015-01-01 to most recent available.

---

## 3. Explicit Scope Cuts (do NOT build in v1)

These are deferred, not forgotten. List them in the dashboard's "Limitations" panel and in `docs/v2_ideas.md`.

- Long/short symmetric strategy (negative-gap shorts)
- Per-stock vol-scaled thresholds
- Sector-neutral or beta-neutral construction
- Intraday data or tick-level execution modeling
- Market-impact modeling
- Position-level risk constraints
- Walk-forward parameter optimization
- Live signal generation (this is a backtest dashboard, not a screening tool)

If the agent finds itself drawn into any of the above, stop and flag it.

---

## 4. Data Stack

**Confirmed: no WRDS access. Tier 1 free stack only.**

- **OHLC:** `yfinance` for daily Open/High/Low/Close/Volume of S&P 500 constituents (current + historical members).
- **Earnings calendar with BMO/AMC flag:** Finnhub free tier (`/calendar/earnings` endpoint, includes `hour` field). Rate limit: 60 calls/min.
- **Historical S&P 500 membership:** [`fja05680/sp500`](https://github.com/fja05680/sp500) GitHub repo for point-in-time constituent lists.

---

## 5. Known Data Limitations (must be surfaced in dashboard)

- **yfinance earnings dates are unreliable** (active GitHub issues on date misalignment). Use Finnhub for the calendar; use yfinance only for prices.
- **yfinance has no delisted-stock prices** → survivorship bias partially mitigated by point-in-time membership but not eliminated.
- **Finnhub free tier rate limit** (60 calls/min) requires batching and caching.
- **fja05680 historical membership** is approximate, not exact CRSP-quality.
- **Friday AMC releases** get weekend digestion — flag these but don't exclude in v1.
- **Intraday earnings releases** (rare): exclude or flag separately, never silently include.

---

## 6. Module Breakdown

```
project/
├── data/
│   ├── raw/                  # cached API responses (gitignored)
│   └── processed/            # cleaned parquet files (gitignored)
├── src/
│   ├── universe.py           # point-in-time S&P 500 membership
│   ├── earnings.py           # earnings calendar fetch + BMO/AMC tagging
│   ├── prices.py             # OHLC fetch and caching
│   ├── signal.py             # gap calculation, threshold logic (flat % and cross-sectional z)
│   ├── backtest.py           # entry/exit, holding-period sweep, P&L
│   ├── metrics.py            # Sharpe, drawdown, hit rate, turnover, decay curve
│   └── diagnostics.py        # BMO vs AMC split, sector distribution, gap distribution, sanity checks
├── app.py                    # Streamlit entry point
├── tests/                    # unit tests on signal + backtest logic
└── README.md                 # methodology + data caveats
```

**Caching is mandatory** — every API call hits local parquet first. Re-running the dashboard does not re-hit Finnhub.

---

## 7. Dashboard Panels (v1)

Keep it tight. Every panel must answer a question.

1. **Controls (sidebar):** threshold mode (flat % or z-score), threshold value, holding period (1–5 days, multi-select), date range, transaction cost (bps), BMO/AMC filter (all / BMO only / AMC only).
2. **Equity curve:** cumulative return of the strategy vs. SPY benchmark, for the selected holding period.
3. **Holding-period decay curve:** mean post-gap return at days 1, 2, 3, 4, 5. This is the headline PEAD plot.
4. **Trade-level diagnostics:** number of trades per quarter, hit rate, average winner vs. average loser.
5. **BMO vs AMC split:** equity curve and decay curve disaggregated by announcement timing. Tests the hypothesis that AMC and BMO behave differently.
6. **Distribution panel:** gap distribution and triggered-name distribution by sector. Surfaces the high-vol-bias problem of a flat-% threshold.
7. **Limitations & methodology:** static markdown panel listing every caveat from §5 and the scope cuts from §3.

---

## 8. Validation Requirements

Before any equity curve is shown to the user:

- **Sanity check 1:** Reproduce a known stylized fact — average post-earnings 1-day return for positive-gap stocks should be positive in the historical literature. If your numbers say otherwise, debug before showing.
- **Sanity check 2:** Number of earnings events per quarter should be in the right ballpark (~125 for S&P 500 per quarter).
- **Sanity check 3:** BMO/AMC distribution should not be ~50/50 random — it should reflect actual market patterns. The agent should not claim a specific split without verifying in the data.
- **Sanity check 4:** Spot-check ten random earnings events against a public source (e.g., company IR page or Yahoo Finance) for date and timing accuracy.

These checks live in `diagnostics.py` and must run as part of data ingestion.

---

## 9. Working Principles for Agents

- **Do not write code without asking the user to attempt the conceptual design first.** This is a learning project; the user's understanding is part of the deliverable.
- **Do not pad with extra features.** If a feature is not in §7, do not build it. Flag it for v2.
- **Surface assumptions, do not hide them.** Every modeling choice gets a docstring explaining why.
- **Caveat lavishly in the dashboard, not in conversation.** The dashboard is the artifact employers will see.
- **Default to simpler.** If the user's instinct is that something is over-engineered, it probably is.
- **Cite data sources in the README**, not academic papers. Citation padding is not the goal.

---

## 10. Hosting

- **v1: local development.**
- **v2 candidate: Streamlit Community Cloud.**
- API keys must be loaded from environment variables (`.env` locally, secrets manager on Cloud). Never hardcoded.
- `.env` is gitignored; `.env.example` is committed as a template.

---

## 11. Resolved Decisions

- Backtest start: **2015-01-01**
- WRDS access: **none** — Tier 1 free stack
- Hosting: **local first**, Cloud later

---

## 12. First Build Order

1. `universe.py` — smallest, most testable, everything else depends on it.
2. `earnings.py` — Finnhub fetch with caching and BMO/AMC tagging.
3. `prices.py` — yfinance OHLC for the universe.
4. `diagnostics.py` — sanity checks must pass before §5.
5. `signal.py` — gap calculation and the two threshold modes.
6. `backtest.py` — entry/exit and holding-period sweep.
7. `metrics.py` — Sharpe, drawdown, hit rate, decay.
8. `app.py` — Streamlit panels in the order listed in §7.

Do not skip ahead. Each step must pass its own tests before the next begins.