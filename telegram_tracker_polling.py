#!/usr/bin/env python3
"""
Telegram Ticker Tracker - Polling Mode for GitHub Actions

This version uses getUpdates polling instead of long-running webhook.
Designed to run every 5 minutes via GitHub Actions cron job.

Stores the last processed update_id in the database to avoid duplicate processing.
"""

import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

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
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Database configuration
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_FILE = DB_DIR / "alphaWhisperer.db"


def init_tracking_db():
    """Initialize the ticker tracking database with bot state table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create table for user ticker tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_tickers (
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
        ON tracked_tickers(ticker)
    """)
    
    # Create table for bot state (stores last update_id)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Ticker tracking database initialized at {DB_FILE}")


def get_last_update_id() -> int:
    """Get the last processed update_id from database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM bot_state WHERE key = 'last_update_id'")
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return int(result[0])
    return 0


def save_last_update_id(update_id: int):
    """Save the last processed update_id to database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO bot_state (key, value, updated_at)
        VALUES ('last_update_id', ?, ?)
    """, (str(update_id), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    logger.info(f"Saved last_update_id: {update_id}")


def add_ticker_for_user(user_id: str, username: str, first_name: str, ticker: str) -> bool:
    """Add a ticker to user's watchlist."""
    ticker = ticker.upper().strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO tracked_tickers (user_id, username, first_name, ticker, added_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, ticker, datetime.now().isoformat()))
        
        conn.commit()
        logger.info(f"Added ticker {ticker} for user {username} ({user_id})")
        return True
        
    except sqlite3.IntegrityError:
        logger.info(f"Ticker {ticker} already tracked by user {username}")
        return False
        
    finally:
        conn.close()


def remove_ticker_for_user(user_id: str, ticker: str) -> bool:
    """Remove a ticker from user's watchlist."""
    ticker = ticker.upper().strip()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM tracked_tickers
        WHERE user_id = ? AND ticker = ?
    """, (user_id, ticker))
    
    rows_deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    if rows_deleted > 0:
        logger.info(f"Removed ticker {ticker} for user {user_id}")
        return True
    return False


def get_user_tickers(user_id: str) -> List[str]:
    """Get all tickers tracked by a user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ticker FROM tracked_tickers
        WHERE user_id = ?
        ORDER BY ticker
    """, (user_id,))
    
    tickers = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return tickers


def send_message(chat_id: int, text: str) -> bool:
    """Send a message via Telegram API."""
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Sent message to chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return False


def process_message(message: Dict) -> Optional[str]:
    """
    Process a message and return response text.
    
    Args:
        message: Telegram message dict
        
    Returns:
        Response text to send, or None if no response needed
    """
    text = message.get("text", "")
    user = message.get("from", {})
    user_id = str(user.get("id", ""))
    username = user.get("username", "")
    first_name = user.get("first_name", "")
    
    # Check if bot is mentioned
    if "@bot" not in text.lower():
        return None
    
    # Check for "list" command first
    if re.search(r"@bot\s+list", text, re.IGNORECASE):
        tickers = get_user_tickers(user_id)
        if tickers:
            ticker_list = ", ".join([f"${t}" for t in tickers])
            return f"Your tracked tickers:\n{ticker_list}\n\nYou'll be notified of any insider trades for these stocks."
        else:
            return "You're not tracking any tickers yet.\n\nTo track a ticker, message: @bot $TICKER"
    
    # Extract tickers
    is_remove = "remove" in text.lower()
    bot_pos = text.lower().find("@bot")
    text_after_bot = text[bot_pos + 4:]
    
    tickers = re.findall(r'\$?([A-Z]{1,5})', text_after_bot)
    tickers = [t.upper() for t in tickers if t.upper() not in ["REMOVE", "LIST", "BOT"]]
    
    if not tickers:
        return ("Usage:\n"
                "- Track: @bot $TICKER\n"
                "- Track multiple: @bot $AAPL, $TSLA, $NVDA\n"
                "- Remove: @bot remove $TICKER\n"
                "- Remove multiple: @bot remove $AAPL, $TSLA\n"
                "- List: @bot list")
    
    # Process tickers
    results = []
    
    if is_remove:
        for ticker in tickers:
            success = remove_ticker_for_user(user_id, ticker)
            results.append(f"{'✓' if success else '✗'} {'Stopped' if success else 'Not'} tracking ${ticker}")
    else:
        for ticker in tickers:
            success = add_ticker_for_user(user_id, username, first_name, ticker)
            if success:
                results.append(f"✓ Now tracking ${ticker}")
            else:
                results.append(f"ℹ Already tracking ${ticker}")
    
    response = "\n".join(results)
    if len(tickers) > 1:
        suffix = "\n\nYou'll no longer receive alerts for these tickers." if is_remove else "\n\nI'll notify you whenever there's insider trading activity for these stocks."
    else:
        suffix = "\n\nYou'll no longer receive alerts for this ticker." if is_remove else "\n\nI'll notify you whenever there's insider trading activity for this stock."
    
    return response + suffix


def get_updates(offset: int = 0, limit: int = 100, timeout: int = 0) -> List[Dict]:
    """
    Get updates from Telegram using getUpdates method.
    
    Args:
        offset: Identifier of the first update to be returned
        limit: Limits the number of updates to be retrieved
        timeout: Timeout in seconds for long polling
        
    Returns:
        List of update dicts
    """
    try:
        response = requests.get(
            f"{TELEGRAM_API_URL}/getUpdates",
            params={"offset": offset, "limit": limit, "timeout": timeout},
            timeout=timeout + 5
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            return data.get("result", [])
        else:
            logger.error(f"Telegram API error: {data}")
            return []
            
    except Exception as e:
        logger.error(f"Failed to get updates: {e}")
        return []


def main():
    """Main polling loop - runs once and exits."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        sys.exit(1)
    
    # Initialize database
    init_tracking_db()
    
    # Get last processed update_id
    last_update_id = get_last_update_id()
    logger.info(f"Last processed update_id: {last_update_id}")
    
    # Get new updates (offset = last_update_id + 1)
    updates = get_updates(offset=last_update_id + 1, limit=100, timeout=0)
    
    if not updates:
        logger.info("No new updates")
        return
    
    logger.info(f"Processing {len(updates)} new update(s)")
    
    # Process each update
    processed_count = 0
    for update in updates:
        update_id = update.get("update_id")
        message = update.get("message")
        
        if not message:
            # Update last_update_id even if no message
            if update_id > last_update_id:
                last_update_id = update_id
            continue
        
        chat_id = message.get("chat", {}).get("id")
        
        # Process message and get response
        response_text = process_message(message)
        
        if response_text:
            send_message(chat_id, response_text)
            processed_count += 1
        
        # Update last_update_id
        if update_id > last_update_id:
            last_update_id = update_id
    
    # Save the latest update_id
    if last_update_id > get_last_update_id():
        save_last_update_id(last_update_id)
    
    logger.info(f"Processed {processed_count} message(s), last_update_id now: {last_update_id}")


if __name__ == "__main__":
    main()
