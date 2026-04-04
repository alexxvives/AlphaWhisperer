#!/usr/bin/env python3
"""
InvestorAI Backtest Module

Replays historical signals through the scoring engine and measures
forward returns at 7/30/60/90 days using yfinance data.

Usage:
    python backtest.py                  # Full backtest
    python backtest.py --tier 1         # Only Tier 1 signals
    python backtest.py --min-score 8    # Only signals scoring 8+
"""

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Reuse project DB and scoring functions
sys.path.insert(0, str(Path(__file__).parent))
from insider_alerts import (
    DB_FILE,
    InsiderAlert,
    calculate_composite_signal_score,
    calculate_insider_alpha_score,
    get_company_context,
    init_database,
    LOOKBACK_DAYS,
    MIN_LARGE_BUY,
    MIN_CEO_CFO_BUY,
    MIN_CLUSTER_BUY_VALUE,
    MIN_CLUSTER_INSIDERS,
    MIN_CORP_PURCHASE,
    CLUSTER_DAYS,
    ELITE_CONGRESSIONAL_TRADERS,
)

# ──────────────────────────────────────────────────────────────────
# Signal detection (simplified re-detection from historical DB data)
# ──────────────────────────────────────────────────────────────────

def load_all_buy_trades() -> pd.DataFrame:
    """Load all buy trades from the database."""
    conn = sqlite3.connect(str(DB_FILE))
    df = pd.read_sql_query(
        "SELECT * FROM openinsider_trades WHERE trade_type = 'Buy' AND value > 0 ORDER BY trade_date",
        conn,
    )
    conn.close()
    if df.empty:
        return df
    # Normalize column names to match what detection functions expect
    df.rename(columns={
        'insider_name': 'Insider Name',
        'insider_title': 'Title',
        'trade_type': 'Trade Type',
        'trade_date': 'Trade Date',
        'value': 'Value ($)',
        'company_name': 'Company Name',
        'delta_own': 'Delta Own',
    }, inplace=True)
    df['Trade Date'] = pd.to_datetime(df['Trade Date'], errors='coerce')
    return df


def detect_historical_signals(df: pd.DataFrame) -> list:
    """
    Re-detect signals from historical data using current thresholds.
    Returns list of dicts with signal metadata (not full InsiderAlert objects).
    """
    signals = []
    if df.empty:
        return signals

    # Group by ticker
    for ticker, group in df.groupby('ticker'):
        group = group.sort_values('Trade Date')

        # ── Cluster Buying ──
        for _, anchor in group.iterrows():
            anchor_date = anchor['Trade Date']
            if pd.isna(anchor_date):
                continue
            window = group[
                (group['Trade Date'] >= anchor_date - timedelta(days=CLUSTER_DAYS))
                & (group['Trade Date'] <= anchor_date + timedelta(days=CLUSTER_DAYS))
            ]
            unique_insiders = window['Insider Name'].nunique()
            total_value = window['Value ($)'].sum()
            if unique_insiders >= MIN_CLUSTER_INSIDERS and total_value >= MIN_CLUSTER_BUY_VALUE:
                signals.append({
                    'signal_type': 'Cluster Buying',
                    'ticker': ticker,
                    'company_name': group['Company Name'].iloc[0] if 'Company Name' in group.columns else ticker,
                    'trade_date': anchor_date,
                    'total_value': total_value,
                    'num_insiders': unique_insiders,
                    'trades': window,
                })
                break  # One cluster signal per ticker

        # ── C-Suite Buy ──
        csuite_pattern = r'(?i)(CEO|CFO|COO|CHIEF|PRESIDENT)'
        if 'Title' in group.columns:
            csuite = group[
                group['Title'].str.contains(csuite_pattern, na=False, regex=True)
                & (group['Value ($)'] >= MIN_CEO_CFO_BUY)
            ]
            if not csuite.empty:
                best = csuite.loc[csuite['Value ($)'].idxmax()]
                signals.append({
                    'signal_type': 'C-Suite Buy',
                    'ticker': ticker,
                    'company_name': group['Company Name'].iloc[0] if 'Company Name' in group.columns else ticker,
                    'trade_date': best['Trade Date'],
                    'total_value': best['Value ($)'],
                    'num_insiders': 1,
                    'trades': csuite.head(1),
                })

        # ── Large Single Buy ──
        large = group[group['Value ($)'] >= MIN_LARGE_BUY]
        if not large.empty:
            best = large.loc[large['Value ($)'].idxmax()]
            # Skip if same ticker already has a Cluster or C-Suite signal
            existing_types = [s['signal_type'] for s in signals if s['ticker'] == ticker]
            if 'Cluster Buying' not in existing_types and 'C-Suite Buy' not in existing_types:
                signals.append({
                    'signal_type': 'Large Single Buy',
                    'ticker': ticker,
                    'company_name': group['Company Name'].iloc[0] if 'Company Name' in group.columns else ticker,
                    'trade_date': best['Trade Date'],
                    'total_value': best['Value ($)'],
                    'num_insiders': 1,
                    'trades': large.head(1),
                })

        # ── Corporation Purchase ──
        corp_pattern = r'(?i)(Corp|LLC|Holdings|Fund|Capital|Ventures|Trust|Management|Investments|Technologies)'
        corp = group[
            group['Insider Name'].str.contains(corp_pattern, na=False, regex=True)
            & (group['Value ($)'] >= MIN_CORP_PURCHASE)
        ]
        if not corp.empty:
            existing_types = [s['signal_type'] for s in signals if s['ticker'] == ticker]
            if not any(t in existing_types for t in ['Cluster Buying', 'C-Suite Buy', 'Large Single Buy']):
                best = corp.loc[corp['Value ($)'].idxmax()]
                signals.append({
                    'signal_type': 'Corporation Purchase',
                    'ticker': ticker,
                    'company_name': group['Company Name'].iloc[0] if 'Company Name' in group.columns else ticker,
                    'trade_date': best['Trade Date'],
                    'total_value': best['Value ($)'],
                    'num_insiders': 1,
                    'trades': corp.head(1),
                })

    # Apply mutual exclusion — keep highest priority per ticker
    priority = {
        'Cluster Buying': 1, 'C-Suite Buy': 2, 'Corporation Purchase': 3, 'Large Single Buy': 4,
    }
    best_per_ticker = {}
    for s in signals:
        t = s['ticker']
        p = priority.get(s['signal_type'], 99)
        if t not in best_per_ticker or p < priority.get(best_per_ticker[t]['signal_type'], 99):
            best_per_ticker[t] = s
    return list(best_per_ticker.values())


# ──────────────────────────────────────────────────────────────────
# Score each historical signal using the production scoring engine
# ──────────────────────────────────────────────────────────────────

def score_signals(signals: list, fetch_context: bool = False) -> list:
    """Score each signal using calculate_composite_signal_score.
    
    Passes the trade date as score_date so time decay evaluates
    the signal as-of its detection day (decay = 0 on day 0).
    """
    scored = []
    for s in signals:
        # Build a lightweight InsiderAlert to pass to the scorer
        alert = InsiderAlert(
            signal_type=s['signal_type'],
            ticker=s['ticker'],
            company_name=s.get('company_name', s['ticker']),
            trades=s['trades'],
            details={
                'total_value': s['total_value'],
                'num_insiders': s.get('num_insiders', 1),
            },
        )
        # Override alert_id to avoid DB conflicts
        alert.alert_id = f"backtest_{s['ticker']}_{s['signal_type']}_{s['trade_date']}"

        context = None
        if fetch_context:
            try:
                context = get_company_context(s['ticker'])
            except Exception:
                pass

        # Pass trade_date as score_date so time decay = 0 on signal day
        trade_dt = s['trade_date']
        if hasattr(trade_dt, 'to_pydatetime'):
            trade_dt = trade_dt.to_pydatetime()
        score = calculate_composite_signal_score(alert, context, score_date=trade_dt)
        s['composite_score'] = score
        s['context'] = context
        scored.append(s)
    return scored


# ──────────────────────────────────────────────────────────────────
# Fetch forward returns from yfinance
# ──────────────────────────────────────────────────────────────────

def get_forward_returns(ticker: str, signal_date, horizons=(7, 30, 60, 90)):
    """
    Fetch forward price returns for a ticker from a signal date.
    Returns dict of {horizon_days: return_pct} or None on failure.
    """
    import yfinance as yf

    if isinstance(signal_date, str):
        signal_date = pd.to_datetime(signal_date)
    if hasattr(signal_date, 'to_pydatetime'):
        signal_date = signal_date.to_pydatetime()

    start = signal_date - timedelta(days=5)  # Buffer for weekends
    end = signal_date + timedelta(days=max(horizons) + 10)

    try:
        hist = yf.download(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), progress=False)
        if hist.empty:
            return None
        
        # Flatten multi-level columns if present
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)

        # Get the close price on or after signal date
        hist.index = pd.to_datetime(hist.index)
        after_signal = hist[hist.index >= pd.Timestamp(signal_date)]
        if after_signal.empty:
            return None

        entry_price = float(after_signal['Close'].iloc[0])
        entry_date = after_signal.index[0]

        returns = {}
        for h in horizons:
            target_date = entry_date + timedelta(days=h)
            future = hist[hist.index >= target_date]
            if not future.empty:
                exit_price = float(future['Close'].iloc[0])
                returns[h] = round(((exit_price - entry_price) / entry_price) * 100, 2)
            else:
                returns[h] = None  # Not enough data yet

        return returns
    except Exception as e:
        print(f"  [WARN] Could not fetch returns for {ticker}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────
# Main backtest runner
# ──────────────────────────────────────────────────────────────────

def run_backtest(min_score: float = 0, tier: int = 0, fetch_context: bool = True):
    """
    Full backtest pipeline:
    1. Load historical buy trades from DB
    2. Re-detect signals with current thresholds
    3. Score signals with current composite scoring
    4. Fetch forward returns from yfinance
    5. Analyze results by signal type & score tier
    """
    print("=" * 70)
    print("INVESTORAI BACKTEST")
    print("=" * 70)

    # 1. Load data
    print("\n[1/5] Loading historical buy trades from database...")
    df = load_all_buy_trades()
    print(f"  Loaded {len(df)} buy trades across {df['ticker'].nunique()} tickers")
    print(f"  Date range: {df['Trade Date'].min()} to {df['Trade Date'].max()}")

    # 2. Detect signals
    print("\n[2/5] Detecting signals with current thresholds...")
    signals = detect_historical_signals(df)
    print(f"  Detected {len(signals)} signals (after mutual exclusion)")

    type_counts = defaultdict(int)
    for s in signals:
        type_counts[s['signal_type']] += 1
    for st, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {st}: {cnt}")

    # 3. Score signals
    print(f"\n[3/5] Scoring signals (fetch_context={fetch_context})...")
    signals = score_signals(signals, fetch_context=fetch_context)

    # Tier filtering
    tier1_threshold = 7.0
    if tier == 1:
        signals = [s for s in signals if s['composite_score'] >= tier1_threshold]
        print(f"  Tier 1 filter: {len(signals)} signals with score >= {tier1_threshold}")
    elif min_score > 0:
        signals = [s for s in signals if s['composite_score'] >= min_score]
        print(f"  Score filter: {len(signals)} signals with score >= {min_score}")

    if not signals:
        print("\n  No signals to backtest after filtering.")
        return

    # Sort by score descending
    signals.sort(key=lambda x: x['composite_score'], reverse=True)
    print(f"  Score range: {signals[-1]['composite_score']} to {signals[0]['composite_score']}")

    # 4. Fetch forward returns
    horizons = (7, 30, 60, 90)
    print(f"\n[4/5] Fetching forward returns for {len(signals)} signals...")
    print(f"  Horizons: {horizons} days")

    results = []
    unique_tickers = list({s['ticker'] for s in signals})
    ticker_returns_cache = {}

    for i, s in enumerate(signals):
        ticker = s['ticker']
        trade_date = s['trade_date']
        cache_key = f"{ticker}_{trade_date}"

        if cache_key not in ticker_returns_cache:
            returns = get_forward_returns(ticker, trade_date, horizons)
            ticker_returns_cache[cache_key] = returns
        else:
            returns = ticker_returns_cache[cache_key]

        s['forward_returns'] = returns

        status = "OK" if returns else "NO DATA"
        print(f"  [{i+1}/{len(signals)}] {ticker} ({s['signal_type']}, score={s['composite_score']}): {status}", end="")
        if returns:
            print(f"  7d={returns.get(7, '?')}%  30d={returns.get(30, '?')}%  60d={returns.get(60, '?')}%  90d={returns.get(90, '?')}%")
        else:
            print()

        results.append(s)

    # 5. Analyze results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    valid = [r for r in results if r['forward_returns'] is not None]
    if not valid:
        print("No valid return data available. Trades may be too recent for forward returns.")
        return

    # ── Overall stats ──
    print(f"\nTotal signals analyzed: {len(valid)} (out of {len(results)})")

    for h in horizons:
        returns_at_h = [r['forward_returns'][h] for r in valid if r['forward_returns'].get(h) is not None]
        if not returns_at_h:
            continue

        positive = sum(1 for r in returns_at_h if r > 0)
        avg_ret = statistics.mean(returns_at_h)
        med_ret = statistics.median(returns_at_h)
        win_rate = (positive / len(returns_at_h)) * 100
        best = max(returns_at_h)
        worst = min(returns_at_h)

        print(f"\n  {h}-Day Forward Returns (n={len(returns_at_h)}):")
        print(f"    Win Rate:  {win_rate:.1f}%")
        print(f"    Avg Return: {avg_ret:+.2f}%")
        print(f"    Median:     {med_ret:+.2f}%")
        print(f"    Best:       {best:+.2f}%")
        print(f"    Worst:      {worst:+.2f}%")

    # ── By signal type ──
    print("\n" + "-" * 70)
    print("RESULTS BY SIGNAL TYPE")
    print("-" * 70)

    by_type = defaultdict(list)
    for r in valid:
        by_type[r['signal_type']].append(r)

    for signal_type in ['Cluster Buying', 'C-Suite Buy', 'Corporation Purchase', 'Large Single Buy']:
        group = by_type.get(signal_type, [])
        if not group:
            continue

        print(f"\n  {signal_type} (n={len(group)}):")
        for h in horizons:
            rets = [r['forward_returns'][h] for r in group if r['forward_returns'].get(h) is not None]
            if not rets:
                continue
            positive = sum(1 for r in rets if r > 0)
            avg = statistics.mean(rets)
            wr = (positive / len(rets)) * 100
            print(f"    {h}d: WR={wr:.0f}%  Avg={avg:+.1f}%  n={len(rets)}")

    # ── By score tier ──
    print("\n" + "-" * 70)
    print("RESULTS BY SCORE TIER")
    print("-" * 70)

    tiers = [
        ("Tier 1 (score >= 7)", lambda s: s['composite_score'] >= 7),
        ("Tier 2 (score 4-7)", lambda s: 4 <= s['composite_score'] < 7),
        ("Tier 3 (score < 4)", lambda s: s['composite_score'] < 4),
    ]

    for tier_name, tier_filter in tiers:
        group = [r for r in valid if tier_filter(r)]
        if not group:
            continue

        print(f"\n  {tier_name} (n={len(group)}):")
        scores = [g['composite_score'] for g in group]
        print(f"    Score range: {min(scores):.1f} - {max(scores):.1f}")

        for h in horizons:
            rets = [r['forward_returns'][h] for r in group if r['forward_returns'].get(h) is not None]
            if not rets:
                continue
            positive = sum(1 for r in rets if r > 0)
            avg = statistics.mean(rets)
            wr = (positive / len(rets)) * 100
            print(f"    {h}d: WR={wr:.0f}%  Avg={avg:+.1f}%  n={len(rets)}")

    # ── Top 10 signals ──
    print("\n" + "-" * 70)
    print("TOP 10 HIGHEST-SCORING SIGNALS")
    print("-" * 70)
    for i, r in enumerate(valid[:10], 1):
        rets = r['forward_returns']
        r7 = f"{rets.get(7, '?'):+.1f}%" if rets.get(7) is not None else "N/A"
        r30 = f"{rets.get(30, '?'):+.1f}%" if rets.get(30) is not None else "N/A"
        r60 = f"{rets.get(60, '?'):+.1f}%" if rets.get(60) is not None else "N/A"
        r90 = f"{rets.get(90, '?'):+.1f}%" if rets.get(90) is not None else "N/A"
        print(f"  {i:2d}. {r['ticker']:6s} | {r['signal_type']:20s} | Score: {r['composite_score']:5.1f} | "
              f"7d={r7:>7s} 30d={r30:>7s} 60d={r60:>7s} 90d={r90:>7s}")

    # ── Bottom 10 signals ──
    print("\n" + "-" * 70)
    print("BOTTOM 10 LOWEST-SCORING SIGNALS")
    print("-" * 70)
    for i, r in enumerate(valid[-10:], len(valid) - 9):
        rets = r['forward_returns']
        r7 = f"{rets.get(7, '?'):+.1f}%" if rets.get(7) is not None else "N/A"
        r30 = f"{rets.get(30, '?'):+.1f}%" if rets.get(30) is not None else "N/A"
        print(f"  {i:2d}. {r['ticker']:6s} | {r['signal_type']:20s} | Score: {r['composite_score']:5.1f} | "
              f"7d={r7:>7s} 30d={r30:>7s}")

    # ── Summary verdict ──
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    tier1 = [r for r in valid if r['composite_score'] >= 7]
    tier2 = [r for r in valid if r['composite_score'] < 7]

    if tier1:
        t1_30d = [r['forward_returns'][30] for r in tier1 if r['forward_returns'].get(30) is not None]
        if t1_30d:
            t1_wr = sum(1 for r in t1_30d if r > 0) / len(t1_30d) * 100
            t1_avg = statistics.mean(t1_30d)
            print(f"\n  Tier 1 (alertable, score >= 7): {len(tier1)} signals")
            print(f"    30-day: {t1_wr:.0f}% win rate, {t1_avg:+.1f}% avg return")

    if tier2:
        t2_30d = [r['forward_returns'][30] for r in tier2 if r['forward_returns'].get(30) is not None]
        if t2_30d:
            t2_wr = sum(1 for r in t2_30d if r > 0) / len(t2_30d) * 100
            t2_avg = statistics.mean(t2_30d)
            print(f"\n  Tier 2 (watchlist, score < 7): {len(tier2)} signals")
            print(f"    30-day: {t2_wr:.0f}% win rate, {t2_avg:+.1f}% avg return")

    if tier1 and tier2:
        t1_30d_vals = [r['forward_returns'][30] for r in tier1 if r['forward_returns'].get(30) is not None]
        t2_30d_vals = [r['forward_returns'][30] for r in tier2 if r['forward_returns'].get(30) is not None]
        if t1_30d_vals and t2_30d_vals:
            edge = statistics.mean(t1_30d_vals) - statistics.mean(t2_30d_vals)
            print(f"\n  Tier 1 vs Tier 2 edge: {edge:+.1f}% avg return difference at 30 days")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InvestorAI Backtest")
    parser.add_argument("--tier", type=int, default=0, help="Filter to tier (1=alertable only)")
    parser.add_argument("--min-score", type=float, default=0, help="Minimum composite score")
    parser.add_argument("--no-context", action="store_true", help="Skip yfinance context (faster but less accurate scoring)")
    args = parser.parse_args()

    run_backtest(
        min_score=args.min_score,
        tier=args.tier,
        fetch_context=not args.no_context,
    )
