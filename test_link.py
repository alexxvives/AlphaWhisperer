import insider_alerts
import pandas as pd
from insider_alerts import InsiderAlert

# Get trades from database directly
db_trades = insider_alerts.get_ticker_trades_from_db("NFG")
print(f"NFG trades in database: {len(db_trades)}\n")

if db_trades:
    print("First NFG trade from DB:")
    print(f"  politician: {db_trades[0]['politician']}")
    print(f"  politician_id: {db_trades[0]['politician_id']}")
    print(f"  ticker: {db_trades[0]['ticker']}")
    print(f"  traded_date: {db_trades[0]['traded_date']}\n")
    
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
    
    # Check politician_id extraction AS THE CODE DOES IT
    politician_id = str(alert.trades.iloc[0]["Politician ID"]).strip()
    print(f"Politician ID from DataFrame: '{politician_id}'")
    print(f"Type: {type(politician_id)}")
    print(f"Is valid: {politician_id and politician_id != 'nan' and politician_id != ''}\n")
    
    if politician_id and politician_id != "nan" and politician_id != "":
        link = f"https://www.capitoltrades.com/trades?politician={politician_id}"
        print(f" Capitol Trades Link:\n{link}\n")
    else:
        link = f"https://www.capitoltrades.com/trades?ticker=NFG"
        print(f" FALLBACK Link:\n{link}\n")
    
    # Send the test alert
    print(f"{'='*60}")
    print("Sending test alert...")
    print(f"{'='*60}\n")
    
    insider_alerts.send_email_alert(alert, dry_run=False, subject_prefix="TEST: ")
    insider_alerts.send_telegram_alert(alert, dry_run=False)
    
    print("\n Done! Check email and Telegram.")
    print(f"The link should be: {link}")
