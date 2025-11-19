from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
driver.get('https://www.capitoltrades.com/trades')
time.sleep(4)

# Count initial rows
soup = BeautifulSoup(driver.page_source, 'html.parser')
initial_rows = len(soup.find_all('tr'))
print(f"Initial rows: {initial_rows}")

# Scroll down to bottom
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)

# Count rows after scroll
soup = BeautifulSoup(driver.page_source, 'html.parser')
after_scroll_rows = len(soup.find_all('tr'))
print(f"After scroll: {after_scroll_rows}")

# Scroll again
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)

soup = BeautifulSoup(driver.page_source, 'html.parser')
after_second_scroll = len(soup.find_all('tr'))
print(f"After 2nd scroll: {after_second_scroll}")

# Try scrolling multiple times
for i in range(5):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

soup = BeautifulSoup(driver.page_source, 'html.parser')
final_rows = len(soup.find_all('tr'))
print(f"After 5 more scrolls: {final_rows}")

driver.quit()
