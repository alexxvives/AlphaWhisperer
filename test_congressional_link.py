import insider_alerts
import pandas as pd

print("Testing Congressional Buy Signal with politician_id...\n")

# Get trades from database
db_trades = insider_alerts.get_ticker_trades_from_db("NFG")
print(f"NFG trades in database: {len(db_trades)}\n")

if db_trades:
    # Create test alert
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
    
    alert = insider_alerts.InsiderAlert(
        signal_type="Congressional Buy",
        ticker="NFG",
        company_name="National Fuel Gas",
        trades=trades_df,
        details={"test": True}
    )
    
    # Extract politician_id as the code does
    politician_id = str(alert.trades.iloc[0]["Politician ID"]).strip()
    print(f"Politician ID: '{politician_id}'")
    
    if politician_id and politician_id != "nan" and politician_id != "":
        link = f"https://www.capitoltrades.com/trades?politician={politician_id}"
        print(f"\nCapitol Trades Link (CORRECT):")
        print(f"  {link}")
    else:
        link = f"https://www.capitoltrades.com/trades?ticker=NFG"
        print(f"\nFallback Link (WRONG):")
        print(f"  {link}")
    
    print(f"\n{'='*60}")
    print("Sending Telegram alert...")
    print(f"{'='*60}\n")
    
    # Send only Telegram (faster than email)
    success = insider_alerts.send_telegram_alert(alert, dry_run=False)
    
    if success:
        print(f"\nSUCCESS! Check Telegram for the Capitol Trades link.")
        print(f"Expected link: {link}")
    else:
        print(f"\nFailed to send or already sent recently (deduplication)")
