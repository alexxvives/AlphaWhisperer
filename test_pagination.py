"""Test pagination with limited pages for debugging"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

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
driver.set_page_load_timeout(20)

try:
    # Navigate to trades page
    driver.get("https://www.capitoltrades.com/trades")
    print("Loaded page, waiting 4 seconds...")
    time.sleep(4)
    
    # Step 1: Click time filter dropdown
    print("\n=== STEP 1: Setting 30 DAYS filter ===")
    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".dropdown-selector.q-flyout--plain"))
        )
        print(f"Found dropdown: {dropdown.text[:50]}")
        dropdown.click()
        time.sleep(1)
        
        # Select 30 DAYS
        options = driver.find_elements(By.TAG_NAME, "button")
        for option in options:
            if '30 DAYS' in option.text.upper():
                print(f"Clicking '30 DAYS' option")
                option.click()
                time.sleep(3)
                break
        print("✓ Set to 30 DAYS")
    except Exception as e:
        print(f"✗ Could not set timeframe: {e}")
    
    # Step 2: Increase page size to 96
    print("\n=== STEP 2: Setting page size to 96 ===")
    try:
        # Find the show more button
        show_more_buttons = driver.find_elements(By.CSS_SELECTOR, ".absolute.right-px")
        print(f"Found {len(show_more_buttons)} buttons with .absolute.right-px")
        
        for button in show_more_buttons:
            if 'items-center' in button.get_attribute('class'):
                print(f"Clicking show-more button")
                button.click()
                time.sleep(1)
                
                # Look for 96 option
                options = driver.find_elements(By.TAG_NAME, "button")
                for option in options:
                    if '96' in option.text:
                        print(f"Found 96 option, clicking...")
                        option.click()
                        time.sleep(3)
                        print("✓ Set page size to 96")
                        break
                break
    except Exception as e:
        print(f"✗ Could not set page size: {e}")
    
    # Step 3: Count rows on first page
    print("\n=== STEP 3: Counting rows on page 1 ===")
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    rows = soup.find_all('tr')
    data_rows = [r for r in rows if r.find('a', href=lambda x: x and '/politicians/' in str(x))]
    print(f"Found {len(data_rows)} trade rows on page 1")
    
    # Show first 3 trades
    for i, row in enumerate(data_rows[:3], 1):
        politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
        ticker_span = row.find('span', class_='issuer-ticker')
        print(f"  {i}. {politician_link.get_text(strip=True)} - {ticker_span.get_text(strip=True) if ticker_span else '?'}")
    
    # Step 4: Find and click next page button
    print("\n=== STEP 4: Looking for NEXT button ===")
    next_buttons = driver.find_elements(
        By.CSS_SELECTOR, 
        "button.inline-flex.items-center.justify-center.font-medium"
    )
    print(f"Found {len(next_buttons)} potential navigation buttons")
    
    next_button = None
    for i, btn in enumerate(next_buttons):
        class_attr = btn.get_attribute('class')
        aria_label = btn.get_attribute('aria-label') or ''
        is_disabled = btn.get_attribute('disabled')
        inner_html = btn.get_attribute('innerHTML')[:100]
        
        print(f"\nButton {i+1}:")
        print(f"  Classes: {class_attr}")
        print(f"  Aria-label: {aria_label}")
        print(f"  Disabled: {is_disabled}")
        print(f"  HTML preview: {inner_html}")
        
        # Check if it's a next button (rounded-full, enabled, likely last one)
        if 'rounded-full' in class_attr and not is_disabled and btn.is_enabled():
            print(f"  → Potential NEXT button")
            next_button = btn
    
    if next_button:
        print(f"\n✓ Found next button, clicking...")
        next_button.click()
        time.sleep(3)
        
        # Count rows on page 2
        print("\n=== STEP 5: Counting rows on page 2 ===")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = soup.find_all('tr')
        data_rows = [r for r in rows if r.find('a', href=lambda x: x and '/politicians/' in str(x))]
        print(f"Found {len(data_rows)} trade rows on page 2")
        
        # Show first 3 trades
        for i, row in enumerate(data_rows[:3], 1):
            politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
            ticker_span = row.find('span', class_='issuer-ticker')
            print(f"  {i}. {politician_link.get_text(strip=True)} - {ticker_span.get_text(strip=True) if ticker_span else '?'}")
        
        print("\n✓ Pagination working!")
    else:
        print("\n✗ No next button found")

finally:
    driver.quit()
    print("\nBrowser closed")
