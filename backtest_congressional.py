#!/usr/bin/env python3
"""
Congressional Trading Backtest

Tests forward returns of congressional stock buys, comparing:
- Elite politicians vs. all politicians
- Returns from TRADE date (theoretical edge) vs. PUBLISHED date (realistic entry)
- Performance by individual politician (ALL ranked)
- Optimal holding period analysis (exit strategy)

Optimized: downloads each ticker's history ONCE, then computes all returns
from cache. This makes full-universe backtests (3000+ signals) feasible.

Usage:
    python backtest_congressional.py                # Full backtest (all politicians)
    python backtest_congressional.py --elite-only   # Only elite politicians
    python backtest_congressional.py --max 5000     # Increase signal cap
    python backtest_congressional.py --min-trades 3 # Lower min for politician ranking
"""

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_FILE = Path(__file__).parent / "data" / "alphaWhisperer.db"

# Backtest-validated elite politicians (Apr 2026)
# Criteria: avg 30d return > +3%, WR > 55%, 10+ trades (published-date entry)
ELITE_POLITICIANS = [
    'Bruce Westerman',         # 56 trades, 87.5% WR, +10.0% avg30d
    'Greg Stanton',            # 59 trades, 86.4% WR, +7.2% avg30d
    'Cleo Fields',             # 36 trades, 58.3% WR, +7.9% avg30d
    'James Comer',             # 12 trades, 75.0% WR, +6.3% avg30d
    'Tommy Tuberville',        # 73 trades, 67.1% WR, +5.6% avg30d
    'Byron Donalds',           # 36 trades, 63.9% WR, +5.5% avg30d
    'John James',              # 63 trades, 63.5% WR, +4.8% avg30d
    'David Taylor',            # 18 trades, 66.7% WR, +4.7% avg30d
    'April McClain Delaney',   # 24 trades, 79.2% WR, +4.0% avg30d
    'Neal Dunn',               # 15 trades, 73.3% WR, +4.0% avg30d
    'Markwayne Mullin',        # 106 trades, 65.1% WR, +3.8% avg30d
    'Rich McCormick',          # 11 trades, 63.6% WR, +3.6% avg30d
    'Marjorie Taylor Greene',  # 173 trades, 58.4% WR, +3.2% avg30d
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


def batch_download_tickers(tickers, earliest_date, latest_date, horizons):
    """Download price history for all tickers at once, returns dict of DataFrames."""
    max_horizon = max(horizons)
    start = (earliest_date - timedelta(days=10)).strftime('%Y-%m-%d')
    end = (latest_date + timedelta(days=max_horizon + 15)).strftime('%Y-%m-%d')

    ticker_data = {}
    ticker_list = sorted(set(tickers))
    batch_size = 50

    for i in range(0, len(ticker_list), batch_size):
        batch = ticker_list[i:i + batch_size]
        batch_str = ' '.join(batch)
        pct = (i + len(batch)) / len(ticker_list) * 100
        print(f"  Downloading batch {i // batch_size + 1} "
              f"({len(batch)} tickers, {pct:.0f}% done)...", flush=True)

        try:
            data = yf.download(batch_str, start=start, end=end,
                               progress=False, group_by='ticker', threads=True)
            if data.empty:
                continue

            if len(batch) == 1:
                # Single ticker: no multi-level columns
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                data.index = pd.to_datetime(data.index)
                if not data.empty:
                    ticker_data[batch[0]] = data
            else:
                for t in batch:
                    try:
                        tdf = data[t].copy() if t in data.columns.get_level_values(0) else None
                        if tdf is not None:
                            tdf = tdf.dropna(subset=['Close'])
                            tdf.index = pd.to_datetime(tdf.index)
                            if not tdf.empty:
                                ticker_data[t] = tdf
                    except (KeyError, TypeError):
                        pass
        except Exception as e:
            print(f"    Batch download error: {e}")

    return ticker_data


def compute_returns_from_cache(ticker_data, ticker, signal_date, horizons):
    """Compute forward returns using pre-downloaded price data."""
    if ticker not in ticker_data:
        return None
    if signal_date is None or pd.isna(signal_date):
        return None

    hist = ticker_data[ticker]
    ts = pd.Timestamp(signal_date)

    after = hist[hist.index >= ts]
    if after.empty:
        return None

    entry_price = float(after['Close'].iloc[0])
    if entry_price <= 0:
        return None

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


def run_backtest(elite_only=False, max_signals=5000, min_trades=5):
    horizons = (7, 14, 30, 60, 90)

    print("=" * 70)
    print("CONGRESSIONAL TRADING BACKTEST" +
          (" (ALL POLITICIANS)" if not elite_only else " (ELITE ONLY)"))
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

    # 3. Batch-download all ticker histories
    all_tickers = df['ticker'].unique().tolist()
    earliest = df['traded_date'].min()
    latest = df['published_date'].max()
    if pd.isna(latest):
        latest = df['traded_date'].max()

    print(f"\n[3/4] Batch-downloading price data for {len(all_tickers)} tickers...")
    ticker_data = batch_download_tickers(all_tickers, earliest, latest, horizons)
    print(f"  Successfully cached: {len(ticker_data)} tickers")

    # 4. Compute returns
    print(f"\n[4/4] Computing forward returns for {len(df)} signals...")

    results_trade_date = []
    results_pub_date = []
    by_politician_trade = defaultdict(list)
    by_politician_pub = defaultdict(list)
    skipped = 0

    for i, (_, row) in enumerate(df.iterrows()):
        ticker = row['ticker']
        politician = row['politician_name']
        trade_dt = row['traded_date']
        pub_dt = row['published_date']

        ret_t = compute_returns_from_cache(ticker_data, ticker, trade_dt, horizons)
        ret_p = compute_returns_from_cache(ticker_data, ticker, pub_dt, horizons)

        if ret_t:
            results_trade_date.append(ret_t)
            by_politician_trade[politician].append(ret_t)
        else:
            skipped += 1

        if ret_p:
            results_pub_date.append(ret_p)
            by_politician_pub[politician].append(ret_p)

        if (i + 1) % 500 == 0:
            print(f"  [{i+1}/{len(df)}] processed...", flush=True)

    print(f"  Successful: {len(results_trade_date)} trade-date, "
          f"{len(results_pub_date)} published-date.  Skipped: {skipped}")

    # === RESULTS ===
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

    # ===== FULL POLITICIAN RANKING (from published date = realistic) =====
    print("\n" + "=" * 70)
    print(f"FULL POLITICIAN RANKING (published-date returns, min {min_trades} trades)")
    print("=" * 70)

    politician_stats = []
    for pol, rets in by_politician_pub.items():
        r30 = [r[30] for r in rets if r.get(30) is not None]
        r90 = [r[90] for r in rets if r.get(90) is not None]
        if len(r30) < min_trades:
            continue
        wr30 = sum(1 for r in r30 if r > 0) / len(r30) * 100
        avg30 = statistics.mean(r30)
        med30 = statistics.median(r30)
        wr90 = sum(1 for r in r90 if r > 0) / len(r90) * 100 if r90 else 0
        avg90 = statistics.mean(r90) if r90 else 0
        # Cumulative return estimate: sum of returns across trades
        cum = sum(r30)
        politician_stats.append({
            'name': pol, 'n': len(r30),
            'wr30': wr30, 'avg30': avg30, 'med30': med30,
            'wr90': wr90, 'avg90': avg90, 'cum30': cum,
        })

    # Sort by avg 30d return
    politician_stats.sort(key=lambda x: x['avg30'], reverse=True)

    print(f"\n  {'#':<4s}{'Politician':<35s} {'Trades':>6s} {'30d WR':>7s} "
          f"{'30d Avg':>8s} {'30d Med':>8s} {'90d Avg':>8s} {'Sum30d':>8s}")
    print(f"  {'─'*4}{'─'*35} {'─'*6} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for rank, ps in enumerate(politician_stats, 1):
        marker = " ★" if ps['avg30'] > 3 and ps['wr30'] > 55 and ps['n'] >= 10 else ""
        print(f"  {rank:<4d}{ps['name']:<35s} {ps['n']:>6d} {ps['wr30']:>6.1f}% "
              f"{ps['avg30']:>+7.1f}% {ps['med30']:>+7.1f}% "
              f"{ps['avg90']:>+7.1f}% {ps['cum30']:>+7.0f}%{marker}")

    print(f"\n  Total: {len(politician_stats)} politicians with {min_trades}+ trades")
    print(f"  ★ = avg30 > +3%, WR > 55%, 10+ trades (strong candidates)")

    # Top 10 & Bottom 10 summary
    top10 = [p for p in politician_stats if p['avg30'] > 0][:10]
    bot10 = [p for p in politician_stats if p['avg30'] < 0][-10:]

    if top10:
        print(f"\n  TOP PERFORMERS (follow these):")
        for ps in top10:
            print(f"    {ps['name']}: {ps['n']} trades, WR={ps['wr30']:.0f}%, "
                  f"avg30={ps['avg30']:+.1f}%, cumulative={ps['cum30']:+.0f}%")

    if bot10:
        print(f"\n  WORST PERFORMERS (avoid or fade):")
        for ps in reversed(bot10):
            print(f"    {ps['name']}: {ps['n']} trades, WR={ps['wr30']:.0f}%, "
                  f"avg30={ps['avg30']:+.1f}%, cumulative={ps['cum30']:+.0f}%")

    # Also show by trade_date for comparison
    print("\n" + "-" * 70)
    print(f"TRADE-DATE RANKING (theoretical, min {min_trades} trades)")
    print("-" * 70)
    trade_stats = []
    for pol, rets in by_politician_trade.items():
        r30 = [r[30] for r in rets if r.get(30) is not None]
        if len(r30) < min_trades:
            continue
        wr = sum(1 for r in r30 if r > 0) / len(r30) * 100
        avg = statistics.mean(r30)
        trade_stats.append((pol, len(r30), wr, avg))

    trade_stats.sort(key=lambda x: x[3], reverse=True)
    print(f"\n  {'Politician':<35s} {'Trades':>6s} {'30d WR':>7s} {'30d Avg':>8s}")
    print(f"  {'─'*35} {'─'*6} {'─'*7} {'─'*8}")
    for pol, n, wr, avg in trade_stats:
        print(f"  {pol:<35s} {n:>6d} {wr:>6.1f}% {avg:>+7.1f}%")

    # Exit strategy analysis
    print("\n" + "-" * 70)
    print("EXIT STRATEGY ANALYSIS")
    print("-" * 70)

    all_signals = [r for r in results_pub_date
                   if all(r.get(h) is not None for h in horizons)]

    if all_signals:
        print(f"\n  Signals with all horizons available: {len(all_signals)}")

        peak_at = defaultdict(int)
        for sig in all_signals:
            best_h = max(horizons, key=lambda h: sig[h])
            peak_at[best_h] += 1

        print("\n  When do returns PEAK?")
        for h in horizons:
            pct = peak_at[h] / len(all_signals) * 100
            print(f"    Peaks at {h:2d}d: {peak_at[h]:4d} signals ({pct:.1f}%)")

        print("\n  Profit target hit rates (from published date):")
        targets = [5, 8, 10, 15, 20, 50]
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
        print("\n  Drawdown analysis (from published date):")
        dd_rets = [r[7] for r in results_pub_date if r.get(7) is not None]
        if dd_rets:
            losses = [r for r in dd_rets if r < 0]
            if losses:
                print(f"    Signals with 7d loss: {len(losses)}/{len(dd_rets)} "
                      f"({len(losses)/len(dd_rets)*100:.1f}%)")
                print(f"    Avg 7d loss when losing: {statistics.mean(losses):+.1f}%")
                print(f"    Worst 7d loss: {min(losses):+.1f}%")

                recovered = 0
                total_dipped = 0
                for r in results_pub_date:
                    if r.get(7) is not None and r[7] < 0 and r.get(30) is not None:
                        total_dipped += 1
                        if r[30] > 0:
                            recovered += 1
                if total_dipped:
                    print(f"    Of 7d losers, recovered by 30d: "
                          f"{recovered}/{total_dipped} ({recovered/total_dipped*100:.1f}%)")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Congressional Trading Backtest")
    parser.add_argument("--elite-only", action="store_true",
                        help="Only test elite 15 politicians")
    parser.add_argument("--max", type=int, default=5000,
                        help="Max signals to test (default 5000)")
    parser.add_argument("--min-trades", type=int, default=5,
                        help="Min trades for politician ranking (default 5)")
    args = parser.parse_args()
    run_backtest(elite_only=args.elite_only, max_signals=args.max,
                 min_trades=args.min_trades)
