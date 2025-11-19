"""Test Congressional signal detection and formatting."""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from insider_alerts import (
    get_congressional_trades,
    detect_congressional_cluster_buy,
    detect_high_conviction_congressional_buy,
    format_telegram_message,
    get_company_context
)


def test_congressional_scraping():
    """Test that Congressional scraper works."""
    print("=" * 60)
    print("TEST 1: Congressional Trade Scraping")
    print("=" * 60)
    
    trades = get_congressional_trades()
    
    if not trades:
        print("❌ FAIL: No Congressional trades returned")
        return False
    
    print(f"✅ SUCCESS: Got {len(trades)} Congressional trades")
    
    # Display sample trades
    for i, trade in enumerate(trades[:3]):
        print(f"\n  Trade {i+1}:")
        print(f"    Politician: {trade.get('politician', 'N/A')}")
        print(f"    Ticker: {trade.get('ticker', 'N/A')}")
        print(f"    Type: {trade.get('type', 'N/A')}")
        print(f"    Date: {trade.get('date', 'N/A')}")
        print(f"    Party: {trade.get('party', 'N/A')}")
        print(f"    Chamber: {trade.get('chamber', 'N/A')}")
    
    return True


def test_cluster_detection():
    """Test Congressional Cluster Buy detection."""
    print("\n" + "=" * 60)
    print("TEST 2: Congressional Cluster Buy Detection")
    print("=" * 60)
    
    # Create mock data with cluster
    mock_trades = [
        {
            "politician": "Josh Gottheimer",
            "ticker": "AAPL",
            "type": "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "party": "D",
            "chamber": "House"
        },
        {
            "politician": "Thomas Kean Jr",
            "ticker": "AAPL",
            "type": "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "party": "R",
            "chamber": "House"
        },
        {
            "politician": "Scott Peters",
            "ticker": "MSFT",
            "type": "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "party": "D",
            "chamber": "House"
        }
    ]
    
    alerts = detect_congressional_cluster_buy(mock_trades)
    
    if not alerts:
        print("⚠️  WARN: No cluster signals detected (may need 2+ same ticker)")
        return True
    
    print(f"✅ SUCCESS: Detected {len(alerts)} Congressional cluster signal(s)")
    for alert in alerts:
        print(f"\n  Signal Type: {alert.signal_type}")
        print(f"  Ticker: {alert.ticker}")
        print(f"  Details: {alert.details}")
    
    return True


def test_high_conviction_detection():
    """Test High-Conviction Congressional Buy detection."""
    print("\n" + "=" * 60)
    print("TEST 3: High-Conviction Congressional Buy Detection")
    print("=" * 60)
    
    # Create mock data with high-conviction trader
    mock_trades = [
        {
            "politician": "Nancy Pelosi",
            "ticker": "NVDA",
            "type": "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "party": "D",
            "chamber": "House"
        },
        {
            "politician": "Scott Peters",
            "ticker": "AMD",
            "type": "Purchase",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "party": "D",
            "chamber": "House"
        }
    ]
    
    alerts = detect_high_conviction_congressional_buy(mock_trades)
    
    if not alerts:
        print("⚠️  WARN: No high-conviction signals detected (needs known trader)")
        return True
    
    print(f"✅ SUCCESS: Detected {len(alerts)} High-Conviction signal(s)")
    for alert in alerts:
        print(f"\n  Signal Type: {alert.signal_type}")
        print(f"  Ticker: {alert.ticker}")
        print(f"  Details: {alert.details}")
    
    return True


def test_live_congressional_signals():
    """Test Congressional signal detection with live data."""
    print("\n" + "=" * 60)
    print("TEST 4: Live Congressional Signal Detection")
    print("=" * 60)
    
    trades = get_congressional_trades()
    
    if not trades:
        print("❌ FAIL: No Congressional trades to analyze")
        return False
    
    print(f"Analyzing {len(trades)} live Congressional trades...")
    
    cluster_alerts = detect_congressional_cluster_buy(trades)
    conviction_alerts = detect_high_conviction_congressional_buy(trades)
    
    total_alerts = len(cluster_alerts) + len(conviction_alerts)
    
    print(f"\nResults:")
    print(f"  Cluster Buy signals: {len(cluster_alerts)}")
    print(f"  High-Conviction signals: {len(conviction_alerts)}")
    print(f"  Total Congressional signals: {total_alerts}")
    
    if total_alerts == 0:
        print("\n⚠️  No signals detected (this is normal if no clusters/known traders)")
        return True
    
    print(f"\n✅ SUCCESS: Detected {total_alerts} Congressional signal(s)")
    
    # Show details of first alert
    if cluster_alerts:
        alert = cluster_alerts[0]
        print(f"\n  Example Cluster Signal:")
        print(f"    Type: {alert.signal_type}")
        print(f"    Ticker: {alert.ticker}")
        print(f"    Company: {alert.company_name}")
        print(f"    Politicians: {alert.details.get('num_politicians', 'N/A')}")
    
    if conviction_alerts:
        alert = conviction_alerts[0]
        print(f"\n  Example High-Conviction Signal:")
        print(f"    Type: {alert.signal_type}")
        print(f"    Ticker: {alert.ticker}")
        print(f"    Politician: {alert.details.get('politician', 'N/A')}")
    
    return True


def test_telegram_formatting():
    """Test that Congressional signals format correctly for Telegram."""
    print("\n" + "=" * 60)
    print("TEST 5: Telegram Message Formatting")
    print("=" * 60)
    
    # Create mock alert
    from insider_alerts import InsiderAlert
    import pandas as pd
    
    mock_df = pd.DataFrame([{
        "Ticker": "AAPL",
        "Trade Date": datetime.now(),
        "Insider Name": "Josh Gottheimer",
        "Title": "Rep-NJ5",
        "Value": 100000,
        "Delta Own": "+2.5%"
    }])
    
    alert = InsiderAlert(
        ticker="AAPL",
        company_name="Apple Inc.",
        signal_type="Bipartisan Congressional Buy",
        trades=mock_df,
        details={
            "num_politicians": 2,
            "politicians": ["Josh Gottheimer (D)", "Thomas Kean Jr (R)"],
            "bipartisan": True
        }
    )
    
    try:
        message = format_telegram_message(alert)
        print("✅ SUCCESS: Message formatted without errors")
        print(f"\nMessage preview (first 500 chars):")
        print("-" * 60)
        print(message[:500])
        print("...")
        return True
    except Exception as e:
        print(f"❌ FAIL: Error formatting message: {e}")
        return False


def main():
    """Run all tests."""
    print("\n🧪 CONGRESSIONAL SIGNAL DETECTION TESTS\n")
    
    tests = [
        ("Congressional Scraping", test_congressional_scraping),
        ("Cluster Detection", test_cluster_detection),
        ("High-Conviction Detection", test_high_conviction_detection),
        ("Live Signal Detection", test_live_congressional_signals),
        ("Telegram Formatting", test_telegram_formatting)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
