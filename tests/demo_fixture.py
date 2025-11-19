#!/usr/bin/env python3
"""
Demo script to test insider_alerts.py with the fixture file.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from insider_alerts import (
    detect_signals,
    filter_by_lookback,
    format_email_html,
    format_email_text,
    parse_openinsider,
)

# Load fixture
fixture_path = Path(__file__).parent / "fixtures" / "sample_openinsider.html"
with open(fixture_path, "r") as f:
    html = f.read()

# Parse
print("=" * 60)
print("PARSING FIXTURE DATA")
print("=" * 60)
df = parse_openinsider(html)
print(f"\nParsed {len(df)} trades")
print(f"\nColumns: {list(df.columns)}")
print(f"\nSample data:")
print(df[["Ticker", "Insider Name", "Trade Type", "Value", "Trade Date"]].head(10))

# Detect signals
print("\n" + "=" * 60)
print("DETECTING SIGNALS")
print("=" * 60)
alerts = detect_signals(df)
print(f"\nFound {len(alerts)} signals:")

for alert in alerts:
    print(f"\n{'-' * 60}")
    print(f"Signal: {alert.signal_type}")
    print(f"Ticker: {alert.ticker}")
    print(f"Company: {alert.company_name}")
    print(f"Trades: {len(alert.trades)}")
    print(f"Details: {alert.details}")
    
    # Show email preview
    print(f"\n--- Email Preview (Text) ---")
    print(format_email_text(alert)[:500] + "...")

print("\n" + "=" * 60)
print("TEST COMPLETED SUCCESSFULLY")
print("=" * 60)
