#!/usr/bin/env python3
"""Send a test Congressional Cluster Buy alert (Bipartisan) to email + Telegram."""
import sys
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, ".")
from insider_alerts import InsiderAlert, send_email_alert, send_telegram_alert, init_database

init_database()

today = datetime.now()

trades_data = {
    "Politician ID": ["P000197", "S000040"],
    "Insider Name": ["Nancy Pelosi (D-CA)", "Ted Cruz (R-TX)"],
    "Title": ["House Representative", "Senator"],
    "Trade Date": [today - timedelta(days=3), today - timedelta(days=5)],
    "Transaction": ["Purchase", "Purchase"],
    "Size Range": ["$500K-$1M", "$250K-$500K"],
    "Value ($)": [750000, 375000],
    "Published Date": [today - timedelta(days=1), today - timedelta(days=2)],
    "filed_after_days": [2, 3],
    "party": ["Democrat", "Republican"],
    "chamber": ["House", "Senate"],
}
trades_df = pd.DataFrame(trades_data)

alert = InsiderAlert(
    signal_type="Congressional Cluster Buy",
    ticker="MSFT",
    company_name="Microsoft Corporation",
    trades=trades_df,
    details={
        "bipartisan": True,
        "insider_count": 2,
        "total_value": 1125000,
        "politicians": ["Nancy Pelosi", "Ted Cruz"],
        "avg_days_to_file": 2.5,
        "issuer_id": "433382",  # MSFT issuer ID on Capitol Trades
    },
)
alert.alert_id = f"TEST_CONGRESS_{today.strftime('%Y%m%d_%H%M%S')}"

print(f"Alert ID:  {alert.alert_id}")
print(f"Signal:    {alert.signal_type}")
print(f"Ticker:    {alert.ticker} ({alert.company_name})")
print()

# Email only — do not send test Telegram messages
email_ok = send_email_alert(alert, dry_run=False, subject_prefix="[TEST] ")
print(f"Email: {'OK' if email_ok else 'FAIL'}")
