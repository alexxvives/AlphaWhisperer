import insider_alerts
import pandas as pd

# Get Congressional trades and detect signals
congressional_trades = insider_alerts.get_congressional_trades()
alerts = insider_alerts.detect_high_conviction_congressional_buy(congressional_trades)

print(f"Found {len(alerts)} Congressional Buy signals\n")

if alerts:
    alert = alerts[0]
    print(f"Testing alert for: {alert.ticker}")
    print(f"Signal type: {alert.signal_type}")
    print(f"\nTrades DataFrame columns: {list(alert.trades.columns)}")
    print(f"Trades DataFrame shape: {alert.trades.shape}\n")
    
    # Check different ways to access politician_id
    if not alert.trades.empty and "Politician ID" in alert.trades.columns:
        row = alert.trades.iloc[0]
        print(f"First row type: {type(row)}")
        print(f"First row: {row}\n")
        
        # Try different access methods
        print("Method 1 - .get():", row.get("Politician ID", "NOT FOUND"))
        print("Method 2 - direct access:", row["Politician ID"] if "Politician ID" in row else "NOT FOUND")
        print("Method 3 - dict conversion:", dict(row).get("Politician ID", "NOT FOUND"))
        
        # Show the actual politician_id value
        politician_id = row["Politician ID"]
        print(f"\nActual politician_id value: '{politician_id}'")
        print(f"Type: {type(politician_id)}")
        print(f"Is empty/None: {politician_id == '' or politician_id is None or pd.isna(politician_id)}")
        
        # Build the link as the code does
        if politician_id and not pd.isna(politician_id) and str(politician_id).strip():
            link_url = f"https://www.capitoltrades.com/trades?politician={politician_id}"
            print(f"\n Link would be: {link_url}")
        else:
            link_url = f"https://www.capitoltrades.com/trades?ticker={alert.ticker}"
            print(f"\n FALLBACK link would be: {link_url}")
    else:
        print("Politician ID column not found or trades empty")
else:
    print("No Congressional Buy signals found")
