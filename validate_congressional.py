#!/usr/bin/env python3
"""
Quick validation: Congressional Cluster signals (2+ politicians same ticker in 7 days)
vs single buys vs elite politicians.
Only downloads tickers with 30+ days of history available.
"""
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_FILE = Path(__file__).parent / "data" / "alphaWhisperer.db"

ELITE_POLITICIANS = [
    'Bruce Westerman', 'Greg Stanton', 'Cleo Fields', 'James Comer',
    'Tommy Tuberville', 'Byron Donalds', 'John James', 'David Taylor',
    'April McClain Delaney', 'Neal Dunn', 'Markwayne Mullin',
    'Rich McCormick', 'Marjorie Taylor Greene',
]

conn = sqlite3.connect(str(DB_FILE))
df = pd.read_sql_query(
    "SELECT politician_name, ticker, traded_date, published_date FROM congressional_trades "
    "WHERE LOWER(trade_type) = 'buy' ORDER BY published_date",
    conn
)
conn.close()
df['traded_date'] = pd.to_datetime(df['traded_date'], errors='coerce')
df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')
df = df.dropna(subset=['published_date', 'ticker'])

# Cutoff: only signals with at least 30 trading days of forward data
cutoff = datetime.now() - timedelta(days=45)
df = df[df['published_date'] < cutoff]

print(f"Signals with 30+ days of forward data: {len(df)}")
print(f"Date range: {df['published_date'].min().date()} to {df['published_date'].max().date()}")

# Identify cluster events: 2+ politicians buy same ticker within 7 days (published date)
df_sorted = df.sort_values(['ticker', 'published_date'])
cluster_signals = []  # (ticker, cluster_date = first published date in cluster)
seen_clusters = set()

for ticker, group in df_sorted.groupby('ticker'):
    dates = sorted(group['published_date'].tolist())
    for i, date in enumerate(dates):
        cluster_end = date + timedelta(days=7)
        pols_in_window = group[
            (group['published_date'] >= date) & (group['published_date'] <= cluster_end)
        ]['politician_name'].tolist()
        if len(pols_in_window) >= 2:
            key = (ticker, date.date())
            if key not in seen_clusters:
                seen_clusters.add(key)
                cluster_signals.append({'ticker': ticker, 'signal_date': date, 'n_politicians': len(pols_in_window)})

# Elite politician single buys
elite_mask = df['politician_name'].apply(lambda x: any(e.lower() in x.lower() for e in ELITE_POLITICIANS))
elite_singles = df[elite_mask].copy()

# All singles
all_singles = df.copy()

print(f"\nCluster signals (2+ pols in 7d window): {len(cluster_signals)}")
print(f"Elite politician single buys: {len(elite_singles)}")
print(f"All single buys: {len(all_singles)}")

# Download prices (only unique tickers needed)
cluster_df = pd.DataFrame(cluster_signals)
all_tickers = list(set(
    cluster_df['ticker'].tolist() + elite_singles['ticker'].tolist()
))
print(f"\nDownloading {len(all_tickers)} unique tickers...")

ticker_data = {}
batch_size = 50
for i in range(0, len(all_tickers), batch_size):
    batch = all_tickers[i:i+batch_size]
    print(f"  Batch {i//batch_size+1}/{(len(all_tickers)+batch_size-1)//batch_size}...")
    try:
        data = yf.download(
            ' '.join(batch),
            start='2023-01-01', end=datetime.now().strftime('%Y-%m-%d'),
            progress=False, group_by='ticker', threads=True
        )
        if data.empty:
            continue
        if len(batch) == 1:
            t = batch[0]
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data.index = pd.to_datetime(data.index)
            ticker_data[t] = data
        else:
            for t in batch:
                try:
                    tdf = data[t].copy()
                    tdf = tdf.dropna(subset=['Close'])
                    tdf.index = pd.to_datetime(tdf.index)
                    if not tdf.empty:
                        ticker_data[t] = tdf
                except (KeyError, TypeError):
                    pass
    except Exception as e:
        print(f"  Error: {e}")

def get_return(ticker, signal_date, days):
    if ticker not in ticker_data:
        return None
    hist = ticker_data[ticker]
    ts = pd.Timestamp(signal_date)
    after = hist[hist.index >= ts]
    if after.empty:
        return None
    entry = float(after['Close'].iloc[0])
    target = after.index[0] + timedelta(days=days)
    future = hist[hist.index >= target]
    if future.empty:
        return None
    return round((float(future['Close'].iloc[0]) - entry) / entry * 100, 2)

def summarize(returns_list, label):
    r30 = [r for r in returns_list if r is not None]
    if not r30:
        print(f"  {label}: no data")
        return
    wr = sum(1 for r in r30 if r > 0) / len(r30) * 100
    avg = statistics.mean(r30)
    med = statistics.median(r30)
    print(f"  {label} (n={len(r30)}): WR={wr:.1f}%  Avg={avg:+.1f}%  Med={med:+.1f}%")

print("\n=== CONGRESSIONAL CLUSTER BUY (2+ politicians in 7 days) ===")
cluster_r30 = [get_return(r['ticker'], r['signal_date'], 30) for _, r in cluster_df.iterrows()]
cluster_r7  = [get_return(r['ticker'], r['signal_date'], 7)  for _, r in cluster_df.iterrows()]
summarize(cluster_r7, "7-day")
summarize(cluster_r30, "30-day")

print("\n=== ELITE POLITICIAN SINGLE BUYS ===")
elite_r7  = [get_return(row['ticker'], row['published_date'], 7)  for _, row in elite_singles.iterrows()]
elite_r30 = [get_return(row['ticker'], row['published_date'], 30) for _, row in elite_singles.iterrows()]
summarize(elite_r7, "7-day")
summarize(elite_r30, "30-day")

print("\n=== ALL CONGRESSIONAL SINGLE BUYS (benchmark) ===")
all_r7  = [get_return(row['ticker'], row['published_date'], 7)  for _, row in all_singles.sample(min(500, len(all_singles)), random_state=42).iterrows()]
all_r30 = [get_return(row['ticker'], row['published_date'], 30) for _, row in all_singles.sample(min(500, len(all_singles)), random_state=42).iterrows()]
summarize(all_r7, "7-day")
summarize(all_r30, "30-day")
