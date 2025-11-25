import insider_alerts

# Get ALL Congressional trades (not just from database)
all_trades = insider_alerts.get_congressional_trades()
print(f"Total Congressional trades: {len(all_trades)}\n")

# Detect high-conviction Congressional buy
alerts = insider_alerts.detect_high_conviction_congressional_buy(all_trades)
print(f"Found {len(alerts)} Congressional Buy signals\n")

if alerts:
    alert = alerts[0]
    print(f"Alert ticker: {alert.ticker}")
    print(f"Signal type: {alert.signal_type}")
    print(f"Trades shape: {alert.trades.shape}")
    print(f"Columns: {list(alert.trades.columns)}\n")
    
    # Check politician_id
    if not alert.trades.empty and "Politician ID" in alert.trades.columns:
        politician_id = str(alert.trades.iloc[0]["Politician ID"]).strip()
        print(f"Politician ID: '{politician_id}'")
        
        if politician_id and politician_id != "nan" and politician_id != "":
            link = f"https://www.capitoltrades.com/trades?politician={politician_id}"
            print(f"\n Capitol Trades Link:\n{link}")
        else:
            print(f"\n Politician ID is empty, would use fallback")
    
    # Send the alert
    print(f"\n{'='*60}")
    print("Sending email and Telegram...")
    print(f"{'='*60}\n")
    
    insider_alerts.send_email_alert(alert, dry_run=False)
    insider_alerts.send_telegram_alert(alert, dry_run=False)
    
    print("\n Test complete! Check email and Telegram.")
else:
    print("No Congressional Buy signals detected")
