"""
Test Congressional trades scraper functionality.
"""
import sys
from insider_alerts import get_congressional_trades

def test_congressional_scraper():
    """Test the Congressional trades scraper with a known ticker."""
    print("Testing Congressional Trades Scraper")
    print("=" * 60)
    
    # Test with tickers we saw in the debug output (FI, MMM, ICE)
    test_tickers = ["FI", "MMM", "ICE", "NVDA", "AAPL"]
    
    for ticker in test_tickers:
        print(f"\nFetching Congressional trades for {ticker}...")
        try:
            trades = get_congressional_trades(ticker)
            
            if trades:
                print(f"✅ Found {len(trades)} Congressional trade(s):")
                for trade in trades[:5]:  # Show first 5
                    print(f"  • {trade['politician']}")
                    print(f"    Type: {trade['type']}")
                    print(f"    Date: {trade['date']}")
                    print(f"    Ticker: {trade['ticker']}")
                    print()
            else:
                print(f"⚠️ No Congressional trades found for {ticker}")
                
        except Exception as e:
            print(f"❌ Error fetching {ticker}: {e}")
            import traceback
            traceback.print_exc()
        
        print("-" * 60)
    
    print("\n✅ Congressional scraper test complete!")

if __name__ == "__main__":
    test_congressional_scraper()
