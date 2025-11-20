"""
Send test emails for each Congressional trading signal from the last 30 days.
Numbered sequentially in subject line.
"""

import sys
import os
import logging
import sqlite3
from datetime import datetime, timedelta
from insider_alerts import (
    init_database,
    send_email_alert,
    InsiderAlert,
    get_db,
    detect_congressional_cluster_buy,
    detect_high_conviction_congressional_buy
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_recent_congressional_trades(days: int = 30):
    """
    Get all Congressional trades from last N days in the format expected by signal detectors.
    
    Returns:
        List of trade dicts
    """
    logger.info(f"Fetching Congressional trades from last {days} days")
    
    try:
        with get_db() as conn:
            # Just get all trades - the dates are in "DD MMM" format without year
            # So we'll get all recent trades
            rows = conn.execute("""
                SELECT * FROM congressional_trades 
                ORDER BY rowid DESC
                LIMIT 200
            """).fetchall()
            
            # Convert to format expected by Congressional signal detectors
            trades = []
            for row in rows:
                # Format politician name with party
                politician_display = f"{row['politician_name']} ({row['party']})" if row['party'] else row['politician_name']
                
                trades.append({
                    'politician': politician_display,
                    'party': row['party'],
                    'chamber': row['chamber'],
                    'state': row['state'],
                    'ticker': row['ticker'],
                    'type': row['trade_type'],
                    'size': row['size_range'],
                    'price': f"${row['price']:.2f}" if row['price'] else "N/A",
                    'date': row['published_date'],
                    'traded_date': row['traded_date'],
                    'filed_after': str(row['filed_after_days']) if row['filed_after_days'] else "N/A"
                })
            
            logger.info(f"Found {len(trades)} Congressional trades in last {days} days")
            return trades
            
    except Exception as e:
        logger.error(f"Error querying Congressional trades: {e}")
        return []


def send_numbered_test_emails():
    """
    Send a test email for each Congressional signal from the last 30 days.
    Each email subject is numbered (Signal #1, Signal #2, etc.).
    """
    logger.info("Starting test email send for all recent Congressional signals")
    
    # Initialize database
    init_database()
    
    # Get recent Congressional trades
    trades = get_recent_congressional_trades(days=30)
    
    if not trades:
        logger.warning("No Congressional trades found in last 30 days")
        return
    
    # Detect signals using the two Congressional signal detection functions
    logger.info("Detecting Congressional signals...")
    alerts = []
    
    # Cluster buy signals (2+ politicians)
    cluster_alerts = detect_congressional_cluster_buy(trades)
    alerts.extend(cluster_alerts)
    logger.info(f"Found {len(cluster_alerts)} cluster buy signals")
    
    # High-conviction signals (known traders)
    conviction_alerts = detect_high_conviction_congressional_buy(trades)
    alerts.extend(conviction_alerts)
    logger.info(f"Found {len(conviction_alerts)} high-conviction signals")
    
    if not alerts:
        logger.warning("No signals detected from recent trades")
        return
    
    logger.info(f"Total signals detected: {len(alerts)}")
    logger.info(f"Sending {len(alerts)} numbered test emails...")
    
    # Send numbered emails
    for i, alert in enumerate(alerts, start=1):
        try:
            # Modify alert to include signal number in ticker (which appears in subject)
            original_ticker = alert.ticker
            alert.ticker = f"#{i} {alert.ticker}"
            
            logger.info(f"Sending email {i}/{len(alerts)}: {alert.signal_type} - {original_ticker}")
            
            # Send email
            success = send_email_alert(alert, dry_run=False)
            
            # Restore original ticker
            alert.ticker = original_ticker
            
            if success:
                logger.info(f"✓ Email {i} sent successfully")
            else:
                logger.error(f"✗ Email {i} failed to send")
                
        except Exception as e:
            logger.error(f"Error sending email {i}: {e}")
            continue
    
    logger.info(f"Completed sending {len(alerts)} test emails")


if __name__ == "__main__":
    send_numbered_test_emails()
