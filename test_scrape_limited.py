"""Test scraping with pagination - LIMITED TO 3 PAGES"""
from insider_alerts import init_database
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import sqlite3
import re

# Initialize database
init_database()

# Configure Chrome
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

print("Starting browser...")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

MAX_PAGES = 3
new_count = 0
dup_count = 0

try:
    driver.get("https://www.capitoltrades.com/trades")
    time.sleep(4)
    
    # Dismiss cookie banner
    try:
        cookie_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in cookie_buttons:
            if 'Accept' in btn.text and 'All' in btn.text:
                btn.click()
                print("✓ Dismissed cookie banner")
                time.sleep(1)
                break
    except:
        pass
    
    # Set 30 DAYS filter
    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".dropdown-selector.q-flyout--plain"))
        )
        dropdown.click()
        time.sleep(1)
        
        options = driver.find_elements(By.TAG_NAME, "button")
        for option in options:
            if '30 DAYS' in option.text.upper():
                option.click()
                print("✓ Set to 30 DAYS")
                time.sleep(3)
                break
    except Exception as e:
        print(f"✗ Could not set timeframe: {e}")
    
    # Try to set page size to 96
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        show_more_buttons = driver.find_elements(By.CSS_SELECTOR, ".absolute.right-px.flex.items-center")
        if show_more_buttons:
            driver.execute_script("arguments[0].click();", show_more_buttons[0])
            time.sleep(1)
            
            options = driver.find_elements(By.TAG_NAME, "button")
            for option in options:
                if '96' in option.text:
                    driver.execute_script("arguments[0].click();", option)
                    print("✓ Set page size to 96")
                    time.sleep(3)
                    break
    except Exception as e:
        print(f"Note: Could not set page size to 96: {e}")
    
    # Scrape pages
    for page_num in range(1, MAX_PAGES + 1):
        print(f"\n{'='*60}")
        print(f"SCRAPING PAGE {page_num}")
        print(f"{'='*60}")
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = soup.find_all('tr')
        page_new = 0
        page_dup = 0
        
        for row in rows:
            try:
                politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                if not politician_link:
                    continue
                
                politician_name = politician_link.get_text(strip=True)
                
                # Get ticker
                ticker_span = row.find('span', class_='issuer-ticker')
                if not ticker_span:
                    continue
                    
                ticker_text = ticker_span.get_text(strip=True)
                ticker_match = re.search(r'([A-Z]{1,5}):', ticker_text)
                if not ticker_match:
                    continue
                ticker = ticker_match.group(1)
                
                # Check if already in DB
                conn = sqlite3.connect('data/congressional_trades.db')
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM congressional_trades WHERE politician_name=? AND ticker=?",
                    (politician_name, ticker)
                )
                exists = cursor.fetchone()[0] > 0
                conn.close()
                
                if exists:
                    page_dup += 1
                    dup_count += 1
                else:
                    page_new += 1
                    new_count += 1
                    print(f"  NEW: {politician_name} - {ticker}")
                    
            except Exception as e:
                continue
        
        print(f"\nPage {page_num} summary: {page_new} new, {page_dup} duplicates")
        
        # Go to next page (if not last)
        if page_num < MAX_PAGES:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                next_link = driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Go to next page"]')
                
                if next_link and not next_link.get_attribute('disabled'):
                    driver.execute_script("arguments[0].click();", next_link)
                    print(f"→ Navigating to page {page_num + 1}...")
                    time.sleep(3)
                else:
                    print("No more pages")
                    break
            except Exception as e:
                print(f"Could not navigate: {e}")
                break
    
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS: {new_count} new trades, {dup_count} duplicates")
    print(f"{'='*60}")
    
finally:
    driver.quit()
