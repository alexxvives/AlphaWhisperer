"""Check what recent trades we have in the database."""

import sqlite3
from datetime import datetime, timedelta

db_path = "data/congressional_trades.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get date range
cursor.execute("SELECT MIN(published_date), MAX(published_date) FROM congressional_trades")
min_date, max_date = cursor.fetchone()

print(f"Date range in database:")
print(f"  Earliest: {min_date}")
print(f"  Latest: {max_date}")

# Get count by recent periods
for days in [7, 30, 90, 180, 365]:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM congressional_trades WHERE date(published_date) >= date(?)",
        (since,)
    )
    count = cursor.fetchone()[0]
    print(f"  Last {days} days: {count} trades")

# Get most recent 10 trades
print("\nMost recent 10 trades:")
cursor.execute("""
    SELECT published_date, politician_name, ticker, trade_type, size_range 
    FROM congressional_trades 
    ORDER BY published_date DESC 
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row[0]} - {row[1]}: {row[3]} {row[2]} ({row[4]})")

conn.close()
