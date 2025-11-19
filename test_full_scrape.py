"""Test the actual scraper function with limited pages"""
from insider_alerts import init_database, scrape_all_congressional_trades_to_db
import sqlite3

# Initialize database
init_database()

print("Starting scrape of 30-day Congressional trades (max 5 pages for testing)...")
print("="*70)

# Run the scraper with max 5 pages
scrape_all_congressional_trades_to_db(days=30, max_pages=5)

print("\n" + "="*70)
print("CHECKING DATABASE...")
print("="*70)

# Check database
conn = sqlite3.connect('data/congressional_trades.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Total count
cursor.execute("SELECT COUNT(*) as count FROM congressional_trades")
total = cursor.fetchone()['count']
print(f"\nTotal trades in database: {total}")

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

# Sample trades
cursor.execute("""
    SELECT politician_name, party, state, ticker, trade_type, traded_date, published_date, filed_after_days
    FROM congressional_trades
    ORDER BY published_date DESC
    LIMIT 10
""")
print("\nSample recent trades:")
for row in cursor.fetchall():
    print(f"  {row['politician_name']} ({row['party']}-{row['state']}) - {row['ticker']} - {row['trade_type']} - Traded: {row['traded_date']}, Published: {row['published_date']}, Filed after: {row['filed_after_days']} days")

conn.close()
