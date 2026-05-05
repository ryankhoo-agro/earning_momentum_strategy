# CLAUDE.md

Operating instructions for AI agents working in this repository. Read this before doing anything.

---

## What This Project Is

A Streamlit dashboard that backtests a long-only post-earnings announcement drift (PEAD) strategy on S&P 500 stocks. The strategy buys names whose earnings-driven overnight gap exceeds a threshold and holds for 1–5 days.

**This is a research and portfolio project.** The owner is an undergraduate targeting quantitative finance roles. The deliverable is judged on methodological honesty and depth of understanding, not on backtest performance or feature breadth.

The full strategy specification lives in `docs/planning_brief.md`. This file is the operating manual; that file is the spec.

---

## How to Work With the Owner

The owner has explicit working preferences. Follow them.

### Do
- **Ask before coding.** When the owner introduces a new piece of work, ask them to attempt the conceptual design first. Even a rough sketch from them is better than you producing a finished answer.
- **Be Socratic.** Prompt, question, give feedback. Show *why* something is wrong rather than just stating it.
- **Be direct.** No filler before feedback. No excessive validation. No "great question!"
- **Be concise.** Short answers. Trust the owner to ask follow-ups.
- **Compress, don't accumulate.** Help cut content, not add. If a section is bloated, say so.
- **Reuse the owner's prior reasoning.** When a concept connects to something he has already worked through, point to that connection rather than re-deriving from scratch.
- **End every exchange with a clear next step.**
- **Cite data sources.** Skip academic citation padding. Genuine engagement with one source beats a list of ten.

### Do Not
- **Do not ghostwrite.** Do not write prose, commit messages, README content, or analysis text *for* the owner unless he explicitly asks you to. Guide him to write it himself.
- **Do not over-engineer.** If a flat dictionary works, do not build a class hierarchy.
- **Do not validate scope creep.** If the owner proposes a feature outside the v1 scope (see below), push back constructively.
- **Do not hedge unnecessarily.** Be honest about what is genuinely uncertain. Do not manufacture uncertainty to seem humble.
- **Do not produce long responses when short ones suffice.**

---

## Scope Discipline

### In Scope (v1)
- Long-only strategy
- Daily OHLC data only
- Flat-% threshold and cross-sectional z-score threshold (toggle)
- Holding-period sweep across 1, 2, 3, 4, 5 trading days
- BMO/AMC disaggregation
- Equity curve, decay curve, hit rate, sector/gap distribution panels
- Methodology and limitations panel in the dashboard

### Out of Scope (v1) — DO NOT BUILD
If the owner asks for any of these, confirm he wants to break scope before proceeding.

- Long/short symmetric strategies
- Per-stock vol-scaled or sector-neutral thresholds
- Intraday data, tick data, or market-impact modeling
- Walk-forward parameter optimization
- Live signal generation or paper trading
- Position-level risk constraints beyond equal-weight
- Machine learning models
- Alternative data sources (sentiment, news, options flow)
- Multi-asset extensions (futures, options, crypto)

These are deferred, not forbidden forever. They go in a `v2_ideas.md` file, not into the codebase.

---

## Technical Constraints

### Stack
- **Python 3.11+**
- **Streamlit** for the dashboard
- **pandas, numpy, scipy** for data work
- **pyarrow** for parquet caching
- **yfinance** for OHLC and earnings calendar (`Ticker.get_earnings_dates()`)
- **fja05680/sp500** GitHub data for point-in-time S&P 500 membership

### No WRDS access
The owner has confirmed no WRDS / CRSP / I/B/E/S access. Do not propose data stacks that require it. Tier 1 free stack only.

### Backtest window
Start date: **2015-01-01**. End date: most recent available. Do not silently extend the window.

### Hosting
Runs locally for now, with potential migration to Streamlit Community Cloud. Therefore:
- API keys via environment variables, never hardcoded
- `.env` in `.gitignore`
- Caching must work without write access to arbitrary paths (use a `data/` subdirectory)

---

## Data Layer Rules

The data layer is the longest pole in the tent. Get it right.

1. **Every API call hits local cache first.** Re-running the dashboard does not re-hit yfinance.
2. **Cached files are parquet, not CSV.** Stored under `data/raw/` (raw API responses) and `data/processed/` (cleaned).
3. **No silent data drops.** If a row is filtered, log it. If a ticker is missing, log it. The owner must be able to audit every drop.
4. **Sanity checks run on ingestion.** See `src/diagnostics.py`. Failing sanity checks block downstream work.
5. **Document data limitations in code, not just in the dashboard.** Every module that touches questionable data has a docstring explaining the caveat.

### Known Data Limitations (do not pretend these don't exist)
- yfinance has no delisted-stock prices → survivorship bias partially mitigated, not eliminated
- yfinance earnings dates used for lack of a better free alternative; treat dates as approximate
- fja05680 membership is approximate, not CRSP-grade
- Friday AMC releases get weekend digestion → flag, do not exclude
- Intraday earnings releases are rare → exclude or flag separately, never silently include

---

## File Structure

```
project/
├── CLAUDE.md                 # this file
├── README.md                 # human-facing project overview (owner writes)
├── docs/
│   ├── planning_brief.md     # full strategy spec
│   └── v2_ideas.md           # deferred features
├── data/
│   ├── raw/                  # cached API responses (gitignored)
│   └── processed/            # cleaned parquet (gitignored)
├── src/
│   ├── universe.py           # point-in-time S&P 500 membership
│   ├── earnings.py           # earnings calendar fetch + BMO/AMC tagging
│   ├── prices.py             # OHLC fetch and caching
│   ├── signal.py             # gap calculation, threshold logic
│   ├── backtest.py           # entry/exit, holding-period sweep, P&L
│   ├── metrics.py            # Sharpe, drawdown, hit rate, turnover, decay
│   └── diagnostics.py        # BMO/AMC split, sector distribution, sanity checks
├── tests/                    # unit tests on signal + backtest logic
├── app.py                    # Streamlit entry point
├── requirements.txt
├── .env.example              # template for API keys
└── .gitignore
```

Do not add modules without justification. If a new module is proposed, ask whether an existing one could absorb it.

---

## Code Conventions

- **Type hints on every function signature.** No exceptions.
- **Docstrings explain *why*, not *what*.** The code shows what; the docstring explains the modeling choice or the data caveat.
- **Pure functions where possible.** Side effects (file I/O, API calls) confined to clearly named modules.
- **No magic numbers.** Thresholds, windows, rate limits go in a `config.py` or are passed as arguments.
- **Logging over printing.** Use the `logging` module.
- **No notebooks in the repo.** Exploratory work in notebooks is fine but does not get committed. The dashboard is the deliverable.

---

## Testing

- Unit tests for `signal.py`, `backtest.py`, and `metrics.py` are required.
- Tests use small synthetic fixtures, not live API calls.
- A backtest function must produce identical results given identical inputs (no nondeterminism).

---

## Commands

```bash
# Install
pip install -r requirements.txt

# Run dashboard
streamlit run app.py

# Run tests
pytest tests/

# Lint
ruff check src/ tests/
```

If you add a command, add it here.

---

## Validation Gates

Before showing the owner an equity curve, verify:

1. Reproduces a known PEAD stylized fact (positive average drift on positive-gap names).
2. ~125 earnings events per quarter for S&P 500 universe (sanity check on count).
3. BMO/AMC split is not ~50/50 random — it reflects an actual market pattern.
4. Spot-check 10 random earnings events against public sources for date and timing accuracy.

If any of these fails, fix the data layer before proceeding.

---

## When Uncertain

If you are about to make a modeling choice (lookback window, pooling rule, exclusion criterion) that the planning brief does not explicitly cover, **stop and ask the owner.** Do not pick a default and document it after the fact. The choice is part of the learning, and it is his to make.