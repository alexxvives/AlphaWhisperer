"""Full scrape of all 30-day trades"""
from insider_alerts import init_database, scrape_all_congressional_trades_to_db
import sqlite3

# Initialize database
init_database()

print("Starting FULL scrape of 30-day Congressional trades...")
print("With 96 records/page, should be ~4 pages for 30 days")
print("="*70 + "\n")

# Run the scraper with max 10 pages (30 days with 96/page should be ~4 pages)
scrape_all_congressional_trades_to_db(days=30, max_pages=10)

print("\n" + "="*70)
print("FINAL DATABASE STATS")
print("="*70)

# Check database
conn = sqlite3.connect('data/congressional_trades.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Total count
cursor.execute("SELECT COUNT(*) as count FROM congressional_trades")
total = cursor.fetchone()['count']
print(f"\nTotal unique trades: {total}")

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

conn.close()
print("\n" + "="*70)
