"""Debug Congressional scraper to see cell contents."""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

url = "https://www.capitoltrades.com/trades"
driver.get(url)
time.sleep(4)

soup = BeautifulSoup(driver.page_source, 'html.parser')
all_rows = soup.find_all('tr')

print("Examining first trade row cells:\n")
for idx, row in enumerate(all_rows[:3]):
    politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
    if not politician_link:
        continue
    
    print(f"Row {idx}:")
    cells = row.find_all('td')
    for i, cell in enumerate(cells):
        print(f"  Cell {i}: {cell.get_text(strip=True)[:100]}")
    print()

driver.quit()
