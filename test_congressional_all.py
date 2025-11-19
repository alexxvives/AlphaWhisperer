"""
Test Congressional trades scraper - should return ALL recent trades.
"""
import sys
import os
os.environ['USE_CAPITOL_TRADES'] = 'true'

from insider_alerts import get_congressional_trades

print("Testing Congressional Trades Scraper (All Recent Trades)")
print("=" * 60)

try:
    trades = get_congressional_trades()
    
    if trades:
        print(f"\n✅ Found {len(trades)} Congressional trades:\n")
        
        # Group by type
        buys = [t for t in trades if t['type'] == 'BUY']
        sells = [t for t in trades if t['type'] == 'SELL']
        
        if buys:
            print(f"📈 BUYS ({len(buys)}):")
            for trade in buys:
                print(f"  • {trade['ticker']:6} - {trade['politician'][:40]:40} - {trade['date']}")
        
        if sells:
            print(f"\n📉 SELLS ({len(sells)}):")
            for trade in sells:
                print(f"  • {trade['ticker']:6} - {trade['politician'][:40]:40} - {trade['date']}")
        
        # Show unique tickers
        tickers = set(t['ticker'] for t in trades if t['ticker'] != 'N/A')
        print(f"\n🎯 Tickers found: {', '.join(sorted(tickers))}")
        
    else:
        print("❌ No trades found")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ Test complete!")
