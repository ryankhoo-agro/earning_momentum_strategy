"""
Streamlit entry point. Panels defined in planning_brief.md §7.

Build order: wire up panels only after each upstream module passes its tests.
"""

import logging

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from src.backtest import calibrate_zscore_threshold, run_backtest, split_signals
from src.config import DATA_PROCESSED_DIR, DATA_RAW_DIR, TEST_START
from src.metrics import compute_drift_paths, hit_rate, max_drawdown, sharpe_ratio

logger = logging.getLogger(__name__)

SIGNALS_CSV = DATA_PROCESSED_DIR / "signals.csv"
PRICES_DIR = DATA_RAW_DIR / "prices"

SEG_COLS = ["gap", "intraday", "day2", "day3", "day4", "day5"]
DISPLAY_LABELS = ["Gap", "Day 1", "Day 2", "Day 3", "Day 4", "Day 5"]
ALL_LABELS = ["Start"] + DISPLAY_LABELS

st.set_page_config(page_title="Earnings Momentum Dashboard", layout="wide")
st.title("Earnings Momentum Dashboard")


@st.cache_data
def load_signals() -> pd.DataFrame | None:
    if not SIGNALS_CSV.exists():
        return None
    return pd.read_csv(SIGNALS_CSV, parse_dates=["earnings_date", "reaction_date"])


@st.cache_data
def load_prices_for(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Load cached price parquets for the given tickers only."""
    frames = []
    for ticker in tickers:
        path = PRICES_DIR / f"{ticker}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ticker", "Open", "Close"])
    combined = pd.concat(frames)
    idx = pd.to_datetime(combined.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    combined.index = idx
    combined.index.name = "date"
    return combined.sort_index()


@st.cache_data
def load_spy() -> pd.DataFrame | None:
    """Load SPY prices from cache. Returns None if not yet ingested."""
    spy_path = PRICES_DIR / "^GSPC.parquet"
    if not spy_path.exists():
        return None
    df = pd.read_parquet(spy_path)
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    df.index.name = "date"
    return df.sort_index()


# ── Load signals ──────────────────────────────────────────────────────────────
signals = load_signals()

if signals is None:
    st.warning("No signals data found. Run `python ingest.py` first to populate `data/processed/signals.csv`.")
    st.stop()

# ── Train / test split (for calibration and equity curve) ─────────────────────
train_signals, test_signals = split_signals(signals, TEST_START)

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Threshold")
    threshold_mode = st.radio("Mode", ["Flat %", "Z-score"], horizontal=True)

    if threshold_mode == "Flat %":
        mean_gap_pct = float(signals["gap"].mean() * 100)
        gap_threshold_pct = st.slider(
            "Min gap (%)",
            min_value=0.0,
            max_value=20.0,
            value=round(mean_gap_pct, 1),
            step=0.1,
        )
        gap_cutoff = gap_threshold_pct / 100.0
        calib: dict | None = None
    else:
        z_threshold = st.slider("Z-score", min_value=0.0, max_value=3.0, value=1.5, step=0.1)
        calib = calibrate_zscore_threshold(train_signals, z_threshold)
        gap_cutoff = calib["cutoff"]
        st.caption(
            f"Train gap (2015–{TEST_START[:4]}): "
            f"μ = {calib['mean']*100:.2f}%  σ = {calib['std']*100:.2f}%"
        )
        train_pass_pct = float((train_signals["gap"] > gap_cutoff).mean()) * 100
        st.caption(f"Cutoff at z={z_threshold:.1f}: **{gap_cutoff*100:.2f}%** ({train_pass_pct:.1f}% of train events pass)")

    st.header("Filters")
    session_filter = st.multiselect(
        "Session",
        options=["bmo", "amc"],
        default=["bmo", "amc"],
        help="BMO = before market open. AMC = after market close.",
    )

    st.header("Backtest (holdout)")
    holding_period = st.slider("Holding period (days)", min_value=1, max_value=5, value=1)
    entry_mode = st.radio("Entry", ["Open", "Close"], horizontal=True,
                          help="Open = buy at open_t (gap already happened). Close = buy at close of reaction day.")

    st.markdown("**Costs** (round-trip bps)")
    use_costs = st.checkbox("Transaction costs", value=True)
    cost_bps = st.slider("Cost (bps)", 0, 30, 5, disabled=not use_costs) if use_costs else 0.0

    use_slippage = st.checkbox("Slippage", value=False)
    slippage_bps = st.slider("Slippage (bps)", 0, 20, 3, disabled=not use_slippage) if use_slippage else 0.0

# ── Filter signals ─────────────────────────────────────────────────────────────
# filter_all: for PEAD analysis across all periods
filter_all = signals[
    (signals["gap"] > gap_cutoff) & (signals["session"].isin(session_filter))
].copy()

# filter_test: for equity curve (holdout only)
filter_test = test_signals[
    (test_signals["gap"] > gap_cutoff) & (test_signals["session"].isin(session_filter))
].copy()

with st.sidebar:
    st.divider()
    st.metric("All-period events (filtered)", f"{len(filter_all):,}")
    st.metric(f"Holdout events ({TEST_START[:4]}+)", f"{len(filter_test):,}")

if filter_all.empty:
    st.warning("No events pass the current filter. Try lowering the gap threshold.")
    st.stop()

# ── Load prices ────────────────────────────────────────────────────────────────
# Load for all tickers in filter_all; holdout tickers are a subset
tickers_needed = tuple(sorted(filter_all["ticker"].unique()))
prices = load_prices_for(tickers_needed)

if prices.empty:
    st.warning("No price data found. Run `python ingest.py` first.")
    st.stop()

# ── PEAD drift paths (all periods, for Summary / All Events tabs) ─────────────
with st.spinner("Computing drift paths..."):
    drift = compute_drift_paths(filter_all, prices, max_hold=5)

if drift.empty:
    st.warning("Could not compute drift paths — price data may be incomplete.")
    st.stop()

caption_all = (
    f"N = {len(drift):,} events | gap > {gap_cutoff*100:.1f}% | "
    f"sessions: {', '.join(session_filter)} | 2015–present"
)

# Per-event cumulative return paths
cum_all = (1 + drift[SEG_COLS]).cumprod(axis=1) - 1
cum_all.columns = DISPLAY_LABELS
cum_all.insert(0, "Start", 0.0)
cum_all["ticker"] = drift["ticker"].values
cum_all["session"] = drift["session"].values
cum_all["date"] = drift["reaction_date"].dt.strftime("%Y-%m-%d").values
cum_all["event_id"] = range(len(cum_all))

mean_segs = drift[SEG_COLS].mean() * 100
mean_cum = cum_all[ALL_LABELS].mean() * 100

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_summary, tab_events, tab_equity = st.tabs(["Summary", "All Events", "Equity Curve"])

# ── Tab 1: Summary ────────────────────────────────────────────────────────────
with tab_summary:
    st.caption(caption_all)

    st.subheader("Average Period Returns")
    period_data = pd.DataFrame({
        "Segment": DISPLAY_LABELS,
        "Mean Return (%)": mean_segs.values,
    })
    bar = (
        alt.Chart(period_data)
        .mark_bar()
        .encode(
            x=alt.X("Segment:N", sort=DISPLAY_LABELS, title=None),
            y=alt.Y("Mean Return (%):Q"),
            color=alt.condition(
                alt.datum["Mean Return (%)"] > 0,
                alt.value("steelblue"),
                alt.value("salmon"),
            ),
            tooltip=["Segment", alt.Tooltip("Mean Return (%):Q", format=".3f")],
        )
    )
    st.altair_chart(bar, use_container_width=True)

    st.subheader("Average Cumulative Return Path")
    cum_avg_data = pd.DataFrame({
        "Segment": ALL_LABELS,
        "Cumulative Return (%)": mean_cum.values,
    })
    line = (
        alt.Chart(cum_avg_data)
        .mark_line(point=True)
        .encode(
            x=alt.X("Segment:N", sort=ALL_LABELS, title=None),
            y=alt.Y("Cumulative Return (%):Q"),
            tooltip=["Segment", alt.Tooltip("Cumulative Return (%):Q", format=".3f")],
        )
    )
    st.altair_chart(line, use_container_width=True)

# ── Tab 2: All Events ─────────────────────────────────────────────────────────
with tab_events:
    st.caption(caption_all)
    st.subheader("Individual Event Cumulative Return Paths")

    spaghetti = cum_all.melt(
        id_vars=["event_id", "ticker", "session", "date"],
        value_vars=ALL_LABELS,
        var_name="Segment",
        value_name="Cumulative Return (%)",
    )
    spaghetti["Cumulative Return (%)"] *= 100

    spaghetti_chart = (
        alt.Chart(spaghetti)
        .mark_line(opacity=0.15, strokeWidth=1)
        .encode(
            x=alt.X("Segment:N", sort=ALL_LABELS, title=None),
            y=alt.Y("Cumulative Return (%):Q"),
            color=alt.Color(
                "session:N",
                scale=alt.Scale(domain=["bmo", "amc"], range=["steelblue", "salmon"]),
                legend=alt.Legend(title="Session"),
            ),
            detail="event_id:N",
            tooltip=["ticker", "date", "session", alt.Tooltip("Cumulative Return (%):Q", format=".2f")],
        )
    )
    st.altair_chart(spaghetti_chart, use_container_width=True)

# ── Tab 3: Equity Curve ───────────────────────────────────────────────────────
with tab_equity:
    train_end = str(int(TEST_START[:4]) - 1)
    st.caption(
        f"Out-of-sample holdout: {TEST_START[:4]}–present | "
        f"Threshold calibrated on {SIGNALS_CSV.parent.parent.parent.name if False else '2015'}–{train_end} | "
        f"Entry: {entry_mode} | Hold: {holding_period}d | "
        f"Costs: {cost_bps:.0f}bps + {slippage_bps:.0f}bps slippage"
    )

    if filter_test.empty:
        st.warning(
            f"No holdout events ({TEST_START[:4]}+) pass the current filter. "
            "Try lowering the threshold or changing the session filter."
        )
        st.stop()

    with st.spinner("Running backtest..."):
        equity_curve, trade_log = run_backtest(
            filter_test,
            prices,
            holding_period=holding_period,
            entry_mode=entry_mode.lower(),
            cost_bps=float(cost_bps),
            slippage_bps=float(slippage_bps),
        )

    if equity_curve.empty or trade_log.empty:
        st.warning("Backtest produced no trades. Price data may be incomplete for holdout tickers.")
        st.stop()

    # ── Metrics row ───────────────────────────────────────────────────────────
    daily_rets = equity_curve.pct_change().dropna()
    sharpe = sharpe_ratio(daily_rets)
    mdd = max_drawdown(equity_curve)
    hr = hit_rate(trade_log["net_return"])
    avg_net = float(trade_log["net_return"].mean()) * 100
    total_return = float(equity_curve.iloc[-1] - 1.0) * 100

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Return", f"{total_return:+.1f}%")
    col2.metric("Sharpe (ann.)", f"{sharpe:.2f}" if not np.isnan(sharpe) else "—")
    col3.metric("Max Drawdown", f"{mdd*100:.1f}%" if not np.isnan(mdd) else "—")
    col4.metric("Hit Rate", f"{hr*100:.1f}%" if not np.isnan(hr) else "—")
    col5.metric("N Trades", f"{len(trade_log):,}")

    # ── Equity curve chart ────────────────────────────────────────────────────
    st.subheader("Portfolio vs SPY")

    chart_df = equity_curve.rename("Strategy").to_frame()

    spy_data = load_spy()
    if spy_data is not None and "Close" in spy_data.columns:
        spy_aligned = spy_data["Close"].reindex(equity_curve.index, method="ffill").dropna()
        if not spy_aligned.empty:
            chart_df["SPY"] = spy_aligned / spy_aligned.iloc[0]
    else:
        st.caption("SPY benchmark not found in cache. Add 'SPY' to your ingest ticker list to show it.")

    chart_long = (
        chart_df.reset_index()
        .rename(columns={"date": "Date"})
        .melt(id_vars="Date", var_name="Series", value_name="Value")
    )

    palette = {"Strategy": "steelblue", "SPY": "#f28e2b"}
    domain = list(chart_df.columns)

    equity_line = (
        alt.Chart(chart_long)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y(
                "Value:Q",
                title="Portfolio value (1.0 = start)",
                axis=alt.Axis(format=".2f"),
            ),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=domain,
                    range=[palette.get(s, "gray") for s in domain],
                ),
                legend=alt.Legend(title=None),
            ),
            tooltip=["Date:T", "Series:N", alt.Tooltip("Value:Q", format=".3f")],
        )
    )
    st.altair_chart(equity_line, use_container_width=True)

    # ── Trade return distribution ──────────────────────────────────────────────
    st.subheader("Trade Return Distribution")
    col_a, col_b = st.columns([2, 1])

    with col_a:
        hist_data = pd.DataFrame({"Net Return (%)": trade_log["net_return"] * 100})
        hist = (
            alt.Chart(hist_data)
            .mark_bar()
            .encode(
                x=alt.X("Net Return (%):Q", bin=alt.Bin(maxbins=50), title="Net Return (%)"),
                y=alt.Y("count():Q", title="Trades"),
                color=alt.condition(
                    alt.datum["Net Return (%)"] > 0,
                    alt.value("steelblue"),
                    alt.value("salmon"),
                ),
                tooltip=[
                    alt.Tooltip("Net Return (%):Q", bin=True, format=".2f"),
                    alt.Tooltip("count():Q", title="Count"),
                ],
            )
        )
        st.altair_chart(hist, use_container_width=True)

    with col_b:
        st.markdown("**Trade stats**")
        st.markdown(f"Avg net return: **{avg_net:+.2f}%**")
        st.markdown(f"Avg gross return: **{trade_log['gross_return'].mean()*100:+.2f}%**")
        st.markdown(f"Winners: **{(trade_log['net_return'] > 0).sum():,}**")
        st.markdown(f"Losers: **{(trade_log['net_return'] <= 0).sum():,}**")
        st.markdown(
            f"Avg winner: **{trade_log.loc[trade_log['net_return']>0,'net_return'].mean()*100:+.2f}%**"
            if (trade_log["net_return"] > 0).any() else "Avg winner: —"
        )
        st.markdown(
            f"Avg loser: **{trade_log.loc[trade_log['net_return']<=0,'net_return'].mean()*100:+.2f}%**"
            if (trade_log["net_return"] <= 0).any() else "Avg loser: —"
        )

    # ── Methodology note ──────────────────────────────────────────────────────
    with st.expander("Methodology & limitations"):
        st.markdown(f"""
**Portfolio construction:** Fixed-notional, calendar-time. Each triggered event
gets one unit of notional; the daily portfolio return is the equal-weighted
average of all currently active positions. Days with no positions earn 0%.

**Entry:** {'Open of reaction day (open_t). The overnight gap has already occurred — this is the first realistically tradeable price.' if entry_mode == 'Open' else 'Close of reaction day. The gap and intraday move are forfeited; only subsequent drift is captured.'}

**Costs:** Round-trip {cost_bps:.0f} bps commission + {slippage_bps:.0f} bps slippage
(bid-ask / execution quality). Market impact is not modelled.

**Threshold calibration:** {'Flat percentage applied uniformly.' if calib is None else f'Z-score cutoff calibrated on 2015–{train_end} training data only (μ={calib["mean"]*100:.2f}%, σ={calib["std"]*100:.2f}%, cutoff={calib["cutoff"]*100:.2f}%). The same cutoff is applied to the holdout without re-fitting — no look-ahead.'}

**Sharpe ratio:** Annualised, no risk-free rate subtracted (document this when presenting).

**Survivorship bias:** Partially mitigated by point-in-time S&P 500 membership
(fja05680/sp500), but yfinance has no prices for stocks that were subsequently
delisted — some positive-gap events from removed names are missing.
        """)
