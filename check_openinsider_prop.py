import requests
import pandas as pd
from io import StringIO

# Fetch OpenInsider page
url = "http://openinsider.com/latest-insider-trading"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

response = requests.get(url, headers=headers, timeout=30)
html = response.text

# Parse with pandas
tables = pd.read_html(StringIO(html))

# Find the trades table
for idx, table in enumerate(tables):
    table.columns = [str(col).strip() for col in table.columns]
    if "Ticker" in table.columns:
        # Filter for PROP
        prop_trades = table[table['Ticker'] == 'PROP']
        
        if len(prop_trades) > 0:
            print(f'Found {len(prop_trades)} PROP trade(s) on OpenInsider latest page:')
            print('-' * 120)
            print(prop_trades.to_string())
        else:
            print('No PROP trades found on OpenInsider latest page')
        break
