"""
Telegram Bot Handler - Process position tracking commands
Reply to alert with: TICKER @PRICE to track position
"""
import os
import re
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from position_tracker import add_position, get_position_summary, close_position

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    
    # Pattern: TICKER @PRICE (e.g., "AAPL @175.50" or "NVDA @ 485.20")
    pattern = r'^([A-Z]{1,5})\s*@\s*(\d+\.?\d*)$'
    match = re.match(pattern, text, re.IGNORECASE)
    
    if match:
        ticker = match.group(1).upper()
        price = float(match.group(2))
        
        # Add position
        success = add_position(ticker, price)
        
        if success:
            response = f"""
✅ **Position Added**

📊 **Ticker:** {ticker}
💵 **Entry Price:** ${price:.2f}

I'll now monitor this position for bearish exit signals:
• Bearish cluster selling (3+ insiders)
• Stop loss (-10%)
• Momentum loss (5-day decline)

You'll get alerts when exit signals are detected.

Reply with `/positions` to see all tracked positions.
"""
        else:
            response = f"⚠️ Position for {ticker} already exists for today. Use a different command to update."
        
        await update.message.reply_text(response, parse_mode='Markdown')
        logger.info(f"Added position: {ticker} @ ${price:.2f}")
        return
    
    # Pattern: CLOSE TICKER @PRICE (e.g., "CLOSE AAPL @180.50")
    close_pattern = r'^CLOSE\s+([A-Z]{1,5})\s*@\s*(\d+\.?\d*)$'
    close_match = re.match(close_pattern, text, re.IGNORECASE)
    
    if close_match:
        ticker = close_match.group(1).upper()
        exit_price = float(close_match.group(2))
        
        success = close_position(ticker, exit_price, "Manual close")
        
        if success:
            # Calculate profit
            from position_tracker import init_positions_db
            import sqlite3
            
            init_positions_db()
            conn = sqlite3.connect("data/positions.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entry_price, profit_pct FROM positions
                WHERE ticker = ? AND status = 'CLOSED'
                ORDER BY exit_date DESC LIMIT 1
            """, (ticker,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                entry_price, profit_pct = result
                pnl_emoji = "📈" if profit_pct > 0 else "📉"
                
                response = f"""
✅ **Position Closed**

📊 **Ticker:** {ticker}
💵 **Entry:** ${entry_price:.2f}
💵 **Exit:** ${exit_price:.2f}
{pnl_emoji} **P/L:** {profit_pct:+.1f}%

Position has been closed. I'll stop monitoring exit signals for this ticker.
"""
            else:
                response = f"✅ Position closed for {ticker} @ ${exit_price:.2f}"
        else:
            response = f"⚠️ No open position found for {ticker}"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        logger.info(f"Closed position: {ticker} @ ${exit_price:.2f}")
        return


async def handle_positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command"""
    summary = get_position_summary()
    await update.message.reply_text(summary, parse_mode='Markdown')


def main():
    """Run the bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        return
    
    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Telegram bot started - listening for position tracking commands...")
    logger.info("Usage:")
    logger.info("  - Add position: TICKER @PRICE (e.g., 'AAPL @175.50')")
    logger.info("  - Close position: CLOSE TICKER @PRICE (e.g., 'CLOSE AAPL @180.50')")
    
    # Run bot
    app.run_polling()


if __name__ == "__main__":
    main()
