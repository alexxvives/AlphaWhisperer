"""Test scraping full history for one politician"""
from scrape_politician_history import scrape_politician_trades, store_politician_trades

# Test with Ro Khanna (had 246 trades in 30 days)
politician_id = "K000389"
politician_name = "Ro Khanna"
party = "D"
chamber = "House"
state = "CA"

print(f"Testing full history scrape for {politician_name}...")
print("="*70)

trades = scrape_politician_trades(politician_id, politician_name, max_pages=20)

if trades:
    print(f"\nScraped {len(trades)} total trades")
    print("\nSample trades:")
    for i, trade in enumerate(trades[:5], 1):
        print(f"{i}. {trade['ticker']} - {trade['trade_type']} - {trade['size_range']} - ${trade['price']} - {trade['traded_date']}")
    
    print("\nStoring in database...")
    new, dup = store_politician_trades(politician_id, politician_name, party, chamber, state, trades)
    print(f"Stored: {new} new trades, {dup} duplicates")
else:
    print("No trades found!")
