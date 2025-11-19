"""Test size and price extraction from Congressional trades."""
from insider_alerts import get_congressional_trades

trades = get_congressional_trades()
print(f"\n✅ Found {len(trades)} trades\n")
print("Detailed trade data (first 5):")
print("=" * 80)

for t in trades[:5]:
    pol = t['politician'][:40].ljust(40)
    ticker = t['ticker'].ljust(6)
    size = str(t.get('size', 'N/A')).ljust(12)
    price = str(t.get('price', 'N/A')).ljust(10)
    trade_type = t['type'].ljust(4)
    
    print(f"{pol} | {ticker} | {trade_type} | Size: {size} | Price: {price}")

print("=" * 80)
