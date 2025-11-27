"""
Unified Daily Alert Runner
Runs both insider alert detection/sending AND ticker tracking bot.
Use this single script for daily automation at 8am.
"""

import logging
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/daily_alerts.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Run all daily alert tasks."""
    try:
        # Ensure logs directory exists
        Path('logs').mkdir(exist_ok=True)
        
        logger.info("="*60)
        logger.info("STARTING DAILY INSIDER ALERTS")
        logger.info("="*60)
        
        # STEP 1: Check for Telegram messages first (to update tracked tickers)
        logger.info("Step 1: Checking Telegram for ticker tracking requests...")
        try:
            import telegram_tracker_polling
            telegram_tracker_polling.main()
            logger.info("Telegram bot processing complete")
        except Exception as e:
            logger.warning(f"Telegram bot processing failed: {e}")
        
        # STEP 2: Run insider alert detection (now includes newly tracked tickers)
        logger.info("\nStep 2: Running insider alert detection and sending...")
        import insider_alerts
        insider_alerts.main()
        
        logger.info("="*60)
        logger.info("DAILY INSIDER ALERTS COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error running daily alerts: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
