"""Check what the default timeframe is on /trades page"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

driver.get("https://www.capitoltrades.com/trades")
time.sleep(4)

# Dismiss cookies
try:
    cookie_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    for btn in cookie_buttons:
        if 'Accept' in btn.text and 'All' in btn.text:
            btn.click()
            time.sleep(1)
            break
except:
    pass

# Check what the dropdown shows
dropdown = driver.find_element(By.CSS_SELECTOR, ".dropdown-selector.q-flyout--plain")
print(f"Current filter showing: {dropdown.text}")

# Count rows
soup = BeautifulSoup(driver.page_source, 'html.parser')
rows = soup.find_all('tr')
data_rows = [r for r in rows if r.find('span', class_='issuer-ticker')]
print(f"Rows on page: {len(data_rows)}")

# Get first trade date
if data_rows:
    import re
    first_row_text = data_rows[0].get_text()
    dates = re.findall(r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', first_row_text)
    print(f"First trade dates found: {dates}")

driver.quit()
