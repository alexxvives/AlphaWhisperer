#!/usr/bin/env python3
"""
Telegram Ticker Tracker

Allows users to track specific tickers by mentioning the bot with $TICKER.
When insider trades occur for tracked tickers, the bot will notify the user.

Usage in Telegram:
  @alphawhisperer_bot $AAPL    # Start tracking AAPL
  @alphawhisperer_bot remove $AAPL  # Stop tracking AAPL
  @alphawhisperer_bot list     # Show your tracked tickers
"""

import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Telegram bot configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "alphawhisperer_bot")

# Database configuration
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "ticker_tracking.db"


def init_tracking_db():
    """Initialize the ticker tracking database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create table for user ticker tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tickers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT,
            first_name TEXT,
            ticker TEXT NOT NULL,
            added_date TEXT NOT NULL,
            UNIQUE(user_id, ticker)
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticker 
        ON user_tickers(ticker)
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Ticker tracking database initialized at {DB_FILE}")


def add_ticker_for_user(user_id: str, username: str, first_name: str, ticker: str) -> bool:
    """
    Add a ticker to user's watchlist.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username
        first_name: User's first name
        ticker: Stock ticker symbol
        
    Returns:
        True if added successfully, False if already exists
    """
    ticker = ticker.upper().strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_tickers (user_id, username, first_name, ticker, added_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, ticker, datetime.now().isoformat()))
        
        conn.commit()
        logger.info(f"Added ticker {ticker} for user {username} ({user_id})")
        return True
        
    except sqlite3.IntegrityError:
        # Ticker already tracked by this user
        logger.info(f"Ticker {ticker} already tracked by user {username}")
        return False
        
    finally:
        conn.close()


def remove_ticker_for_user(user_id: str, ticker: str) -> bool:
    """
    Remove a ticker from user's watchlist.
    
    Args:
        user_id: Telegram user ID
        ticker: Stock ticker symbol
        
    Returns:
        True if removed successfully, False if not found
    """
    ticker = ticker.upper().strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM user_tickers
        WHERE user_id = ? AND ticker = ?
    """, (user_id, ticker))
    
    rows_deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    if rows_deleted > 0:
        logger.info(f"Removed ticker {ticker} for user {user_id}")
        return True
    else:
        logger.info(f"Ticker {ticker} not found for user {user_id}")
        return False


def get_user_tickers(user_id: str) -> List[str]:
    """
    Get all tickers tracked by a user.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        List of ticker symbols
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ticker FROM user_tickers
        WHERE user_id = ?
        ORDER BY ticker
    """, (user_id,))
    
    tickers = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return tickers


def get_users_tracking_ticker(ticker: str) -> List[Dict[str, str]]:
    """
    Get all users tracking a specific ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        List of dicts with user info: {user_id, username, first_name}
    """
    ticker = ticker.upper().strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, username, first_name
        FROM user_tickers
        WHERE ticker = ?
    """, (ticker,))
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2]
        })
    
    conn.close()
    return users


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages that mention the bot."""
    message = update.message
    
    if not message or not message.text:
        return
    
    text = message.text
    user = message.from_user
    
    # Check if bot is mentioned
    bot_mention = f"@bot"
    if bot_mention not in text.lower():
        return
    
    # Check for "list" command first (before ticker pattern)
    if re.search(r"@bot\s+list", text, re.IGNORECASE):
        tickers = get_user_tickers(str(user.id))
        if tickers:
            ticker_list = ", ".join([f"${t}" for t in tickers])
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"Your tracked tickers:\n{ticker_list}\n\nYou'll be notified of any insider trades for these stocks."
            )
        else:
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="You're not tracking any tickers yet.\n\nTo track a ticker, message: @bot $TICKER"
            )
        return
    
    # Extract command after bot mention
    # Pattern: @bot $TICKER1, $TICKER2 or @bot remove $TICKER1, $TICKER2
    # First check if this is a remove command
    is_remove = "remove" in text.lower()
    
    # Extract all tickers (with or without $)
    ticker_pattern = r'\$?([A-Z]{1,5})(?:\s*,\s*\$?([A-Z]{1,5}))*'
    
    # Find all tickers in the message after @bot
    bot_pos = text.lower().find("@bot")
    text_after_bot = text[bot_pos + 4:]  # Everything after @bot
    
    # Extract tickers
    tickers = re.findall(r'\$?([A-Z]{1,5})', text_after_bot)
    # Filter out "remove" and "list" keywords
    tickers = [t.upper() for t in tickers if t.upper() not in ["REMOVE", "LIST", "BOT"]]
    
    if not tickers:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="Usage:\n"
                 "- Track: @bot $TICKER\n"
                 "- Track multiple: @bot $AAPL, $TSLA, $NVDA\n"
                 "- Remove: @bot remove $TICKER\n"
                 "- Remove multiple: @bot remove $AAPL, $TSLA\n"
                 "- List: @bot list"
        )
        return
    
    # Process tickers (add or remove)
    results = []
    
    if is_remove:
        # Remove tickers
        for ticker in tickers:
            success = remove_ticker_for_user(str(user.id), ticker)
            if success:
                results.append(f"✓ Stopped tracking ${ticker}")
            else:
                results.append(f"✗ You weren't tracking ${ticker}")
    else:
        # Add tickers
        for ticker in tickers:
            success = add_ticker_for_user(
                str(user.id),
                user.username or "",
                user.first_name or "",
                ticker
            )
            if success:
                results.append(f"✓ Now tracking ${ticker}")
            else:
                results.append(f"ℹ Already tracking ${ticker}")
    
    # Send response
    response = "\n".join(results)
    if len(tickers) > 1:
        if is_remove:
            response += "\n\nYou'll no longer receive alerts for these tickers."
        else:
            response += "\n\nI'll notify you whenever there's insider trading activity for these stocks."
    else:
        if is_remove:
            response += "\n\nYou'll no longer receive alerts for this ticker."
        else:
            response += "\n\nI'll notify you whenever there's insider trading activity for this stock."
    
    await context.bot.send_message(
        chat_id=message.chat_id,
        text=response
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to the Insider Trading Tracker Bot!\n\n"
        "Track specific tickers:\n"
        "- Message: @bot $TICKER\n"
        "- Example: @bot $AAPL\n\n"
        "Stop tracking:\n"
        "- Message: @bot remove $TICKER\n\n"
        "View your list:\n"
        "- Message: @bot list\n\n"
        "I'll notify you with @mentions whenever insider trades happen for your tracked tickers!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "**Insider Trading Tracker Bot Help**\n\n"
        f"🔹 Track a ticker: @bot $TICKER\n"
        f"🔹 Stop tracking: @bot remove $TICKER\n"
        f"🔹 View your list: @bot list\n\n"
        "When insider trades occur for your tracked tickers, "
        "I'll send an alert and @mention you!"
    )


def run_bot():
    """Run the Telegram bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return
    
    # Initialize database
    init_tracking_db()
    
    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    logger.info("Starting Telegram tracker bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
