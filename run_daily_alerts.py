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
        
        # Import insider_alerts and run main detection
        import insider_alerts
        
        logger.info("Running insider alert detection and sending...")
        insider_alerts.main()
        
        logger.info("="*60)
        logger.info("DAILY INSIDER ALERTS COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error running daily alerts: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
