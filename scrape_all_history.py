"""
Scrape ALL historical Congressional trades from CapitolTrades.com
Uses the /trades endpoint with 3 YEARS filter and 96 records/page
"""

from insider_alerts import init_database, scrape_all_congressional_trades_to_db
import sqlite3

print("="*80)
print("SCRAPING ALL HISTORICAL CONGRESSIONAL TRADES")
print("Using: https://www.capitoltrades.com/trades with 3 YEARS filter")
print("="*80)

# Initialize database
init_database()

# Run full scrape (None = 3 YEARS filter, max_pages=500 to handle all 369 pages)
print("\nStarting scrape (this may take 30-60 minutes for all 369 pages)...")
print("Press Ctrl+C to stop early if needed\n")

scrape_all_congressional_trades_to_db(days=None, max_pages=500)

# Show final stats
print("\n" + "="*80)
print("FINAL DATABASE STATISTICS")
print("="*80)

conn = sqlite3.connect('data/congressional_trades.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Total trades
cursor.execute("SELECT COUNT(*) as count FROM congressional_trades")
total = cursor.fetchone()['count']
print(f"\nTotal trades: {total}")

# Trades with prices
cursor.execute("SELECT COUNT(*) as count FROM congressional_trades WHERE price IS NOT NULL AND price > 0")
with_price = cursor.fetchone()['count']
print(f"Trades with price: {with_price} ({with_price/total*100:.1f}%)")

# By party
cursor.execute("SELECT party, COUNT(*) as count FROM congressional_trades GROUP BY party ORDER BY count DESC")
print("\nBy party:")
for row in cursor.fetchall():
    print(f"  {row['party']}: {row['count']}")

# By type
cursor.execute("SELECT trade_type, COUNT(*) as count FROM congressional_trades GROUP BY trade_type ORDER BY count DESC")
print("\nBy type:")
for row in cursor.fetchall():
    print(f"  {row['trade_type']}: {row['count']}")

# Top politicians
cursor.execute("""
    SELECT politician_name, party, state, COUNT(*) as count 
    FROM congressional_trades 
    GROUP BY politician_name 
    ORDER BY count DESC 
    LIMIT 10
""")
print("\nTop 10 most active traders:")
for row in cursor.fetchall():
    print(f"  {row['politician_name']} ({row['party']}-{row['state']}): {row['count']} trades")

# Date range
cursor.execute("SELECT MIN(traded_date) as first, MAX(traded_date) as last FROM congressional_trades")
result = cursor.fetchone()
print(f"\nDate range: {result['first']} to {result['last']}")

conn.close()

print("\n" + "="*80)
print("COMPLETE! Now run: python politician_pnl.py")
print("="*80)
