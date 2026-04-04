#!/usr/bin/env python3
"""
Congressional Trading Backtest

Tests forward returns of congressional stock buys, comparing:
- Elite politicians vs. all politicians
- Returns from TRADE date (theoretical edge) vs. PUBLISHED date (realistic entry)
- Performance by individual politician
- Optimal holding period analysis (exit strategy)

Usage:
    python backtest_congressional.py                # Full backtest
    python backtest_congressional.py --elite-only   # Only elite 15 politicians
"""

import argparse
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_FILE = Path(__file__).parent / "data" / "alphaWhisperer.db"

ELITE_POLITICIANS = [
    'Nancy Pelosi', 'Josh Gottheimer', 'Ro Khanna', 'Michael McCaul',
    'Tommy Tuberville', 'Markwayne Mullin', 'Dan Crenshaw', 'Brian Higgins',
    'Richard Blumenthal', 'Debbie Wasserman Schultz', 'Tom Kean',
    'Gil Cisneros', 'Cleo Fields', 'Marjorie Taylor Greene', 'Lisa McClain',
]


def load_congressional_buys(elite_only=False):
    """Load congressional buy trades from database."""
    conn = sqlite3.connect(str(DB_FILE))
    df = pd.read_sql_query(
        "SELECT * FROM congressional_trades WHERE LOWER(trade_type) = 'buy' ORDER BY traded_date",
        conn,
    )
    conn.close()
    if df.empty:
        return df

    df['traded_date'] = pd.to_datetime(df['traded_date'], errors='coerce')
    df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')

    if elite_only:
        mask = pd.Series(False, index=df.index)
        for name in ELITE_POLITICIANS:
            mask |= df['politician_name'].str.contains(name, case=False, na=False)
        df = df[mask]

    return df


def parse_size_range(size_str):
    """Parse congressional size range string to midpoint dollar value."""
    if not size_str or pd.isna(size_str):
        return 0
    s = size_str.replace('$', '').replace(',', '').strip()
    if '-' in s:
        parts = s.split('-')
        try:
            lo = float(parts[0].strip())
            hi = float(parts[1].strip())
            return (lo + hi) / 2
        except (ValueError, IndexError):
            return 0
    return 0


def get_forward_returns(ticker, signal_date, horizons=(7, 14, 30, 60, 90)):
    """Fetch forward price returns."""
    if isinstance(signal_date, str):
        signal_date = pd.to_datetime(signal_date)
    if hasattr(signal_date, 'to_pydatetime'):
        signal_date = signal_date.to_pydatetime()
    if signal_date is None or pd.isna(signal_date):
        return None

    start = signal_date - timedelta(days=5)
    end = signal_date + timedelta(days=max(horizons) + 10)

    try:
        hist = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                           end=end.strftime('%Y-%m-%d'), progress=False)
        if hist.empty:
            return None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        hist.index = pd.to_datetime(hist.index)

        after = hist[hist.index >= pd.Timestamp(signal_date)]
        if after.empty:
            return None

        entry_price = float(after['Close'].iloc[0])
        returns = {}
        for h in horizons:
            target = after.index[0] + timedelta(days=h)
            future = hist[hist.index >= target]
            if not future.empty:
                exit_price = float(future['Close'].iloc[0])
                returns[h] = round(((exit_price - entry_price) / entry_price) * 100, 2)
            else:
                returns[h] = None
        return returns
    except Exception:
        return None


def deduplicate_signals(df):
    """
    Deduplicate: for each (politician, ticker), keep only the first buy
    in any 30-day window. This avoids counting repeat buys of the same
    position as separate signals.
    """
    df = df.sort_values('traded_date')
    keep = []
    seen = {}  # (politician, ticker) -> last_date

    for _, row in df.iterrows():
        key = (row['politician_name'], row['ticker'])
        td = row['traded_date']
        if pd.isna(td):
            continue
        if key in seen and (td - seen[key]).days < 30:
            continue
        seen[key] = td
        keep.append(row)

    return pd.DataFrame(keep)


def print_returns_table(results, horizons, label=""):
    """Print a formatted returns table."""
    if label:
        print(f"\n  {label} (n={len(results)}):")

    for h in horizons:
        rets = [r[h] for r in results if r.get(h) is not None]
        if not rets:
            continue
        pos = sum(1 for r in rets if r > 0)
        wr = pos / len(rets) * 100
        avg = statistics.mean(rets)
        med = statistics.median(rets)
        print(f"    {h:2d}d: WR={wr:5.1f}%  Avg={avg:+7.1f}%  Med={med:+7.1f}%  n={len(rets)}")


def run_backtest(elite_only=False, max_signals=500):
    horizons = (7, 14, 30, 60, 90)

    print("=" * 70)
    print("CONGRESSIONAL TRADING BACKTEST")
    print("=" * 70)

    # 1. Load data
    print("\n[1/4] Loading congressional buys...")
    df = load_congressional_buys(elite_only=elite_only)
    print(f"  Raw buys: {len(df)}")
    print(f"  Unique politicians: {df['politician_name'].nunique()}")
    print(f"  Unique tickers: {df['ticker'].nunique()}")
    print(f"  Date range: {df['traded_date'].min()} to {df['traded_date'].max()}")

    # 2. Deduplicate
    print("\n[2/4] Deduplicating (30-day window per politician+ticker)...")
    df = deduplicate_signals(df)
    print(f"  After dedup: {len(df)} signals")

    # Cap for speed
    if len(df) > max_signals:
        print(f"  Sampling {max_signals} signals for speed (use --max to increase)")
        df = df.sample(max_signals, random_state=42)

    # 3. Fetch returns
    print(f"\n[3/4] Fetching forward returns for {len(df)} signals...")
    print(f"  Testing BOTH trade_date (theoretical) and published_date (realistic)...")

    results_trade_date = []  # returns from when trade happened  
    results_pub_date = []    # returns from when we'd actually know about it
    by_politician = defaultdict(list)
    ticker_cache = {}

    for i, (_, row) in enumerate(df.iterrows()):
        ticker = row['ticker']
        politician = row['politician_name']
        trade_dt = row['traded_date']
        pub_dt = row['published_date']

        # From trade date (theoretical)
        cache_key_t = f"{ticker}_{trade_dt}"
        if cache_key_t not in ticker_cache:
            ticker_cache[cache_key_t] = get_forward_returns(ticker, trade_dt, horizons)
        ret_t = ticker_cache[cache_key_t]

        # From published date (realistic — when you'd buy)
        cache_key_p = f"{ticker}_{pub_dt}"
        if cache_key_p not in ticker_cache:
            ticker_cache[cache_key_p] = get_forward_returns(ticker, pub_dt, horizons)
        ret_p = ticker_cache[cache_key_p]

        if ret_t:
            results_trade_date.append(ret_t)
            by_politician[politician].append(ret_t)
        if ret_p:
            results_pub_date.append(ret_p)

        status_t = "OK" if ret_t else "NO DATA"
        if (i + 1) % 25 == 0 or i == 0:
            print(f"  [{i+1}/{len(df)}] {ticker} ({politician[:20]}): {status_t}")

    # 4. Analyze
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print("\n--- FROM TRADE DATE (theoretical: if you knew instantly) ---")
    print_returns_table(results_trade_date, horizons,
                        f"All {'Elite ' if elite_only else ''}Congressional Buys")

    print("\n--- FROM PUBLISHED DATE (realistic: when alert fires) ---")
    print_returns_table(results_pub_date, horizons,
                        f"All {'Elite ' if elite_only else ''}Congressional Buys")

    # Delay cost
    print("\n--- INFORMATION DELAY COST ---")
    for h in horizons:
        t_rets = [r[h] for r in results_trade_date if r.get(h) is not None]
        p_rets = [r[h] for r in results_pub_date if r.get(h) is not None]
        if t_rets and p_rets:
            diff = statistics.mean(t_rets) - statistics.mean(p_rets)
            print(f"  {h:2d}d: Trade-date avg {statistics.mean(t_rets):+.1f}% vs "
                  f"Published-date avg {statistics.mean(p_rets):+.1f}%  "
                  f"(delay cost: {diff:+.1f}%)")

    # By politician (top performers)
    print("\n" + "-" * 70)
    print("PERFORMANCE BY POLITICIAN (from trade date, min 5 signals)")
    print("-" * 70)
    politician_stats = []
    for pol, rets in by_politician.items():
        r30 = [r[30] for r in rets if r.get(30) is not None]
        if len(r30) < 5:
            continue
        wr = sum(1 for r in r30 if r > 0) / len(r30) * 100
        avg = statistics.mean(r30)
        politician_stats.append((pol, len(r30), wr, avg))

    politician_stats.sort(key=lambda x: x[3], reverse=True)
    print(f"\n  {'Politician':<35s} {'Trades':>6s} {'30d WR':>7s} {'30d Avg':>8s}")
    print(f"  {'-'*35} {'-'*6} {'-'*7} {'-'*8}")
    for pol, n, wr, avg in politician_stats[:20]:
        print(f"  {pol:<35s} {n:>6d} {wr:>6.1f}% {avg:>+7.1f}%")

    if politician_stats:
        print(f"\n  ... showing top 20 of {len(politician_stats)} politicians with 5+ signals")

    # Exit strategy analysis: what % gain covers most winners?
    print("\n" + "-" * 70)
    print("EXIT STRATEGY ANALYSIS")
    print("-" * 70)

    # Peak return analysis: at which horizon do returns peak?
    all_signals = []
    for ret in results_pub_date:
        if all(ret.get(h) is not None for h in horizons):
            all_signals.append(ret)

    if all_signals:
        print(f"\n  Signals with all horizons available: {len(all_signals)}")

        # What % of signals peak at each horizon?
        peak_at = defaultdict(int)
        for sig in all_signals:
            best_h = max(horizons, key=lambda h: sig[h])
            peak_at[best_h] += 1

        print("\n  When do returns PEAK?")
        for h in horizons:
            pct = peak_at[h] / len(all_signals) * 100
            print(f"    Peaks at {h:2d}d: {peak_at[h]:4d} signals ({pct:.1f}%)")

        # Profit target analysis
        print("\n  Profit target hit rates (from published date):")
        targets = [5, 8, 10, 15, 20]
        for target in targets:
            for h in horizons:
                rets = [r[h] for r in results_pub_date if r.get(h) is not None]
                hit = sum(1 for r in rets if r >= target)
                hit_pct = hit / len(rets) * 100 if rets else 0
                if h == horizons[0]:
                    print(f"    +{target:2d}%: ", end="")
                print(f"{h}d={hit_pct:5.1f}%  ", end="")
            print()

        # Stop-loss analysis
        print("\n  Max drawdown within first 30 days (from published date):")
        dd_rets = [r[7] for r in results_pub_date if r.get(7) is not None]
        if dd_rets:
            losses = [r for r in dd_rets if r < 0]
            if losses:
                print(f"    Signals with 7d loss: {len(losses)}/{len(dd_rets)} ({len(losses)/len(dd_rets)*100:.1f}%)")
                print(f"    Avg 7d loss when losing: {statistics.mean(losses):+.1f}%")
                print(f"    Worst 7d loss: {min(losses):+.1f}%")

                # Of those that dipped in first 7 days, how many recovered by 30d?
                recovered = 0
                total_dipped = 0
                for r in results_pub_date:
                    if r.get(7) is not None and r[7] < 0 and r.get(30) is not None:
                        total_dipped += 1
                        if r[30] > 0:
                            recovered += 1
                if total_dipped:
                    print(f"    Of 7d losers, recovered by 30d: {recovered}/{total_dipped} ({recovered/total_dipped*100:.1f}%)")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Congressional Trading Backtest")
    parser.add_argument("--elite-only", action="store_true", help="Only test elite 15 politicians")
    parser.add_argument("--max", type=int, default=500, help="Max signals to test (default 500)")
    args = parser.parse_args()
    run_backtest(elite_only=args.elite_only, max_signals=args.max)
