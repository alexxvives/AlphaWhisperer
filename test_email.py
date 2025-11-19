#!/usr/bin/env python3
"""Test email with fixture data"""

from pathlib import Path
from insider_alerts import parse_openinsider, detect_signals, send_email_alert

# Load fixture
fixture_path = Path("tests/fixtures/sample_openinsider.html")
with open(fixture_path) as f:
    html = f.read()

# Parse and detect
print("Parsing fixture data...")
df = parse_openinsider(html)
print(f"Found {len(df)} trades")

print("\nDetecting signals...")
alerts = detect_signals(df)
print(f"Found {len(alerts)} signals")

if alerts:
    print(f"\nSending test email with first alert: {alerts[0].signal_type} - {alerts[0].ticker}")
    success = send_email_alert(alerts[0], dry_run=False)
    if success:
        print("✅ Email sent! Check your inbox: alexxvives@gmail.com")
    else:
        print("❌ Email failed - check logs/insider_alerts.log")
else:
    print("No alerts found")
