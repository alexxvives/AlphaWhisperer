"""
Scrape full trading history for each politician from their individual pages
Uses politician_id from congressional_trades table
"""

import sqlite3
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_unique_politicians():
    """Get all unique politician IDs from congressional_trades"""
    conn = sqlite3.connect('data/congressional_trades.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT politician_id, politician_name, party, chamber, state
        FROM congressional_trades
        WHERE politician_id IS NOT NULL
        ORDER BY politician_name
    """)
    
    politicians = cursor.fetchall()
    conn.close()
    
    return politicians


def scrape_politician_trades(politician_id: str, politician_name: str, max_pages: int = 20):
    """
    Scrape all trades for a specific politician from their page
    Returns list of trade dictionaries
    """
    driver = None
    all_trades = []
    
    try:
        # Configure Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)
        
        # Navigate to politician page
        url = f"https://www.capitoltrades.com/politicians/{politician_id}"
        logger.info(f"Scraping {politician_name} ({politician_id}): {url}")
        driver.get(url)
        time.sleep(4)
        
        # Dismiss cookie banner
        try:
            cookie_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in cookie_buttons:
                if 'Accept' in btn.text and 'All' in btn.text:
                    btn.click()
                    time.sleep(1)
                    break
        except:
            pass
        
        page_num = 1
        
        while page_num <= max_pages:
            logger.info(f"  Page {page_num}...")
            
            # Get page HTML
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Find all trade rows
            rows = soup.find_all('tr')
            page_trades = 0
            
            for row in rows:
                try:
                    # Check if this row has a ticker
                    ticker_span = row.find('span', class_='issuer-ticker')
                    if not ticker_span:
                        continue
                    
                    ticker_text = ticker_span.get_text(strip=True)
                    ticker_match = re.search(r'([A-Z]{1,5}):', ticker_text)
                    if not ticker_match:
                        continue
                    ticker = ticker_match.group(1)
                    
                    # Get company name
                    company_name = None
                    issuer_link = row.find('a', href=lambda x: x and '/issuers/' in str(x))
                    if issuer_link:
                        company_name = issuer_link.get_text(strip=True)
                    
                    # Determine trade type
                    row_text = row.get_text()
                    trade_type = None
                    if 'buy' in row_text.lower() and 'sell' not in row_text.lower():
                        trade_type = 'BUY'
                    elif 'sell' in row_text.lower():
                        trade_type = 'SELL'
                    
                    if not trade_type:
                        continue
                    
                    # Extract cells
                    cells = row.find_all('td')
                    published_date = None
                    traded_date = None
                    filed_after_days = None
                    owner_type = None
                    size_range = None
                    price = None
                    
                    today_str = datetime.now().strftime("%d %b")
                    
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        
                        # Published date (time = today)
                        if not published_date:
                            time_match = re.search(r'\d{1,2}:\d{2}', cell_text)
                            if time_match:
                                published_date = today_str
                            elif any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                                match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', cell_text)
                                if match:
                                    published_date = match.group(1)
                        
                        # Traded date
                        elif not traded_date:
                            if any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                                match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', cell_text)
                                if match:
                                    traded_date = match.group(1)
                        
                        # Filed after days
                        if not filed_after_days:
                            gap_cell = cell.find('div', class_='cell--reporting-gap')
                            if gap_cell:
                                value_div = gap_cell.find('div', class_='q-value')
                                if value_div:
                                    try:
                                        filed_after_days = int(value_div.get_text(strip=True))
                                    except:
                                        pass
                        
                        # Owner type
                        if any(owner in cell_text for owner in ['Joint', 'Child', 'Spouse', 'Undisclosed']):
                            if 'Joint' in cell_text:
                                owner_type = 'Joint'
                            elif 'Child' in cell_text:
                                owner_type = 'Child'
                            elif 'Spouse' in cell_text:
                                owner_type = 'Spouse'
                            elif 'Undisclosed' in cell_text:
                                owner_type = 'Undisclosed'
                        
                        # Size range
                        if not size_range:
                            size_match = re.search(r'(\d+[KM][-–]\d+[KM])', cell_text, re.IGNORECASE)
                            if size_match:
                                size_range = size_match.group(1)
                        
                        # Price
                        if not price:
                            price_match = re.search(r'\$(\d+(?:,\d+)?(?:\.\d{2})?)', cell_text)
                            if price_match:
                                try:
                                    price = float(price_match.group(1).replace(',', ''))
                                except:
                                    pass
                    
                    # Add trade to list
                    trade = {
                        'ticker': ticker,
                        'company_name': company_name,
                        'trade_type': trade_type,
                        'size_range': size_range,
                        'price': price,
                        'traded_date': traded_date or published_date,
                        'published_date': published_date or traded_date,
                        'filed_after_days': filed_after_days,
                        'owner_type': owner_type
                    }
                    
                    all_trades.append(trade)
                    page_trades += 1
                    
                except Exception as e:
                    logger.debug(f"Could not parse row: {e}")
                    continue
            
            logger.info(f"    Found {page_trades} trades")
            
            # Stop if no trades found
            if page_trades == 0:
                logger.info("    No trades found, stopping")
                break
            
            # Try to go to next page
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                next_link = driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Go to next page"]')
                
                if next_link and not next_link.get_attribute('disabled'):
                    driver.execute_script("arguments[0].click();", next_link)
                    time.sleep(3)
                    page_num += 1
                else:
                    logger.info("    No more pages")
                    break
                    
            except Exception as e:
                logger.info(f"    Reached last page: {e}")
                break
        
        logger.info(f"  Total trades for {politician_name}: {len(all_trades)}")
        
    except Exception as e:
        logger.error(f"Error scraping {politician_name}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return all_trades


def store_politician_trades(politician_id: str, politician_name: str, party: str, chamber: str, state: str, trades: list):
    """Store scraped trades in a separate table for full history"""
    conn = sqlite3.connect('data/congressional_trades.db')
    
    # Create table for full politician history if doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS politician_full_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            politician_id TEXT NOT NULL,
            politician_name TEXT NOT NULL,
            party TEXT,
            chamber TEXT,
            state TEXT,
            ticker TEXT NOT NULL,
            company_name TEXT,
            trade_type TEXT NOT NULL,
            size_range TEXT,
            price REAL,
            traded_date TEXT NOT NULL,
            published_date TEXT,
            filed_after_days INTEGER,
            owner_type TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(politician_id, ticker, traded_date, trade_type, size_range)
        )
    """)
    
    # Create index
    conn.execute("CREATE INDEX IF NOT EXISTS idx_politician_id ON politician_full_history(politician_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_full_ticker ON politician_full_history(ticker)")
    
    cursor = conn.cursor()
    new_count = 0
    dup_count = 0
    
    for trade in trades:
        try:
            cursor.execute("""
                INSERT INTO politician_full_history 
                (politician_id, politician_name, party, chamber, state, ticker, company_name, 
                 trade_type, size_range, price, traded_date, published_date, filed_after_days, owner_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                politician_id, politician_name, party, chamber, state,
                trade['ticker'], trade['company_name'], trade['trade_type'],
                trade['size_range'], trade['price'], trade['traded_date'],
                trade['published_date'], trade['filed_after_days'], trade['owner_type']
            ))
            new_count += 1
        except sqlite3.IntegrityError:
            dup_count += 1
    
    conn.commit()
    conn.close()
    
    logger.info(f"  Stored: {new_count} new, {dup_count} duplicates")
    return new_count, dup_count


if __name__ == "__main__":
    print("="*80)
    print("SCRAPING FULL TRADING HISTORY FOR ALL POLITICIANS")
    print("="*80)
    
    politicians = get_unique_politicians()
    print(f"\nFound {len(politicians)} unique politicians\n")
    
    total_new = 0
    total_dup = 0
    
    for pol_id, pol_name, party, chamber, state in politicians:
        trades = scrape_politician_trades(pol_id, pol_name, max_pages=20)
        
        if trades:
            new, dup = store_politician_trades(pol_id, pol_name, party, chamber, state, trades)
            total_new += new
            total_dup += dup
        
        # Small delay between politicians
        time.sleep(2)
    
    print("\n" + "="*80)
    print(f"COMPLETE: {total_new} total new trades, {total_dup} duplicates")
    print("="*80)
