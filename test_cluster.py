"""Test Congressional Cluster Buy signal with politician_id"""
import insider_alerts

# Get Congressional trades and detect signals
congressional_trades = insider_alerts.get_congressional_trades()
alerts = insider_alerts.detect_congressional_cluster_buy(congressional_trades)

print(f"Found {len(alerts)} Congressional Cluster Buy signals")

if alerts:
    alert = alerts[0]
    print(f"\nTesting alert for: {alert.ticker}")
    print(f"Signal type: {alert.signal_type}")
    
    # Check if politician_id is in the DataFrame
    if not alert.trades.empty and "Politician ID" in alert.trades.columns:
        politician_id = alert.trades.iloc[0].get("Politician ID", "")
        print(f"Politician ID: '{politician_id}'")
    else:
        print("Politician ID column not found or trades empty")
    
    # Send email and Telegram
    print("\nSending email...")
    insider_alerts.send_email_alert(alert, dry_run=False)
    
    print("\nSending Telegram...")
    insider_alerts.send_telegram_alert(alert, dry_run=False)
    
    print("\n Test complete! Check email and Telegram for Capitol Trades link.")
else:
    print("No Congressional Cluster Buy signals found")
