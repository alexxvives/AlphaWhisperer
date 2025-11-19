"""
Debug Congressional trades scraper - saves HTML to file for inspection.
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

def debug_capitol_trades(ticker="NVDA", use_filter=False):
    """Debug the CapitolTrades scraping by saving HTML."""
    driver = None
    
    try:
        # Configure Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        print(f"Initializing Chrome driver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(15)
        
        # Visit page - try general trades page first
        if use_filter:
            url = f"https://www.capitoltrades.com/trades?asset={ticker}"
        else:
            url = "https://www.capitoltrades.com/trades"
        print(f"Loading: {url}")
        driver.get(url)
        
        # Wait for JavaScript
        print("Waiting for page to render...")
        time.sleep(5)
        
        # Get HTML
        page_source = driver.page_source
        
        # Save to file
        filename = f"capitol_trades_{ticker}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(page_source)
        
        print(f"\n✅ Saved HTML to: {filename}")
        print(f"File size: {len(page_source)} bytes")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Show key elements
        print(f"\n--- Page Analysis ---")
        print(f"Title: {soup.title.string if soup.title else 'No title'}")
        
        # Count tables
        tables = soup.find_all('table')
        print(f"Tables found: {len(tables)}")
        
        # Count rows
        all_rows = soup.find_all('tr')
        print(f"Table rows found: {len(all_rows)}")
        
        # Look for ticker mentions
        ticker_mentions = page_source.upper().count(ticker.upper())
        print(f"'{ticker}' mentions in HTML: {ticker_mentions}")
        
        # Check for "0 TRADES" message
        if "0 TRADES" in page_source or "No results" in page_source:
            print("⚠️ Page shows '0 TRADES' or 'No results'")
        
        # Show first few rows with content
        print(f"\n--- Sample Table Rows ---")
        for i, row in enumerate(all_rows[:5]):
            text = row.get_text(strip=True)[:100]
            if text:
                print(f"Row {i}: {text}...")
        
        # Look for specific class patterns
        print(f"\n--- Looking for CapitolTrades patterns ---")
        politician_links = soup.find_all('a', href=lambda x: x and '/politicians/' in str(x))
        print(f"Politician links found: {len(politician_links)}")
        if politician_links:
            print(f"First politician link: {politician_links[0].get('href')}")
            print(f"Text: {politician_links[0].get_text(strip=True)}")
        
        # Look for trade-related divs
        divs_with_trade = soup.find_all('div', class_=lambda x: x and 'trade' in str(x).lower())
        print(f"Divs with 'trade' in class: {len(divs_with_trade)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    print("=== Test 1: General trades page (no filter) ===")
    debug_capitol_trades("NVDA", use_filter=False)
    
    print("\n\n=== Test 2: Filtered by NVDA ===")
    debug_capitol_trades("NVDA", use_filter=True)
