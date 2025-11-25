#!/usr/bin/env python3
"""Quick test for Telegram formatting fixes."""

import sys
import sqlite3
from pathlib import Path
from insider_alerts import *

# Get Congressional trade
db_path = Path("data") / "congressional_trades.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("""
    SELECT * FROM congressional_trades 
    WHERE ticker = 'NFG' 
    ORDER BY traded_date DESC 
    LIMIT 1
""")
rows = cursor.fetchall()
conn.close()

if not rows:
    print("No Congressional trades found for NFG")
    sys.exit(1)

# Create DataFrame
columns = ['ticker', 'politician', 'type', 'traded_date', 'published_date', 
           'filed_after', 'size_range', 'price', 'chamber', 'party']
df = pd.DataFrame(rows, columns=columns)

# Rename columns to match InsiderAlert format
df = df.rename(columns={
    'ticker': 'Ticker',
    'politician': 'Insider Name',
    'traded_date': 'Traded Date',
    'published_date': 'Published Date',
    'filed_after': 'Filed After',
    'size_range': 'Size Range',
    'price': 'Price',
    'chamber': 'Chamber',
    'party': 'Party'
})

# Convert dates
df['Traded Date'] = pd.to_datetime(df['Traded Date'])
df['Published Date'] = pd.to_datetime(df['Published Date'])

# Create alert
alert = InsiderAlert(
    signal_type="Congressional Buy",
    ticker="NFG",
    company_name="National Fuel Gas Company",
    trades=df,
    details={}
)

print("Testing Telegram message formatting...")
print("\nAlert details:")
print(f"  Ticker: {alert.ticker}")
print(f"  Signal: {alert.signal_type}")
print(f"  Trades: {len(alert.trades)}")
print(f"  First trade date: {alert.trades.iloc[0]['Traded Date']}")

# Send Telegram
print("\nSending to Telegram...")
success = send_telegram_alert(alert, dry_run=False)

if success:
    print("\n✓ Telegram sent successfully!")
    print("\nCheck your Telegram for:")
    print("  1. No extra line break between company name and 'Trades:'")
    print("  2. Date should show (not N/A)")  
    print("  3. Link should be to Capitol Trades (not OpenInsider)")
    print("  4. Chart should be from Finviz")
else:
    print("\n✗ Telegram send failed")
