import sqlite3
import yfinance as yf
from datetime import datetime, timedelta

conn = sqlite3.connect('data/alphaWhisperer.db')

# Get congressional alerts
rows = conn.execute(
    "SELECT ticker, signal_date, signal_type FROM sent_alerts WHERE signal_type LIKE '%Congressional%' ORDER BY signal_date"
).fetchall()

print("Congressional signals sent:")
for ticker, signal_date, signal_type in rows:
    print(f"  {ticker} on {signal_date} ({signal_type})")

    # Fetch forward returns
    try:
        date_obj = datetime.strptime(signal_date[:10], "%Y-%m-%d")
        end_date = date_obj + timedelta(days=100)
        hist = yf.download(ticker, start=signal_date[:10], end=end_date.strftime("%Y-%m-%d"), progress=False)
        if len(hist) >= 2:
            start_price = hist['Close'].iloc[0]
            for label, days in [('7d', 5), ('30d', 21), ('60d', 42), ('90d', 63)]:
                if len(hist) > days:
                    ret = (hist['Close'].iloc[days] - start_price) / start_price * 100
                    print(f"    {label}: {ret.item():.1f}%")
    except Exception as e:
        print(f"    Error: {e}")
