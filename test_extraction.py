from insider_alerts import init_database, scrape_all_congressional_trades_to_db, get_db
import json

# Scrape fresh data (will add new trades, skip duplicates)
print("Scraping fresh data...")
init_database()
scrape_all_congressional_trades_to_db(30)

print("\n" + "="*70)
print("Sample trades with improved extraction:")
print("="*70)

with get_db() as conn:
    rows = conn.execute("""
        SELECT politician_name, party, chamber, state, ticker, 
               traded_date, published_date, filed_after_days, owner_type
        FROM congressional_trades 
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()
    
    for i, row in enumerate(rows, 1):
        print(f"\n[Trade {i}]")
        print(f"  Politician: {row['politician_name']}")
        print(f"  Party: {row['party']}, Chamber: {row['chamber']}, State: {row['state']}")
        print(f"  Ticker: {row['ticker']}")
        print(f"  Traded: {row['traded_date']}")
        print(f"  Published: {row['published_date']}")
        print(f"  Filed After: {row['filed_after_days']} days" if row['filed_after_days'] else "  Filed After: N/A")
        print(f"  Owner: {row['owner_type']}")
