"""Test fetching prices for NVDA and GOOGL"""
import yfinance as yf
import time

print("Testing NVDA...")
time.sleep(0.5)
nvda = yf.Ticker('NVDA')
print(f"Info keys available: {list(nvda.info.keys())[:15]}")
print(f"currentPrice: {nvda.info.get('currentPrice')}")
print(f"regularMarketPrice: {nvda.info.get('regularMarketPrice')}")
print(f"previousClose: {nvda.info.get('previousClose')}")

hist = nvda.history(period='1d')
if not hist.empty:
    print(f"History Close: ${hist['Close'].iloc[-1]:.2f}")
else:
    print("History: empty")

print("\n" + "="*50)
print("Testing GOOGL...")
time.sleep(0.5)
googl = yf.Ticker('GOOGL')
print(f"Info keys available: {list(googl.info.keys())[:15]}")
print(f"currentPrice: {googl.info.get('currentPrice')}")
print(f"regularMarketPrice: {googl.info.get('regularMarketPrice')}")
print(f"previousClose: {googl.info.get('previousClose')}")

hist = googl.history(period='1d')
if not hist.empty:
    print(f"History Close: ${hist['Close'].iloc[-1]:.2f}")
else:
    print("History: empty")
