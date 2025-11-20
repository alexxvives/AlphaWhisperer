#!/usr/bin/env python3
"""Send a test Telegram message with sample signal"""

import logging
from insider_alerts import (
    scrape_all_congressional_trades_to_db,
    detect_high_conviction_congressional_buy,
    send_telegram_alert
)
import sqlite3

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # First, scrape fresh data
    logger.info("Scraping fresh Congressional trades...")
    scrape_all_congressional_trades_to_db(days=30, max_pages=10)  # Last 30 days, max 10 pages
    
    # Now query the database
    logger.info("Fetching trades from database...")
    conn = sqlite3.connect('data/congressional_trades.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT politician, ticker, type, size_range, transaction_date, published_date, price
        FROM congressional_trades
        WHERE type IN ('Purchase', 'purchase', 'BUY', 'buy')
        ORDER BY transaction_date DESC
        LIMIT 1000
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    # Convert to dict format
    trades = []
    for row in rows:
        trades.append({
            'politician': row[0],
            'ticker': row[1],
            'type': row[2],
            'size_range': row[3],
            'transaction_date': row[4],
            'published_date': row[5],
            'price': row[6]
        })
    
    logger.info(f"Found {len(trades)} Congressional BUY trades")
    
    logger.info("Detecting High-Conviction Congressional signals...")
    alerts = detect_high_conviction_congressional_buy(trades)
    logger.info(f"Found {len(alerts)} alerts")
    
    if alerts:
        alert = alerts[0]
        logger.info(f"\nSending Telegram message: {alert.signal_type} - {alert.ticker}")
        success = send_telegram_alert(alert, dry_run=False)
        
        if success:
            print("\n✅ Telegram message sent! Check your Telegram app")
        else:
            print("\n❌ Failed to send Telegram message")
    else:
        print("No alerts found to send")

if __name__ == "__main__":
    main()
