"""
Send one test email for each type of signal (both Congressional and OpenInsider).
"""

import logging
from insider_alerts import (
    init_database,
    send_email_alert,
    get_db,
    detect_congressional_cluster_buy,
    detect_high_conviction_congressional_buy,
    fetch_openinsider_html,
    parse_openinsider,
    filter_by_lookback,
    detect_signals
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_congressional_trades():
    """Get all Congressional trades from database."""
    logger.info("Fetching all Congressional trades")
    
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM congressional_trades 
                ORDER BY rowid DESC
            """).fetchall()
            
            # Convert to format expected by signal detectors
            trades = []
            for row in rows:
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
            
            logger.info(f"Found {len(trades)} Congressional trades total")
            return trades
            
    except Exception as e:
        logger.error(f"Error querying Congressional trades: {e}")
        return []


def send_one_of_each_signal():
    """
    Send ONE test email for each type of signal (Congressional and OpenInsider).
    """
    logger.info("Sending one test email per signal type")
    
    # Initialize database
    init_database()
    
    # ===== CONGRESSIONAL SIGNALS =====
    logger.info("\n" + "="*60)
    logger.info("PART 1: CONGRESSIONAL SIGNALS")
    logger.info("="*60)
    
    # Get all Congressional trades
    trades = get_all_congressional_trades()
    
    congressional_alerts = []
    if trades:
        # Detect Congressional signals
        logger.info("Detecting Congressional signals...")
        
        # Get cluster buy signals
        cluster_alerts = detect_congressional_cluster_buy(trades)
        logger.info(f"Found {len(cluster_alerts)} cluster buy signals")
        
        # Get high-conviction signals
        conviction_alerts = detect_high_conviction_congressional_buy(trades)
        logger.info(f"Found {len(conviction_alerts)} high-conviction signals")
        
        congressional_alerts = cluster_alerts + conviction_alerts
    else:
        logger.warning("No Congressional trades found")
    
    # ===== OPENINSIDER SIGNALS =====
    logger.info("\n" + "="*60)
    logger.info("PART 2: OPENINSIDER CORPORATE INSIDER SIGNALS")
    logger.info("="*60)
    
    openinsider_alerts = []
    try:
        # Fetch OpenInsider data
        logger.info("Fetching data from OpenInsider.com...")
        html = fetch_openinsider_html()
        
        # Parse data
        logger.info("Parsing OpenInsider data...")
        df = parse_openinsider(html)
        logger.info(f"Found {len(df)} trades on OpenInsider")
        
        # Filter by lookback period
        df = filter_by_lookback(df)
        logger.info(f"Filtered to {len(df)} recent trades")
        
        # Detect signals
        logger.info("Detecting OpenInsider signals...")
        openinsider_alerts = detect_signals(df)
        logger.info(f"Found {len(openinsider_alerts)} OpenInsider signals")
        
    except Exception as e:
        logger.error(f"Error fetching OpenInsider signals: {e}", exc_info=True)
    
    # ===== COMBINE AND SEND =====
    logger.info("\n" + "="*60)
    logger.info("SENDING TEST EMAILS")
    logger.info("="*60)
    
    # Group all signals by type to get one of each
    signal_types = {}
    
    for alert in congressional_alerts:
        signal_type = alert.signal_type
        if signal_type not in signal_types:
            signal_types[signal_type] = alert
    
    for alert in openinsider_alerts:
        signal_type = alert.signal_type
        if signal_type not in signal_types:
            signal_types[signal_type] = alert
    
    if not signal_types:
        logger.warning("No signals detected from either source")
        return
    
    logger.info(f"Found {len(signal_types)} unique signal types total")
    logger.info(f"  Congressional: {len([a for a in congressional_alerts if a.signal_type in signal_types])}")
    logger.info(f"  OpenInsider: {len([a for a in openinsider_alerts if a.signal_type in signal_types])}")
    
    # Send ONLY ONE email (first OpenInsider signal for testing)
    openinsider_signal = None
    for signal_type, alert in signal_types.items():
        if alert in openinsider_alerts:
            openinsider_signal = (signal_type, alert)
            break
    
    # If no OpenInsider signal, use first Congressional signal
    if not openinsider_signal:
        signal_type, alert = list(signal_types.items())[0]
    else:
        signal_type, alert = openinsider_signal
    
    try:
        source = "Congressional" if alert in congressional_alerts else "OpenInsider"
        logger.info(f"\nSending TEST email: {signal_type} - {alert.ticker} ({source})")
        
        # Send email with numbered subject
        success = send_email_alert(alert, dry_run=False, subject_prefix=f"TEST: ")
        
        if success:
            logger.info(f"Email sent successfully")
        else:
            logger.error(f"Email failed to send")
            
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Completed sending test email")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    send_one_of_each_signal()
