#!/usr/bin/env python3
"""
Main script to:
1. Scrape fresh Congressional trades (last few days)
2. Scrape fresh OpenInsider trades
3. Detect all signal types
4. Send email and Telegram alerts for any signals found
"""

import logging
from insider_alerts import (
    scrape_all_congressional_trades_to_db,
    get_congressional_trades,
    detect_congressional_cluster_buy,
    detect_high_conviction_congressional_buy,
    fetch_openinsider_html,
    parse_openinsider,
    store_openinsider_trades,
    filter_by_lookback,
    detect_signals,
    send_email_alert,
    send_telegram_alert
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("STARTING ALERT SCAN")
    logger.info("="*60)
    
    # Step 1: Scrape fresh Congressional trades (last 7 days worth)
    logger.info("\n[1/5] Scraping Congressional trades (last 7 days)...")
    try:
        scrape_all_congressional_trades_to_db(days=7, max_pages=5)
        logger.info("✓ Congressional scrape complete")
    except Exception as e:
        logger.error(f"✗ Congressional scrape failed: {e}")
    
    # Step 2: Get Congressional trades and detect signals
    logger.info("\n[2/5] Detecting Congressional signals...")
    congressional_alerts = []
    try:
        trades = get_congressional_trades()
        logger.info(f"Found {len(trades)} Congressional trades in database")
        
        cluster_alerts = detect_congressional_cluster_buy(trades)
        conviction_alerts = detect_high_conviction_congressional_buy(trades)
        
        congressional_alerts = cluster_alerts + conviction_alerts
        logger.info(f"✓ Found {len(congressional_alerts)} Congressional signals")
        
    except Exception as e:
        logger.error(f"✗ Congressional detection failed: {e}")
    
    # Step 3: Scrape OpenInsider
    logger.info("\n[3/5] Scraping OpenInsider trades...")
    openinsider_alerts = []
    try:
        html = fetch_openinsider_html()
        df = parse_openinsider(html)
        logger.info(f"Found {len(df)} OpenInsider trades")
        
        # Store in database
        new_trades = store_openinsider_trades(df)
        logger.info(f"Stored {new_trades} new trades in database")
        
        # Filter to recent trades (last 7 days)
        df_recent = filter_by_lookback(df, lookback_days=7)
        logger.info(f"Filtered to {len(df_recent)} recent trades")
        
        # Detect signals
        openinsider_alerts = detect_signals(df_recent)
        logger.info(f"✓ Found {len(openinsider_alerts)} OpenInsider signals")
        
    except Exception as e:
        logger.error(f"✗ OpenInsider scrape/detection failed: {e}")
    
    # Step 4: Combine all alerts
    all_alerts = congressional_alerts + openinsider_alerts
    logger.info(f"\n[4/5] Total alerts: {len(all_alerts)}")
    
    if not all_alerts:
        logger.info("No signals detected. Exiting.")
        return
    
    # Step 5: Send alerts
    logger.info(f"\n[5/5] Sending {len(all_alerts)} alerts...")
    
    for i, alert in enumerate(all_alerts, 1):
        logger.info(f"\n  [{i}/{len(all_alerts)}] {alert.signal_type} - {alert.ticker}")
        
        # Send email
        try:
            email_success = send_email_alert(alert, dry_run=False)
            if email_success:
                logger.info("    ✓ Email sent")
            else:
                logger.warning("    ✗ Email failed")
        except Exception as e:
            logger.error(f"    ✗ Email error: {e}")
        
        # Send Telegram
        try:
            telegram_success = send_telegram_alert(alert, dry_run=False)
            if telegram_success:
                logger.info("    ✓ Telegram sent")
            else:
                logger.warning("    ✗ Telegram failed")
        except Exception as e:
            logger.error(f"    ✗ Telegram error: {e}")
    
    logger.info("\n" + "="*60)
    logger.info(f"SCAN COMPLETE: {len(all_alerts)} alerts sent")
    logger.info("="*60)

if __name__ == "__main__":
    main()
