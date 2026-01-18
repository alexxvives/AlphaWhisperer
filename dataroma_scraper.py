#!/usr/bin/env python3
"""
Dataroma Superinvestor Holdings Scraper

Scrapes quarterly 13F holdings from elite superinvestors tracked on Dataroma.com:
- Warren Buffett (Berkshire Hathaway)
- Bill Ackman (Pershing Square)
- Seth Klarman (Baupost Group)
- David Tepper (Appaloosa)
- And 50+ other proven investors

Updates dataroma_holdings table with current positions.
"""

import logging
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger(__name__)

# Database
DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "alphaWhisperer.db"

# Dataroma URLs
DATAROMA_MANAGERS_URL = "https://www.dataroma.com/m/managers.php"
DATAROMA_HOLDINGS_URL = "https://www.dataroma.com/m/holdings.php?m={manager_code}"
DATAROMA_INSIDER_ACTIVITY_URL = "https://www.dataroma.com/m/ins/ins.php"

# Elite superinvestors to track (can expand this list)
ELITE_SUPERINVESTORS = {
    "BRK": "Warren Buffett - Berkshire Hathaway",
    "BAM": "Bill Ackman - Pershing Square",
    "BG": "Seth Klarman - Baupost Group",
    "APPALOOSA": "David Tepper - Appaloosa",
    "SOLO": "Stanley Druckenmiller - Duquesne Family Office",
    "THIRD": "Dan Loeb - Third Point",
    "LOEWS": "Allan Mecham - Arlington Value",
    "OAKMARK": "Bill Nygren - Oakmark Funds",
    "PRIMECAP": "PRIMECAP Management",
    "TWEEDY": "Tweedy Browne",
}


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_dataroma_table():
    """
    Create dataroma_holdings table if it doesn't exist.
    
    Schema:
    - manager_code: Dataroma manager identifier (e.g., 'BRK', 'BAM')
    - manager_name: Full name (e.g., 'Warren Buffett - Berkshire Hathaway')
    - ticker: Stock symbol
    - company_name: Company name
    - portfolio_pct: Percentage of portfolio (e.g., 25.5 for 25.5%)
    - shares_held: Number of shares
    - value_usd: Value in USD
    - quarter: Reporting quarter (e.g., 'Q4 2025')
    - last_updated: Timestamp of last scrape
    """
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dataroma_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manager_code TEXT NOT NULL,
                manager_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                portfolio_pct REAL,
                shares_held INTEGER,
                value_usd INTEGER,
                quarter TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(manager_code, ticker, quarter)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dataroma_ticker 
            ON dataroma_holdings(ticker)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dataroma_manager 
            ON dataroma_holdings(manager_code)
        """)
        
        # Create new table for daily insider transactions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dataroma_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manager_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                activity_type TEXT NOT NULL,  -- 'BUY', 'SELL', 'ADD', 'REDUCE'
                transaction_date TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(manager_name, ticker, activity_type, transaction_date)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dataroma_trans_ticker
            ON dataroma_transactions(ticker)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dataroma_trans_date
            ON dataroma_transactions(transaction_date)
        """)
        
        logger.info("Dataroma holdings and transactions tables initialized")


def scrape_manager_holdings(manager_code: str, manager_name: str) -> List[Dict]:
    """
    Scrape holdings for a specific superinvestor from Dataroma.
    
    Args:
        manager_code: Dataroma manager code (e.g., 'BRK')
        manager_name: Full manager name
        
    Returns:
        List of holding dictionaries
    """
    holdings = []
    url = DATAROMA_HOLDINGS_URL.format(manager_code=manager_code)
    
    try:
        logger.info(f"Scraping holdings for {manager_name} ({manager_code})...")
        
        # Add headers to avoid 406 blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the holdings table - try multiple IDs (different managers use different table IDs)
        table = None
        table_ids = ['grid', 'holdings', 'portfolio', 'holding_table']
        
        for table_id in table_ids:
            table = soup.find('table', {'id': table_id})
            if table:
                logger.info(f"Found table with id='{table_id}' for {manager_code}")
                break
        
        # If no table found by ID, try finding any table with class containing 'stock' or 'holding'
        if not table:
            table = soup.find('table', {'class': lambda c: c and ('stock' in c.lower() or 'holding' in c.lower() or 'portfolio' in c.lower())})
            if table:
                logger.info(f"Found table by class search for {manager_code}")
        
        # Last resort: find first table with multiple rows (likely the holdings table)
        if not table:
            tables = soup.find_all('table')
            for t in tables:
                rows = t.find_all('tr')
                if len(rows) > 5:  # Holdings tables typically have 10+ rows
                    table = t
                    logger.info(f"Found table by row count heuristic for {manager_code}")
                    break
        
        if not table:
            logger.warning(f"No holdings table found for {manager_code}")
            return holdings
        
        # Try to find quarter info
        quarter = "Unknown"
        quarter_element = soup.find(text=lambda t: t and 'Quarter' in str(t))
        if quarter_element:
            # Extract quarter (e.g., "Q4 2025")
            quarter_text = str(quarter_element)
            if 'Q' in quarter_text:
                import re
                match = re.search(r'Q[1-4]\s+\d{4}', quarter_text)
                if match:
                    quarter = match.group(0)
        
        # Parse holdings table using pandas
        df = pd.read_html(str(table))[0]
        
        # Typical Dataroma columns: Stock, Portfolio %, Shares, Activity, Value (in $1000s)
        for _, row in df.iterrows():
            try:
                # Extract ticker and company name
                stock = str(row.get('Stock', ''))
                if not stock or stock == 'nan':
                    continue
                
                # Format: "AAPL - Apple Inc" or just "AAPL"
                if ' - ' in stock:
                    ticker, company_name = stock.split(' - ', 1)
                else:
                    ticker = stock
                    company_name = None
                
                ticker = ticker.strip()
                
                # Get portfolio percentage
                portfolio_pct = None
                pct_col = row.get('Portfolio %', row.get('Portfolio', None))
                if pct_col is not None:
                    try:
                        # Remove % sign and convert
                        pct_str = str(pct_col).replace('%', '').strip()
                        portfolio_pct = float(pct_str) if pct_str != 'nan' else None
                    except:
                        pass
                
                # Get shares held
                shares_held = None
                shares_col = row.get('Shares', None)
                if shares_col is not None:
                    try:
                        # Remove commas and convert
                        shares_str = str(shares_col).replace(',', '').strip()
                        shares_held = int(float(shares_str)) if shares_str != 'nan' else None
                    except:
                        pass
                
                # Get value (in $1000s)
                value_usd = None
                value_col = row.get('Value *', row.get('Value', None))
                if value_col is not None:
                    try:
                        # Value is in thousands, e.g., "1234" = $1,234,000
                        value_str = str(value_col).replace(',', '').strip()
                        value_usd = int(float(value_str) * 1000) if value_str != 'nan' else None
                    except:
                        pass
                
                holding = {
                    'manager_code': manager_code,
                    'manager_name': manager_name,
                    'ticker': ticker,
                    'company_name': company_name,
                    'portfolio_pct': portfolio_pct,
                    'shares_held': shares_held,
                    'value_usd': value_usd,
                    'quarter': quarter
                }
                holdings.append(holding)
                
            except Exception as e:
                logger.warning(f"Error parsing row for {manager_code}: {e}")
                continue
        
        logger.info(f"Found {len(holdings)} holdings for {manager_name}")
        
    except Exception as e:
        logger.error(f"Error scraping {manager_name}: {e}", exc_info=True)
    
    return holdings


def store_holdings(holdings: List[Dict]):
    """Store holdings in database."""
    if not holdings:
        return
    
    with get_db() as conn:
        for holding in holdings:
            conn.execute("""
                INSERT OR REPLACE INTO dataroma_holdings
                (manager_code, manager_name, ticker, company_name, 
                 portfolio_pct, shares_held, value_usd, quarter, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                holding['manager_code'],
                holding['manager_name'],
                holding['ticker'],
                holding['company_name'],
                holding['portfolio_pct'],
                holding['shares_held'],
                holding['value_usd'],
                holding['quarter']
            ))
    
    logger.info(f"Stored {len(holdings)} holdings in database")


def scrape_all_superinvestors():
    """Scrape holdings for all elite superinvestors."""
    init_dataroma_table()
    
    total_holdings = 0
    for manager_code, manager_name in ELITE_SUPERINVESTORS.items():
        holdings = scrape_manager_holdings(manager_code, manager_name)
        if holdings:
            store_holdings(holdings)
            total_holdings += len(holdings)
        
        # Be respectful - wait 2 seconds between requests
        time.sleep(2)
    
    logger.info(f"Scraping complete: {total_holdings} total holdings from {len(ELITE_SUPERINVESTORS)} superinvestors")
    return total_holdings


def scrape_dataroma_insider_activity(lookback_days: int = 30) -> List[Dict]:
    """
    DEPRECATED: The /m/ins/ins.php page shows corporate insider Form 4 filings, 
    not superinvestor fund manager activity.
    
    For fund manager activity, use detect_investment_fund_buys() which compares
    quarterly 13F holdings to detect BUY/ADD/REDUCE/SELL activities.
    """
    logger.warning("scrape_dataroma_insider_activity is deprecated - it scrapes corporate insiders, not fund managers")
    logger.info("Use detect_investment_fund_buys() instead for fund manager activity from quarterly 13Fs")
    return []


def store_transactions(transactions: List[Dict]):
    """Store transactions in database."""
    if not transactions:
        return
    
    with get_db() as conn:
        new_count = 0
        for txn in transactions:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO dataroma_transactions
                (manager_name, ticker, company_name, activity_type, transaction_date, scraped_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                txn['manager_name'],
                txn['ticker'],
                txn['company_name'],
                txn['activity_type'],
                txn['transaction_date']
            ))
            if cursor.rowcount > 0:
                new_count += 1
    
    logger.info(f"Stored {new_count} new transactions ({len(transactions)} total scraped)")


def detect_investment_fund_buys(lookback_quarters: int = 2) -> List[Dict]:
    """
    Detect "Investment Fund Buy" signals by comparing quarters of 13F holdings.
    
    Signals generated when elite fund managers:
    1. Enter NEW position (0 shares → any amount)
    2. INCREASE position significantly (50%+ more shares)
    3. Hold LARGE position (>2% of portfolio)
    
    This uses quarterly 13F data already scraped, comparing Q(current) vs Q(previous).
    
    Args:
        lookback_quarters: How many quarters back to compare (default 2 = most recent 2 quarters)
        
    Returns:
        List of Investment Fund Buy signal dictionaries
    """
    signals = []
    
    with get_db() as conn:
        # Get all quarters available in database, sorted newest first
        cursor = conn.execute("""
            SELECT DISTINCT quarter
            FROM dataroma_holdings
            ORDER BY quarter DESC
            LIMIT ?
        """, (lookback_quarters,))
        
        quarters = [row[0] for row in cursor.fetchall()]
        
        if len(quarters) < 2:
            logger.warning(f"Need at least 2 quarters of data, found {len(quarters)}")
            return signals
        
        current_quarter = quarters[0]
        previous_quarter = quarters[1]
        
        logger.info(f"Comparing {current_quarter} vs {previous_quarter} for fund activity")
        
        # Get current quarter holdings
        cursor = conn.execute("""
            SELECT manager_code, manager_name, ticker, company_name, 
                   portfolio_pct, shares_held, value_usd
            FROM dataroma_holdings
            WHERE quarter = ?
        """, (current_quarter,))
        
        current_holdings = {(row[0], row[2]): dict(row) for row in cursor.fetchall()}
        
        # Get previous quarter holdings  
        cursor = conn.execute("""
            SELECT manager_code, manager_name, ticker, company_name,
                   portfolio_pct, shares_held, value_usd
            FROM dataroma_holdings
            WHERE quarter = ?
        """, (previous_quarter,))
        
        previous_holdings = {(row[0], row[2]): dict(row) for row in cursor.fetchall()}
        
        # Compare quarters to detect activity
        for (manager_code, ticker), current in current_holdings.items():
            previous = previous_holdings.get((manager_code, ticker))
            
            activity_type = None
            change_pct = None
            
            if not previous:
                # NEW position
                activity_type = "BUY"
                change_pct = 100.0  # New = 100% increase from 0
            elif current['shares_held'] > previous['shares_held']:
                # INCREASED position
                change_pct = ((current['shares_held'] - previous['shares_held']) / previous['shares_held']) * 100
                if change_pct >= 50:
                    activity_type = "ADD"  # Significant increase
            
            # Generate signal for BUY or ADD
            if activity_type in ['BUY', 'ADD']:
                signal = {
                    'manager_name': current['manager_name'],
                    'manager_code': current['manager_code'],
                    'ticker': ticker,
                    'company_name': current['company_name'],
                    'activity_type': activity_type,
                    'current_shares': current['shares_held'],
                    'previous_shares': previous['shares_held'] if previous else 0,
                    'change_pct': round(change_pct, 1),
                    'portfolio_pct': current['portfolio_pct'],
                    'value_usd': current['value_usd'],
                    'quarter': current_quarter
                }
                signals.append(signal)
    
    logger.info(f"Detected {len(signals)} Investment Fund Buy signals ({current_quarter} vs {previous_quarter})")
    return signals


def get_superinvestor_holdings(ticker: str) -> List[Dict]:
    """
    Get all superinvestors holding a specific ticker.
    
    Args:
        ticker: Stock symbol
        
    Returns:
        List of holdings (manager_name, portfolio_pct, shares_held, etc.)
    """
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT manager_name, manager_code, ticker, portfolio_pct, 
                   shares_held, value_usd, quarter, last_updated
            FROM dataroma_holdings
            WHERE ticker = ?
            ORDER BY portfolio_pct DESC
        """, (ticker,))
        
        return [dict(row) for row in cursor.fetchall()]


def detect_trinity_signals() -> List[Dict]:
    """
    Detect "Trinity Signals": Tickers where Corporate Insider + Elite Congressional + Superinvestor
    are all buying within the last 30 days.
    
    This is the ULTIMATE conviction signal:
    1. Company insiders buying (material non-public info)
    2. Elite politicians buying (policy/regulatory advantage)
    3. Superinvestors holding (due diligence + capital commitment)
    
    Returns:
        List of Trinity Signal dictionaries
    """
    signals = []
    
    with get_db() as conn:
        # Find tickers with recent insider buying (last 30 days)
        insider_query = """
            SELECT DISTINCT ticker
            FROM openinsider_trades
            WHERE trade_type = 'P'
            AND trade_date >= date('now', '-30 days')
        """
        
        # Find tickers with Elite Congressional buying (last 30 days)
        elite_filter = " OR ".join([f"politician_name LIKE '%{name}%'" 
                                   for name in [
                                       "Nancy Pelosi", "Josh Gottheimer", "Ro Khanna", 
                                       "Michael McCaul", "Tommy Tuberville", "Markwayne Mullin", 
                                       "Dan Crenshaw", "Brian Higgins", "Richard Blumenthal",
                                       "Debbie Wasserman Schultz", "Tom Kean Jr", "Gil Cisneros", 
                                       "Cleo Fields", "Marjorie Taylor Greene", "Lisa McClain"
                                   ]])
        
        congressional_query = f"""
            SELECT DISTINCT ticker
            FROM congressional_trades
            WHERE trade_type = 'BUY'
            AND published_date >= date('now', '-30 days')
            AND ({elite_filter})
        """
        
        # Find intersection: tickers with BOTH insider + congressional + superinvestor
        trinity_query = f"""
            SELECT DISTINCT i.ticker
            FROM ({insider_query}) AS i
            INNER JOIN ({congressional_query}) AS c ON i.ticker = c.ticker
            INNER JOIN dataroma_holdings AS d ON i.ticker = d.ticker
        """
        
        cursor = conn.execute(trinity_query)
        trinity_tickers = [row[0] for row in cursor.fetchall()]
        
        # Get details for each Trinity Signal
        for ticker in trinity_tickers:
            # Get insider details
            cursor.execute("""
                SELECT COUNT(*) as insider_count, SUM(value) as total_value
                FROM openinsider_trades
                WHERE ticker = ? AND trade_type = 'P'
                AND trade_date >= date('now', '-30 days')
            """, (ticker,))
            insider_data = cursor.fetchone()
            
            # Get Congressional details
            cursor.execute(f"""
                SELECT COUNT(*) as congressional_count, 
                       GROUP_CONCAT(DISTINCT politician_name) as politicians
                FROM congressional_trades
                WHERE ticker = ? AND trade_type = 'BUY'
                AND published_date >= date('now', '-30 days')
                AND ({elite_filter})
            """, (ticker,))
            congressional_data = cursor.fetchone()
            
            # Get superinvestor details
            cursor.execute("""
                SELECT COUNT(*) as superinvestor_count,
                       GROUP_CONCAT(manager_name) as managers
                FROM dataroma_holdings
                WHERE ticker = ?
            """, (ticker,))
            superinvestor_data = cursor.fetchone()
            
            signals.append({
                'ticker': ticker,
                'insider_count': insider_data['insider_count'],
                'insider_value': insider_data['total_value'],
                'congressional_count': congressional_data['congressional_count'],
                'politicians': congressional_data['politicians'],
                'superinvestor_count': superinvestor_data['superinvestor_count'],
                'managers': superinvestor_data['managers']
            })
    
    logger.info(f"Detected {len(signals)} Trinity Signals")
    return signals


def detect_temporal_convergence(ticker: str, lookback_days: int = 30) -> Optional[Dict]:
    """
    Analyze temporal sequence of buys across three actor types:
    1. Congressional trades (earliest signal - policy/regulatory advantage)
    2. Corporate insider trades (second - material non-public information)
    3. Superinvestor holdings (last - deep due diligence confirmation)
    
    Returns dict with timeline and convergence score if pattern detected, else None.
    
    Temporal Pattern Recognition:
    - STRONG: All three buying within 30 days in sequence (Congress → Insider → Fund)
    - MODERATE: Any two buying within 30 days
    - WEAK: All three holding but purchases not time-correlated
    
    Convergence Score (1-10):
    - +5 base for Trinity convergence
    - +3 if sequential (Congress first, then Insider, then Fund)
    - +2 if tight window (all within 14 days)
    - +1 if bipartisan Congressional buy
    - -1 if reverse sequence (Fund before Insider - less conviction)
    """
    with get_db() as conn:
        # Get all relevant activity for this ticker
        
        # Congressional trades (with published_date as proxy for trade timing)
        elite_filter = " OR ".join([f"politician_name LIKE '%{name}%'" 
                                   for name in [
                                       "Nancy Pelosi", "Josh Gottheimer", "Ro Khanna", 
                                       "Michael McCaul", "Tommy Tuberville", "Markwayne Mullin", 
                                       "Dan Crenshaw", "Brian Higgins", "Richard Blumenthal",
                                       "Debbie Wasserman Schultz", "Tom Kean Jr", "Gil Cisneros", 
                                       "Cleo Fields", "Marjorie Taylor Greene", "Lisa McClain"
                                   ]])
        
        cursor = conn.execute(f"""
            SELECT politician_name, party, published_date, size_range
            FROM congressional_trades
            WHERE ticker = ? AND trade_type = 'BUY'
            AND published_date >= date('now', '-{lookback_days} days')
            AND ({elite_filter})
            ORDER BY published_date ASC
        """, (ticker,))
        congressional_buys = [dict(row) for row in cursor.fetchall()]
        
        # Corporate insider trades
        cursor = conn.execute("""
            SELECT insider_name, insider_title, trade_date, value
            FROM openinsider_trades
            WHERE ticker = ? AND trade_type = 'P'
            AND trade_date >= date('now', '-? days')
            ORDER BY trade_date ASC
        """, (ticker, lookback_days))
        insider_buys = [dict(row) for row in cursor.fetchall()]
        
        # Superinvestor holdings (13F filings are quarterly, so just check if holding)
        cursor = conn.execute("""
            SELECT manager_name, portfolio_pct, value_usd, last_updated
            FROM dataroma_holdings
            WHERE ticker = ?
            ORDER BY last_updated DESC
        """, (ticker,))
        superinvestor_holdings = [dict(row) for row in cursor.fetchall()]
        
        # Check if Trinity convergence exists
        if not (congressional_buys and insider_buys and superinvestor_holdings):
            return None
        
        # Calculate temporal pattern
        earliest_congressional = min([b['published_date'] for b in congressional_buys]) if congressional_buys else None
        earliest_insider = min([b['trade_date'] for b in insider_buys]) if insider_buys else None
        latest_superinvestor = max([h['last_updated'] for h in superinvestor_holdings]) if superinvestor_holdings else None
        
        # Convert dates to datetime for comparison
        from datetime import datetime
        cong_date = datetime.fromisoformat(earliest_congressional) if earliest_congressional else None
        insider_date = datetime.fromisoformat(earliest_insider) if earliest_insider else None
        fund_date = datetime.fromisoformat(latest_superinvestor) if latest_superinvestor else None
        
        # Build timeline
        timeline = []
        if cong_date:
            timeline.append(('Congressional', cong_date, len(congressional_buys)))
        if insider_date:
            timeline.append(('Corporate Insider', insider_date, len(insider_buys)))
        if fund_date:
            timeline.append(('Superinvestor', fund_date, len(superinvestor_holdings)))
        
        timeline.sort(key=lambda x: x[1])  # Sort by date
        
        # Calculate convergence score
        score = 5  # Base for Trinity convergence
        pattern = "CONCURRENT"
        
        # Check if sequential (ideal pattern: Congress → Insider → Fund)
        if len(timeline) == 3:
            sequence = [t[0] for t in timeline]
            if sequence == ['Congressional', 'Corporate Insider', 'Superinvestor']:
                score += 3
                pattern = "SEQUENTIAL (Ideal)"
            elif sequence == ['Superinvestor', 'Corporate Insider', 'Congressional']:
                score -= 1  # Reverse sequence less bullish
                pattern = "REVERSE"
            
            # Tight window bonus (all within 14 days)
            date_span = (timeline[-1][1] - timeline[0][1]).days
            if date_span <= 14:
                score += 2
                pattern += f" - TIGHT ({date_span}d)"
        
        # Bipartisan bonus
        parties = set([b['party'] for b in congressional_buys if b.get('party')])
        if 'Democratic' in parties and 'Republican' in parties:
            score += 1
        
        return {
            'ticker': ticker,
            'convergence_score': min(10, score),  # Cap at 10
            'pattern': pattern,
            'timeline': [
                {
                    'actor_type': t[0],
                    'date': t[1].strftime('%Y-%m-%d'),
                    'count': t[2]
                } for t in timeline
            ],
            'congressional_details': congressional_buys,
            'insider_details': insider_buys,
            'superinvestor_details': superinvestor_holdings,
            'earliest_date': timeline[0][1].strftime('%Y-%m-%d'),
            'latest_date': timeline[-1][1].strftime('%Y-%m-%d'),
            'window_days': (timeline[-1][1] - timeline[0][1]).days if len(timeline) > 1 else 0
        }


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Scrape all superinvestor holdings
    print("=" * 80)
    print("DATAROMA SUPERINVESTOR HOLDINGS SCRAPER")
    print("=" * 80)
    
    total = scrape_all_superinvestors()
    
    print(f"\nSuccessfully scraped {total} holdings from {len(ELITE_SUPERINVESTORS)} superinvestors")
    
    # Detect Investment Fund Buy signals (quarter-over-quarter comparison)
    print("\n" + "=" * 80)
    print("DETECTING INVESTMENT FUND BUY SIGNALS (Q-over-Q Analysis)")
    print("=" * 80)
    
    fund_signals = detect_investment_fund_buys(lookback_quarters=2)
    if fund_signals:
        print(f"\nFound {len(fund_signals)} INVESTMENT FUND BUY signals:")
        for signal in fund_signals[:20]:  # Show first 20
            print(f"\n${signal['ticker']} - {signal['company_name']}")
            print(f"  Manager: {signal['manager_name']}")
            print(f"  Activity: {signal['activity_type']} ({signal['change_pct']}% change)")
            print(f"  Position: {signal['portfolio_pct']}% of portfolio (${signal['value_usd']:,})")
            print(f"  Shares: {signal['previous_shares']:,} → {signal['current_shares']:,}")
    else:
        print("\nNo Investment Fund Buy signals detected (need 2+ quarters of data)")
    
    # Detect Trinity Signals
    print("\n" + "=" * 80)
    print("DETECTING TRINITY SIGNALS")
    print("=" * 80)
    
    trinity_signals = detect_trinity_signals()
    
    if trinity_signals:
        print(f"\nFound {len(trinity_signals)} TRINITY SIGNALS:")
        for signal in trinity_signals:
            print(f"\n${signal['ticker']}:")
            print(f"  Corporate Insiders: {signal['insider_count']} buying (${signal['insider_value']:,})")
            print(f"  Elite Congressional: {signal['congressional_count']} buying ({signal['politicians']})")
            print(f"  Superinvestors: {signal['superinvestor_count']} holding ({signal['managers']})")
    else:
        print("\nNo Trinity Signals detected currently")
