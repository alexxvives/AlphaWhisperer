import insider_alerts

# Clear cache properly
with insider_alerts.get_db() as conn:
    conn.execute("DELETE FROM cache_metadata WHERE key = 'last_congressional_fetch'")

print("Cache cleared.\n")

# Get trades from database directly
db_trades = insider_alerts.get_ticker_trades_from_db("NFG")
print(f"NFG trades in database: {len(db_trades)}\n")

if db_trades:
    print("First NFG trade from DB:")
    for key, value in db_trades[0].items():
        print(f"  {key}: {value}")
    
    print(f"\npolitician_id in DB: '{db_trades[0].get('politician_id', 'NOT FOUND')}'")
    
    # Now create a signal manually for testing
    print(f"\n{'='*60}")
    print("Creating test signal with NFG data...")
    print(f"{'='*60}\n")
    
    import pandas as pd
    from insider_alerts import InsiderAlert
    
    # Create DataFrame with politician_id
    trades_data = {
        "Ticker": "NFG",
        "Insider Name": db_trades[0]['politician'],
        "Politician ID": db_trades[0]['politician_id'],
        "Traded Date": db_trades[0]['traded_date'],
        "Published Date": db_trades[0]['published_date'],
        "Filed After": db_trades[0]['filed_after_days'],
        "Title": db_trades[0]['chamber'],
        "Value": 0,
        "Size Range": db_trades[0]['size'],
        "Price": db_trades[0]['price']
    }
    trades_df = pd.DataFrame([trades_data])
    
    alert = InsiderAlert(
        signal_type="Congressional Buy",
        ticker="NFG",
        company_name="National Fuel Gas",
        trades=trades_df,
        details={"test": True}
    )
    
    # Check politician_id extraction
    politician_id = str(alert.trades.iloc[0]["Politician ID"]).strip()
    print(f"Politician ID from DataFrame: '{politician_id}'")
    
    if politician_id and politician_id != "nan" and politician_id != "":
        link = f"https://www.capitoltrades.com/trades?politician={politician_id}"
        print(f"\n Capitol Trades Link:\n{link}\n")
    else:
        print(f"\n Would use fallback\n")
    
    # Send the test alert
    print(f"{'='*60}")
    print("Sending test alert...")
    print(f"{'='*60}\n")
    
    insider_alerts.send_email_alert(alert, dry_run=False, subject_prefix="TEST: ")
    insider_alerts.send_telegram_alert(alert, dry_run=False)
    
    print("\n Done! Check email and Telegram for the link.")
