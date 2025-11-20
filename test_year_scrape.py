"""
Test script to scrape a few Congressional trades and check if we can extract the year.
This will help us verify the year is available on the Capitol Trades website.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime

def test_year_extraction():
    """Test extracting the year from Capitol Trades website"""
    driver = None
    
    try:
        # Configure Chrome for headless mode
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        print("Starting Chrome...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)
        
        # Navigate to trades page
        url = "https://www.capitoltrades.com/trades?pageSize=10"
        print(f"Loading: {url}")
        driver.get(url)
        time.sleep(4)
        
        # Dismiss cookie banner if present
        try:
            cookie_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in cookie_buttons:
                if 'Accept' in btn.text and 'All' in btn.text:
                    btn.click()
                    print("Dismissed cookie banner")
                    time.sleep(1)
                    break
        except:
            pass
        
        # Get rendered HTML
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Find all table rows
        all_rows = soup.find_all('tr')
        print(f"\nFound {len(all_rows)} rows\n")
        
        today_str = datetime.now().strftime("%d %b %Y")
        current_year = datetime.now().year
        
        trades_found = 0
        for row in all_rows[:5]:  # Check first 5 rows only
            try:
                # Extract politician name
                politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                if not politician_link:
                    continue
                
                politician_name = politician_link.get_text(strip=True)
                
                # Extract ticker
                ticker_span = row.find('span', class_='issuer-ticker')
                if not ticker_span:
                    continue
                    
                ticker_text = ticker_span.get_text(strip=True)
                ticker_match = re.search(r'([A-Z]{1,5}):(?:US|NYSE|NASDAQ)', ticker_text)
                if not ticker_match:
                    continue
                    
                ticker = ticker_match.group(1)
                
                trades_found += 1
                print(f"=" * 80)
                print(f"TRADE #{trades_found}")
                print(f"Politician: {politician_name}")
                print(f"Ticker: {ticker}")
                print(f"\n--- Searching for dates and year in cells ---")
                
                # Get all cells and their text
                cells = row.find_all('td')
                
                published_date = None
                traded_date = None
                year_info = None
                
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    cell_html = str(cell)[:200]  # First 200 chars of HTML
                    
                    # Look for time pattern (means published today)
                    time_match = re.search(r'\d{1,2}:\d{2}', cell_text)
                    if time_match:
                        print(f"\nCell {i} (TIME FOUND - means published today):")
                        print(f"  Text: {cell_text}")
                        print(f"  HTML: {cell_html}")
                        if not published_date:
                            published_date = today_str
                            year_info = current_year
                    
                    # Look for date with month
                    if any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                        print(f"\nCell {i} (DATE FOUND):")
                        print(f"  Text: {cell_text}")
                        print(f"  HTML: {cell_html}")
                        
                        # Look for year in the cell
                        year_match = re.search(r'\b(20\d{2})\b', cell_text)
                        if year_match:
                            year_found = year_match.group(1)
                            print(f"  *** YEAR FOUND: {year_found} ***")
                            if not year_info:
                                year_info = year_found
                        
                        # Extract the date
                        date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', cell_text)
                        if date_match:
                            date_str = date_match.group(1)
                            if not published_date:
                                published_date = date_str
                                print(f"  -> Published Date: {date_str}")
                            elif not traded_date:
                                traded_date = date_str
                                print(f"  -> Traded Date: {date_str}")
                
                print(f"\n--- EXTRACTED DATA ---")
                print(f"Published: {published_date}")
                print(f"Traded: {traded_date}")
                print(f"Year: {year_info}")
                print()
                
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
        
        if trades_found == 0:
            print("No trades found! The page structure may have changed.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            driver.quit()
            print("\nBrowser closed")

if __name__ == "__main__":
    test_year_extraction()
