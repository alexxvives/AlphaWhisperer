#!/usr/bin/env python3
"""
Test script to send a sample email alert with the new v1.1 format.
Uses fake NVDA data to demonstrate the email template.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Verify SMTP credentials are configured
smtp_user = os.getenv("SMTP_USER", "")
smtp_pass = os.getenv("SMTP_PASS", "")
alert_to = os.getenv("ALERT_TO", "")

if not all([smtp_user, smtp_pass, alert_to]):
    print("ERROR: SMTP credentials not configured in .env file.")
    print(f"  SMTP_USER: {'set' if smtp_user else 'MISSING'}")
    print(f"  SMTP_PASS: {'set' if smtp_pass else 'MISSING'}")
    print(f"  ALERT_TO:  {'set' if alert_to else 'MISSING'}")
    sys.exit(1)

print(f"Sending test email to: {alert_to}")
print(f"From: {smtp_user}")

# Import from insider_alerts after dotenv is loaded
from insider_alerts import (
    InsiderAlert,
    format_email_html,
    format_email_text,
    send_email_alert,
)

# Build fake NVDA insider trades DataFrame
today = datetime.now()
trades_data = {
    "Insider Name": [
        "Jensen Huang",
        "Colette Kress",
        "Ajay Puri",
        "Debora Shoquist",
        "Timothy Teter",
    ],
    "Title": ["CEO", "CFO", "EVP", "EVP Operations", "General Counsel"],
    "Trade Date": [
        today - timedelta(days=2),
        today - timedelta(days=3),
        today - timedelta(days=3),
        today - timedelta(days=4),
        today - timedelta(days=5),
    ],
    "Filing Date": [
        today - timedelta(days=1),
        today - timedelta(days=1),
        today - timedelta(days=2),
        today - timedelta(days=2),
        today - timedelta(days=3),
    ],
    "Transaction": ["Purchase", "Purchase", "Purchase", "Purchase", "Purchase"],
    "Qty": [15000, 8000, 5000, 3500, 2000],
    "Price": [134.50, 133.80, 134.20, 132.90, 133.10],
    "Value": [2017500, 1070400, 671000, 465150, 266200],
    "Delta Own": ["+12%", "+8%", "+15%", "+5%", "+3%"],
}

trades_df = pd.DataFrame(trades_data)

# Create a sample InsiderAlert
alert = InsiderAlert(
    signal_type="C-Suite Cluster Buy",
    ticker="NVDA",
    company_name="NVIDIA Corporation",
    trades=trades_df,
    details={
        "total_value": 4490250,
        "insider_count": 5,
        "avg_value": 898050,
        "days_span": 5,
        "titles": ["CEO", "CFO", "EVP", "EVP Operations", "General Counsel"],
    },
)

# Override alert_id to avoid dedup blocking
alert.alert_id = f"TEST_EMAIL_{today.strftime('%Y%m%d_%H%M%S')}"

print(f"\nAlert ID: {alert.alert_id}")
print(f"Signal: {alert.signal_type}")
print(f"Ticker: {alert.ticker} ({alert.company_name})")
print(f"Trades: {len(alert.trades)}")
print(f"\nSending email...")

result = send_email_alert(alert, dry_run=False, subject_prefix="[TEST] ")
if result:
    print("Test email sent successfully! Check your inbox.")
else:
    print("Failed to send test email. Check logs for details.")
