#!/usr/bin/env python3
"""
Test all signal types by sending each one to Telegram
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from insider_alerts import (
    parse_openinsider,
    detect_signals,
    send_telegram_alert,
    logger
)

load_dotenv()

def main():
    # Load fixture data
    fixture_path = Path("tests/fixtures/sample_openinsider.html")
    
    if not fixture_path.exists():
        print(f"❌ Fixture file not found: {fixture_path}")
        return
    
    print("Parsing fixture data...")
    with open(fixture_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    df = parse_openinsider(html)
    print(f"Found {len(df)} trades\n")
    
    # Detect all signals
    print("Detecting signals...")
    signals = detect_signals(df)
    print(f"Found {len(signals)} signals\n")
    
    # Group signals by type
    signal_types = {}
    for signal in signals:
        sig_type = signal.signal_type
        if sig_type not in signal_types:
            signal_types[sig_type] = []
        signal_types[sig_type].append(signal)
    
    # Send one example of each signal type
    print(f"Sending {len(signal_types)} different signal types to Telegram...\n")
    
    for idx, (sig_type, alerts) in enumerate(signal_types.items(), 1):
        # Pick first alert of this type
        alert = alerts[0]
        
        print(f"{idx}. Sending: {sig_type} - {alert.ticker}")
        success = send_telegram_alert(alert, dry_run=False)
        
        if success:
            print(f"   ✅ Sent successfully\n")
        else:
            print(f"   ❌ Failed to send\n")
        
        # Small delay between messages to avoid rate limiting
        if idx < len(signal_types):
            import time
            time.sleep(1)
    
    print("=" * 60)
    print(f"✅ Done! Sent {len(signal_types)} different signal examples")
    print("Check your Telegram group for all the messages")

if __name__ == "__main__":
    main()
