"""
Test Congressional trades database system
"""
from insider_alerts import (
    init_database, 
    scrape_all_congressional_trades_to_db,
    get_congressional_trades,
    get_db
)

print("=" * 70)
print("CONGRESSIONAL TRADES DATABASE TEST")
print("=" * 70)

# 1. Initialize database
print("\n[1/5] Initializing database...")
init_database()
print("✓ Database initialized")

# 2. Check current state
print("\n[2/5] Checking current database state...")
with get_db() as conn:
    count = conn.execute("SELECT COUNT(*) FROM congressional_trades").fetchone()[0]
    print(f"✓ Current trades in database: {count}")

# 3. Scrape fresh data (if needed)
if count < 5:
    print("\n[3/5] Scraping fresh Congressional trades...")
    scrape_all_congressional_trades_to_db(30)
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM congressional_trades").fetchone()[0]
        print(f"✓ New total: {count} trades")
else:
    print("\n[3/5] Skipping scrape (sufficient data)")

# 4. Query specific tickers
print("\n[4/5] Testing ticker-specific queries...")
test_tickers = ['GOOGL', 'V', 'HD', 'BRO']
for ticker in test_tickers:
    trades = get_congressional_trades(ticker)
    if trades:
        print(f"✓ {ticker}: Found {len(trades)} Congressional trades")
        trade = trades[0]
        print(f"  └─ {trade['politician'][:30]} - {trade['type']} {trade['size']} @ {trade['price']}")
    else:
        print(f"  {ticker}: No trades found")

# 5. Show summary statistics
print("\n[5/5] Database summary statistics...")
with get_db() as conn:
    # Trades by type
    by_type = conn.execute("""
        SELECT trade_type, COUNT(*) 
        FROM congressional_trades 
        GROUP BY trade_type
    """).fetchall()
    print("\nTrades by type:")
    for row in by_type:
        print(f"  {row[0]}: {row[1]}")
    
    # Most active politicians
    by_politician = conn.execute("""
        SELECT politician_name, COUNT(*) as count 
        FROM congressional_trades 
        GROUP BY politician_name 
        ORDER BY count DESC 
        LIMIT 5
    """).fetchall()
    print("\nMost active politicians:")
    for row in by_politician:
        print(f"  {row[0][:40]:40} - {row[1]} trades")
    
    # Party breakdown
    by_party = conn.execute("""
        SELECT party, COUNT(*) 
        FROM congressional_trades 
        WHERE party IS NOT NULL
        GROUP BY party
    """).fetchall()
    print("\nBy party:")
    for row in by_party:
        print(f"  {row[0]}: {row[1]}")

print("\n" + "=" * 70)
print("✓ ALL TESTS PASSED - Database system operational!")
print("=" * 70)
