"""Full scrape of Capitol Trades with issuer_id extraction."""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import sqlite3
import time
import re
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

DB_FILE = 'data/alphaWhisperer.db'

def store_trade(trade):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.execute("""
            INSERT OR IGNORE INTO congressional_trades 
            (politician_name, politician_id, party, chamber, state, ticker, company_name,
             trade_type, size_range, price, traded_date, published_date, filed_after_days,
             issuer_id)
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
        conn.close()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f'Error storing trade: {e}')
        return False

def main():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)

    total_new = 0
    total_dupes = 0
    current_year = datetime.now().year
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # Scrape multiple pages using direct URL with page parameter
    for page_num in range(1, 350):  # Full scrape
        try:
            url = f'https://www.capitoltrades.com/trades?page={page_num}&pageSize=96'
            logger.info(f'Loading page {page_num}: {url}')
            driver.get(url)
            time.sleep(3)
            
            # Dismiss cookie banner on first page
            if page_num == 1:
                try:
                    cookie_buttons = driver.find_elements(By.CSS_SELECTOR, 'button')
                    for btn in cookie_buttons:
                        if 'Accept' in btn.text and 'All' in btn.text:
                            btn.click()
                            time.sleep(1)
                            break
                except:
                    pass
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.find_all('tr')
            
            page_new = 0
            page_dupes = 0
            
            for row in rows:
                try:
                    # Extract politician
                    pol_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                    if not pol_link:
                        continue
                    
                    politician_name = pol_link.get_text(strip=True)
                    politician_href = pol_link.get('href', '')
                    politician_id = politician_href.split('/')[-1] if politician_href else None
                    
                    # Party/chamber/state - extract from the first cell which contains politician info
                    # Format: "NamePartyChamberState" e.g. "Dave McCormickRepublicanSenatePA"
                    row_text = row.get_text()
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
                        
                        # Extract state - last 2 characters should be state abbreviation
                        # Pattern: ends with 2 uppercase letters that are a valid state
                        state_match = re.search(r'(House|Senate)([A-Z]{2})$', first_cell)
                        if state_match:
                            state = state_match.group(2)
                    
                    # Trade type
                    trade_type = None
                    if 'buy' in row_text.lower() and 'sell' not in row_text.lower():
                        trade_type = 'BUY'
                    elif 'sell' in row_text.lower():
                        trade_type = 'SELL'
                    if not trade_type:
                        continue
                    
                    # Ticker
                    ticker_span = row.find('span', class_='issuer-ticker')
                    if not ticker_span:
                        continue
                    ticker_text = ticker_span.get_text(strip=True)
                    ticker_match = re.search(r'([A-Z]{1,5}):(?:US|NYSE|NASDAQ)', ticker_text)
                    if not ticker_match:
                        continue
                    ticker = ticker_match.group(1)
                    
                    # Issuer
                    issuer_link = row.find('a', href=lambda x: x and '/issuers/' in str(x))
                    company_name = None
                    issuer_id = None
                    if issuer_link:
                        company_name = issuer_link.get_text(strip=True)
                        issuer_href = issuer_link.get('href', '')
                        if '/issuers/' in issuer_href:
                            issuer_id = issuer_href.split('/issuers/')[-1].strip('/')
                    
                    # Size range
                    size_range = None
                    size_match = re.search(r'(\d+[KM][-–]\d+[KM])', row_text, re.IGNORECASE)
                    if size_match:
                        size_range = size_match.group(1)
                    
                    # Price - skip rows with N/A price
                    if 'N/A' in row_text:
                        continue
                    
                    price_numeric = None
                    price_match = re.search(r'\$(\d+(?:,\d+)?(?:\.\d{2})?)', row_text)
                    if price_match:
                        try:
                            price_numeric = float(price_match.group(1).replace(',', ''))
                        except:
                            pass
                    
                    # Dates - extract from cells
                    published_date = None
                    traded_date = None
                    
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        cell_lower = cell_text.lower()
                        
                        if not published_date:
                            # Check for time with today/yesterday indicator
                            time_match = re.search(r'\d{1,2}:\d{2}', cell_text)
                            if time_match:
                                # Look for today/yesterday in the same cell
                                if 'yesterday' in cell_lower:
                                    published_date = yesterday.strftime('%Y-%m-%d')
                                else:
                                    # Default to today if time is present (either says "today" or just time)
                                    published_date = today.strftime('%Y-%m-%d')
                            elif any(m in cell_text for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
                                # Format can be "24 Nov2025" or "24 Nov 2025"
                                match = re.search(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(20\d{2})?', cell_text)
                                if match:
                                    day = match.group(1)
                                    month = match.group(2)
                                    year = match.group(3) or str(current_year)
                                    try:
                                        date_obj = datetime.strptime(f'{day} {month} {year}', '%d %b %Y')
                                        published_date = date_obj.strftime('%Y-%m-%d')
                                    except:
                                        pass
                        elif not traded_date:
                            if any(m in cell_text for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
                                # Format can be "24 Nov2025" or "24 Nov 2025"
                                match = re.search(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(20\d{2})?', cell_text)
                                if match:
                                    day = match.group(1)
                                    month = match.group(2)
                                    year = match.group(3) or str(current_year)
                                    try:
                                        date_obj = datetime.strptime(f'{day} {month} {year}', '%d %b %Y')
                                        traded_date = date_obj.strftime('%Y-%m-%d')
                                    except:
                                        pass
                    
                    # Calculate filed_after_days as difference between published and traded dates
                    filed_after_days = None
                    final_traded = traded_date or published_date
                    final_published = published_date or traded_date
                    if final_traded and final_published:
                        try:
                            traded_dt = datetime.strptime(final_traded, '%Y-%m-%d')
                            published_dt = datetime.strptime(final_published, '%Y-%m-%d')
                            filed_after_days = (published_dt - traded_dt).days
                        except:
                            pass
                    
                    trade = {
                        'politician': politician_name,
                        'politician_id': politician_id,
                        'party': party,
                        'chamber': chamber,
                        'state': state,
                        'ticker': ticker,
                        'company_name': company_name,
                        'issuer_id': issuer_id,
                        'type': trade_type,
                        'size': size_range,
                        'price_numeric': price_numeric,
                        'traded_date': final_traded,
                        'published_date': final_published,
                        'filed_after_days_numeric': filed_after_days,
                    }
                    
                    if store_trade(trade):
                        page_new += 1
                    else:
                        page_dupes += 1
                        
                except Exception as e:
                    continue
            
            total_new += page_new
            total_dupes += page_dupes
            logger.info(f'  Page {page_num}: {page_new} new, {page_dupes} dupes | Total: {total_new} new')
            
            # Stop if no data on page
            if page_new == 0 and page_dupes == 0:
                logger.info('Empty page - stopping')
                break
                
        except Exception as e:
            logger.error(f'Error on page {page_num}: {e}')
            continue

    driver.quit()
    print(f'\n=== COMPLETE: {total_new} total new trades scraped ===')

if __name__ == '__main__':
    main()
