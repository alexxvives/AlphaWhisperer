#!/usr/bin/env python3
"""
Insider Trading Alert System

Monitors OpenInsider.com for significant insider trading activity and sends
email alerts when high-conviction signals are detected.

Author: Senior Python Engineer
Version: 1.0.0
"""

import argparse
import json
import logging
import os
import smtplib
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from io import BytesIO

import pandas as pd
import requests
# schedule is optional (only used for continuous mode, not run_once)
try:
    import schedule
except ImportError:
    schedule = None
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Load environment variables
load_dotenv()

# Configure logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "insider_alerts.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import Trinity Signal detection from dataroma_scraper (after logger setup)
try:
    from dataroma_scraper import detect_trinity_signals as dataroma_detect_trinity, detect_temporal_convergence
    DATAROMA_AVAILABLE = True
    logger.info("Trinity Signal detection enabled (dataroma_scraper.py found)")
except ImportError:
    logger.warning("dataroma_scraper.py not found - Trinity Signals disabled")
    DATAROMA_AVAILABLE = False

# Database for Congressional trades
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = DATA_DIR / "alphaWhisperer.db"

# Configuration from environment
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_TO = os.getenv("ALERT_TO", "")

# Telegram Configuration (optional)
USE_TELEGRAM = os.getenv("USE_TELEGRAM", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # Comma-separated for multiple accounts

# News API Configuration - REMOVED (not needed)
# USE_NEWS_CONTEXT = os.getenv("USE_NEWS_CONTEXT", "false").lower() == "true"
# NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Top Signals Configuration
TOP_SIGNALS_PER_DAY = int(os.getenv("TOP_SIGNALS_PER_DAY", "3"))  # Only report top N signals

# Congressional Trading (CapitolTrades)
USE_CAPITOL_TRADES = os.getenv("USE_CAPITOL_TRADES", "true").lower() == "true"
MIN_CONGRESSIONAL_CLUSTER = int(os.getenv("MIN_CONGRESSIONAL_CLUSTER", "2"))
CONGRESSIONAL_LOOKBACK_DAYS = int(os.getenv("CONGRESSIONAL_LOOKBACK_DAYS", "30"))

# Elite Congressional Traders - Top 15 proven performers (party irrelevant for filtering)
ELITE_CONGRESSIONAL_TRADERS = [
    "Nancy Pelosi", "Josh Gottheimer", "Ro Khanna", "Michael McCaul", 
    "Tommy Tuberville", "Markwayne Mullin", "Dan Crenshaw", "Brian Higgins",
    "Richard Blumenthal", "Debbie Wasserman Schultz", "Tom Kean Jr", 
    "Gil Cisneros", "Cleo Fields", "Marjorie Taylor Greene", "Lisa McClain"
]

LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))
CLUSTER_DAYS = int(os.getenv("CLUSTER_DAYS", "5"))
MIN_LARGE_BUY = float(os.getenv("MIN_LARGE_BUY", "500000"))  # Raised from 250K to reduce noise
MIN_CEO_CFO_BUY = float(os.getenv("MIN_CEO_CFO_BUY", "250000"))  # Raised from 100K to reduce noise
MIN_CLUSTER_BUY_VALUE = float(os.getenv("MIN_CLUSTER_BUY_VALUE", "300000"))
MIN_CLUSTER_INSIDERS = int(os.getenv("MIN_CLUSTER_INSIDERS", "5"))  # Require 5+ insiders (not 3)
MIN_CORP_PURCHASE = float(os.getenv("MIN_CORP_PURCHASE", "250000"))  # Minimum for corporation purchases
MIN_CONGRESSIONAL_CLUSTER_VALUE = float(os.getenv("MIN_CONGRESSIONAL_CLUSTER_VALUE", "50000"))  # Minimum total for Congressional cluster
MAX_FILING_DELAY_DAYS = int(os.getenv("MAX_FILING_DELAY_DAYS", "45"))  # Filter trades filed too late
MIN_FIRST_BUY_12M = float(os.getenv("MIN_FIRST_BUY_12M", "50000"))
MIN_SECTOR_CLUSTER_VALUE = float(os.getenv("MIN_SECTOR_CLUSTER_VALUE", "1000000"))
MIN_BEARISH_CLUSTER_VALUE = float(os.getenv("MIN_BEARISH_CLUSTER_VALUE", "1000000"))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# OpenInsider URLs
OPENINSIDER_URL = "http://openinsider.com/latest-insider-trading"
# Screener URL for last 30 days of trades (fd=30 means filed in last 30 days)
OPENINSIDER_LAST_WEEK_URL = "http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=30&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=1000&page={page}"
# Stop scraping if we see this many consecutive duplicates
DUPLICATE_THRESHOLD = 50

# Title normalization mapping
TITLE_MAPPING = {
    "chief executive officer": "CEO",
    "chief exec officer": "CEO",
    "ceo": "CEO",
    "president and ceo": "CEO",
    "pres. & ceo": "CEO",
    "chief financial officer": "CFO",
    "chief fin officer": "CFO",
    "cfo": "CFO",
    "vp & cfo": "CFO",
    "chief operating officer": "COO",
    "coo": "COO",
    "chief technology officer": "CTO",
    "cto": "CTO",
    "director": "Director",
    "dir": "Director",
    "board member": "Director",
    "chairman": "Chairman",
    "chair": "Chairman",
    "president": "President",
    "pres": "President",
}


class InsiderAlert:
    """Represents an insider trading alert."""
    
    def __init__(
        self,
        signal_type: str,
        ticker: str,
        company_name: str,
        trades: pd.DataFrame,
        details: Dict,
    ):
        self.signal_type = signal_type
        self.ticker = ticker
        self.company_name = company_name
        self.trades = trades
        self.details = details
        self.alert_id = self._generate_alert_id()
        
    def _generate_alert_id(self) -> str:
        """Generate simplified unique alert ID: {signal_type}_{ticker}_{investors}_{dates}."""
        from datetime import datetime
        
        ticker = self.ticker
        
        # Get unique investor names
        investors = sorted(set(self.trades['Insider Name'].tolist()))
        investors_str = "_".join([name.replace(" ", "")[:20] for name in investors[:5]])  # Max 5 names, 20 chars each
        
        # Get unique dates in day/month format
        dates = []
        for _, row in self.trades.iterrows():
            date_val = row.get('Trade Date') or row.get('Traded Date')
            if pd.notna(date_val):
                if isinstance(date_val, str):
                    try:
                        date_obj = datetime.strptime(date_val, "%Y-%m-%d")
                        dates.append(date_obj.strftime("%d/%m"))
                    except:
                        pass
                else:
                    dates.append(date_val.strftime("%d/%m"))
        
        dates_str = "_".join(sorted(set(dates))[:10])  # Max 10 unique dates
        
        return f"{self.signal_type}_{ticker}_{investors_str}_{dates_str}"


# ============================================================================
# Database Functions for Congressional Trades
# ============================================================================

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """
    Initialize SQLite database with schema for Congressional and OpenInsider trades.
    Creates tables if they don't exist, and handles schema migrations.
    
    Note: 
    - tracked_tickers table is managed by telegram_tracker_polling.py
    - politician_pnl table is for calculate_pnl.py (separate analysis script)
    """
    with get_db() as conn:
        # Main trades table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS congressional_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                politician_name TEXT NOT NULL,
                politician_id TEXT,
                party TEXT,
                chamber TEXT,
                state TEXT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                trade_type TEXT NOT NULL,
                size_range TEXT,
                price REAL,
                traded_date TEXT NOT NULL,
                published_date TEXT NOT NULL,
                filed_after_days INTEGER,
                issuer_id TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(politician_name, ticker, traded_date, trade_type, published_date)
            )
        """)
        
        # Schema migration: Add issuer_id column if it doesn't exist (for older databases)
        try:
            cursor = conn.execute("PRAGMA table_info(congressional_trades)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'issuer_id' not in columns:
                conn.execute("ALTER TABLE congressional_trades ADD COLUMN issuer_id TEXT")
                conn.commit()  # Ensure migration is committed immediately
                logger.info("Schema migration: Added issuer_id column to congressional_trades")
        except Exception as e:
            logger.error(f"Schema migration failed: {e}", exc_info=True)
        
        # Create indices for faster queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON congressional_trades(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traded_date ON congressional_trades(traded_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_published_date ON congressional_trades(published_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON congressional_trades(scraped_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_politician_id ON congressional_trades(politician_id)")
        
        # Politician P&L stats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS politician_pnl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                politician_id TEXT NOT NULL,
                politician_name TEXT NOT NULL,
                party TEXT,
                state TEXT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                shares_held REAL,
                avg_cost_basis REAL,
                current_price REAL,
                position_value REAL,
                unrealized_pnl REAL,
                realized_pnl REAL,
                total_pnl REAL,
                return_percent REAL,
                trades_count INTEGER,
                status TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(politician_id, ticker)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_politician ON politician_pnl(politician_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_ticker ON politician_pnl(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_total ON politician_pnl(total_pnl)")
        
        # OpenInsider corporate trades table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS openinsider_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                insider_name TEXT NOT NULL,
                insider_title TEXT,
                trade_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                value REAL,
                qty INTEGER,
                owned INTEGER,
                delta_own REAL,
                price REAL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, insider_name, trade_date, value, trade_type)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oi_ticker ON openinsider_trades(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oi_trade_date ON openinsider_trades(trade_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oi_scraped_at ON openinsider_trades(scraped_at)")
        
        # Superinvestor holdings table (Dataroma 13F filings)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dataroma_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manager_code TEXT NOT NULL,
                manager_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                portfolio_pct REAL,
                shares_held INTEGER,
                value_usd REAL,
                quarter TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(manager_code, ticker, quarter)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dataroma_ticker ON dataroma_holdings(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dataroma_manager ON dataroma_holdings(manager_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dataroma_quarter ON dataroma_holdings(quarter)")
        
        # Sent alerts tracking table (prevent duplicate alerts)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sent_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL UNIQUE,
                ticker TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_alert_id ON sent_alerts(alert_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_ticker ON sent_alerts(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_expires ON sent_alerts(expires_at)")
        
        # Tracked tickers table (for Telegram bot ticker monitoring feature)
        conn.execute("""
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
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_ticker ON tracked_tickers(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_user ON tracked_tickers(user_id)")
        
        conn.commit()
    
    logger.info(f"Database initialized at {DB_FILE}")

def is_alert_already_sent(alert_id: str) -> bool:
    """Check if an alert was already sent (and not expired)."""
    try:
        with get_db() as conn:
            result = conn.execute("""
                SELECT COUNT(*) FROM sent_alerts 
                WHERE alert_id = ? 
                AND (expires_at IS NULL OR expires_at > datetime('now'))
            """, (alert_id,)).fetchone()
            return result[0] > 0
    except Exception as e:
        logger.error(f"Error checking sent alert: {e}")
        return False

def mark_alert_as_sent(alert_id: str, ticker: str, signal_type: str, expires_days: int = 30, test_mode: bool = False):
    """Mark an alert as sent to prevent duplicates (expires in 30 days)."""
    if test_mode:
        logger.info(f"[TEST MODE] Would mark alert as sent: {alert_id} (expires in {expires_days} days)")
        return
    
    try:
        with get_db() as conn:
            expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
            conn.execute("""
                INSERT OR REPLACE INTO sent_alerts (alert_id, ticker, signal_type, sent_at, expires_at)
                VALUES (?, ?, ?, datetime('now'), ?)
            """, (alert_id, ticker, signal_type, expires_at))
            conn.commit()
            logger.info(f"Marked alert as sent: {alert_id} (expires in {expires_days} days)")
    except Exception as e:
        logger.error(f"Error marking alert as sent: {e}")

def cleanup_expired_alerts():
    """Remove expired alert records to keep database clean."""
    try:
        with get_db() as conn:
            result = conn.execute("""
                DELETE FROM sent_alerts 
                WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
            """)
            deleted = result.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired alert records")
    except Exception as e:
        logger.error(f"Error cleaning up expired alerts: {e}")

def get_last_scrape_time() -> Optional[datetime]:
    """Get timestamp of most recent scrape"""
    try:
        with get_db() as conn:
            result = conn.execute("SELECT MAX(scraped_at) FROM congressional_trades").fetchone()
            if result[0]:
                return datetime.fromisoformat(result[0])
    except:
        return None
    return None

def get_ticker_trades_from_db(ticker: str, limit: int = 50) -> List[Dict]:
    """Query database for Congressional trades on a specific ticker"""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM congressional_trades 
                WHERE ticker = ? 
                ORDER BY published_date DESC 
                LIMIT ?
            """, (ticker, limit)).fetchall()
            
            # Convert to dict format matching current code expectations
            trades = []
            for row in rows:
                trades.append({
                    'politician': row['politician_name'],
                    'politician_id': row['politician_id'],
                    'party': row['party'],
                    'chamber': row['chamber'],
                    'state': row['state'],
                    'ticker': row['ticker'],
                    'type': row['trade_type'],
                    'size': row['size_range'],
                    'price': f"${row['price']:.2f}" if row['price'] else "N/A",
                    'price_numeric': row['price'],
                    'traded_date': row['traded_date'],
                    'published_date': row['published_date'],
                    'filed_after_days': str(row['filed_after_days']) if row['filed_after_days'] else "N/A",
                    'filed_after_days_numeric': row['filed_after_days'],
                    'owner': row['owner_type'],
                    'date': row['published_date']  # Use published_date for signal detection
                })
            
            return trades
    except Exception as e:
        logger.error(f"Error querying DB for ticker {ticker}: {e}")
        return []

def store_congressional_trade(trade: Dict) -> bool:
    """Store a single Congressional trade in database (with deduplication)"""
    try:
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO congressional_trades 
                (politician_name, politician_id, party, chamber, state, ticker, company_name,
                 trade_type, size_range, price, traded_date, published_date, 
                 filed_after_days, issuer_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.get('politician'),
                trade.get('politician_id'),
                trade.get('party'),
                trade.get('chamber'),
                trade.get('state'),
                trade.get('ticker'),
                trade.get('company_name'),
                trade.get('type'),
                trade.get('size'),
                trade.get('price_numeric'),
                trade.get('traded_date'),
                trade.get('published_date'),
                trade.get('filed_after_days_numeric'),
                trade.get('issuer_id')
            ))
            conn.commit()
            return cursor.rowcount > 0  # True if new row inserted
    except Exception as e:
        logger.error(f"Error storing trade: {e}")
        return False


def get_company_context(ticker: str) -> Dict[str, any]:
    """
    Get comprehensive company context including financials, price action, and news.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary with company context or empty dict if error
    """
    context = {
        "description": None,
        "sector": None,
        "industry": None,
        "market_cap": None,
        "pe_ratio": None,
        "short_interest": None,
        "price_change_5d": None,
        "price_change_1m": None,
        "current_price": None,
        "week_52_high": None,
        "week_52_low": None,
        "distance_from_52w_high": None,
        "distance_from_52w_low": None,
        "news": [],
        "congressional_trades": []
    }
    
    try:
        import yfinance as yf
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Company info
        context["company_name"] = info.get("longName", info.get("shortName", ticker))
        context["description"] = info.get("longBusinessSummary", "")
        context["sector"] = info.get("sector", "")
        context["industry"] = info.get("industry", "")
        context["market_cap"] = info.get("marketCap")
        context["pe_ratio"] = info.get("trailingPE")
        context["short_interest"] = info.get("shortPercentOfFloat")
        
        # 52-week range
        context["week_52_high"] = info.get("fiftyTwoWeekHigh")
        context["week_52_low"] = info.get("fiftyTwoWeekLow")
        context["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        
        # Calculate distance from 52w high/low
        if context["current_price"] and context["week_52_high"]:
            context["distance_from_52w_high"] = ((context["current_price"] - context["week_52_high"]) / context["week_52_high"]) * 100
        
        if context["current_price"] and context["week_52_low"]:
            context["distance_from_52w_low"] = ((context["current_price"] - context["week_52_low"]) / context["week_52_low"]) * 100
        
        # Get historical data for price changes
        try:
            hist = stock.history(period="1mo")
            if not hist.empty and len(hist) > 0:
                # 5-day change
                if len(hist) >= 5:
                    price_5d_ago = hist['Close'].iloc[-6] if len(hist) > 5 else hist['Close'].iloc[0]
                    current = hist['Close'].iloc[-1]
                    context["price_change_5d"] = ((current - price_5d_ago) / price_5d_ago) * 100
                
                # 1-month change
                price_1m_ago = hist['Close'].iloc[0]
                current = hist['Close'].iloc[-1]
                context["price_change_1m"] = ((current - price_1m_ago) / price_1m_ago) * 100
        except Exception as e:
            logger.warning(f"Could not fetch price history for {ticker}: {e}")
        
        logger.debug(f"Fetched company info for {ticker}")
        
    except Exception as e:
        logger.warning(f"Could not fetch company info for {ticker}: {e}")
    
    # NewsAPI integration removed - not needed for core signal detection
    
    # Get congressional trades
    context["congressional_trades"] = get_congressional_trades(ticker)
    
    return context


def get_congressional_trades(ticker: str = None) -> List[Dict]:
    """
    Get Congressional trades for a specific ticker.
    
    NEW APPROACH:
    1. Check if we need to refresh database (>1 hour old or empty)
    2. If refresh needed: Scrape ALL 30-day trades into SQLite
    3. Query database for ticker-specific trades
    4. Return filtered results
    
    Args:
        ticker: Stock ticker to filter by. If None, returns recent trades.
        
    Returns:
        List of congressional trades with full details
    """
    if not USE_CAPITOL_TRADES:
        return []
    
    # Initialize database if needed
    try:
        init_database()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return []
    
    # Data is now scraped explicitly in run_once() at the same time as OpenInsider
    # This function just queries the database
    
    # Query database for ticker-specific trades
    if ticker:
        trades = get_ticker_trades_from_db(ticker, limit=50)
        if trades:
            logger.debug(f"Found {len(trades)} Congressional trades for {ticker} in database")
        return trades
    else:
        # Return recent trades across all tickers
        try:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM congressional_trades 
                    ORDER BY scraped_at DESC 
                    LIMIT 15
                """).fetchall()
                
                trades = []
                for row in rows:
                    trades.append({
                        'politician': row['politician_name'],
                        'type': row['trade_type'],
                        'ticker': row['ticker'],
                        'size': row['size_range'],
                        'price': f"${row['price']:.2f}" if row['price'] else "N/A",
                        'date': row['traded_date']
                    })
                return trades
        except Exception as e:
            logger.error(f"Error querying recent trades: {e}")
            return []


def scrape_all_congressional_trades_to_db(days: int = None, max_pages: int = 500):
    """
    Scrape ALL Congressional trades and store in database.
    This is the main bulk scraping function with pagination support.
    
    Args:
        days: Number of days to look back (30, 90, 365, or None for ALL TIME - 3 YEARS filter)
        max_pages: Maximum number of pages to scrape (default 500 to handle all historical data)
    """
    driver = None
    new_trades_count = 0
    duplicate_count = 0
    total_pages = 0
    consecutive_duplicate_pages = 0  # Track pages with all duplicates
    
    # Calculate cutoff date for 30-day window
    from datetime import datetime, timedelta
    import re  # Need re for regex patterns
    cutoff_date = datetime.now() - timedelta(days=30)
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        import time
        
        # Configure Chrome for headless mode
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        logger.info(f"Starting bulk scrape of Congressional trades...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Navigate to trades page with pageSize parameter
        url = "https://www.capitoltrades.com/trades?pageSize=96"
        driver.get(url)
        
        # Wait for data rows to load (not just page skeleton)
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/politicians/']"))
            )
            time.sleep(2)  # Extra wait for all rows to render
            logger.info("Initial page data loaded")
        except Exception as e:
            logger.warning(f"Timeout waiting for initial page data: {e}")
            time.sleep(5)  # Fallback wait
        
        # Dismiss cookie banner if present
        try:
            cookie_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in cookie_buttons:
                if 'Accept' in btn.text and 'All' in btn.text:
                    btn.click()
                    logger.info("Dismissed cookie banner")
                    time.sleep(1)
                    break
        except:
            pass
        
        # Scrape all pages (with max limit)
        while total_pages < max_pages:
            total_pages += 1
            logger.info(f"Scraping page {total_pages}...")
            
            # Get rendered HTML
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Find all table rows
            all_rows = soup.find_all('tr')
            
            # Quick check: how many rows have politician links?
            politician_rows = [r for r in all_rows if r.find('a', href=lambda x: x and '/politicians/' in str(x))]
            logger.debug(f"Page {total_pages}: Found {len(all_rows)} total rows, {len(politician_rows)} with politician links")
            
            page_trades = 0
            page_dupes = 0
            rows_with_politician_link = 0
            
            for row in all_rows:
                try:
                    # Extract politician name and ID
                    politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                    if not politician_link:
                        continue
                    
                    rows_with_politician_link += 1
                    
                    politician_name = politician_link.get_text(strip=True)
                    politician_href = politician_link.get('href', '')
                    politician_id = politician_href.split('/')[-1] if politician_href else None
                    
                    # Processing row for politician
                    
                    # Get row text for parsing
                    row_text = row.get_text()
                    
                    # Extract party, chamber, state from first cell
                    # Format: "NamePartyChamberState" e.g. "Dave McCormickRepublicanSenatePA"
                    party = None
                    chamber = None
                    state = None
                    
                    cells = row.find_all('td')
                    if cells:
                        first_cell = cells[0].get_text(strip=True)
                        
                        # Extract party
                        if 'Republican' in first_cell:
                            party = 'R'
                        elif 'Democrat' in first_cell:
                            party = 'D'
                        elif 'Other' in first_cell:
                            party = 'O'
                        
                        # Extract chamber
                        if 'House' in first_cell:
                            chamber = 'House'
                        elif 'Senate' in first_cell:
                            chamber = 'Senate'
                        
                        # Extract state - last 2 characters after House/Senate
                        state_match = re.search(r'(House|Senate)([A-Z]{2})$', first_cell)
                        if state_match:
                            state = state_match.group(2)
                    
                    # Determine transaction type
                    trade_type = None
                    if 'buy' in row_text.lower() and 'sell' not in row_text.lower():
                        trade_type = 'BUY'
                    elif 'sell' in row_text.lower():
                        trade_type = 'SELL'
                    
                    if not trade_type:
                        continue
                    
                    # Extract ticker from span
                    ticker_found = None
                    ticker_span = row.find('span', class_='issuer-ticker')
                    if ticker_span:
                        ticker_text = ticker_span.get_text(strip=True)
                        ticker_match = re.search(r'([A-Z]{1,5}):(?:US|NYSE|NASDAQ)', ticker_text)
                        if ticker_match:
                            ticker_found = ticker_match.group(1)
                    
                    if not ticker_found:
                        continue
                    
                    # Extract company name and issuer_id
                    company_name = None
                    issuer_id = None
                    issuer_link = row.find('a', href=lambda x: x and '/issuers/' in str(x))
                    if issuer_link:
                        company_name = issuer_link.get_text(strip=True)
                        # Extract issuer_id from href (e.g., /issuers/AAPL-apple-inc -> AAPL-apple-inc)
                        issuer_href = issuer_link.get('href', '')
                        if '/issuers/' in issuer_href:
                            issuer_id = issuer_href.split('/issuers/')[-1].strip('/')
                    
                    # Extract dates, size, price from cells
                    published_date = None
                    traded_date = None
                    filed_after_days = None
                    size_range = None
                    price_numeric = None
                    
                    from datetime import datetime, timedelta
                    current_year = datetime.now().year
                    today = datetime.now().date()
                    yesterday = today - timedelta(days=1)
                    
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        cell_lower = cell_text.lower()
                        
                        # Find all dates in this cell (format: "27 Nov2025" or "27 Nov 2025")
                        all_date_matches = re.findall(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(20\d{2})', cell_text)
                        
                        if len(all_date_matches) >= 2:
                            # Two dates in same cell - first is published, second is traded
                            if not published_date:
                                try:
                                    day1, month1, year1 = all_date_matches[0]
                                    date_obj1 = datetime.strptime(f"{day1} {month1} {year1}", "%d %b %Y")
                                    published_date = date_obj1.strftime("%Y-%m-%d")
                                except:
                                    pass
                            if not traded_date:
                                try:
                                    day2, month2, year2 = all_date_matches[1]
                                    date_obj2 = datetime.strptime(f"{day2} {month2} {year2}", "%d %b %Y")
                                    traded_date = date_obj2.strftime("%Y-%m-%d")
                                except:
                                    pass
                        elif len(all_date_matches) == 1:
                            # Single date in cell - assign to published first, then traded
                            try:
                                day, month, year = all_date_matches[0]
                                date_obj = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
                                date_str = date_obj.strftime("%Y-%m-%d")
                                if not published_date:
                                    published_date = date_str
                                elif not traded_date:
                                    traded_date = date_str
                            except:
                                pass
                        
                        # Match published date with time (today/yesterday) - for recently filed
                        if not published_date:
                            time_match = re.search(r'\d{1,2}:\d{2}', cell_text)
                            if time_match:
                                # Look for today/yesterday in the same cell
                                if 'yesterday' in cell_lower:
                                    published_date = yesterday.strftime("%Y-%m-%d")
                                else:
                                    # Default to today if time is present (either says "today" or just time)
                                    published_date = today.strftime("%Y-%m-%d")
                        
                        # Match "Filed After" days - look in q-value span
                        if not filed_after_days:
                            # Check if this cell has the reporting-gap structure
                            gap_cell = cell.find('div', class_='cell--reporting-gap')
                            if gap_cell:
                                value_div = gap_cell.find('div', class_='q-value')
                                if value_div:
                                    try:
                                        filed_after_days = int(value_div.get_text(strip=True))
                                    except:
                                        pass
                        
                        # Match size range
                        if not size_range:
                            size_match = re.search(r'(\d+[KM][-–]\d+[KM])', cell_text, re.IGNORECASE)
                            if size_match:
                                size_range = size_match.group(1)
                        
                        # Match price
                        if not price_numeric:
                            price_match = re.search(r'\$(\d+(?:,\d+)?(?:\.\d{2})?)', cell_text)
                            if price_match:
                                try:
                                    price_numeric = float(price_match.group(1).replace(',', ''))
                                except:
                                    pass
                    
                    # Skip trades outside 30-day window (based on published_date)
                    if published_date:
                        try:
                            pub_date_obj = datetime.strptime(published_date, "%Y-%m-%d")
                            if pub_date_obj < cutoff_date:
                                logger.debug(f"Skipping trade published before cutoff: {published_date}")
                                continue
                        except:
                            pass
                    
                    # Skip trades filed more than 30 days after transaction
                    if filed_after_days and filed_after_days > 30:
                        logger.debug(f"Skipping trade filed {filed_after_days} days late (>30 day threshold)")
                        continue
                    
                    # Build trade dict
                    trade = {
                        'politician': politician_name,
                        'politician_id': politician_id,
                        'party': party,
                        'chamber': chamber,
                        'state': state,
                        'ticker': ticker_found,
                        'company_name': company_name,
                        'issuer_id': issuer_id,
                        'type': trade_type,
                        'size': size_range,
                        'price_numeric': price_numeric,
                        'traded_date': traded_date or published_date,
                        'published_date': published_date or traded_date,
                        'filed_after_days_numeric': filed_after_days,
                    }
                    
                    # Store in database (with deduplication)
                    if store_congressional_trade(trade):
                        new_trades_count += 1
                        page_trades += 1
                    else:
                        duplicate_count += 1
                        page_dupes += 1
                        
                except Exception as e:
                    logger.debug(f"Could not parse row: {e}")
                    continue
            
            logger.info(f"  Page {total_pages}: {page_trades} new, {page_dupes} duplicates")
            
            # Commit database every 10 pages to prevent data loss on timeout
            if total_pages % 10 == 0:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    conn.commit()
                    conn.close()
                    logger.info(f"Checkpoint: Database committed at page {total_pages}")
                except Exception as e:
                    logger.warning(f"Failed to commit database checkpoint: {e}")
            
            # Track consecutive pages with all duplicates (early stopping optimization)
            if page_trades == 0 and page_dupes > 0:
                consecutive_duplicate_pages += 1
                if consecutive_duplicate_pages >= 5:
                    logger.info(f"Found 5 consecutive pages with all duplicates - assuming rest is already in DB")
                    break
            else:
                consecutive_duplicate_pages = 0  # Reset counter if we found new trades
            
            # Stop early if we got zero trades on this page (means we're past the data or page didn't load)
            if page_trades == 0 and page_dupes == 0:
                logger.info(f"No trades found on page {total_pages} (rows_with_politician_link={rows_with_politician_link}, politician_rows={len(politician_rows)})")
                if rows_with_politician_link == 0:
                    logger.warning("Page may not have loaded properly - no politician links found")
                break
            
            # Stop if we hit max pages
            if total_pages >= max_pages:
                logger.info(f"Reached max pages limit ({max_pages})")
                break
            
            # Navigate to next page using URL (more reliable than clicking)
            try:
                next_page = total_pages + 1
                next_url = f"https://www.capitoltrades.com/trades?pageSize=96&page={next_page}"
                logger.info(f"Navigating to page {next_page}...")
                driver.get(next_url)
                
                # Wait for data rows to load (not just table skeleton)
                # Capitol Trades loads data via JavaScript, so table exists immediately
                # but rows with politician links are loaded asynchronously
                try:
                    # Wait for at least one politician link to appear (indicates data loaded)
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/politicians/']"))
                    )
                    time.sleep(2)  # Extra wait for all rows to render
                except Exception as e:
                    logger.warning(f"Timeout waiting for page {next_page} data to load: {e}")
                    # Try one more time with longer wait
                    time.sleep(5)
                    
            except Exception as e:
                logger.info(f"Reached last page or pagination error: {e}")
                break
        
        logger.info(f"Scrape complete: {new_trades_count} new trades, {duplicate_count} duplicates skipped across {total_pages} pages")
        
    except ImportError as e:
        logger.error(f"Selenium not installed. Run: pip install selenium webdriver-manager")
    except Exception as e:
        logger.error(f"Error during bulk scrape: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def get_congressional_trades_legacy(ticker: str = None) -> List[Dict]:
    """
    DEPRECATED: Old approach that scraped on-demand without database.
    Kept for reference only.
    """
    if not USE_CAPITOL_TRADES:
        return []
    
    trades = []
    driver = None
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        import time
        
        # Configure Chrome for headless mode (runs in background without window)
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Initialize Chrome driver (webdriver-manager handles driver download automatically)
        logger.info(f"Initializing Chrome WebDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(15)
        logger.info(f"Chrome WebDriver initialized successfully")
        
        # Visit trades page - filter by ticker if provided
        if ticker:
            url = f"https://www.capitoltrades.com/trades?txDate=all&pageSize=100&politician=all&asset={ticker}"
            logger.info(f"Fetching Congressional trades for {ticker}...")
        else:
            url = "https://www.capitoltrades.com/trades"
            logger.info(f"Fetching recent Congressional trades...")
        driver.get(url)
        
        # Wait for page to load and JavaScript to render
        time.sleep(4)
        
        # Get rendered HTML
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Find all table rows
        all_rows = soup.find_all('tr')
        
        for row in all_rows:
            try:
                # Extract politician name from link
                politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                if not politician_link:
                    continue
                
                politician_name = politician_link.get_text(strip=True)
                
                # Get row text
                row_text = row.get_text()
                
                # Extract party and chamber from row
                party_chamber = ""
                if 'Republican' in row_text:
                    party_chamber = " (R)"
                elif 'Democrat' in row_text:
                    party_chamber = " (D)"
                
                if 'House' in row_text:
                    party_chamber += "-House"
                elif 'Senate' in row_text:
                    party_chamber += "-Senate"
                
                # Determine transaction type
                if 'buy' in row_text.lower() or 'purchase' in row_text.lower():
                    trade_type = 'BUY'
                elif 'sell' in row_text.lower() or 'sale' in row_text.lower():
                    trade_type = 'SELL'
                else:
                    continue
                
                # Extract ticker symbol - look for issuer ticker span
                ticker_found = None
                import re
                
                # New structure: <span class="q-field issuer-ticker">GOOGL:US</span>
                ticker_span = row.find('span', class_='issuer-ticker')
                if ticker_span:
                    ticker_text = ticker_span.get_text(strip=True)
                    ticker_match = re.search(r'([A-Z]{1,5}):(?:US|NYSE|NASDAQ)', ticker_text)
                    if ticker_match:
                        ticker_found = ticker_match.group(1)
                
                # Fallback: Try finding it in the row text as "TICKER:US" pattern
                if not ticker_found:
                    row_text_full = row.get_text()
                    ticker_match = re.search(r'\b([A-Z]{2,5}):US\b', row_text_full)
                    if ticker_match:
                        ticker_found = ticker_match.group(1)
                
                # Extract date, size (amount range), price, and additional fields from cells
                cells = row.find_all('td')
                date_str = "Recent"
                published_date = None
                traded_date = None
                filed_after_days = None
                owner_type = None
                size_range = None
                price = None
                
                import re
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    
                    # Match date patterns like "30 Oct", "15 Nov"
                    if any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                        # Extract date - could be published or traded
                        match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', cell_text)
                        if match:
                            if not published_date:
                                published_date = match.group(1)
                            elif not traded_date:
                                traded_date = match.group(1)
                            date_str = match.group(1)  # Keep for backwards compatibility
                    
                    # Match "Filed After" days (e.g., "39 days", "4 days")
                    filed_match = re.search(r'(\d+)\s*days?', cell_text)
                    if filed_match and not filed_after_days:
                        filed_after_days = filed_match.group(1)
                    
                    # Match Owner type (Joint, Child, Spouse, Undisclosed)
                    if any(owner in cell_text for owner in ['Joint', 'Child', 'Spouse', 'Undisclosed']):
                        if 'Joint' in cell_text:
                            owner_type = 'Joint'
                        elif 'Child' in cell_text:
                            owner_type = 'Child'
                        elif 'Spouse' in cell_text:
                            owner_type = 'Spouse'
                        elif 'Undisclosed' in cell_text:
                            owner_type = 'Undisclosed'
                    
                    # Match size patterns like "1K-15K", "100K-250K", "15K-50K", "50K-100K"
                    # Note: CapitolTrades uses en-dash (–) not regular hyphen (-)
                    if not size_range:
                        size_match = re.search(r'(\d+[KM][-–]\d+[KM])', cell_text, re.IGNORECASE)
                        if size_match:
                            size_range = size_match.group(1)
                    
                    # Match price patterns like "$66.69", "$148.21", "$110,589.00"
                    if not price:
                        price_match = re.search(r'\$(\d+(?:,\d+)?(?:\.\d{2})?)', cell_text)
                        if price_match:
                            price = price_match.group(0)
                
                trades.append({
                    'politician': politician_name + party_chamber,
                    'type': trade_type,
                    'date': date_str,
                    'ticker': ticker_found or 'N/A',
                    'size': size_range,
                    'price': price
                })
                
            except Exception as e:
                logger.debug(f"Could not parse row: {e}")
                continue
        
        # Limit to 15 most recent
        trades = trades[:15]
        
        if trades:
            logger.info(f"Found {len(trades)} recent Congressional trades")
        else:
            logger.info(f"No Congressional trades found")
        
    except ImportError as e:
        logger.error(f"Selenium not installed. Run: pip install selenium webdriver-manager")
        logger.error(f"Error: {e}")
    except Exception as e:
        logger.warning(f"Could not fetch Congressional trades: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    finally:
        # Always close browser
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return trades


def get_insider_role_description(title: str) -> str:
    """
    Get detailed description of insider's role and significance.
    
    Args:
        title: Insider's title
        
    Returns:
        Description string
    """
    role_descriptions = {
        "CEO": "Chief Executive Officer - Top decision maker, deeply familiar with company strategy and performance",
        "CFO": "Chief Financial Officer - Manages finances, has deep insight into company's financial health",
        "COO": "Chief Operating Officer - Oversees daily operations, understands operational performance",
        "CTO": "Chief Technology Officer - Leads technology strategy, knows product roadmap",
        "President": "Senior leader, often involved in strategic decisions and operations",
        "Director": "Board member - Has fiduciary duty and access to confidential strategic information",
        "VP": "Vice President - Senior executive with significant inside knowledge",
        "10% Owner": "Large shareholder with substantial influence and privileged access to information",
        "Officer": "Corporate officer with executive responsibilities and insider knowledge",
        "Unknown": "Insider with access to material non-public information"
    }
    
    title_normalized = title.upper()
    
    for key, description in role_descriptions.items():
        if key.upper() in title_normalized:
            return description
    
    return role_descriptions["Unknown"]


def generate_ai_insight(alert: InsiderAlert, context: Dict, confidence: int) -> str:
    """
    Generate AI-powered insight using local Llama 3 via Ollama.
    Falls back to rule-based analysis if Ollama is unavailable.
    
    Args:
        alert: InsiderAlert object
        context: Company context dictionary
        confidence: Confidence score (1-5)
        
    Returns:
        Detailed insight string with analysis and recommendation
    """
    try:
        import requests
        
        # Build context for LLM
        prompt = f"""You are a senior hedge fund analyst with 15+ years experience. Analyze this insider trading signal with professional precision. DO NOT explain what the signal type means - I already know. Focus on NON-OBVIOUS insights, catalysts, and edge.

SIGNAL: {alert.signal_type}
TICKER: {alert.ticker} ({alert.company_name})
CONFIDENCE: {confidence}/5

MARKET DATA:"""
        
        # Add relevant context
        if context.get("sector"):
            prompt += f"\n• Sector: {context['sector']}"
        if context.get("market_cap"):
            mc_billions = context["market_cap"] / 1e9
            prompt += f"\n• Market Cap: ${mc_billions:.1f}B"
        if context.get("price_change_5d"):
            prompt += f"\n• 5D: {context['price_change_5d']:+.1f}%"
        if context.get("price_change_1m"):
            prompt += f"\n• 1M: {context['price_change_1m']:+.1f}%"
        if context.get("short_interest"):
            si = context['short_interest']*100
            prompt += f"\n• Short Interest: {si:.1f}%" + (" (SQUEEZE RISK!)" if si > 15 else "")
        if context.get("pe_ratio"):
            pe = context['pe_ratio']
            pe_note = " (undervalued)" if pe < 15 else " (expensive)" if pe > 30 else ""
            prompt += f"\n• P/E: {pe:.1f}{pe_note}"
        if context.get("distance_from_52w_low"):
            prompt += f"\n• From 52W Low: +{context['distance_from_52w_low']:.1f}%"
        
        # Congressional alignment - highlight proven track record
        congressional_trades = context.get("congressional_trades", [])
        ticker = alert.ticker
        congressional_buys = [
            t for t in congressional_trades 
            if t.get("type", "").upper() in ["BUY", "PURCHASE"] 
            and t.get("ticker", "").upper() == ticker.upper()
        ]
        if congressional_buys:
            politicians = [t.get('politician', 'Unknown') for t in congressional_buys[:2]]
            prompt += f"\n• 🏛️ **CONGRESSIONAL ALIGNMENT**: {len(congressional_buys)} politicians with proven track records buying ({', '.join(politicians)})"
            prompt += "\n  NOTE: These are HIGH-CONVICTION traders who consistently outperform the market"
        
        # Signal-specific details
        if "num_insiders" in alert.details:
            prompt += f"\n• {alert.details['num_insiders']} insiders buying simultaneously"
            if "total_value" in alert.details:
                prompt += f" (${alert.details['total_value']:,.0f} total)"
        if "num_politicians" in alert.details:
            prompt += f"\n• {alert.details['num_politicians']} politicians"
            if alert.details.get("bipartisan"):
                prompt += " (BIPARTISAN - both parties!)"
        if "investor" in alert.details:
            prompt += f"\n• Strategic buyer: {alert.details['investor']}"
        
        # Add ownership change information (capital delta) if available
        if len(alert.trades) > 0:
            # Check if Delta Own column exists (shows increase in capital/ownership %)
            if "Delta Own" in alert.trades.columns:
                delta_values = []
                for _, row in alert.trades.iterrows():
                    if pd.notna(row.get("Delta Own")):
                        delta_own = row["Delta Own"]
                        if isinstance(delta_own, str) and delta_own.strip():
                            delta_values.append(delta_own)
                        elif isinstance(delta_own, (int, float)):
                            delta_values.append(f"+{delta_own:.1f}%")
                
                if delta_values:
                    prompt += f"\n• Ownership Increase: {', '.join(delta_values[:3])} (shows strong conviction)"
        
        # Add recent news headlines for context
        if context.get("news") and len(context["news"]) > 0:
            prompt += "\n\nRECENT NEWS:"
            for news_item in context["news"][:3]:
                prompt += f"\n• {news_item['title']}"
                if news_item.get('description'):
                    prompt += f"\n  {news_item['description']}"
        
        prompt += """

TASK: Provide sharp, professional analysis formatted in clear paragraphs:

**KEY INSIGHT** (2-3 sentences):
What's the non-obvious edge here? Reference P/E, short interest, sector dynamics, and price action. Be critical - insider buying doesn't guarantee success.

**CATALYSTS** (2 sentences):
What sector-specific or technical factors could drive this? Be specific to the metrics shown.

**RISKS** (2 sentences):
What could go wrong? Consider valuation, sector headwinds, technical weakness.

**RECOMMENDATION** (100 words maximum):
Provide a clear, actionable recommendation with detailed reasoning. Explain WHY you're giving this recommendation based on the specific data points. If it's a BUY, explain what makes it attractive. If it's HOLD or WAIT, explain what concerns exist. Be specific - reference the actual numbers (P/E, short interest, price action, etc.). Use STRONG BUY only if metrics are exceptional. Use BUY if solid but not perfect. Use HOLD if mixed signals. Use WAIT if overvalued or weak momentum. Keep response under 100 words but ensure all sentences are complete and provide reasoning.

CRITICAL RULES:
- Insider buying is just ONE signal - don't automatically recommend STRONG BUY
- High P/E (>30) should trigger caution
- Negative price momentum should be acknowledged  
- Be skeptical and balanced - this is real money
- If Congressional alignment shows proven traders, emphasize this as a strong signal
- ALWAYS explain WHY you're giving the recommendation - cite specific metrics
- Base analysis ONLY on data provided above
- MAXIMUM 100 WORDS - be thorough but concise, complete all sentences

Format your response with bold section headers and clear paragraph breaks. DO NOT use markdown ** for bold - just write naturally with good structure."""
        
        # Call Ollama API
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3:latest",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 500
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            insight = result.get("response", "").strip()
            
            # Clean up the output
            # Remove common prefixes the model adds
            prefixes_to_remove = [
                "Here's the analysis:",
                "Here is the analysis:",
                "Analysis:",
                "Here's my analysis:"
            ]
            for prefix in prefixes_to_remove:
                if insight.startswith(prefix):
                    insight = insight[len(prefix):].strip()
            
            # Format the insight with HTML bold tags and line breaks
            # Replace section headers with bold HTML tags
            insight = insight.replace("KEY INSIGHT", "<strong>KEY INSIGHT</strong><br>")
            insight = insight.replace("CATALYSTS", "<br><br><strong>CATALYSTS</strong><br>")
            insight = insight.replace("RISKS", "<br><br><strong>RISKS</strong><br>")
            insight = insight.replace("RECOMMENDATION", "<br><br><strong>RECOMMENDATION</strong><br>")
            
            # Clean up any remaining ** markdown
            insight = insight.replace("**", "")
            
            if insight:
                logger.info(f"Generated AI insight using Llama 3 for {alert.ticker}")
                return insight
    
    except Exception as e:
        logger.warning(f"Could not generate AI insight via Ollama: {e}. Using rule-based fallback.")
    
    # Fallback to rule-based analysis
    insights = []
    recommendation = "HOLD"  # Default
    reasoning = []
    
    # Analyze Congressional alignment - check if any politician bought THIS ticker
    congressional_trades = context.get("congressional_trades", [])
    # Filter for buys of THIS specific ticker
    ticker = alert.ticker
    congressional_buys_this_stock = [
        t for t in congressional_trades 
        if t.get("type", "").upper() in ["BUY", "PURCHASE"] 
        and t.get("ticker", "").upper() == ticker.upper()
    ]
    
    if congressional_buys_this_stock:
        num_congress = len(congressional_buys_this_stock)
        politicians = [f"{t['politician']}" for t in congressional_buys_this_stock[:3]]  # First 3
        politicians_str = ", ".join(politicians)
        if num_congress > 3:
            politicians_str += f", and {num_congress - 3} others"
        
        insights.append(f"🏛️ CONGRESSIONAL ALIGNMENT: {num_congress} politician(s) recently bought {ticker} ({politicians_str}). "
                       f"Members of Congress have access to policy discussions, committee hearings, and regulatory insights not available to the public. "
                       f"When Congressional buys align with corporate insider buying, it creates an exceptionally strong signal - "
                       f"both groups with privileged information are betting on the same outcome.")
        recommendation = "STRONG BUY"
        reasoning.append(f"{num_congress} Congressional buy(s) of {ticker} + insider buying")
    
    # Analyze short squeeze potential
    short_interest = context.get("short_interest")
    if short_interest and short_interest > 0.15:  # >15% short
        if alert.signal_type in ["Cluster Buying", "Strategic Investor Buy", "CEO/CFO Buy"]:
            insights.append(f"🔥 SHORT SQUEEZE SETUP: {short_interest*100:.1f}% of shares are sold short. "
                          f"Insiders are buying heavily while shorts bet against the stock. "
                          f"If the stock rises, short sellers will be forced to buy shares to cover their positions, "
                          f"creating a feedback loop that could rocket the price higher.")
            recommendation = "STRONG BUY"
            reasoning.append("High short interest + insider buying = squeeze potential")
    
    # Analyze dip buying
    dist_from_low = context.get("distance_from_52w_low")
    if dist_from_low is not None and dist_from_low < 20:  # Within 20% of 52w low
        insights.append(f"💎 DIP BUYING OPPORTUNITY: Stock is trading just {dist_from_low:.1f}% above its 52-week low. "
                       f"Insiders are buying at/near the bottom, signaling they believe the worst is over. "
                       f"This is classic 'smart money' behavior - buying when pessimism is highest.")
        if recommendation != "STRONG BUY":
            recommendation = "BUY"
        reasoning.append("Buying near 52-week low")
    
    # Analyze insider conviction
    if alert.signal_type == "Cluster Buying":
        num_insiders = alert.details.get("num_insiders", 0)
        insights.append(f"👥 INSIDER CONSENSUS: {num_insiders} different insiders are buying simultaneously. "
                       f"When multiple insiders act together, it's rarely a coincidence. "
                       f"They have access to non-public information and collectively see major upside ahead.")
        reasoning.append("Multiple insiders = strong conviction")
    elif alert.signal_type == "Strategic Investor Buy":
        investor = alert.details.get("investor", "")
        insights.append(f"🏢 STRATEGIC INVESTMENT: {investor} is taking a position. "
                       f"Corporate investors conduct months of due diligence before investing. "
                       f"This could signal a strategic partnership, acquisition interest, or validation of the technology/business model.")
        recommendation = "STRONG BUY"
        reasoning.append("Corporate strategic investment")
    
    # Analyze valuation + buying
    pe_ratio = context.get("pe_ratio")
    if pe_ratio and 5 < pe_ratio < 15:
        insights.append(f"📊 UNDERVALUED + INSIDER BUYING: P/E ratio of {pe_ratio:.1f} suggests the stock is attractively valued. "
                       f"Insiders are buying when the stock is already cheap - double signal of opportunity.")
        reasoning.append("Attractive valuation")
    
    # Price momentum consideration
    price_change_5d = context.get("price_change_5d")
    price_change_1m = context.get("price_change_1m")
    if price_change_5d is not None and price_change_1m is not None:
        if price_change_5d < -5 and price_change_1m < -10:
            insights.append(f"⚠️ CATCHING A FALLING KNIFE: Stock is down {abs(price_change_1m):.1f}% over the last month. "
                           f"While insiders may be right long-term, short-term momentum is negative. "
                           f"Consider waiting for price stabilization or dollar-cost averaging.")
            if recommendation == "BUY":
                recommendation = "WAIT FOR CONFIRMATION"
            reasoning.append("Negative momentum - caution advised")
    
    # Final recommendation based on confidence
    if confidence >= 4 and not insights:
        insights.append(f"✅ HIGH CONVICTION SIGNAL: This {alert.signal_type.lower()} scores {confidence}/5 on our confidence scale. "
                       f"Multiple positive factors align, suggesting significant insider conviction about future prospects.")
        recommendation = "BUY"
    elif confidence <= 2:
        insights.append(f"⚠️ LOWER CONVICTION: This signal scores {confidence}/5. "
                       f"While insiders are buying, the size and context suggest moderate rather than exceptional opportunity.")
        recommendation = "MONITOR"
        reasoning.append("Lower confidence score")
    
    # Default insight if none triggered
    if not insights:
        insights.append(f"📈 INSIDER ACCUMULATION: {alert.signal_type} detected. "
                       f"Insiders are putting their own money on the line, which historically signals undervaluation. "
                       f"However, no exceptional catalysts identified. Standard insider buy opportunity.")
        recommendation = "HOLD/ACCUMULATE"
    
    # Build final insight
    insight_text = " ".join(insights)
    
    # Add recommendation
    if recommendation == "STRONG BUY":
        action = "🚀 RECOMMENDATION: STRONG BUY - Multiple bullish factors align. Consider taking a position."
    elif recommendation == "BUY":
        action = "✅ RECOMMENDATION: BUY - Positive setup with good risk/reward. Entry recommended."
    elif recommendation == "HOLD/ACCUMULATE":
        action = "📊 RECOMMENDATION: HOLD/ACCUMULATE - Solid opportunity. Build position gradually."
    elif recommendation == "MONITOR":
        action = "👀 RECOMMENDATION: MONITOR - Watch for additional confirmation before entering."
    elif recommendation == "WAIT FOR CONFIRMATION":
        action = "⏳ RECOMMENDATION: WAIT - Let price stabilize before entering. Set alerts."
    else:
        action = "📌 RECOMMENDATION: HOLD - Neutral signal. Existing holders maintain position."
    
    insight_text += f"\n\n{action}"
    
    if reasoning:
        insight_text += f"\n\nKey factors: {', '.join(reasoning)}"
    
    return insight_text


def calculate_confidence_score(alert: InsiderAlert, context: Dict) -> tuple[int, str]:
    """
    Calculate confidence score (1-5 stars) based on multiple factors.
    
    Scoring factors:
    - Signal type (cluster > CEO/CFO > large buy)
    - Buy amount (larger = better)
    - Ownership increase % (bigger stake = more conviction)
    - Price action (buying dip = better)
    - Short interest (high short + buy = squeeze potential)
    - P/E ratio (undervalued = better)
    
    Args:
        alert: InsiderAlert object
        context: Company context dictionary
        
    Returns:
        Tuple of (score 1-5, explanation string)
    """
    score = 0
    reasons = []
    
    # Congressional signals get different scoring
    is_congressional = "Congressional" in alert.signal_type or "Bipartisan" in alert.signal_type
    
    if is_congressional:
        # Congressional signal scoring (0-3 points for signal type)
        if "Bipartisan" in alert.signal_type:
            score += 3
            reasons.append("Bipartisan Congressional agreement")
        elif "Cluster" in alert.signal_type:
            num_pols = alert.details.get("num_politicians", 2)
            score += 2.5
            reasons.append(f"{num_pols} politicians buying")
        elif "High-Conviction" in alert.signal_type:
            score += 2
            reasons.append("Known successful Congressional trader")
        else:
            score += 2
            reasons.append("Congressional insider activity")
    else:
        # Corporate insider signal type scoring (0-2 points)
        if alert.signal_type == "Cluster Buying":
            score += 2
            reasons.append("Multiple insiders buying")
        elif alert.signal_type == "Strategic Investor Buy":
            score += 2
            reasons.append("Corporate strategic investment")
        elif alert.signal_type == "CEO/CFO Buy":
            score += 1.5
            reasons.append("C-suite executive buying")
        elif alert.signal_type == "Large Single Buy":
            score += 1
            reasons.append("Significant purchase size")
    
    # Purchase size (0-1 points)
    total_value = alert.details.get("total_value") or alert.details.get("value", 0)
    if total_value >= 1_000_000:
        score += 1
        reasons.append("$1M+ purchase")
    elif total_value >= 500_000:
        score += 0.5
    
    # Ownership increase (0-1 points)
    try:
        if not alert.trades.empty and "Delta Own" in alert.trades.columns:
            # Clean and convert Delta Own values
            delta_vals = alert.trades["Delta Own"].astype(str).str.replace('%', '').str.replace('+', '')
            delta_vals = pd.to_numeric(delta_vals, errors='coerce')
            avg_delta = delta_vals.mean()
            
            if pd.notna(avg_delta) and avg_delta > 10:
                score += 1
                reasons.append(f"+{avg_delta:.0f}% ownership increase")
            elif pd.notna(avg_delta) and avg_delta > 5:
                score += 0.5
    except Exception as e:
        logger.debug(f"Could not calculate ownership delta: {e}")
    
    # Price action - buying the dip (0-1 points)
    if context.get("distance_from_52w_low") is not None:
        dist_from_low = context["distance_from_52w_low"]
        if dist_from_low < 20:  # Within 20% of 52w low
            score += 1
            reasons.append("Buying near 52-week low")
        elif dist_from_low < 40:
            score += 0.5
    
    # Short interest squeeze potential (0-0.5 points)
    if context.get("short_interest") and context["short_interest"] > 0.15:  # >15% short
        score += 0.5
        reasons.append(f"High short interest ({context['short_interest']*100:.1f}%)")
    
    # Valuation (0-0.5 points)
    if context.get("pe_ratio") and 5 < context["pe_ratio"] < 15:
        score += 0.5
        reasons.append("Attractive valuation")
    
    # Congressional alignment (0-0.5 points) - MAJOR SIGNAL
    # Check if politicians bought THIS specific ticker
    congressional_trades = context.get("congressional_trades", [])
    ticker = alert.ticker
    congressional_buys_this_stock = [
        t for t in congressional_trades 
        if t.get("type", "").upper() in ["BUY", "PURCHASE"]
        and t.get("ticker", "").upper() == ticker.upper()
    ]
    if congressional_buys_this_stock:
        score += 0.5
        num_pols = len(congressional_buys_this_stock)
        reasons.append(f"{num_pols} Congressional buy(s) of {ticker}")
    
    # Cap at 5, round to nearest 0.5
    score = min(5, round(score * 2) / 2)
    
    explanation = "; ".join(reasons) if reasons else "Standard insider buy"
    
    return int(score), explanation


@retry(
    retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def fetch_openinsider_html(url: str = OPENINSIDER_URL) -> str:
    """
    Fetch HTML content from OpenInsider with retry logic.
    
    Args:
        url: OpenInsider URL to fetch
        
    Returns:
        HTML content as string
        
    Raises:
        requests.RequestException: On request failure after retries
    """
    logger.info(f"Fetching data from {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    
    logger.info(f"Successfully fetched {len(response.text)} bytes")
    return response.text


def parse_openinsider_pandas(html: str) -> Optional[pd.DataFrame]:
    """
    Parse OpenInsider table using pandas.read_html (preferred method).
    
    Args:
        html: HTML content
        
    Returns:
        DataFrame of trades or None if parsing fails
    """
    try:
        logger.debug("Attempting pandas.read_html parsing")
        from io import StringIO
        tables = pd.read_html(StringIO(html))
        
        # Find table with expected columns
        expected_cols = ["Ticker", "Insider Name", "Trade Type"]
        
        for table in tables:
            # Normalize column names
            table.columns = [str(col).strip() for col in table.columns]
            
            # Check if this looks like the trades table
            if any(col in table.columns for col in expected_cols):
                logger.info(f"Found trades table with pandas: {len(table)} rows")
                return table
                
        logger.warning("No matching table found with pandas")
        return None
        
    except Exception as e:
        logger.warning(f"pandas.read_html failed: {e}")
        return None


def parse_openinsider_bs4(html: str) -> Optional[pd.DataFrame]:
    """
    Parse OpenInsider table using BeautifulSoup (fallback method).
    
    Args:
        html: HTML content
        
    Returns:
        DataFrame of trades or None if parsing fails
    """
    try:
        logger.debug("Attempting BeautifulSoup parsing")
        soup = BeautifulSoup(html, "lxml")
        
        # Find table with trade data
        # OpenInsider uses specific table structure
        table = soup.find("table", {"class": "tinytable"})
        
        if not table:
            # Try finding any table with expected headers
            for t in soup.find_all("table"):
                header_text = t.get_text().lower()
                if "ticker" in header_text and "insider name" in header_text:
                    table = t
                    break
        
        if not table:
            logger.warning("Could not find trades table with BeautifulSoup")
            return None
        
        # Extract headers
        headers = []
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        
        if not headers:
            logger.warning("Could not extract table headers")
            return None
        
        # Extract rows
        rows = []
        for tr in table.find_all("tr")[1:]:  # Skip header row
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        
        if not rows:
            logger.warning("No data rows found")
            return None
        
        # Create DataFrame
        df = pd.DataFrame(rows, columns=headers)
        logger.info(f"Parsed {len(df)} rows with BeautifulSoup")
        return df
        
    except Exception as e:
        logger.error(f"BeautifulSoup parsing failed: {e}")
        return None


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and clean the trades DataFrame.
    
    Args:
        df: Raw trades DataFrame
        
    Returns:
        Cleaned and normalized DataFrame
    """
    logger.debug(f"Normalizing DataFrame with {len(df)} rows")
    
    # First, fix column names - replace non-breaking spaces with regular spaces
    df.columns = [str(col).replace('\xa0', ' ').strip() for col in df.columns]
    
    # Standardize column names
    column_mapping = {
        "X": "Filing Type",
        "Filing Date": "Filing Date",
        "Trade Date": "Trade Date",
        "Ticker": "Ticker",
        "Company Name": "Company Name",
        "Insider Name": "Insider Name",
        "Title": "Title",
        "Trade Type": "Trade Type",
        "Price": "Price",
        "Qty": "Qty",
        "Owned": "Owned",
        "ΔOwn": "Delta Own",
        "Value": "Value",
    }
    
    # Rename columns that exist
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)
    
    # Ensure required columns exist
    required_cols = ["Ticker", "Insider Name", "Trade Type", "Trade Date"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        logger.warning(f"Missing required columns: {missing_cols}")
        for col in missing_cols:
            df[col] = None
    
    # Clean and convert data types
    
    # Dates
    for date_col in ["Trade Date", "Filing Date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    
    # Numeric columns - remove commas and dollar signs
    numeric_cols = ["Price", "Qty", "Owned", "Value"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(r"[\$,]", "", regex=True)
                .str.replace(r"[^\d.-]", "", regex=True)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # Normalize trade types
    if "Trade Type" in df.columns:
        df["Trade Type"] = df["Trade Type"].str.strip().str.title()
        df["Trade Type"] = df["Trade Type"].replace({
            "P - Purchase": "Buy",
            "Purchase": "Buy",
            "S - Sale": "Sale",
            "S": "Sale",
            "P": "Buy",
        })
    
    # Normalize titles
    if "Title" in df.columns:
        df["Title Normalized"] = df["Title"].str.lower().map(TITLE_MAPPING)
        df["Title Normalized"] = df["Title Normalized"].fillna(df["Title"])
    else:
        df["Title Normalized"] = None
    
    # Filter out invalid trade types
    valid_types = ["Buy", "Sale"]
    if "Trade Type" in df.columns:
        before_count = len(df)
        df = df[df["Trade Type"].isin(valid_types)].copy()
        after_count = len(df)
        if before_count != after_count:
            logger.info(f"Filtered out {before_count - after_count} rows with invalid trade types")
    
    # Remove rows with missing critical data
    before_count = len(df)
    df = df.dropna(subset=["Ticker", "Trade Date", "Trade Type"])
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Removed {before_count - after_count} rows with missing critical data")
    
    # Check for 10b5-1 planned trades
    if "Filing Type" in df.columns:
        df["Is_Planned"] = df["Filing Type"].str.contains("10b5-1", case=False, na=False)
    else:
        df["Is_Planned"] = False
    
    # Create unique key for de-duplication
    df["Unique_Key"] = (
        df["Ticker"].astype(str) + "_" +
        df["Insider Name"].astype(str) + "_" +
        df["Trade Date"].astype(str) + "_" +
        df["Trade Type"].astype(str) + "_" +
        df["Qty"].astype(str) + "_" +
        df["Price"].astype(str)
    )
    
    # Remove duplicates
    before_count = len(df)
    df = df.drop_duplicates(subset=["Unique_Key"], keep="first")
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Removed {before_count - after_count} duplicate rows")
    
    # Filter out planned trades
    before_count = len(df)
    df = df[~df["Is_Planned"]].copy()
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Filtered out {before_count - after_count} planned (10b5-1) trades")
    
    logger.info(f"Normalized DataFrame: {len(df)} rows remain")
    return df


def parse_openinsider(html: str) -> pd.DataFrame:
    """
    Parse OpenInsider HTML with fallback methods.
    
    Args:
        html: HTML content from OpenInsider
        
    Returns:
        Normalized DataFrame of trades (filtered to last 30 days)
        
    Raises:
        ValueError: If parsing fails with all methods
    """
    from datetime import datetime, timedelta
    
    # Try pandas first (faster and more reliable)
    df = parse_openinsider_pandas(html)
    
    # Fall back to BeautifulSoup if pandas fails
    if df is None:
        df = parse_openinsider_bs4(html)
    
    if df is None:
        raise ValueError("Failed to parse OpenInsider table with all methods")
    
    # Normalize the data
    df = normalize_dataframe(df)
    
    # Filter to last 30 days based on Trade Date
    cutoff_date = datetime.now() - timedelta(days=30)
    if 'Trade Date' in df.columns:
        before_count = len(df)
        df = df[df['Trade Date'] >= cutoff_date].copy()
        after_count = len(df)
        filtered_count = before_count - after_count
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} OpenInsider trades older than 30 days")
    
    return df


def check_trade_exists_in_db(ticker: str, insider_name: str, trade_date: str, 
                              trade_type: str, qty: float, price: float) -> bool:
    """
    Check if a trade already exists in the database.
    
    Args:
        ticker: Stock ticker
        insider_name: Name of insider
        trade_date: Trade date (YYYY-MM-DD format)
        trade_type: 'Buy' or 'Sale'
        qty: Number of shares
        price: Price per share
        
    Returns:
        True if trade exists, False otherwise
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM openinsider_trades
            WHERE ticker = ? AND insider_name = ? AND trade_date = ?
              AND trade_type = ? AND qty = ? AND price = ?
        """, (ticker, insider_name, trade_date, trade_type, qty, price))
        count = cursor.fetchone()[0]
        return count > 0


def fetch_openinsider_last_week() -> pd.DataFrame:
    """
    Fetch ALL trades from the last 7 days using OpenInsider screener.
    Implements early termination when consecutive duplicates exceed threshold.
    
    Returns:
        DataFrame of all new trades from last week
    """
    logger.info("Fetching OpenInsider trades from last 30 days (paginated screener)")
    
    all_trades = []
    page = 1
    consecutive_duplicates = 0
    total_new = 0
    total_duplicates = 0
    
    while True:
        try:
            # Fetch page
            url = OPENINSIDER_LAST_WEEK_URL.format(page=page)
            logger.info(f"Fetching page {page}...")
            html = fetch_openinsider_html(url)
            
            # Parse page
            df = parse_openinsider_pandas(html)
            if df is None:
                df = parse_openinsider_bs4(html)
            
            if df is None or len(df) == 0:
                logger.info(f"No more trades found on page {page}, stopping pagination")
                break
            
            # Normalize the data
            df = normalize_dataframe(df)
            
            if len(df) == 0:
                logger.info(f"No valid trades on page {page} after normalization, stopping")
                break
            
            # Check each trade for duplicates
            page_new_count = 0
            page_duplicate_count = 0
            
            for _, row in df.iterrows():
                ticker = row.get('Ticker', '').strip().upper()
                insider_name = row.get('Insider Name', '')
                trade_type = row.get('Trade Type', '')
                qty = row.get('Qty', 0)
                price = row.get('Price', 0)
                
                # Handle trade date
                trade_date = row.get('Trade Date')
                if pd.notna(trade_date):
                    if isinstance(trade_date, pd.Timestamp):
                        trade_date_str = trade_date.strftime('%Y-%m-%d')
                    else:
                        trade_date_str = str(trade_date)
                else:
                    trade_date_str = None
                
                # Skip if missing critical data
                if not ticker or not insider_name or not trade_date_str:
                    continue
                
                # Check if exists in database
                if check_trade_exists_in_db(ticker, insider_name, trade_date_str, 
                                           trade_type, qty, price):
                    page_duplicate_count += 1
                    consecutive_duplicates += 1
                else:
                    page_new_count += 1
                    consecutive_duplicates = 0  # Reset counter
                    all_trades.append(row)
            
            total_new += page_new_count
            total_duplicates += page_duplicate_count
            
            logger.info(f"  Page {page}: {page_new_count} new, {page_duplicate_count} duplicates "
                       f"(consecutive: {consecutive_duplicates})")
            
            # Early termination: if we see many consecutive duplicates, stop
            if consecutive_duplicates >= DUPLICATE_THRESHOLD:
                logger.info(f"Reached {consecutive_duplicates} consecutive duplicates, "
                           f"stopping pagination (threshold: {DUPLICATE_THRESHOLD})")
                break
            
            # Move to next page
            page += 1
            
            # Safety limit: don't scrape more than 10 pages
            if page > 10:
                logger.warning("Reached safety limit of 10 pages, stopping pagination")
                break
                
        except Exception as e:
            logger.error(f"Error fetching page {page}: {e}", exc_info=True)
            break
    
    logger.info(f"Scraping complete: {total_new} new trades, {total_duplicates} duplicates "
               f"across {page} page(s)")
    
    # Convert to DataFrame
    if all_trades:
        result_df = pd.DataFrame(all_trades)
        return result_df
    else:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=['Ticker', 'Company Name', 'Insider Name', 'Title', 
                                    'Trade Type', 'Trade Date', 'Value', 'Qty', 
                                    'Owned', 'Delta Own', 'Price'])


def store_openinsider_trades(df: pd.DataFrame) -> int:
    """
    Store OpenInsider trades in database, skipping duplicates.
    
    Args:
        df: DataFrame of OpenInsider trades
        
    Returns:
        Number of new trades inserted
    """
    new_count = 0
    duplicate_count = 0
    
    with get_db() as conn:
        for _, row in df.iterrows():
            try:
                # Extract data
                ticker = row.get('Ticker', '').strip().upper()
                company_name = row.get('Company Name', '')
                insider_name = row.get('Insider Name', '')
                insider_title = row.get('Title', '')
                trade_type = row.get('Trade Type', '')
                
                # Handle trade date
                trade_date = row.get('Trade Date')
                if pd.notna(trade_date):
                    if isinstance(trade_date, pd.Timestamp):
                        trade_date_str = trade_date.strftime('%Y-%m-%d')
                    else:
                        trade_date_str = str(trade_date)
                else:
                    trade_date_str = None
                
                value = row.get('Value', 0)
                qty = row.get('Qty', 0)
                owned = row.get('Owned', 0)
                delta_own = row.get('Delta Own')
                price = row.get('Price')
                
                # Skip if missing critical data
                if not ticker or not insider_name or not trade_date_str:
                    continue
                
                # Try to insert (will fail on duplicate)
                conn.execute("""
                    INSERT INTO openinsider_trades 
                    (ticker, company_name, insider_name, insider_title, trade_type, 
                     trade_date, value, qty, owned, delta_own, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticker, company_name, insider_name, insider_title, trade_type,
                      trade_date_str, value, qty, owned, delta_own, price))
                
                new_count += 1
                
            except sqlite3.IntegrityError:
                # Duplicate - skip
                duplicate_count += 1
            except Exception as e:
                logger.warning(f"Error storing OpenInsider trade: {e}")
        
        conn.commit()
    
    logger.info(f"Stored {new_count} new OpenInsider trades, {duplicate_count} duplicates skipped")
    return new_count


def load_openinsider_trades_from_db(lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Load all OpenInsider trades from database within the lookback window.
    
    Args:
        lookback_days: Number of days to look back
        
    Returns:
        DataFrame of trades from database
    """
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
    
    with get_db() as conn:
        query = """
            SELECT ticker, company_name, insider_name, insider_title as Title, 
                   trade_type as 'Trade Type', trade_date as 'Trade Date', 
                   value as Value, qty as Qty, owned as Owned, 
                   delta_own as 'Delta Own', price as Price
            FROM openinsider_trades
            WHERE trade_date >= ?
            ORDER BY trade_date DESC
        """
        df = pd.read_sql_query(query, conn, params=(cutoff_date_str,))
    
    # Convert trade_date to datetime
    df['Trade Date'] = pd.to_datetime(df['Trade Date'])
    
    # Standardize column names
    df.rename(columns={
        'ticker': 'Ticker',
        'company_name': 'Company Name',
        'insider_name': 'Insider Name'
    }, inplace=True)
    
    # Add Title Normalized column for C-Suite detection
    if 'Title' in df.columns:
        df['Title Normalized'] = df['Title'].str.lower().map(TITLE_MAPPING)
        df['Title Normalized'] = df['Title Normalized'].fillna(df['Title'])
    
    logger.info(f"Loaded {len(df)} trades from database within {lookback_days} days")
    return df


def filter_by_lookback(df: pd.DataFrame, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Filter trades to only include those within the lookback window.
    
    Args:
        df: Trades DataFrame
        lookback_days: Number of days to look back
        
    Returns:
        Filtered DataFrame
    """
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    filtered = df[df["Trade Date"] >= cutoff_date].copy()
    logger.info(f"Filtered to {len(filtered)} trades within {lookback_days} days")
    return filtered


def detect_cluster_buying(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect cluster buying: ≥3 insiders from same ticker buy within cluster window,
    total value ≥ MIN_CLUSTER_BUY_VALUE.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Filter to buys only
    buys = df[df["Trade Type"] == "Buy"].copy()
    
    if buys.empty:
        return alerts
    
    # Group by ticker
    for ticker in buys["Ticker"].unique():
        ticker_buys = buys[buys["Ticker"] == ticker].sort_values("Trade Date")
        
        # Check rolling window
        for i, row in ticker_buys.iterrows():
            window_start = row["Trade Date"] - timedelta(days=CLUSTER_DAYS)
            window_end = row["Trade Date"]
            
            window_trades = ticker_buys[
                (ticker_buys["Trade Date"] >= window_start) &
                (ticker_buys["Trade Date"] <= window_end)
            ]
            
            # Check if cluster criteria met
            unique_insiders = window_trades["Insider Name"].nunique()
            total_value = window_trades["Value"].sum()
            
            if unique_insiders >= MIN_CLUSTER_INSIDERS and total_value >= MIN_CLUSTER_BUY_VALUE:
                company_name = window_trades["Company Name"].iloc[0] if "Company Name" in window_trades.columns else ticker
                
                alert = InsiderAlert(
                    signal_type="Cluster Buying",
                    ticker=ticker,
                    company_name=company_name,
                    trades=window_trades,
                    details={
                        "num_insiders": unique_insiders,
                        "total_value": total_value,
                        "window_days": CLUSTER_DAYS,
                        "window_start": window_start,
                        "window_end": window_end,
                    }
                )
                alerts.append(alert)
                break  # Only alert once per ticker
    
    logger.info(f"Detected {len(alerts)} cluster buying signals")
    return alerts


def detect_ceo_cfo_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect C-Suite buy: Top executives (CEO/CFO/President) buy ≥ $250K.
    Restricted to highest-level executives only to reduce noise.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Only top C-Suite titles (removed VP, GC, Officer to reduce noise)
    c_suite_titles = [
        "CEO", "CFO", "COO", "President", "Pres", 
        "Chief Executive Officer", "Chief Financial Officer", "Chief Operating Officer"
    ]
    
    # Filter to C-Suite buys
    exec_buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Title Normalized"].isin(c_suite_titles)) &
        (df["Value"] >= MIN_CEO_CFO_BUY)
    ].copy()
    
    for _, row in exec_buys.iterrows():
        company_name = row.get("Company Name", row["Ticker"])
        
        alert = InsiderAlert(
            signal_type="C-Suite Buy",
            ticker=row["Ticker"],
            company_name=company_name,
            trades=pd.DataFrame([row]),
            details={
                "insider": row["Insider Name"],
                "title": row["Title Normalized"],
                "value": row["Value"],
                "trade_date": row["Trade Date"],
            }
        )
        alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} C-Suite buy signals")
    return alerts


def detect_large_single_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect large single buy: Any insider buys ≥ $500K (raised from $250K to reduce noise).
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    large_buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Value"] >= MIN_LARGE_BUY)
    ].copy()
    
    for _, row in large_buys.iterrows():
        company_name = row.get("Company Name", row["Ticker"])
        
        alert = InsiderAlert(
            signal_type="Large Single Buy",
            ticker=row["Ticker"],
            company_name=company_name,
            trades=pd.DataFrame([row]),
            details={
                "insider": row["Insider Name"],
                "title": row.get("Title Normalized", row.get("Title", "Unknown")),
                "value": row["Value"],
                "trade_date": row["Trade Date"],
                "qty": row["Qty"],
                "price": row["Price"],
            }
        )
        alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} large single buy signals")
    return alerts


def detect_first_buy_12m(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect first buy in 12 months: Insider's first purchase in 365 days, ≥ MIN_FIRST_BUY_12M.
    
    Note: This requires historical data. We'll check if this is the only buy for this
    insider+ticker combination in our dataset.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Value"] >= MIN_FIRST_BUY_12M)
    ].copy()
    
    # Group by ticker and insider
    for (ticker, insider), group in buys.groupby(["Ticker", "Insider Name"]):
        # Check if this is the only buy in our dataset (proxy for first in 12m)
        all_buys_for_insider = df[
            (df["Ticker"] == ticker) &
            (df["Insider Name"] == insider) &
            (df["Trade Type"] == "Buy")
        ]
        
        if len(all_buys_for_insider) == 1:
            row = group.iloc[0]
            company_name = row.get("Company Name", ticker)
            
            alert = InsiderAlert(
                signal_type="First Buy in 12 Months",
                ticker=ticker,
                company_name=company_name,
                trades=pd.DataFrame([row]),
                details={
                    "insider": insider,
                    "title": row.get("Title Normalized", row.get("Title", "Unknown")),
                    "value": row["Value"],
                    "trade_date": row["Trade Date"],
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} first buy in 12 months signals")
    return alerts


def detect_bearish_cluster_selling(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect bearish cluster selling: ≥3 insiders from same ticker sell within cluster window,
    total value ≥ MIN_BEARISH_CLUSTER_VALUE.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Filter to sales only
    sales = df[df["Trade Type"] == "Sale"].copy()
    
    if sales.empty:
        return alerts
    
    # Group by ticker
    for ticker in sales["Ticker"].unique():
        ticker_sales = sales[sales["Ticker"] == ticker].sort_values("Trade Date")
        
        # Check rolling window
        for i, row in ticker_sales.iterrows():
            window_start = row["Trade Date"] - timedelta(days=CLUSTER_DAYS)
            window_end = row["Trade Date"]
            
            window_trades = ticker_sales[
                (ticker_sales["Trade Date"] >= window_start) &
                (ticker_sales["Trade Date"] <= window_end)
            ]
            
            # Check if cluster criteria met (5+ insiders for higher confidence)
            unique_insiders = window_trades["Insider Name"].nunique()
            total_value = window_trades["Value"].sum()
            
            if unique_insiders >= MIN_CLUSTER_INSIDERS and total_value >= MIN_BEARISH_CLUSTER_VALUE:
                company_name = window_trades["Company Name"].iloc[0] if "Company Name" in window_trades.columns else ticker
                
                alert = InsiderAlert(
                    signal_type="Bearish Cluster Selling",
                    ticker=ticker,
                    company_name=company_name,
                    trades=window_trades,
                    details={
                        "num_insiders": unique_insiders,
                        "total_value": total_value,
                        "window_days": CLUSTER_DAYS,
                        "window_start": window_start,
                        "window_end": window_end,
                    }
                )
                alerts.append(alert)
                break  # Only alert once per ticker
    
    logger.info(f"Detected {len(alerts)} bearish cluster selling signals")
    return alerts


def detect_strategic_investor_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect Corporation Purchase: When a corporation (not an individual) buys stock.
    Examples: NVIDIA buying SERV, Amazon buying RIVN, etc.
    
    This is highly bullish as it signals:
    - Strategic partnerships/acquisitions
    - Deep due diligence by corporate teams
    - Potential integration/collaboration
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Corporate name indicators
    corporate_indicators = [
        'Corp', 'Corporation', 'Inc', 'Incorporated', 'LLC', 'Ltd', 
        'Limited', 'LP', 'LLP', 'Company', 'Co.', 'Group', 
        'Holdings', 'Partners', 'Capital', 'Ventures', 'Fund',
        'Trust', 'Management', 'Investments', 'Technologies'
    ]
    
    # Filter to buys only, with minimum value
    buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Value"] >= MIN_CORP_PURCHASE)
    ].copy()
    
    # Identify corporate buyers by name patterns
    for _, row in buys.iterrows():
        insider_name = str(row["Insider Name"])
        
        # Check if name contains corporate indicators
        is_corporate = any(indicator in insider_name for indicator in corporate_indicators)
        
        # Also check if it's all caps (common for corporate names like "NVIDIA")
        words = insider_name.split()
        has_all_caps_word = any(word.isupper() and len(word) > 2 for word in words)
        
        if is_corporate or has_all_caps_word:
            company_name = row.get("Company Name", row["Ticker"])
            
            alert = InsiderAlert(
                signal_type="Corporation Purchase",
                ticker=row["Ticker"],
                company_name=company_name,
                trades=pd.DataFrame([row]),
                details={
                    "investor": insider_name,
                    "value": row["Value"],
                    "trade_date": row["Trade Date"],
                    "qty": row["Qty"],
                    "price": row["Price"],
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} corporation purchase signals")
    return alerts


def detect_congressional_cluster_buy(congressional_trades: List[Dict] = None) -> List[InsiderAlert]:
    """
    Detect Elite Congressional Cluster Buy: 2+ Elite traders buy same ticker within 30 days.
    
    This is a HIGHLY filtered signal:
    - ONLY tracks Top 15 proven Elite traders (ignores all other politicians)
    - Requires 2+ Elite traders buying same stock (any trade size)
    - Party tracked only for "Bipartisan Elite Cluster" bonus (rare = extremely bullish)
    
    Elite traders have demonstrated consistent outperformance and trade with conviction.
    
    Uses published_date (when we found out) for lookback window, not traded_date.
    
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    try:
        # Query database for Elite trader buys only (last 30 days by published_date)
        with get_db() as conn:
            # Build SQL filter for Elite traders only
            elite_filter = " OR ".join([f"politician_name LIKE '%{name}%'" for name in ELITE_CONGRESSIONAL_TRADERS])
            
            query = f"""
                SELECT ticker, COUNT(DISTINCT politician_name) as num_politicians,
                       GROUP_CONCAT(DISTINCT politician_name) as politicians,
                       GROUP_CONCAT(DISTINCT party) as parties,
                       SUM(CASE 
                           WHEN size_range LIKE '%1K-15K%' THEN 8000
                           WHEN size_range LIKE '%15K-50K%' THEN 32500
                           WHEN size_range LIKE '%50K-100K%' THEN 75000
                           WHEN size_range LIKE '%100K-250K%' THEN 175000
                           WHEN size_range LIKE '%250K-500K%' THEN 375000
                           WHEN size_range LIKE '%500K-1M%' THEN 750000
                           WHEN size_range LIKE '%1M%' THEN 2500000
                           ELSE 0
                       END) as estimated_total_value
                FROM congressional_trades
                WHERE trade_type = "BUY"
                AND published_date >= date("now", "-30 days")
                AND filed_after_days <= ?
                AND ({elite_filter})
                GROUP BY ticker
                HAVING COUNT(DISTINCT politician_name) >= 2
                ORDER BY num_politicians DESC
            """
            cursor = conn.execute(query, (MAX_FILING_DELAY_DAYS,))
            clusters = cursor.fetchall()
            
            for cluster in clusters:
                ticker = cluster['ticker']
                num_politicians = cluster['num_politicians']
                politicians = cluster['politicians'].split(',')
                parties = cluster['parties'].split(',')
                
                # Check if bipartisan
                has_dem = 'D' in parties
                has_rep = 'R' in parties
                is_bipartisan = has_dem and has_rep
                
                # Get individual trades for this ticker cluster
                # Check if issuer_id column exists (for backward compatibility)
                cursor_info = conn.execute("PRAGMA table_info(congressional_trades)")
                columns = [row[1] for row in cursor_info.fetchall()]
                has_issuer_id = 'issuer_id' in columns
                
                if has_issuer_id:
                    trade_query = """
                        SELECT politician_name, politician_id, party, chamber, size_range, 
                               traded_date, published_date, filed_after_days, price, company_name, issuer_id
                        FROM congressional_trades
                        WHERE ticker = ?
                        AND trade_type = "BUY"
                        AND published_date >= date("now", "-30 days")
                        ORDER BY published_date DESC
                    """
                else:
                    trade_query = """
                        SELECT politician_name, politician_id, party, chamber, size_range, 
                               traded_date, published_date, filed_after_days, price, company_name
                        FROM congressional_trades
                        WHERE ticker = ?
                        AND trade_type = "BUY"
                        AND published_date >= date("now", "-30 days")
                        ORDER BY published_date DESC
                    """
                trade_cursor = conn.execute(trade_query, (ticker,))
                trades = trade_cursor.fetchall()
                
                # Get company_name from first trade
                company_name_from_db = trades[0]['company_name'] if trades and trades[0]['company_name'] else ticker
                
                # Get first issuer_id for linking (may not exist in older records)
                first_issuer_id = None
                if has_issuer_id and trades:
                    try:
                        first_issuer_id = trades[0]['issuer_id']
                    except (KeyError, IndexError):
                        pass
                
                # Build DataFrame for display
                trades_data = []
                for trade in trades:
                    # Convert date strings to datetime objects
                    trade_date = pd.to_datetime(trade['traded_date']) if trade['traded_date'] else pd.NaT
                    published_date = pd.to_datetime(trade['published_date']) if trade['published_date'] else pd.NaT
                    
                    trades_data.append({
                        "Ticker": ticker,
                        "Insider Name": f"{trade['politician_name']} ({trade['party']})",
                        "Politician ID": trade['politician_id'],
                        "Title": trade['chamber'] or 'Congress',
                        "Trade Date": trade_date,
                        "Published Date": published_date,
                        "Size Range": trade['size_range'],
                        "Filed After": f"{trade['filed_after_days']} days" if trade['filed_after_days'] else 'N/A',
                        "Price": f"${trade['price']:.2f}" if trade['price'] else 'N/A'
                    })
                trades_df = pd.DataFrame(trades_data)
                
                # Signal type: Add "Bipartisan" prefix if both D and R involved (rare = extra bullish)
                signal_type = "Bipartisan Elite Congressional Cluster" if is_bipartisan else "Elite Congressional Cluster"
                
                alert = InsiderAlert(
                    signal_type=signal_type,
                    ticker=ticker,
                    company_name=company_name_from_db,
                    trades=trades_df,
                    details={
                        "num_politicians": num_politicians,
                        "politicians": politicians[:5],
                        "bipartisan": is_bipartisan,
                        "issuer_id": first_issuer_id,
                        "elite_traders": True
                    }
                )
                alerts.append(alert)
        
        logger.info(f"Detected {len(alerts)} Elite Congressional cluster buy signals (2+ Elite traders)")
    except Exception as e:
        logger.error(f"Error detecting Congressional cluster buys: {e}", exc_info=True)
    
    return alerts


def detect_large_congressional_buy(congressional_trades: List[Dict] = None) -> List[InsiderAlert]:
    """
    Detect Elite Large Congressional Buy: Elite trader purchases $100K+ in last 30 days.
    
    HIGHLY filtered signal:
    - ONLY tracks Top 15 proven Elite traders (ignores all other politicians)
    - Minimum $100K purchase size (100K-250K, 250K-500K, 500K-1M, 1M-5M, etc.)
    - Published within last 30 days
    
    Party is tracked for display but irrelevant for filtering (smart trades = smart trades).
    
    Uses published_date (when disclosed) for lookback window, not traded_date.
    
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    try:
        # Build SQL filter for Elite traders only
        elite_filter = " OR ".join([f"politician_name LIKE '%{name}%'" for name in ELITE_CONGRESSIONAL_TRADERS])
        
        # Query database for Elite large buys (last 30 days by published_date, size ≥$100K)
        with get_db() as conn:
            # Check if issuer_id column exists (for backward compatibility)
            cursor_info = conn.execute("PRAGMA table_info(congressional_trades)")
            columns = [row[1] for row in cursor_info.fetchall()]
            has_issuer_id = 'issuer_id' in columns
            
            if has_issuer_id:
                query = f"""
                    SELECT politician_name, politician_id, party, chamber, state,
                           ticker, company_name, size_range, price,
                           traded_date, published_date, filed_after_days, issuer_id
                    FROM congressional_trades
                    WHERE trade_type = "BUY"
                    AND published_date >= date("now", "-30 days")
                    AND filed_after_days <= ?
                    AND (size_range LIKE '%100K%' OR size_range LIKE '%250K%' OR size_range LIKE '%500K%' 
                         OR size_range LIKE '%1M%' OR size_range LIKE '%5M%' 
                         OR size_range LIKE '%25M%' OR size_range LIKE '>%')
                    AND ({elite_filter})
                    ORDER BY published_date DESC
                """
                cursor = conn.execute(query, (MAX_FILING_DELAY_DAYS,))
            else:
                query = f"""
                    SELECT politician_name, politician_id, party, chamber, state,
                           ticker, company_name, size_range, price,
                           traded_date, published_date, filed_after_days
                    FROM congressional_trades
                    WHERE trade_type = "BUY"
                    AND published_date >= date("now", "-30 days")
                    AND filed_after_days <= ?
                    AND (size_range LIKE '%100K%' OR size_range LIKE '%250K%' OR size_range LIKE '%500K%' 
                         OR size_range LIKE '%1M%' OR size_range LIKE '%5M%' 
                         OR size_range LIKE '%25M%' OR size_range LIKE '>%')
                    AND ({elite_filter})
                    ORDER BY published_date DESC
                """
                cursor = conn.execute(query, (MAX_FILING_DELAY_DAYS,))
            large_buys = cursor.fetchall()
            
            for trade in large_buys:
                ticker = trade['ticker']
                politician = f"{trade['politician_name']} ({trade['party']})"
                
                # Convert date strings to datetime objects
                trade_date = pd.to_datetime(trade['traded_date']) if trade['traded_date'] else pd.NaT
                published_date = pd.to_datetime(trade['published_date']) if trade['published_date'] else pd.NaT
                
                # Build DataFrame for display
                trades_data = [{
                    "Ticker": ticker,
                    "Insider Name": politician,
                    "Politician ID": trade['politician_id'],
                    "Title": f"{trade['chamber'] or 'Congress'} - {trade['state']}",
                    "Trade Date": trade_date,
                    "Published Date": published_date,
                    "Size Range": trade['size_range'],
                    "Filed After": f"{trade['filed_after_days']} days" if trade['filed_after_days'] else 'N/A',
                    "Price": f"${trade['price']:.2f}" if trade['price'] else 'N/A'
                }]
                trades_df = pd.DataFrame(trades_data)
                
                # Get issuer_id safely (may not exist in older records)
                issuer_id_val = None
                if has_issuer_id:
                    try:
                        issuer_id_val = trade['issuer_id']
                    except (KeyError, IndexError):
                        pass
                
                alert = InsiderAlert(
                    signal_type="Elite Congressional Buy",
                    ticker=ticker,
                    company_name=trade['company_name'] or ticker,
                    trades=trades_df,
                    details={
                        "politician": trade['politician_name'],
                        "politician_id": trade['politician_id'],
                        "party": trade['party'],
                        "size": trade['size_range'],
                        "published_date": trade['published_date'],
                        "issuer_id": issuer_id_val,
                        "elite_trader": True
                    }
                )
                alerts.append(alert)
        
        logger.info(f"Detected {len(alerts)} Elite Congressional buy signals ($100K+, Elite traders only)")
    except Exception as e:
        logger.error(f"Error detecting large Congressional buys: {e}", exc_info=True)
    
    return alerts


def detect_trinity_signal_alerts() -> List[InsiderAlert]:
    """
    Detect Trinity Signals: Corporate Insider + Elite Congressional + Superinvestor convergence.
    
    Returns list of InsiderAlert objects with temporal correlation analysis.
    """
    alerts = []
    
    try:
        # Get raw Trinity signals from dataroma_scraper
        trinity_signals = dataroma_detect_trinity()
        
        if not trinity_signals:
            logger.info("No Trinity Signals detected")
            return alerts
        
        logger.info(f"Found {len(trinity_signals)} raw Trinity convergences")
        
        # Enrich each signal with temporal correlation analysis
        for signal in trinity_signals:
            ticker = signal['ticker']
            
            # Get temporal convergence analysis
            temporal = detect_temporal_convergence(ticker, lookback_days=30)
            
            if not temporal:
                continue  # Skip if temporal analysis fails
            
            # Create synthetic DataFrame for alert (Trinity signals don't have traditional "trades")
            trades_df = pd.DataFrame([{
                'Ticker': ticker,
                'Company Name': ticker,  # Will be enriched later
                'Insider Name': f"{signal['insider_count']} Corporate Insiders",
                'Title': 'Trinity Signal',
                'Trans': 'P',
                'Value ($)': signal.get('insider_value', 0),
                'Trade Date': temporal['earliest_date']
            }])
            
            # Build details dict with full temporal context
            details = {
                'signal_type': 'Trinity Signal',
                'convergence_score': temporal['convergence_score'],
                'temporal_pattern': temporal['pattern'],
                'window_days': temporal['window_days'],
                'timeline': temporal['timeline'],
                'insider_count': signal['insider_count'],
                'insider_value': signal.get('insider_value', 0),
                'congressional_count': signal['congressional_count'],
                'politicians': signal.get('politicians', ''),
                'superinvestor_count': signal['superinvestor_count'],
                'managers': signal.get('managers', ''),
                'insider_details': temporal.get('insider_details', []),
                'congressional_details': temporal.get('congressional_details', []),
                'superinvestor_details': temporal.get('superinvestor_details', [])
            }
            
            alert = InsiderAlert(
                signal_type="Trinity Signal",
                ticker=ticker,
                company_name=ticker,  # Will be enriched
                trades=trades_df,
                details=details
            )
            alerts.append(alert)
        
        logger.info(f"Created {len(alerts)} Trinity Signal alerts with temporal correlation")
        
    except Exception as e:
        logger.error(f"Error creating Trinity Signal alerts: {e}", exc_info=True)
    
    return alerts


def detect_signals(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Run all signal detection functions.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of all InsiderAlert objects
    """
    logger.info("Running signal detection")
    
    all_alerts = []
    
    # Corporate insider signals
    all_alerts.extend(detect_cluster_buying(df))
    all_alerts.extend(detect_ceo_cfo_buy(df))
    all_alerts.extend(detect_large_single_buy(df))
    # REMOVED: First Buy in 12 Months signal (less reliable)
    # all_alerts.extend(detect_first_buy_12m(df))
    all_alerts.extend(detect_bearish_cluster_selling(df))
    all_alerts.extend(detect_strategic_investor_buy(df))
    
    # Congressional signals (if enabled)
    # Congressional data is scraped at the start of run_once() (same time as OpenInsider)
    if USE_CAPITOL_TRADES:
        try:
            logger.info("Detecting Congressional signals from database")
            # New approach: Query database directly (no need to pass trades list)
            all_alerts.extend(detect_congressional_cluster_buy())
            all_alerts.extend(detect_large_congressional_buy())
        except Exception as e:
            logger.error(f"Error detecting Congressional signals: {e}", exc_info=True)
    
    # Trinity Signals (if Dataroma integration enabled)
    if DATAROMA_AVAILABLE:
        try:
            logger.info("Detecting Trinity Signals (Corporate + Congressional + Superinvestor convergence)")
            trinity_alerts = detect_trinity_signal_alerts()
            all_alerts.extend(trinity_alerts)
        except Exception as e:
            logger.error(f"Error detecting Trinity signals: {e}", exc_info=True)
    
    logger.info(f"Total signals detected before deduplication: {len(all_alerts)}")
    
    # Deduplicate: If same ticker+insider triggers multiple signals, keep only highest priority
    all_alerts = deduplicate_alerts(all_alerts)
    
    logger.info(f"Total signals after deduplication: {len(all_alerts)}")
    return all_alerts


def deduplicate_alerts(alerts: List[InsiderAlert]) -> List[InsiderAlert]:
    """
    Remove duplicate alerts for same ticker when a trade triggers multiple signal types.
    Keeps only the highest-priority signal per ticker+insider combination.
    
    Priority order (highest to lowest):
    1. Trinity Signal (NEW - highest conviction)
    2. Congressional Cluster Buy
    3. Large Congressional Buy  
    4. Corporation Purchase
    5. Cluster Buying
    6. C-Suite Buy
    7. Large Single Buy
    8. Bearish Cluster Selling
    9. Strategic Investor Buy
    
    Args:
        alerts: List of InsiderAlert objects
        
    Returns:
        Deduplicated list of InsiderAlert objects
    """
    if not alerts:
        return alerts
    
    # Define priority ranking (lower number = higher priority)
    priority_map = {
        'Congressional Cluster Buy': 1,
        'Large Congressional Buy': 2,
        'Corporation Purchase': 3,
        'Cluster Buying': 4,
        'C-Suite Buy': 5,
        'Large Single Buy': 6,
        'Bearish Cluster Selling': 7,
        'Strategic Investor Buy': 8,
    }
    
    # Group alerts by ticker
    ticker_groups = {}
    for alert in alerts:
        ticker = alert.ticker
        if ticker not in ticker_groups:
            ticker_groups[ticker] = []
        ticker_groups[ticker].append(alert)
    
    deduplicated = []
    
    for ticker, ticker_alerts in ticker_groups.items():
        if len(ticker_alerts) == 1:
            # Only one signal for this ticker, keep it
            deduplicated.append(ticker_alerts[0])
        else:
            # Multiple signals for same ticker - check if they're truly duplicates
            # Keep clusters (multiple insiders) separate from single-insider signals
            cluster_alerts = []
            single_alerts = {}  # key: insider_name -> alert
            
            for alert in ticker_alerts:
                # Cluster signals involve multiple people
                if 'Cluster' in alert.signal_type:
                    cluster_alerts.append(alert)
                else:
                    # Single-insider signals - track by insider name
                    if not alert.trades.empty and 'Insider Name' in alert.trades.columns:
                        insider_name = alert.trades['Insider Name'].iloc[0]
                        
                        # If we already have a signal for this insider, keep higher priority one
                        if insider_name in single_alerts:
                            existing = single_alerts[insider_name]
                            existing_priority = priority_map.get(existing.signal_type, 99)
                            new_priority = priority_map.get(alert.signal_type, 99)
                            
                            if new_priority < existing_priority:
                                single_alerts[insider_name] = alert
                                logger.debug(f"Replaced {existing.signal_type} with {alert.signal_type} for {ticker} - {insider_name}")
                        else:
                            single_alerts[insider_name] = alert
                    else:
                        # No insider name found, keep it
                        single_alerts[f"unknown_{len(single_alerts)}"] = alert
            
            # Add all cluster alerts (they represent different groups)
            deduplicated.extend(cluster_alerts)
            
            # Add single-insider alerts (deduplicated per insider)
            deduplicated.extend(single_alerts.values())
    
    removed_count = len(alerts) - len(deduplicated)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} duplicate signals (same ticker+insider, lower priority)")
    
    return deduplicated


def calculate_composite_signal_score(alert: InsiderAlert, context: Optional[Dict] = None) -> float:
    """
    Calculate composite score for signal ranking using multi-factor analysis.
    
    Scoring Factors:
    1. Signal Type Hierarchy (0-10 points)
       - Trinity Signal: 10
       - Elite Congressional Cluster: 9
       - Elite Congressional Buy: 8
       - Cluster Buying: 7
       - Corporation Purchase: 7
       - C-Suite Buy: 6
       - Large Single Buy: 5
       - Strategic Investor: 5
       - Bearish Selling: 3
    
    2. Temporal Convergence Bonus (0-3 points)
       - Sequential pattern (Congress → Insider → Fund): +3
       - Tight window (<14 days): +2
       - Concurrent buying: +1
    
    3. Dollar Value Score (0-3 points)
       - $5M+: 3
       - $1M-$5M: 2
       - $500K-$1M: 1.5
       - $100K-$500K: 1
       - <$100K: 0.5
    
    4. Insider Seniority Bonus (0-2 points)
       - CEO/CFO/COO: +2
       - VP/Director: +1
       - Other: +0.5
    
    5. Market Cap Multiplier (0.8-1.2x)
       - Small cap (<$2B): 1.2x (higher beta, more impact)
       - Mid cap ($2B-$10B): 1.1x
       - Large cap ($10B-$100B): 1.0x
       - Mega cap (>$100B): 0.9x (harder to move)
    
    6. Short Interest Adjustment (-2 to +1)
       - <5%: 0 (neutral)
       - 5-15%: +1 (potential squeeze)
       - 15-30%: 0 (risky)
       - >30%: -2 (very risky)
    
    7. Bipartisan Bonus (0-1 points)
       - Bipartisan Congressional: +1
    
    Returns:
        Float score (typically 5-20 range, higher = stronger signal)
    """
    score = 0.0
    
    # 1. Signal Type Hierarchy
    signal_type_scores = {
        'Trinity Signal': 10,
        'Elite Congressional Cluster': 9,
        'Bipartisan Elite Congressional Cluster': 9.5,
        'Elite Congressional Buy': 8,
        'Cluster Buying': 7,
        'Corporation Purchase': 5,                     # Reduced from 7 - still significant but not dominating
        'C-Suite Buy': 6,
        'Large Single Buy': 5,
        'Strategic Investor Buy': 5,
        'Bearish Cluster Selling': 3,
        'Congressional Cluster Buy': 8,  # Legacy name
        'Large Congressional Buy': 7     # Legacy name
    }
    score += signal_type_scores.get(alert.signal_type, 4)
    
    # 2. Temporal Convergence Bonus (for Trinity Signals)
    if alert.signal_type == 'Trinity Signal' and alert.details:
        convergence_score = alert.details.get('convergence_score', 0)
        pattern = alert.details.get('temporal_pattern', '')
        
        if 'SEQUENTIAL (Ideal)' in pattern:
            score += 3
        elif 'TIGHT' in pattern:
            score += 2
        else:
            score += 1
        
        # Additional bonus for high convergence score
        if convergence_score >= 9:
            score += 1
    
    # 3. Dollar Value Score
    total_value = 0
    if not alert.trades.empty and 'Value ($)' in alert.trades.columns:
        total_value = alert.trades['Value ($)'].sum()
    elif alert.details and 'total_value' in alert.details:
        total_value = alert.details['total_value']
    elif alert.details and 'insider_value' in alert.details:
        total_value = alert.details['insider_value']
    
    if total_value >= 5_000_000:
        score += 3
    elif total_value >= 1_000_000:
        score += 2
    elif total_value >= 500_000:
        score += 1.5
    elif total_value >= 100_000:
        score += 1
    else:
        score += 0.5
    
    # 4. Insider Seniority Bonus
    if not alert.trades.empty and 'Title' in alert.trades.columns:
        titles = alert.trades['Title'].str.upper().tolist()
        if any(title in str(t) for t in titles for title in ['CEO', 'CFO', 'COO', 'CHIEF']):
            score += 2
        elif any(title in str(t) for t in titles for title in ['VP', 'DIRECTOR', 'PRESIDENT']):
            score += 1
        else:
            score += 0.5
    
    # 5. Market Cap Multiplier (applied if context available)
    if context and 'market_cap' in context:
        market_cap = context['market_cap']
        if market_cap < 2_000_000_000:  # <$2B
            score *= 1.2
        elif market_cap < 10_000_000_000:  # $2B-$10B
            score *= 1.1
        elif market_cap > 100_000_000_000:  # >$100B
            score *= 0.9
        # Else 1.0x (no change)
    
    # 6. Short Interest Adjustment
    if context and 'short_interest' in context:
        short_pct = context.get('short_interest', 0)
        if short_pct is not None:
            if 5 <= short_pct < 15:
                score += 1  # Potential squeeze
            elif short_pct > 30:
                score -= 2  # Very risky
    
    # 7. Bipartisan Bonus
    if 'Bipartisan' in alert.signal_type:
        score += 1
    elif alert.details and alert.details.get('bipartisan'):
        score += 1
    
    return round(score, 2)


def select_top_signals(
    alerts: List[InsiderAlert],
    top_n: int = 3,
    enrich_context: bool = True
) -> List[InsiderAlert]:
    """
    Select top N signals based on composite scoring algorithm.
    
    Process:
    1. Calculate composite score for each signal
    2. Optionally enrich with market context (for market cap / short interest factors)
    3. Sort by score (descending)
    4. Return top N
    
    Args:
        alerts: List of InsiderAlert objects
        top_n: Number of top signals to return
        enrich_context: Whether to fetch market data for scoring (slower but more accurate)
    
    Returns:
        List of top N InsiderAlert objects, sorted by score
    """
    if not alerts:
        return alerts
    
    if len(alerts) <= top_n:
        logger.info(f"Only {len(alerts)} signals detected (≤ top_n={top_n}), returning all")
        return alerts
    
    logger.info(f"Scoring {len(alerts)} signals to select top {top_n}...")
    
    # Calculate scores with optional context enrichment
    scored_alerts = []
    for alert in alerts:
        context = None
        
        if enrich_context:
            try:
                # Get basic market context for scoring (lightweight version)
                context = get_company_context(alert.ticker)
            except Exception as e:
                logger.warning(f"Could not get context for {alert.ticker}: {e}")
        
        score = calculate_composite_signal_score(alert, context)
        scored_alerts.append((score, alert))
        
        logger.debug(f"{alert.ticker} ({alert.signal_type}): score={score}")
    
    # Sort by score (descending)
    scored_alerts.sort(key=lambda x: x[0], reverse=True)
    
    # Log scoring results
    logger.info("=" * 60)
    logger.info("COMPOSITE SCORING RESULTS")
    logger.info("=" * 60)
    for i, (score, alert) in enumerate(scored_alerts[:top_n], 1):
        logger.info(f"{i}. {alert.ticker} - {alert.signal_type}: {score} points")
    
    if len(scored_alerts) > top_n:
        logger.info("")
        logger.info(f"Filtered out {len(scored_alerts) - top_n} lower-scoring signals:")
        for i, (score, alert) in enumerate(scored_alerts[top_n:], top_n + 1):
            logger.info(f"{i}. {alert.ticker} - {alert.signal_type}: {score} points")
    
    logger.info("=" * 60)
    
    # Return top N alerts
    top_alerts = [alert for _, alert in scored_alerts[:top_n]]
    return top_alerts


# State file functions removed - using database-only deduplication


def format_email_html(alert: InsiderAlert) -> str:
    """
    Format alert as HTML email body with full context (matching Telegram format).
    
    Args:
        alert: InsiderAlert object
        
    Returns:
        HTML string
    """
    html = f"""
    <html>
    <head>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 30px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{ 
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-top: 0;
            }}
            h2 {{ 
                color: #2980b9;
                margin-top: 25px;
                margin-bottom: 10px;
                font-size: 1.3em;
            }}
            .header {{
                background: #ffffff;
                color: #1a1a1a;
                padding: 25px 20px;
                text-align: center;
                border-bottom: 3px solid #667eea;
                margin-bottom: 25px;
            }}
            .ticker {{
                font-size: 2.2em;
                font-weight: 700;
                margin: 5px 0;
                color: #667eea;
                letter-spacing: -0.5px;
            }}
            .company {{
                font-size: 1em;
                color: #666;
                font-weight: 400;
            }}
            .signal-box {{
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
                border-left: 4px solid #3498db;
            }}
            .signal-item {{
                margin: 8px 0;
            }}
            .trades-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
                font-size: 0.95em;
            }}
            .trades-table th {{
                background-color: #3498db;
                color: white;
                padding: 12px 8px;
                text-align: left;
                font-weight: 600;
            }}
            .trades-table td {{
                border: 1px solid #ddd;
                padding: 10px 8px;
            }}
            .trades-table tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            .metric-row {{
                display: flex;
                justify-content: space-between;
                margin: 10px 0;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }}
            .metric-label {{
                font-weight: 600;
                color: #555;
            }}
            .metric-value {{
                color: #2c3e50;
            }}
            .positive {{ color: #27ae60; }}
            .negative {{ color: #e74c3c; }}
            .stars {{
                color: #f39c12;
                font-size: 1.2em;
            }}
            .ai-insight {{
                background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
                border-left: 4px solid #667eea;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }}
            .congressional-section {{
                margin: 20px 0;
            }}
            .trade-list {{
                list-style: none;
                padding: 0;
            }}
            .trade-list li {{
                padding: 8px;
                margin: 5px 0;
                background-color: #f8f9fa;
                border-radius: 4px;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 0.9em;
                color: #7f8c8d;
                text-align: center;
            }}
            .link-button {{
                display: inline-block;
                background-color: #3498db;
                color: white !important;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 0;
            }}
            .link-button:hover {{
                background-color: #2980b9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div style="font-size: 1.5em;">🚨 {alert.signal_type.upper()} 🚨</div>
                <div style="margin-top:10px;">
                    <span class="ticker" style="font-size:2em;">{alert.company_name if alert.company_name != alert.ticker else alert.ticker}</span>
                    <span class="ticker" style="font-size:2em; margin-left:10px;">{f'(${alert.ticker})' if alert.company_name != alert.ticker else ''}</span>
                </div>
            </div>
    """
    
    # Signal-specific details
    if "investor" in alert.details:
        # Strategic investor - skip the info section
        pass
        
    elif "politician" in alert.details:
        # High-conviction Congressional trade - only show if known trader
        html += f"""
            <div class="signal-box">
                <div class="signal-item"><strong>⭐ Known Trader:</strong> Proven track record</div>
            </div>
        """
    
    # Trades table
    html += """
        <h2>📊 Trade Details</h2>
        <table class="trades-table">
            <tr>
                <th>Traded</th>
                <th>Published</th>
                <th>Days Past</th>
                <th>Name</th>
                <th>Role</th>
                <th>Type</th>
                <th>Price</th>
                <th>Amount</th>
                <th>Delta %</th>
            </tr>
    """
    
    for _, row in alert.trades.iterrows():  # Show ALL trades instead of head(5)
        # Check if this is a Congressional trade (has Published Date column)
        is_congressional = "Published Date" in row and pd.notna(row.get("Published Date"))
        
        if is_congressional:
            # Format as "1st Jan 2025"
            if pd.notna(row.get("Traded Date")):
                td = row["Traded Date"]
                day_suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(td.day if td.day < 20 else td.day % 10, 'th')
                traded_date = f"{td.day}{day_suffix} {td.strftime('%b %Y')}"
            else:
                traded_date = "N/A"
            
            if pd.notna(row.get("Published Date")):
                pd_date = row["Published Date"]
                day_suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(pd_date.day if pd_date.day < 20 else pd_date.day % 10, 'th')
                published_date = f"{pd_date.day}{day_suffix} {pd_date.strftime('%b %Y')}"
            else:
                published_date = "N/A"
            
            filed_after = str(row.get("Filed After", "N/A"))
        else:
            # Corporate insider trade - use Trade Date and Filing Date
            date_col = "Traded Date" if "Traded Date" in row else "Trade Date"
            if pd.notna(row.get(date_col)):
                td = row[date_col]
                day_suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(td.day if td.day < 20 else td.day % 10, 'th')
                traded_date = f"{td.day}{day_suffix} {td.strftime('%b %Y')}"
            else:
                traded_date = "N/A"
            
            # Filing Date (Published Date for corporate insiders)
            # Check if Filing Date column exists and has data
            if "Filing Date" in row and pd.notna(row.get("Filing Date")):
                try:
                    fd = pd.to_datetime(row["Filing Date"])
                    day_suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(fd.day if fd.day < 20 else fd.day % 10, 'th')
                    published_date = f"{fd.day}{day_suffix} {fd.strftime('%b %Y')}"
                    
                    # Calculate Days Past
                    if pd.notna(row.get(date_col)):
                        trade_dt = pd.to_datetime(row[date_col])
                        days_diff = (fd - trade_dt).days
                        filed_after = str(days_diff)
                    else:
                        filed_after = "—"
                except Exception as e:
                    logger.debug(f"Could not parse Filing Date: {e}")
                    published_date = "—"
                    filed_after = "—"
            else:
                # No Filing Date available for this corporate insider trade
                published_date = "—"
                filed_after = "—"
        
        name = row['Insider Name']
        
        # Determine role (party/chamber for Congressional, title for corporate)
        role = ""
        if is_congressional:
            # Extract party and chamber for Congressional trades
            party = ""
            chamber = ""
            if '(' in name and ')' in name:
                party_match = name.split('(')[1].split(')')[0] if '(' in name else ''
                party = party_match.strip()
            
            # Try to get chamber from row if available
            if 'Chamber' in row and pd.notna(row.get('Chamber')):
                chamber = str(row['Chamber'])
            elif 'State' in row and pd.notna(row.get('State')):
                # Infer it might be congressional
                chamber = "Congress"
            
            role = f"{party} {chamber}".strip() if party or chamber else "Congressman"
        else:
            # Corporate insider - use title and clean up abbreviations
            if 'Title' in row and pd.notna(row.get('Title')):
                role = str(row['Title'])
            elif 'Title Normalized' in row and pd.notna(row.get('Title Normalized')):
                role = str(row['Title Normalized'])
            else:
                role = "Insider"
            
            # Expand common abbreviations
            role = role.replace("10%", "10%+ Owner")
            role = role.replace("Dir", "Director") if role == "Dir" else role
            role = role.replace("Pres", "President") if role == "Pres" else role
            role = role.replace("VP", "Vice President") if role == "VP" else role
            role = role.replace("GC", "General Counsel") if role == "GC" else role
        
        # Format name for Congressional trades
        if '(' in name and ')' in name:
            party_match = name.split('(')[1].split(')')[0] if '(' in name else ''
            name_part = name.split('(')[0].strip()
            name_parts = name_part.split()
            if len(name_parts) >= 2:
                name = f"{name_parts[0][0]}. {' '.join(name_parts[1:])} ({party_match})"
        
        # Determine transaction type from row data - use P for Purchase, S for Sale
        trans_type = "P"
        if "Transaction" in row and pd.notna(row.get("Transaction")):
            trans_str = str(row["Transaction"]).upper()
            if "SALE" in trans_str or "SELL" in trans_str:
                trans_type = "S"
        # For Congressional trades, type might be in row text
        row_text = str(row).upper()
        if "SALE" in row_text or "SELL" in row_text:
            trans_type = "S"
        
        type_color = "#27ae60" if trans_type == "P" else "#e74c3c"
        
        # Price column
        price_cell = "—"
        if "Price" in row and pd.notna(row.get("Price")) and row.get("Price"):
            try:
                price_val = float(row["Price"])
                price_cell = f"${price_val:.2f}"
            except:
                price_cell = str(row["Price"])
        
        # Amount column
        value_cell = ""
        if "Size Range" in row and pd.notna(row.get("Size Range")) and row.get("Size Range"):
            value_cell = str(row["Size Range"])
        elif pd.notna(row.get('Value')) and row['Value'] > 0:
            value_cell = f"${row['Value']:,.0f}"
        
        # Delta % column (ownership change)
        delta_cell = "—"
        if "Delta Own" in row and pd.notna(row.get("Delta Own")):
            delta_val = str(row["Delta Own"]).strip()
            if delta_val and delta_val != "—" and delta_val != "":
                # Delta Own might be "New" or a percentage like "+15%"
                delta_cell = delta_val
        
        html += f"""
            <tr>
                <td>{traded_date}</td>
                <td>{published_date}</td>
                <td>{filed_after}</td>
                <td>{name[:50]}</td>
                <td>{role[:30]}</td>
                <td style="color:{type_color}; font-weight:500;">{trans_type}</td>
                <td>{price_cell}</td>
                <td>{value_cell}</td>
                <td>{delta_cell}</td>
            </tr>
        """
    
    html += """</table>"""
    
    # Add company context
    try:
        context = get_company_context(alert.ticker)
        
        # Update alert company_name if we got it from yfinance
        if alert.company_name == alert.ticker:
            try:
                import yfinance as yf
                stock = yf.Ticker(alert.ticker)
                info = stock.info
                if info.get("longName"):
                    alert.company_name = info["longName"]
                elif info.get("shortName"):
                    alert.company_name = info["shortName"]
            except:
                pass
        
        # Price Action with chart
        if context.get("price_change_5d") is not None or context.get("price_change_1m") is not None:
            html += "<h2>📊 Price Action</h2>"
            
            # Price changes ABOVE the chart
            try:
                import yfinance as yf
                stock = yf.Ticker(alert.ticker)
                hist = stock.history(period="5y")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    
                    timeframes = [
                        ('1D', 1, '1-day'),
                        ('5D', 5, '5-day'),
                        ('1M', 21, '1-month'),
                        ('3M', 63, '3-month'),
                        ('6M', 126, '6-month'),
                        ('1Y', 252, '1-year'),
                        ('2Y', 504, '2-year'),
                        ('5Y', 1260, '5-year')
                    ]
                    
                    # Use flexbox for mobile-responsive layout - span full width
                    html += '<div style="display:flex; flex-wrap:wrap; gap:4px; margin:8px 0 20px 0; width:100%;">'
                    for label, days, desc in timeframes:
                        if len(hist) > days:
                            past = hist['Close'].iloc[-days-1]
                            change = ((current - past) / past) * 100
                            color = '#27ae60' if change > 0 else '#e74c3c'
                            html += f'<div style="flex: 1 1 70px; min-width:70px; padding:10px; background:#f8f9fa; border-radius:4px; text-align:center;"><strong>{label}:</strong><br><span style="color:{color}; font-weight:600; font-size:1.1em;">{change:+.1f}%</span></div>'
                    html += '</div>'
            except Exception as e:
                logger.warning(f"Could not fetch full yfinance data for {alert.ticker}: {e}")
                # Fallback to context data if yfinance fails
                html += '<div style="display:flex; flex-wrap:wrap; gap:4px; margin:8px 0 20px 0; width:100%;">'
                if context.get("price_change_5d") is not None:
                    change_5d = context["price_change_5d"]
                    color = '#27ae60' if change_5d > 0 else '#e74c3c'
                    html += f'<div style="flex: 1 1 70px; min-width:70px; padding:10px; background:#f8f9fa; border-radius:4px; text-align:center;"><strong>5D:</strong><br><span style="color:{color}; font-weight:600; font-size:1.1em;">{change_5d:+.1f}%</span></div>'
                if context.get("price_change_1m") is not None:
                    change_1m = context["price_change_1m"]
                    color = '#27ae60' if change_1m > 0 else '#e74c3c'
                    html += f'<div style="flex: 1 1 70px; min-width:70px; padding:10px; background:#f8f9fa; border-radius:4px; text-align:center;"><strong>1M:</strong><br><span style="color:{color}; font-weight:600; font-size:1.1em;">{change_1m:+.1f}%</span></div>'
                html += '</div>'
            
            # Chart below price changes
            html += f'<img src="https://finviz.com/chart.ashx?t={alert.ticker}&ty=c&ta=1&p=d&s=l" alt="{alert.ticker} Chart" style="width:100%; height:auto; border:1px solid #ddd; border-radius:5px; margin-top:10px;">'
        
        # 52-week range as boxes below chart
        if context.get("week_52_high") and context.get("week_52_low") and context.get("current_price"):
            html += '<table style="width:100%; border-collapse:collapse; margin-top:10px;"><tr>'
            html += f'<td style="background:#f5f5f5; padding:20px 15px; width:33%; text-align:center; border-right:2px solid white;"><div style="font-size:1.8em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">${context["week_52_low"]:.2f}</div><div style="font-size:0.85em; color:#7f8c8d;">52W Low</div></td>'
            html += f'<td style="background:#f5f5f5; padding:20px 15px; width:33%; text-align:center; border-right:2px solid white;"><div style="font-size:1.8em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">${context["current_price"]:.2f}</div><div style="font-size:0.85em; color:#7f8c8d;">Current</div></td>'
            html += f'<td style="background:#f5f5f5; padding:20px 15px; width:33%; text-align:center;"><div style="font-size:1.8em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">${context["week_52_high"]:.2f}</div><div style="font-size:0.85em; color:#7f8c8d;">52W High</div></td>'
            html += '</tr></table>'
        
        # Market data
        if context.get("market_cap") or context.get("pe_ratio") or context.get("sector") or context.get("short_interest"):
            html += "<h2>📈 Market Data</h2>"
            html += '<table style="width:100%; border-collapse:collapse;"><tr>'
            
            if context.get("sector"):
                html += f'<td style="background:#f5f5f5; padding:20px 15px; width:25%; text-align:center; border-right:2px solid white;"><div style="font-size:1.5em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">{context["sector"]}</div><div style="font-size:0.85em; color:#7f8c8d;">Sector</div></td>'
            if context.get("market_cap"):
                mc_billions = context["market_cap"] / 1e9
                border_style = "border-right:2px solid white;" if context.get("pe_ratio") or context.get("short_interest") else ""
                html += f'<td style="background:#f5f5f5; padding:20px 15px; width:25%; text-align:center; {border_style}"><div style="font-size:1.5em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">${mc_billions:.1f}B</div><div style="font-size:0.85em; color:#7f8c8d;">Market Cap</div></td>'
            if context.get("pe_ratio"):
                border_style = "border-right:2px solid white;" if context.get("short_interest") else ""
                html += f'<td style="background:#f5f5f5; padding:20px 15px; width:25%; text-align:center; {border_style}"><div style="font-size:1.5em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">{context["pe_ratio"]:.1f}</div><div style="font-size:0.85em; color:#7f8c8d;">P/E Ratio</div></td>'
            if context.get("short_interest"):
                si_pct = context["short_interest"] * 100
                emoji = "🔥" if si_pct > 15 else ""
                html += f'<td style="background:#f5f5f5; padding:20px 15px; width:25%; text-align:center;"><div style="font-size:1.5em; font-weight:bold; color:#2c3e50; margin-bottom:5px;">{emoji}{si_pct:.1f}%</div><div style="font-size:0.85em; color:#7f8c8d;">Short Interest</div></td>'
            
            html += '</tr></table>'
        
        # Congressional trades
        if context.get("congressional_trades"):
            congressional_trades = context["congressional_trades"]
            buys = [t for t in congressional_trades if t.get("type", "").upper() in ["BUY", "PURCHASE"]]
            sells = [t for t in congressional_trades if t.get("type", "").upper() in ["SELL", "SALE"]]
            
            if buys or sells:
                html += """
                    <div style="margin-top:20px;">
                        <h2 style="margin-top:0;">🏛️ Congressional Market Activity</h2>
                        <p style="font-size:0.9em; color:#666; margin-top:0; margin-bottom:15px;">Recent Congressional trades on this ticker</p>
                        <table style="width:100%; border-collapse:collapse;"><tr>
                """
                
                if buys:
                    html += "<td style='width:50%; background:#e8f5e9; padding:20px; vertical-align:top; border-right:2px solid white;'>"
                    html += "<h3 style='margin-top:0; color:#27ae60;'>↑ Recent Buys</h3>"
                    for trade in buys[:5]:  # Show max 5
                        pol = trade.get("politician", "Unknown")
                        # Format name: First letter. Last name
                        if pol and pol != "Unknown":
                            parts = pol.split()
                            if len(parts) >= 2:
                                # Extract party if present
                                party = ""
                                if '(' in pol and ')' in pol:
                                    party_part = pol.split('(')[1].split(')')[0]
                                    party = f" ({party_part})"
                                    pol_name = pol.split('(')[0].strip()
                                    parts = pol_name.split()
                                
                                if len(parts) >= 2:
                                    pol = f"{parts[0][0]}. {' '.join(parts[1:])}{party}"
                        
                        size = trade.get("size", "N/A")
                        price = trade.get("price", "N/A")
                        traded_date = trade.get("traded_date", trade.get("date", "N/A"))
                        filed_after = trade.get("filed_after_days", "N/A")
                        
                        html += f"<div style='margin:10px 0; padding:10px; background:white; border-radius:4px; border-left:3px solid #27ae60;'>"
                        html += f"<strong style='color:#2c3e50;'>{pol}</strong><br>"
                        html += f"<span style='font-size:0.85em; color:#666;'>{size}"
                        if price and price != "N/A":
                            html += f" @ {price}"
                        html += "</span><br>"
                        html += f"<span style='font-size:0.8em; color:#999;'>"
                        html += f"Traded: {traded_date}"
                        if filed_after and filed_after != "N/A":
                            html += f" ({filed_after}d delay)"
                        html += "</span></div>"
                    if len(buys) > 5:
                        html += f"<p style='text-align:center; color:#999; font-style:italic; margin-top:10px;'>...and {len(buys)-5} more purchases</p>"
                    html += "</td>"
                else:
                    html += "<td style='width:50%; background:#e8f5e9; padding:20px; vertical-align:top; border-right:2px solid white; text-align:center; color:#999;'><em>No recent purchases</em></td>"
                
                if sells:
                    html += "<td style='width:50%; background:#ffebee; padding:20px; vertical-align:top;'>"
                    html += "<h3 style='margin-top:0; color:#e74c3c;'>↓ Recent Sells</h3>"
                    for trade in sells[:5]:  # Show max 5
                        pol = trade.get("politician", "Unknown")
                        # Format name: First letter. Last name
                        if pol and pol != "Unknown":
                            parts = pol.split()
                            if len(parts) >= 2:
                                # Extract party if present
                                party = ""
                                if '(' in pol and ')' in pol:
                                    party_part = pol.split('(')[1].split(')')[0]
                                    party = f" ({party_part})"
                                    pol_name = pol.split('(')[0].strip()
                                    parts = pol_name.split()
                                
                                if len(parts) >= 2:
                                    pol = f"{parts[0][0]}. {' '.join(parts[1:])}{party}"
                        
                        size = trade.get("size", "N/A")
                        price = trade.get("price", "N/A")
                        traded_date = trade.get("traded_date", trade.get("date", "N/A"))
                        filed_after = trade.get("filed_after_days", "N/A")
                        
                        html += f"<div style='margin:10px 0; padding:10px; background:white; border-radius:4px; border-left:3px solid #e74c3c;'>"
                        html += f"<strong style='color:#2c3e50;'>{pol}</strong><br>"
                        html += f"<span style='font-size:0.85em; color:#666;'>{size}"
                        if price and price != "N/A":
                            html += f" @ {price}"
                        html += "</span><br>"
                        html += f"<span style='font-size:0.8em; color:#999;'>"
                        html += f"Traded: {traded_date}"
                        if filed_after and filed_after != "N/A":
                            html += f" ({filed_after}d delay)"
                        html += "</span></div>"
                    if len(sells) > 5:
                        html += f"<p style='text-align:center; color:#999; font-style:italic; margin-top:10px;'>...and {len(sells)-5} more sales</p>"
                    html += "</td>"
                else:
                    html += "<td style='width:50%; background:#ffebee; padding:20px; vertical-align:top; text-align:center; color:#999;'><em>No recent sales</em></td>"
                
                html += "</tr></table></div>"
        
        # Recent News (only show if news contains ticker mention)
        if context.get("news") and len(context["news"]) > 0:
            html += '<h2 style="margin-top:25px;">📰 Recent News</h2>'
            for news_item in context["news"][:3]:
                title = news_item.get("title", "")
                url = news_item.get("url", "")
                published = news_item.get("published_at", "")
                image_url = news_item.get("image_url", "")
                
                # Format published date
                pub_date = ""
                if published:
                    try:
                        from dateutil import parser
                        dt = parser.parse(published)
                        pub_date = dt.strftime('%b %d, %Y')
                    except:
                        pub_date = published[:10]
                
                # News item card without image
                html += '<div style="background:#f8f9fa; border-left:4px solid #3498db; padding:15px; border-radius:4px; margin-bottom:15px;">'
                
                if url:
                    html += f'<a href="{url}" style="color:#2c3e50; text-decoration:none; font-weight:500; font-size:1.05em;">{title}</a>'
                else:
                    html += f'<span style="color:#2c3e50; font-weight:500; font-size:1.05em;">{title}</span>'
                
                if pub_date:
                    html += f'<div style="color:#7f8c8d; font-size:0.85em; margin-top:4px;">{pub_date}</div>'
                html += '</div>'
        
        # Confidence score display (AI insights removed)
        confidence_score, score_reason = calculate_confidence_score(alert, context)
        html += f"""
            <div class="ai-insight">
                <h2 style="margin-top:0;">🧠 AI Insight</h2>
                <p style="margin:0;line-height:1.8;">{formatted_insight}</p>
            </div>
        """
        
    except Exception as e:
        logger.warning(f"Could not add context to email: {e}")
    
    # Footer with link - use Capitol Trades for Congressional signals
    is_congressional = "Congressional" in alert.signal_type
    if is_congressional:
        # Get ALL politician_ids from trades for a comprehensive link
        politician_ids = []
        if not alert.trades.empty and "Politician ID" in alert.trades.columns:
            for _, row in alert.trades.iterrows():
                pid = str(row.get("Politician ID", "")).strip()
                if pid and pid != "nan" and pid not in politician_ids:
                    politician_ids.append(pid)
        
        if politician_ids:
            # Build link with all politician IDs (Capitol Trades doesn't filter by ticker param)
            pol_params = '&'.join([f"politician={pid}" for pid in politician_ids])
            link_url = f"https://www.capitoltrades.com/trades?{pol_params}"
        else:
            # Fallback - just show all trades
            link_url = f"https://www.capitoltrades.com/trades"
        link_text = "View on Capitol Trades →"
    else:
        # OpenInsider link with full screener format and date range filter
        if not alert.trades.empty and "Trade Date" in alert.trades.columns:
            trade_dates = alert.trades["Trade Date"].dropna().tolist()
            if trade_dates:
                try:
                    min_date = pd.to_datetime(min(trade_dates))
                    max_date = pd.to_datetime(max(trade_dates))
                    # Use URL-encoded format: %2F for /
                    date_range = f"{min_date.strftime('%m')}%2F{min_date.strftime('%d')}%2F{min_date.strftime('%Y')}+-+{max_date.strftime('%m')}%2F{max_date.strftime('%d')}%2F{max_date.strftime('%Y')}"
                    link_url = f"http://openinsider.com/screener?s={alert.ticker}&o=&pl=&ph=&ll=&lh=&fd=-1&fdr={date_range}&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
                except:
                    link_url = f"http://openinsider.com/screener?s={alert.ticker}"
            else:
                link_url = f"http://openinsider.com/screener?s={alert.ticker}"
        else:
            link_url = f"http://openinsider.com/screener?s={alert.ticker}"
        link_text = "View on OpenInsider →"
    
    html += f"""
            <div style="text-align:center;margin:30px 0;">
                <a href="{link_url}" class="link-button" style="color:white;">
                    {link_text}
                </a>
            </div>
            
            <div class="footer">
                <p><strong>ALPHA WHISPERER</strong> - Insider Trading Intelligence</p>
                <p>Alert ID: {alert.alert_id[:16]}...</p>
                <p style="font-size:0.85em;color:#999;">
                    This alert combines corporate insider Form 4 filings with Congressional stock trades,
                    delivering high-conviction signals with AI-powered analysis.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def get_users_tracking_ticker(ticker: str) -> List[Dict[str, str]]:
    """
    Get all users tracking a specific ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        List of dicts with user info: {user_id, username, first_name}
    """
    try:
        ticker = ticker.upper().strip()
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, username, first_name
            FROM tracked_tickers
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
        
    except Exception as e:
        logger.warning(f"Could not check ticker tracking: {e}")
        return []


def detect_tracked_ticker_activity() -> List[Tuple[str, List[Dict], List[Dict]]]:
    """
    Check for ANY activity (OpenInsider or Congressional trades) on tracked tickers.
    Returns activity regardless of signal thresholds - ANY trade triggers notification.
    
    Returns:
        List of tuples: (ticker, tracking_users, trades)
        - ticker: Stock symbol
        - tracking_users: List of {user_id, username, first_name}
        - trades: List of trade dicts with combined OpenInsider + Congressional data
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Get all tracked tickers
        cursor.execute("SELECT DISTINCT ticker FROM tracked_tickers")
        tracked_tickers = [row[0] for row in cursor.fetchall()]
        
        if not tracked_tickers:
            return []
        
        logger.info(f"Checking activity for {len(tracked_tickers)} tracked ticker(s): {', '.join(tracked_tickers)}")
        
        results = []
        lookback_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
        
        for ticker in tracked_tickers:
            all_trades = []
            
            # Check OpenInsider trades (last 7 days by trade_date)
            cursor.execute("""
                SELECT ticker, company_name, insider_name, insider_title, trade_type, 
                       trade_date, value, qty, owned, price
                FROM openinsider_trades
                WHERE ticker = ? AND trade_date >= ?
                ORDER BY trade_date DESC
            """, (ticker, lookback_date))
            
            for row in cursor.fetchall():
                all_trades.append({
                    'source': 'OpenInsider',
                    'ticker': row[0],
                    'company_name': row[1],
                    'insider_name': row[2],
                    'title': row[3] or 'Insider',
                    'trade_type': row[4],
                    'trade_date': row[5],
                    'value': row[6],
                    'qty': row[7],
                    'owned': row[8],
                    'price': row[9]
                })
            
            # Check Congressional trades (last 7 days by published_date)
            cursor.execute("""
                SELECT ticker, company_name, politician_name, party, trade_type,
                       traded_date, published_date, size_range, price, politician_id, issuer_id
                FROM congressional_trades
                WHERE ticker = ? AND published_date >= ?
                ORDER BY published_date DESC
            """, (ticker, lookback_date))
            
            for row in cursor.fetchall():
                all_trades.append({
                    'source': 'Congressional',
                    'ticker': row[0],
                    'company_name': row[1],
                    'insider_name': row[2],  # Just the name
                    'party': row[3],  # Store party separately (D, R, I, etc.)
                    'title': 'Member of Congress',
                    'trade_type': row[4],
                    'trade_date': row[5],  # traded_date
                    'published_date': row[6],
                    'size_range': row[7],
                    'price': row[8],
                    'politician_id': row[9],
                    'issuer_id': row[10]
                })
            
            if all_trades:
                # Get users tracking this ticker
                tracking_users = get_users_tracking_ticker(ticker)
                if tracking_users:
                    results.append((ticker, tracking_users, all_trades))
                    logger.info(f"Found {len(all_trades)} trade(s) for tracked ticker {ticker} (tracked by {len(tracking_users)} user(s))")
        
        conn.close()
        return results
        
    except Exception as e:
        logger.error(f"Error detecting tracked ticker activity: {e}")
        return []


def format_telegram_message(alert: InsiderAlert) -> str:
    """Format alert as Telegram message with markdown."""
    # Escape special characters for Telegram MarkdownV2
    def escape_md(text):
        """Escape special characters for Telegram MarkdownV2."""
        if not isinstance(text, str):
            text = str(text)
        chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text
    
    def format_value(value):
        """Format dollar values with K/M suffixes."""
        if value >= 1_000_000:
            return f"${value/1_000_000:.1f}M"
        elif value >= 999_500:  # Round up to 1M if >= 999.5K
            return f"${value/1_000_000:.1f}M"
        elif value >= 1_000:
            return f"${value/1_000:.0f}K"
        else:
            return f"${value:.0f}"
    
    # Check if any users are tracking this ticker
    tracked_users = get_users_tracking_ticker(alert.ticker)
    
    msg = f"🚨 *{escape_md(alert.signal_type.upper())}* 🚨\n\n"
    # Format as "Company Name ($TICKER)" instead of "TICKER - Company Name"
    company_esc = escape_md(alert.company_name)
    ticker_esc = escape_md(alert.ticker)
    if alert.company_name != alert.ticker:
        msg += f"*{company_esc} \\(${ticker_esc}\\)*\n\n"
    else:
        msg += f"*${ticker_esc}*\n\n"
    
    # Mention users who are tracking this ticker
    if tracked_users:
        mentions = []
        for user in tracked_users:
            if user['username']:
                # Use @username if available
                mentions.append(f"@{user['username']}")
            else:
                # Use clickable mention with user_id (works even without username)
                user_id = user['user_id']
                first_name = user['first_name'] or 'User'
                mentions.append(f"[{first_name}](tg://user?id={user_id})")
        
        if mentions:
            msg += f"👤 {', '.join(mentions)}\n\n"
    
    # Top trades (max 5 for brevity)
    msg += f"📊 *Trades:*\n"
    for idx, (_, row) in enumerate(alert.trades.head(5).iterrows()):
        # Trade Date format: "15Nov" (day + 3-letter month)
        # For Congressional trades, use "Traded Date" column
        trade_date = row.get("Traded Date") if pd.notna(row.get("Traded Date")) else row.get("Trade Date")
        if pd.notna(trade_date):
            if isinstance(trade_date, str):
                # Parse string date if needed
                try:
                    from dateutil import parser
                    trade_date = parser.parse(trade_date)
                    date = f"{trade_date.day}{trade_date.strftime('%b')}"
                except:
                    date = trade_date[:5] if len(trade_date) >= 5 else trade_date
            else:
                date = f"{trade_date.day}{trade_date.strftime('%b')}"
        else:
            date = "N/A"
        
        # Format insider name - for Congressional trades, shorten to "Initial. LastName (Party)"
        insider_name = row['Insider Name']
        if '(' in insider_name and ')' in insider_name:  # Congressional format: "Name (D)-House"
            # Extract party letter
            party_match = insider_name.split('(')[1].split(')')[0] if '(' in insider_name else ''
            # Get name parts
            name_part = insider_name.split('(')[0].strip()
            name_parts = name_part.split()
            if len(name_parts) >= 2:
                # Format as "J. LastName (D)" - First initial + Last name
                formatted_name = f"{name_parts[0][0]}. {name_parts[-1]} ({party_match})"
            else:
                formatted_name = f"{name_part} ({party_match})"
            insider = escape_md(formatted_name[:30])
        else:
            # Corporate insider - format based on signal type
            if alert.signal_type == "Corporation Purchase":
                # Keep full name for Corporation Purchase signal
                insider = escape_md(insider_name[:50])
            else:
                # For other signals, format as Initial + Last Name
                # Only abbreviate if name has exactly 2 parts (FirstName LastName)
                name_parts = insider_name.split()
                if len(name_parts) == 2:
                    # Two-part name: abbreviate first name
                    formatted_name = f"{name_parts[0][0]}. {name_parts[1]}"
                    insider = escape_md(formatted_name[:25])
                elif len(name_parts) > 2:
                    # Three or more parts (e.g., Robertson Peter J): keep first + last, drop middle
                    formatted_name = f"{name_parts[0]} {name_parts[-1]}"
                    insider = escape_md(formatted_name[:25])
                else:
                    # Single name or empty
                    insider = escape_md(insider_name[:25])
        
        date_esc = escape_md(date)
        
        # Build trade line with underlined date and line break
        trade_line = f"__"
        trade_line += date_esc
        trade_line += f"__\n{insider}"
        
        # For Congressional trades, show size range and price
        if "Size Range" in row and pd.notna(row.get("Size Range")) and row.get("Size Range"):
            size_range = escape_md(str(row["Size Range"]))
            trade_line += f" \\- {size_range}"
            # Add price if available
            if "Price" in row and pd.notna(row.get("Price")) and row.get("Price"):
                price_val = escape_md(str(row["Price"]))
                trade_line += f" @ {price_val}"
        # For corporate insider trades, show dollar value
        elif pd.notna(row['Value']) and row['Value'] > 0:
            value_esc = escape_md(format_value(row['Value']))
            trade_line += f" \\- {value_esc}"
            # Add price if available for corporate trades
            if "Price" in row and pd.notna(row.get("Price")) and row.get("Price"):
                price_val = escape_md(str(row["Price"]))
                trade_line += f" @ {price_val}"
        
        # Add ownership change % if available and not empty (corporate insiders only)
        if "Delta Own" in row and pd.notna(row["Delta Own"]):
            delta_own = row["Delta Own"]
            # Only add if it's a meaningful value (not empty string)
            if isinstance(delta_own, str) and delta_own.strip():
                trade_line += f" \\({escape_md(delta_own)}\\)"
            elif isinstance(delta_own, (int, float)):
                trade_line += f" \\({delta_own:+.1f}%\\)"
        
        msg += trade_line + "\n"
    
    if len(alert.trades) > 5:
        msg += f"• \\.\\.\\.\\+{len(alert.trades) - 5} more\n"
    
    # Add company context if available
    try:
        context = get_company_context(alert.ticker)
        # Context fetched for internal use, no AI insights displayed
    except Exception as e:
        logger.warning(f"Could not add context to message: {e}")
    
    # Provide link - HTTPS links are clickable in Telegram
    # Check if this is a Congressional signal
    if "Congressional" in alert.signal_type:
        # Get ALL politician_ids from trades for a comprehensive link
        politician_ids = []
        if not alert.trades.empty and "Politician ID" in alert.trades.columns:
            for _, row in alert.trades.iterrows():
                pid = str(row.get("Politician ID", "")).strip()
                if pid and pid != "nan" and pid not in politician_ids:
                    politician_ids.append(pid)
        
        if politician_ids:
            # Build link with all politician IDs (Capitol Trades doesn't filter by ticker param)
            pol_params = '&'.join([f"politician={pid}" for pid in politician_ids])
            link_url = f"https://www.capitoltrades.com/trades?{pol_params}"
        else:
            # Fallback - just show all trades
            link_url = f"https://www.capitoltrades.com/trades"
        msg += f"\n🔗 [View on Capitol Trades]({escape_md(link_url)})"
    else:
        # OpenInsider link with full screener format and date range filter
        if not alert.trades.empty and "Trade Date" in alert.trades.columns:
            trade_dates = alert.trades["Trade Date"].dropna().tolist()
            if trade_dates:
                try:
                    min_date = pd.to_datetime(min(trade_dates))
                    max_date = pd.to_datetime(max(trade_dates))
                    # Use URL-encoded format: %2F for /
                    date_range = f"{min_date.strftime('%m')}%2F{min_date.strftime('%d')}%2F{min_date.strftime('%Y')}+-+{max_date.strftime('%m')}%2F{max_date.strftime('%d')}%2F{max_date.strftime('%Y')}"
                    link_url = f"http://openinsider.com/screener?s={alert.ticker}&o=&pl=&ph=&ll=&lh=&fd=-1&fdr={date_range}&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
                except:
                    link_url = f"http://openinsider.com/screener?s={alert.ticker}"
            else:
                link_url = f"http://openinsider.com/screener?s={alert.ticker}"
        else:
            link_url = f"http://openinsider.com/screener?s={alert.ticker}"
        msg += f"\n🔗 [View on OpenInsider]({escape_md(link_url)})"
    return msg


def format_email_text(alert: InsiderAlert) -> str:
    """
    Format alert as plain text email body (fallback for email clients that don't support HTML).
    
    Args:
        alert: InsiderAlert object
        
    Returns:
        Plain text string
    """
    text = f"""
🚨 INSIDER ALERT: {alert.signal_type}
{'=' * 70}

Ticker: {alert.ticker}
Company: {alert.company_name}
Signal: {alert.signal_type}
Alert Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    # Add signal-specific details
    if "num_insiders" in alert.details or "num_politicians" in alert.details:
        num = alert.details.get('num_insiders', alert.details.get('num_politicians', 0))
        text += f"\n{'Insiders' if 'num_insiders' in alert.details else 'Politicians'}: {num}\n"
        if "total_value" in alert.details:
            text += f"Total Value: ${alert.details['total_value']:,.0f}\n"
        if "window_days" in alert.details:
            text += f"Window: {alert.details['window_days']} days\n"
        if alert.details.get("bipartisan"):
            text += "🏛️ Bipartisan: Both parties involved\n"
            
    elif "politician" in alert.details:
        text += f"\nPolitician: {alert.details['politician']}\n"
        text += f"Date: {alert.details['date']}\n"
        text += "⭐ Known Trader: Proven track record\n"
        
    elif "investor" in alert.details:
        # Skip Corporate Investor info section for text email too
        pass
            
    elif "value" in alert.details:
        if "insider" in alert.details:
            text += f"\nInsider: {alert.details['insider']}\n"
        if "title" in alert.details:
            text += f"Title: {alert.details['title']}\n"
        text += f"Value: ${alert.details['value']:,.0f}\n"
    
    text += "\n" + "=" * 70 + "\n"
    text += "TRADE DETAILS:\n"
    text += "=" * 70 + "\n"
    
    # Add trade rows
    for _, row in alert.trades.iterrows():
        # Handle both Trade Date (corporate) and Traded Date (congressional)
        date_col = "Traded Date" if "Traded Date" in row else "Trade Date"
        date_value = row.get(date_col)
        
        # Convert to datetime if string, handle pd.Timestamp or datetime
        if isinstance(date_value, str):
            try:
                date_value = pd.to_datetime(date_value)
            except:
                date_value = None
        
        trade_date = date_value.strftime('%m/%d/%Y') if pd.notna(date_value) else "N/A"
        name = row['Insider Name']
        
        # Format name for Congressional trades
        if '(' in name and ')' in name:
            party_match = name.split('(')[1].split(')')[0] if '(' in name else ''
            name_part = name.split('(')[0].strip()
            name_parts = name_part.split()
            if len(name_parts) >= 2:
                name = f"{name_parts[0][0]}. {' '.join(name_parts[1:])} ({party_match})"
        
        text += f"\n• {trade_date}: {name}\n"
        
        # Value/Size
        if "Size Range" in row and pd.notna(row.get("Size Range")) and row.get("Size Range"):
            text += f"  Size: {row['Size Range']}"
            if "Price" in row and pd.notna(row.get("Price")) and row.get("Price"):
                text += f" @ {row['Price']}"
            text += "\n"
        elif pd.notna(row.get('Value')) and row['Value'] > 0:
            text += f"  Value: ${row['Value']:,.0f}"
            if "Delta Own" in row and pd.notna(row["Delta Own"]) and str(row["Delta Own"]).strip():
                text += f" ({row['Delta Own']})"
            text += "\n"
    
    if len(alert.trades) > 5:
        text += f"\n...and {len(alert.trades) - 5} more trades\n"
    
    # Add context summary
    try:
        context = get_company_context(alert.ticker)
        confidence_score, score_reason = calculate_confidence_score(alert, context)
        
        text += "\n" + "=" * 70 + "\n"
        text += f"CONFIDENCE: {'⭐' * confidence_score} ({confidence_score}/5)\n"
        text += f"{score_reason}\n"
        
        text += "\n" + "=" * 70 + "\n"
        # AI insights removed - cleaner signal reporting
        
    except Exception as e:
        logger.warning(f"Could not add context to text email: {e}")
    
    text += "\n" + "=" * 70 + "\n"
    # Build filtered OpenInsider link with date range (same as Telegram)
    oi_link = f"http://openinsider.com/screener?s={alert.ticker}"
    if not alert.trades.empty and "Trade Date" in alert.trades.columns:
        trade_dates = alert.trades["Trade Date"].dropna().tolist()
        if trade_dates:
            try:
                min_date = pd.to_datetime(min(trade_dates))
                max_date = pd.to_datetime(max(trade_dates))
                date_range = f"{min_date.strftime('%m')}%2F{min_date.strftime('%d')}%2F{min_date.strftime('%Y')}+-+{max_date.strftime('%m')}%2F{max_date.strftime('%d')}%2F{max_date.strftime('%Y')}"
                oi_link = f"http://openinsider.com/screener?s={alert.ticker}&o=&pl=&ph=&ll=&lh=&fd=-1&fdr={date_range}&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
            except:
                pass
    text += f"View on OpenInsider: {oi_link}\n"
    text += f"\nAlert ID: {alert.alert_id[:16]}...\n"
    text += "\nALPHA WHISPERER - Insider Trading Intelligence\n"
    
    return text


def generate_stock_chart(ticker: str, days: int = 180) -> BytesIO:
    """
    Fetch stock price chart from Finviz (same as used in emails).
    
    Args:
        ticker: Stock ticker symbol
        days: Number of days of historical data (not used, Finviz has fixed timeframes)
        
    Returns:
        BytesIO buffer containing PNG image
    """
    try:
        # Fetch chart from Finviz (same source as email charts)
        chart_url = f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d&s=l"
        
        # Add browser headers to avoid 403 errors
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://finviz.com/',
        }
        
        response = requests.get(chart_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            buf = BytesIO(response.content)
            buf.seek(0)
            return buf
        else:
            logger.warning(f"Failed to fetch Finviz chart for {ticker}: HTTP {response.status_code}")
            return None
        
    except Exception as e:
        logger.warning(f"Failed to fetch chart for {ticker}: {e}")
        return None


def send_telegram_intro(signal_counts: dict, dry_run: bool = False) -> bool:
    """Send intro message before sending individual alerts."""
    if not USE_TELEGRAM or dry_run:
        return False
    
    import random
    
    intros = [
        "AlphaWhisperer reporting in… crunching numbers and organizing signals into something that looks civilized. Here's the rundown:",
        "AlphaWhisperer online… signals sorted, noise filtered, sanity preserved. Here's what surfaced:",
        "AlphaWhisperer checking in… scanning patterns and translating chaos into English. Here's the latest:",
        "AlphaWhisperer activated… data reviewed, signals detected, confidence adjusted accordingly. Here's your update:",
        "AlphaWhisperer speaking… algorithms agree this is worth your attention. Here's the batch:",
        "AlphaWhisperer booted… charts inspected, signals wrangled, conclusions packaged. Here's what I've got:",
        "AlphaWhisperer online… combing through the noise so you don't have to. Here's the breakdown:",
        "AlphaWhisperer checking logs… patterns confirmed, surprises noted, results incoming:",
        "AlphaWhisperer ready… sorting real signals from market drama. Here's the update:",
        "AlphaWhisperer transmitting… data aligned, indicators behaving, insights prepared. Here's what I found:",
        "AlphaWhisperer engaged… noise filtered out, signals locked in. Here's the summary:",
        "AlphaWhisperer reporting… analytics completed, signal cluster identified. Here's the output:",
        "AlphaWhisperer back online… market murmurs analyzed and neatly packaged. Here's the latest batch:",
        "AlphaWhisperer status: operational… signals classified and ready for review. Here's your feed:",
        "AlphaWhisperer scanning complete… nothing exploded, which is a win. Here are the signals:",
        "AlphaWhisperer initiating report… pattern recognition says these are worth a look. Here's the data:",
        "AlphaWhisperer delivering… calculations done, anomalies labeled, insights queued. Here's what turned up:",
        "AlphaWhisperer prepared… sifted the noise, kept the good stuff. Here's the report:",
        "AlphaWhisperer transmitting analysis… the market whispered, I listened. Here's what came through:",
        "AlphaWhisperer ready to brief… signals detected, logs parsed, summary loaded. Here you go:"
    ]
    
    try:
        import asyncio
        from telegram import Bot
        from telegram.constants import ParseMode
        
        # Support multiple chat IDs
        chat_ids = [cid.strip() for cid in TELEGRAM_CHAT_ID.split(",")]
        
        # Build intro message
        intro_text = random.choice(intros)
        intro_text += "\n\n"
        
        # Add signal counts (show all, including 0 for Congressional signals)
        for signal_type, count in signal_counts.items():
            intro_text += f"• {signal_type}: {count}\n"
        
        # Escape markdown special characters
        def escape_md(text):
            chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in chars_to_escape:
                text = text.replace(char, f'\\{char}')
            return text
        
        intro_text = escape_md(intro_text)
        
        # Send via Telegram Bot API
        async def send_intro():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            success_count = 0
            
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=intro_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send intro to chat_id {chat_id}: {e}")
            
            return success_count
        
        # Run async function
        success_count = asyncio.run(send_intro())
        
        if success_count > 0:
            logger.info(f"Telegram intro sent successfully to {success_count}/{len(chat_ids)} accounts")
            return True
        else:
            logger.error("Failed to send Telegram intro to any account")
            return False
    
    except Exception as e:
        logger.error(f"Failed to send Telegram intro: {e}")
        return False


def send_telegram_alert(alert: InsiderAlert, dry_run: bool = False) -> bool:
    """Send Telegram alert via Bot API to one or more accounts."""
    # Check if alert already sent
    if is_alert_already_sent(alert.alert_id):
        logger.info(f"Skipping duplicate Telegram alert: {alert.ticker} - {alert.signal_type} (already sent)")
        return False
    
    if not USE_TELEGRAM:
        return False
    
    if dry_run:
        logger.info(f"DRY RUN - Would send Telegram: {alert.ticker} - {alert.signal_type}")
        return True
    
    try:
        import asyncio
        from telegram import Bot
        from telegram.constants import ParseMode
        
        # Support multiple chat IDs (comma-separated)
        chat_ids = [cid.strip() for cid in TELEGRAM_CHAT_ID.split(",")]
        
        # Format message
        message_text = format_telegram_message(alert)
        
        # Generate chart image
        chart_buf = generate_stock_chart(alert.ticker, days=180)
        
        # Send via Telegram Bot API (async)
        async def send_message():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            success_count = 0
            
            for chat_id in chat_ids:
                try:
                    # Send text message
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                    
                    # Send chart if available
                    if chart_buf:
                        chart_buf.seek(0)  # Reset buffer position before each send
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=chart_buf,
                            caption=f'{alert.ticker} - Chart'
                        )
                        logger.info(f"Chart sent to {chat_id}")
                    else:
                        logger.warning(f"No chart available for {alert.ticker}")
                    
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to chat_id {chat_id}: {e}")
            
            return success_count
        
        # Run async function
        success_count = asyncio.run(send_message())
        
        if success_count > 0:
            logger.info(f"Telegram sent successfully to {success_count}/{len(chat_ids)} accounts: {alert.ticker}")
            return True
        else:
            logger.error(f"Failed to send Telegram to any account: {alert.ticker}")
            return False
        
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")
        return False


def send_tracked_ticker_alert(ticker: str, tracking_users: List[Dict], trades: List[Dict], dry_run: bool = False) -> bool:
    """
    Send Telegram alert for tracked ticker activity (no AI insight, just trade info).
    
    Args:
        ticker: Stock ticker symbol
        tracking_users: List of users tracking this ticker
        trades: List of trade dictionaries (OpenInsider + Congressional)
        dry_run: If True, don't actually send
        
    Returns:
        True if sent successfully
    """
    if not USE_TELEGRAM:
        return False
    
    if dry_run:
        logger.info(f"DRY RUN - Would send tracked ticker alert: {ticker}")
        return True
    
    try:
        import asyncio
        from telegram import Bot
        from telegram.constants import ParseMode
        
        # Escape markdown
        def escape_md(text):
            if not isinstance(text, str):
                text = str(text)
            chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in chars_to_escape:
                text = text.replace(char, f'\\{char}')
            return text
        
        # Build message
        msg = f"📌 *TRACKED TICKER* 📌\n"
        
        # User mentions (right after title, no break line)
        mentions = []
        for user in tracking_users:
            if user['username']:
                mentions.append(f"@{user['username']}")
            else:
                user_id = user['user_id']
                first_name = user['first_name'] or 'User'
                mentions.append(f"[{first_name}](tg://user?id={user_id})")
        
        if mentions:
            msg += f"by {', '.join(mentions)}\n\n"
        
        # Company name
        company_name = trades[0].get('company_name', ticker)
        company_esc = escape_md(company_name)
        ticker_esc = escape_md(ticker)
        if company_name != ticker:
            msg += f"*{company_esc} \\(${ticker_esc}\\)*\n\n"
        else:
            msg += f"*${ticker_esc}*\n\n"
        
        # Trades section with today's date
        today_str = datetime.now().strftime('%B %d')  # "November 26"
        today_esc = escape_md(today_str)
        msg += f"📊 *Activity on {today_esc}*\n"
        
        # Sort trades by trade_date descending, then by trade_type
        sorted_trades = sorted(trades, key=lambda t: (t.get('trade_date', ''), t.get('trade_type', '')), reverse=True)
        
        # Determine which sources we have
        has_congressional = any(t.get('source') == 'Congressional' for t in sorted_trades)
        has_openinsider = any(t.get('source') == 'OpenInsider' for t in sorted_trades)
        
        # Group trades by date and type
        from collections import defaultdict
        grouped_trades = defaultdict(lambda: defaultdict(list))
        for trade in sorted_trades:
            trade_date = trade.get('trade_date', 'N/A')
            trade_type = trade.get('trade_type', 'N/A').upper()
            grouped_trades[trade_date][trade_type].append(trade)
        
        # Display grouped trades
        for trade_date in sorted(grouped_trades.keys(), reverse=True):
            # Format date as underlined "Nov 26"
            try:
                dt = pd.to_datetime(trade_date)
                date_str = dt.strftime('%b %d')
                date_underlined = f"__{escape_md(date_str)}__"
            except:
                date_underlined = f"__{escape_md(trade_date)}__"
            
            for trade_type in sorted(grouped_trades[trade_date].keys()):
                # Header: Date - Type
                msg += f"{date_underlined} \\- {escape_md(trade_type)}\n"
                
                trades_in_group = grouped_trades[trade_date][trade_type]
                total_trades = len(trades_in_group)
                
                # List trades under this date/type (max 5)
                for idx, trade in enumerate(trades_in_group[:5]):
                    source = trade.get('source', 'Unknown')
                    insider_name = trade.get('insider_name', 'Unknown')
                    
                    # Add party affiliation for Congressional trades
                    if source == 'Congressional':
                        party = trade.get('party', '')
                        if party:
                            if party == 'D':
                                party_label = '(D)'
                            elif party == 'R':
                                party_label = '(R)'
                            else:
                                party_label = '(O)'
                            insider_display = f"{insider_name} {party_label}"
                        else:
                            insider_display = insider_name
                    else:
                        insider_display = insider_name
                    
                    insider = escape_md(insider_display)
                    
                    # Build trade details
                    if source == 'OpenInsider':
                        value = trade.get('value', 0)
                        price = trade.get('price', 0)
                        owned = trade.get('owned', 0)
                        qty = trade.get('qty', 0)
                        
                        # Format value
                        if value >= 1_000_000:
                            value_str = f"${value/1_000_000:.1f}M"  # Show as M for millions
                        elif value >= 1_000:
                            value_str = f"${value/1_000:.0f}K"
                        else:
                            value_str = f"${value:.0f}"
                        value_esc = escape_md(value_str)
                        
                        # Format price
                        price_str = f"@${price:.2f}" if price > 0 else ""
                        price_esc = escape_md(price_str)
                        
                        # Calculate delta (change in ownership)
                        if owned > 0 and qty != 0:
                            delta_pct = (qty / (owned - qty)) * 100 if (owned - qty) > 0 else 0
                            delta_str = f"(+{delta_pct:.1f}%)" if trade_type == 'BUY' else f"(-{abs(delta_pct):.1f}%)"
                            delta_esc = escape_md(delta_str)
                        else:
                            delta_esc = ""
                        
                        # Name on one line, details on next line, then line break
                        msg += f"{insider}\n"
                        msg += f"{value_esc} {price_esc} {delta_esc}\n\n"
                        
                    else:  # Congressional
                        size_range = trade.get('size_range', 'N/A')
                        price = trade.get('price', 0)
                        
                        # Format price
                        price_str = f"@${price:.2f}" if price and price > 0 else ""
                        price_esc = escape_md(price_str)
                        size_esc = escape_md(size_range)
                        
                        # Name on one line, amount and price on next line, then line break
                        msg += f"{insider}\n"
                        if price_esc:
                            msg += f"{size_esc} {price_esc}\n\n"
                        else:
                            msg += f"{size_esc}\n\n"
                
                # Show +X more if there are more than 5 trades
                if total_trades > 5:
                    remaining = total_trades - 5
                    msg += f"\\.\\.\\.\\ \\+{remaining} more trades\n"
                else:
                    # Remove one trailing line break from the last trade
                    if msg.endswith("\n\n"):
                        msg = msg[:-1]  # Remove one \n
        
        # Footer with links (based on sources) - add line break before links
        msg += "\n"
        links = []
        if has_congressional:
            # Build Capitol Trades link with all politician IDs (no ticker param - doesn't work)
            congressional_trades = [t for t in sorted_trades if t.get('source') == 'Congressional']
            politician_ids = list(set(t.get('politician_id') for t in congressional_trades if t.get('politician_id')))
            if politician_ids:
                pol_params = '&'.join([f"politician={pid}" for pid in politician_ids])
                capitol_link = f"https://www.capitoltrades.com/trades?{pol_params}"
            else:
                capitol_link = f"https://www.capitoltrades.com/trades"
            capitol_link_esc = escape_md(capitol_link)
            links.append(f"[View on Capitol Trades]({capitol_link_esc})")
        if has_openinsider:
            # Build OpenInsider link with full screener format and date range
            oi_trades = [t for t in sorted_trades if t.get('source') == 'OpenInsider']
            if oi_trades:
                # Get date range from trades
                trade_dates = [t.get('trade_date') for t in oi_trades if t.get('trade_date')]
                if trade_dates:
                    min_date = min(trade_dates)
                    max_date = max(trade_dates)
                    # Format dates with URL encoding
                    try:
                        min_dt = pd.to_datetime(min_date)
                        max_dt = pd.to_datetime(max_date)
                        date_range = f"{min_dt.strftime('%m')}%2F{min_dt.strftime('%d')}%2F{min_dt.strftime('%Y')}+-+{max_dt.strftime('%m')}%2F{max_dt.strftime('%d')}%2F{max_dt.strftime('%Y')}"
                        oi_link = f"http://openinsider.com/screener?s={ticker}&o=&pl=&ph=&ll=&lh=&fd=-1&fdr={date_range}&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
                    except:
                        oi_link = f"http://openinsider.com/screener?s={ticker}"
                else:
                    oi_link = f"http://openinsider.com/screener?s={ticker}"
            else:
                oi_link = f"http://openinsider.com/screener?s={ticker}"
            oi_link_esc = escape_md(oi_link)
            links.append(f"[View on OpenInsider]({oi_link_esc})")
        
        if links:
            separator = " \\| "
            msg += f"🔗 {separator.join(links)}"
        
        # Generate chart
        chart_buf = generate_stock_chart(ticker, days=180)
        
        # Send via Telegram
        chat_ids = [cid.strip() for cid in TELEGRAM_CHAT_ID.split(",")]
        
        async def send_message():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            success_count = 0
            
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                    
                    if chart_buf:
                        chart_buf.seek(0)
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=chart_buf,
                            caption=f'{ticker} - Chart'
                        )
                        logger.info(f"Chart sent to {chat_id}")
                    
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send tracked ticker alert to {chat_id}: {e}")
            
            return success_count
        
        success_count = asyncio.run(send_message())
        
        if success_count > 0:
            logger.info(f"Tracked ticker alert sent successfully: {ticker} ({len(trades)} trades, {len(tracking_users)} users)")
            return True
        else:
            logger.error(f"Failed to send tracked ticker alert: {ticker}")
            return False
        
    except Exception as e:
        logger.error(f"Error sending tracked ticker alert for {ticker}: {e}")
        return False


def send_signal_summary_email(alerts: List[InsiderAlert]) -> bool:
    """
    Send summary email showing ALL detected signals with their composite scores
    before filtering to top N. This allows user to verify the ranking algorithm.
    
    Args:
        alerts: List of ALL InsiderAlert objects before filtering
        
    Returns:
        True if email sent successfully
    """
    if not alerts:
        logger.info("No signals to summarize")
        return False
    
    logger.info(f"Sending pre-filter signal summary email for {len(alerts)} signals...")
    
    # Calculate scores for all alerts
    scored_alerts = []
    for alert in alerts:
        try:
            context = get_company_context(alert.ticker)
        except:
            context = None
        
        score = calculate_composite_signal_score(alert, context)
        scored_alerts.append((score, alert))
    
    # Sort by score descending
    scored_alerts.sort(key=lambda x: x[0], reverse=True)
    
    # Build email body
    subject = f"[Insider Whisper] Signal Summary - {len(alerts)} Detected"
    
    # HTML body
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f5f5f5;
                padding: 20px;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 30px;
                max-width: 900px;
                margin: 0 auto;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-top: 0;
            }}
            .summary {{
                background: #e8f4f8;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .signal {{
                background: #f9f9f9;
                border-left: 4px solid #3498db;
                padding: 15px;
                margin: 15px 0;
                border-radius: 3px;
            }}
            .top3 {{
                border-left: 4px solid #27ae60;
                background: #e8f8f0;
            }}
            .signal-header {{
                font-weight: bold;
                font-size: 1.1em;
                color: #2c3e50;
                margin-bottom: 8px;
            }}
            .score {{
                font-weight: bold;
                color: #e74c3c;
                font-size: 1.2em;
            }}
            .score.high {{
                color: #27ae60;
            }}
            .details {{
                color: #555;
                font-size: 0.95em;
                margin-top: 5px;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 2px solid #eee;
                color: #777;
                font-size: 0.9em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Signal Detection Summary</h1>
            
            <div class="summary">
                <strong>Total Signals Detected:</strong> {len(alerts)}<br>
                <strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                <strong>Top Signals Selected:</strong> Top 3 (highlighted in green)
            </div>
            
            <h2>All Signals Ranked by Composite Score:</h2>
    """
    
    # Add each signal
    for i, (score, alert) in enumerate(scored_alerts, 1):
        is_top3 = i <= 3
        signal_class = "signal top3" if is_top3 else "signal"
        score_class = "score high" if score >= 15 else "score"
        
        # Get total value
        total_value = 0
        if not alert.trades.empty and 'Value ($)' in alert.trades.columns:
            total_value = alert.trades['Value ($)'].sum()
        elif alert.details and 'total_value' in alert.details:
            total_value = alert.details['total_value']
        
        value_str = f"${total_value:,.0f}" if total_value > 0 else "N/A"
        
        # Get insider count
        insider_count = len(alert.trades) if not alert.trades.empty else 1
        if alert.details and 'insider_count' in alert.details:
            insider_count = alert.details['insider_count']
        
        rank_emoji = "🏆" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        
        html_body += f"""
            <div class="{signal_class}">
                <div class="signal-header">
                    {rank_emoji} #{i} - ${alert.ticker} - {alert.signal_type}
                </div>
                <div class="{score_class}">Composite Score: {score} points</div>
                <div class="details">
                    Value: {value_str} | Participants: {insider_count} | 
                    {'✅ SELECTED FOR REPORTING' if is_top3 else '❌ Filtered Out'}
                </div>
            </div>
        """
    
    html_body += """
            <div class="footer">
                <strong>Next Step:</strong> The top 3 signals will be sent in separate detailed alert emails.<br>
                <strong>Note:</strong> This summary helps you verify the ranking algorithm is selecting the strongest signals.
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text version
    text_body = f"""
SIGNAL DETECTION SUMMARY
{'='*80}

Total Signals Detected: {len(alerts)}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Top Signals Selected: Top 3

ALL SIGNALS RANKED BY COMPOSITE SCORE:
{'='*80}

"""
    
    for i, (score, alert) in enumerate(scored_alerts, 1):
        is_top3 = i <= 3
        status = "✅ SELECTED" if is_top3 else "❌ FILTERED"
        
        total_value = 0
        if not alert.trades.empty and 'Value ($)' in alert.trades.columns:
            total_value = alert.trades['Value ($)'].sum()
        elif alert.details and 'total_value' in alert.details:
            total_value = alert.details['total_value']
        
        value_str = f"${total_value:,.0f}" if total_value > 0 else "N/A"
        
        text_body += f"""
#{i} - ${alert.ticker} - {alert.signal_type}
    Composite Score: {score} points
    Value: {value_str}
    Status: {status}

"""
    
    text_body += """
{'='*80}
Next Step: The top 3 signals will be sent in separate detailed alert emails.
"""
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_TO
        
        # Attach both versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        
        logger.info(f"Signal summary email sent successfully: {len(alerts)} signals")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send signal summary email: {e}")
        return False


def send_email_alert(alert: InsiderAlert, dry_run: bool = False, subject_prefix: str = "") -> bool:
    """
    Send email alert for detected signal.
    
    Args:
        alert: InsiderAlert object
        dry_run: If True, log email but don't send
        subject_prefix: Optional prefix for subject line (e.g., "Signal #1: ")
        
    Returns:
        True if email sent successfully
    """
    # Check if alert already sent
    if is_alert_already_sent(alert.alert_id):
        logger.info(f"Skipping duplicate alert: {alert.ticker} - {alert.signal_type} (already sent)")
        return False
    
    subject = f"[Insider Whisper] {alert.signal_type}"
    
    # Format email body
    text_body = format_email_text(alert)
    html_body = format_email_html(alert)
    
    if dry_run:
        logger.info(f"DRY RUN - Would send email: {subject}")
        logger.debug(f"Email body:\n{text_body}")
        return True
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_TO
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully: {subject}")
        
        # Mark as sent to prevent duplicates
        mark_alert_as_sent(alert.alert_id, alert.ticker, alert.signal_type)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def process_alerts(alerts: List[InsiderAlert], dry_run: bool = False, tracked_ticker_activity: Optional[List] = None, test_mode: bool = False):
    """
    Process list of alerts: check if new, send emails, update state.
    
    Args:
        alerts: List of InsiderAlert objects
        dry_run: If True, don't send emails or update state
        tracked_ticker_activity: List of tracked ticker activity tuples
        test_mode: If True, don't mark alerts as sent (for testing)
    """
    if not alerts:
        logger.info("No alerts to process")
        return
    
    # Filter to only new alerts (check database for deduplication)
    new_alerts = []
    duplicate_alerts = []
    for alert in alerts:
        if not is_alert_already_sent(alert.alert_id):
            new_alerts.append(alert)
        else:
            duplicate_alerts.append(alert)
    
    logger.info(f"Found {len(new_alerts)} new alerts (out of {len(alerts)} total)")
    
    # If all top signals already sent, log which ones were blocked
    if len(new_alerts) == 0 and len(duplicate_alerts) > 0:
        logger.warning("⚠️ All top-scoring signals were already sent within the last 30 days:")
        for alert in duplicate_alerts:
            logger.warning(f"  - {alert.ticker} ({alert.signal_type}) - Blocked by deduplication")
        logger.info("No new signals to report. System working correctly - preventing duplicate alerts.")
    
    # Separate tracked ticker alerts from regular signals
    tracked_alerts = []
    regular_alerts = []
    
    for alert in new_alerts:
        # Check if this ticker is being tracked by any user
        tracking_users = get_users_tracking_ticker(alert.ticker)
        if tracking_users:
            tracked_alerts.append((alert, tracking_users))
        else:
            regular_alerts.append(alert)
    
    # Cap regular signals using TOP_SIGNALS_PER_DAY configuration (currently set to 1)
    if TOP_SIGNALS_PER_DAY > 0 and len(regular_alerts) > TOP_SIGNALS_PER_DAY:
        logger.info(f"Capping regular signals from {len(regular_alerts)} to {TOP_SIGNALS_PER_DAY}")
        
        # Smart prioritization based on signal strength
        # Score each alert based on multiple factors
        def calculate_priority_score(alert: InsiderAlert) -> float:
            """
            Calculate priority score for signal ranking.
            Higher score = higher priority (sent first)
            
            Scoring factors:
            1. Signal type base score (stronger signals get higher base)
            2. Dollar value multiplier (larger purchases = higher priority)
            3. Number of participants (more insiders/politicians = higher priority)
            4. Bipartisan bonus for Congressional (both parties = higher priority)
            """
            score = 0.0
            
            # Base scores by signal type (0-100)
            base_scores = {
                'Congressional Cluster Buy': 95,      # Multiple politicians = policy signal
                'Large Congressional Buy': 90,         # Single politician >$100K = high conviction
                'C-Suite Buy': 85,                     # CEO/CFO/COO = strongest corporate signal
                'Cluster Buying': 80,                  # 3+ insiders = coordinated buying
                'Large Single Buy': 70,                # Single large purchase >$500K
                'Corporation Purchase': 65,            # Strategic/institutional buying
                'Strategic Investor Buy': 60           # Corporation buying
            }
            score += base_scores.get(alert.signal_type, 50)
            
            # Participant multiplier (more participants = stronger signal)
            if 'num_politicians' in alert.details:
                # Congressional: 3 politicians = 1.2x, 4 = 1.4x, 5 = 1.6x, 6+ = 1.8x
                num_pols = alert.details['num_politicians']
                participant_bonus = min(1.0 + (num_pols - 2) * 0.2, 1.8)
                score *= participant_bonus
                
                # Bipartisan bonus (both parties involved = extra credibility)
                if alert.details.get('bipartisan'):
                    score *= 1.15  # 15% bonus for bipartisan agreement
            
            elif 'num_insiders' in alert.details:
                # Corporate insiders: 3 = 1.1x, 4 = 1.2x, 5 = 1.3x, 6+ = 1.4x
                num_insiders = alert.details['num_insiders']
                participant_bonus = min(1.0 + (num_insiders - 2) * 0.1, 1.4)
                score *= participant_bonus
            
            # Dollar value multiplier (larger = more conviction)
            # Uses logarithmic scaling: higher values have diminishing returns
            # This reflects that $2M isn't twice as significant as $1M
            import math
            
            if 'total_value' in alert.details:
                # Corporate cluster: log scale from 1.0x ($300K) to ~2.0x ($5M+)
                total_value = alert.details['total_value']
                if total_value >= 300_000:
                    # log10(300K) ≈ 5.48, log10(5M) ≈ 6.70
                    # Formula: 1.0 + 0.82 * (log10(value) - 5.48)
                    # Result: $300K=1.0x, $1M=1.4x, $2M=1.7x, $5M=2.0x
                    log_value = math.log10(total_value)
                    multiplier = 1.0 + 0.82 * (log_value - 5.48)
                    score *= min(max(multiplier, 1.0), 2.0)  # Cap between 1.0x-2.0x
            
            elif 'value' in alert.details:
                # Single purchase: log scale from 1.0x ($100K) to ~1.8x ($2M+)
                value = alert.details['value']
                if value >= 100_000:
                    # log10(100K) ≈ 5.0, log10(2M) ≈ 6.30
                    # Formula: 1.0 + 0.62 * (log10(value) - 5.0)
                    # Result: $100K=1.0x, $500K=1.43x, $1M=1.62x, $2M=1.8x
                    log_value = math.log10(value)
                    multiplier = 1.0 + 0.62 * (log_value - 5.0)
                    score *= min(max(multiplier, 1.0), 1.8)  # Cap between 1.0x-1.8x
            
            # Congressional trades use size ranges (parse midpoint)
            elif alert.signal_type in ['Congressional Cluster Buy', 'Large Congressional Buy']:
                # Parse size range from trades (e.g., "100K-250K" -> 175K)
                # Extract from alert.details if available, or from first trade
                if not alert.trades.empty and 'Size Range' in alert.trades.columns:
                    # Get all size ranges and estimate total
                    import re
                    total_estimated = 0
                    for _, row in alert.trades.iterrows():
                        size_str = row.get('Size Range', '')
                        if size_str and '-' in size_str:
                            # Parse "100K-250K" format
                            parts = size_str.replace('$', '').replace(',', '').split('-')
                            if len(parts) == 2:
                                try:
                                    # Extract numbers and convert K/M to actual values
                                    low = parts[0].strip()
                                    high = parts[1].strip()
                                    
                                    low_val = float(re.sub(r'[KM]', '', low))
                                    if 'K' in low:
                                        low_val *= 1000
                                    elif 'M' in low:
                                        low_val *= 1_000_000
                                    
                                    high_val = float(re.sub(r'[KM]', '', high))
                                    if 'K' in high:
                                        high_val *= 1000
                                    elif 'M' in high:
                                        high_val *= 1_000_000
                                    
                                    midpoint = (low_val + high_val) / 2
                                    total_estimated += midpoint
                                except:
                                    pass
                    
                    if total_estimated >= 50_000:
                        # Congressional: log scale from 1.0x ($50K) to ~1.6x ($500K+)
                        # log10(50K) ≈ 4.70, log10(500K) ≈ 5.70
                        # Formula: 1.0 + 0.6 * (log10(value) - 4.70)
                        log_value = math.log10(total_estimated)
                        multiplier = 1.0 + 0.6 * (log_value - 4.70)
                        score *= min(max(multiplier, 1.0), 1.6)  # Cap between 1.0x-1.6x
            
            # Recency bonus: More recent trades get higher priority
            # Trades from today = 1.3x, 1 day ago = 1.25x, 7 days ago = 1.0x, 14+ days = 0.8x
            try:
                from datetime import datetime, timedelta
                trade_date = None
                
                # Try to get trade date from DataFrame
                if not alert.trades.empty:
                    if 'Trade Date' in alert.trades.columns:
                        trade_date = alert.trades['Trade Date'].max()
                    elif 'Published Date' in alert.trades.columns:
                        trade_date = alert.trades['Published Date'].max()
                
                if trade_date is not None and pd.notna(trade_date):
                    # Convert to datetime if needed
                    if isinstance(trade_date, str):
                        trade_date = pd.to_datetime(trade_date)
                    
                    days_ago = (datetime.now() - trade_date.to_pydatetime().replace(tzinfo=None)).days
                    
                    # Recency multiplier: exponential decay from 1.3x (today) to 0.8x (14+ days)
                    # Formula: 1.3 - 0.036 * days_ago, capped at 0.8 minimum
                    recency_multiplier = max(1.3 - 0.036 * days_ago, 0.8)
                    score *= recency_multiplier
            except Exception:
                pass  # If we can't determine recency, don't modify score
            
            # Position Impact Multiplier: Filters out "cosmetic" purchases
            # +20% if position increase >20%
            # +10% if position increase >10%
            # 0% if position increase <5%
            try:
                if not alert.trades.empty and 'Delta Own' in alert.trades.columns:
                    # Extract Delta Own percentage values
                    delta_vals = alert.trades['Delta Own'].astype(str).str.replace('%', '').str.replace('+', '')
                    delta_vals = pd.to_numeric(delta_vals, errors='coerce')
                    
                    # Use max delta (most significant position increase)
                    max_delta = delta_vals.max()
                    
                    if pd.notna(max_delta):
                        if max_delta >= 20:
                            score *= 1.20  # +20% for significant position increase
                        elif max_delta >= 10:
                            score *= 1.10  # +10% for moderate position increase
                        elif max_delta < 5:
                            score *= 0.9   # -10% penalty for cosmetic purchases
            except Exception:
                pass  # If we can't determine position impact, don't modify score
            
            return score
        
        # Sort by priority score (highest first)
        regular_alerts.sort(key=lambda a: calculate_priority_score(a), reverse=True)
        regular_alerts = regular_alerts[:TOP_SIGNALS_PER_DAY]
    
    # Count ALL signals by type for intro message (not just top 3)
    signal_counts = {}
    all_detected_alerts = [alert for alert, _ in tracked_alerts] + new_alerts
    for alert in all_detected_alerts:
        signal_type = alert.signal_type
        signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
    
    # Always include Congressional signals in the count (even if 0) when Capitol Trades is enabled
    if USE_CAPITOL_TRADES:
        if 'Elite Congressional Cluster' not in signal_counts:
            signal_counts['Elite Congressional Cluster'] = 0
        if 'Elite Congressional Buy' not in signal_counts:
            signal_counts['Elite Congressional Buy'] = 0
    
    # Always include all signal types in the summary (even if 0)
    # Note: Bearish signals removed - we focus on BUY opportunities only
    all_signal_types = [
        'Trinity Signal',
        'Elite Congressional Cluster',
        'Elite Congressional Buy',
        'Cluster Buying',
        'C-Suite Buy',
        'Corporation Purchase',
        'Large Single Buy'
    ]
    for sig_type in all_signal_types:
        if sig_type not in signal_counts:
            signal_counts[sig_type] = 0
    
    # Add tracked ticker count if provided
    tracked_ticker_count = len(tracked_ticker_activity) if tracked_ticker_activity else 0
    if tracked_ticker_count > 0:
        signal_counts['Tracked Tickers'] = tracked_ticker_count
    
    # Send intro message to Telegram if there are signals to send
    if USE_TELEGRAM and (tracked_ticker_count > 0 or tracked_alerts or regular_alerts) and not dry_run:
        send_telegram_intro(signal_counts, dry_run=dry_run)
    
    # Send regular signals to Telegram (capped at 3)
    for alert in regular_alerts:
        if USE_TELEGRAM:
            telegram_sent = send_telegram_alert(alert, dry_run=dry_run)
            if telegram_sent:
                logger.info(f"Alert sent via Telegram: {alert.ticker}")
    
    # Send tracked ticker alerts to Telegram (all of them, no cap)
    if tracked_ticker_activity:
        for ticker, tracking_users, trades in tracked_ticker_activity:
            if not dry_run:
                send_tracked_ticker_alert(ticker, tracking_users, trades, dry_run=dry_run)
    
    # Send tracked ticker alerts via email (all of them)
    for alert, users in tracked_alerts:
        logger.info(f"[TRACKED TICKER] {alert.ticker} - tracked by {len(users)} user(s)")
        send_email_alert(alert, dry_run=dry_run)
        # Mark as sent in database
        if not dry_run:
            mark_alert_as_sent(alert.alert_id, alert.ticker, alert.signal_type, test_mode=test_mode)
    
    # Send regular signals via email (capped at 3)
    for alert in regular_alerts:
        send_email_alert(alert, dry_run=dry_run)
        # Mark as sent in database
        if not dry_run:
            mark_alert_as_sent(alert.alert_id, alert.ticker, alert.signal_type, test_mode=test_mode)


def run_once(since_date: Optional[str] = None, dry_run: bool = False, verbose: bool = False, test_mode: bool = False):
    """
    Run a single check for insider trading alerts.
    
    Args:
        since_date: Optional date string (YYYY-MM-DD) to filter trades
        dry_run: If True, don't send emails
        verbose: If True, enable debug logging
        test_mode: If True, don't mark alerts as sent (for testing without wasting signals)
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 60)
    logger.info("Starting insider trading alert check")
    logger.info("=" * 60)
    
    # Initialize database and cleanup old alerts
    init_database()
    cleanup_expired_alerts()
    
    try:
        # Fetch and store OpenInsider data using new pagination approach
        df = fetch_openinsider_last_week()
        
        # Fetch and store Congressional trades (same time as OpenInsider)
        if USE_CAPITOL_TRADES:
            try:
                logger.info("Refreshing Congressional trades data...")
                logger.info("USE_CAPITOL_TRADES is enabled, starting scrape...")
                scrape_all_congressional_trades_to_db()
                logger.info("Congressional trades refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh Congressional trades: {e}", exc_info=True)
        
        # Store in database for deduplication
        new_trades = store_openinsider_trades(df)
        logger.info(f"Stored OpenInsider data: {new_trades} new trades")
        
        # Load ALL trades from database for signal detection (not just new ones!)
        df = load_openinsider_trades_from_db(lookback_days=LOOKBACK_DAYS)
        
        # Check for tracked ticker activity (detect but don't send yet)
        tracked_ticker_activity = detect_tracked_ticker_activity()
        tracked_ticker_count = len(tracked_ticker_activity) if tracked_ticker_activity else 0
        
        # Apply date filter if provided
        if since_date:
            since_dt = datetime.strptime(since_date, "%Y-%m-%d")
            df = df[df["Trade Date"] >= since_dt]
            logger.info(f"Filtered to trades since {since_date}: {len(df)} rows")
        
        # Detect signals from ALL trades in database
        alerts = detect_signals(df)
        
        # Log signal counts by type
        signal_counts = {}
        for alert in alerts:
            signal_type = alert.signal_type
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
        
        logger.info("=" * 60)
        logger.info("SIGNAL DETECTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total signals detected: {len(alerts)}")
        logger.info("")
        logger.info("Breakdown by signal type:")
        for signal_type in sorted(signal_counts.keys()):
            count = signal_counts[signal_type]
            logger.info(f"  {signal_type}: {count}")
        logger.info("=" * 60)
        
        # Apply Top-N signal filter (select only highest-scoring signals)
        if TOP_SIGNALS_PER_DAY > 0 and len(alerts) > TOP_SIGNALS_PER_DAY:
            logger.info(f"\nApplying Top-{TOP_SIGNALS_PER_DAY} filter to select strongest signals...")
            
            # Send pre-filter summary email showing ALL signals and their scores
            if not dry_run:
                send_signal_summary_email(alerts)
            
            # Apply the filter
            filtered_alerts = select_top_signals(alerts, top_n=TOP_SIGNALS_PER_DAY, enrich_context=True)
            logger.info(f"Filtered to top {len(filtered_alerts)} signals for reporting\n")
            alerts = filtered_alerts
        
        # Process alerts (pass tracked ticker activity for sending with signals)
        process_alerts(alerts, dry_run=dry_run, tracked_ticker_activity=tracked_ticker_activity, test_mode=test_mode)
        
        logger.info("Check completed successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during check: {e}", exc_info=True)
        raise


def run_loop(interval_minutes: int = 30, dry_run: bool = False, verbose: bool = False):
    """
    Run continuous monitoring with scheduled checks.
    
    Args:
        interval_minutes: Minutes between checks
        dry_run: If True, don't send emails
        verbose: If True, enable debug logging
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"Starting continuous monitoring (every {interval_minutes} minutes)")
    logger.info("Press Ctrl+C to stop")
    
    # Schedule job
    schedule.every(interval_minutes).minutes.do(
        run_once,
        since_date=None,
        dry_run=dry_run,
        verbose=verbose
    )
    
    # Run immediately on start
    run_once(since_date=None, dry_run=dry_run, verbose=verbose)
    
    # Keep running
    try:
        while True:
            schedule.run_pending()
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Insider Trading Alert System - Monitor OpenInsider for high-conviction signals"
    )
    
    # Run mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit"
    )
    mode_group.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously with scheduled checks"
    )
    
    # Options
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=30,
        help="Minutes between checks in loop mode (default: 30)"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only process trades since this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't send emails, only log alerts"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: don't mark alerts as sent (prevents wasting signals)"
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not args.dry_run:
        has_email = all([SMTP_USER, SMTP_PASS, ALERT_TO])
        has_telegram = USE_TELEGRAM and all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID])
        
        if not has_email and not has_telegram:
            logger.error("Alert configuration missing. Set either email (SMTP_*) or Telegram (TELEGRAM_*) credentials in .env")
            sys.exit(1)
        
        if USE_TELEGRAM and not has_telegram:
            logger.warning("USE_TELEGRAM=true but Telegram credentials missing. Falling back to email only.")
    
    # Run appropriate mode
    try:
        if args.once:
            run_once(
                since_date=args.since,
                dry_run=args.dry_run,
                verbose=args.verbose,
                test_mode=args.test
            )
        else:  # loop
            run_loop(
                interval_minutes=args.interval_minutes,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
