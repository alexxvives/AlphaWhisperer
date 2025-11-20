"""
Test script to debug OpenInsider parsing
"""

from insider_alerts import fetch_openinsider_html, parse_openinsider
import logging

logging.basicConfig(level=logging.DEBUG)

# Fetch HTML
print("Fetching OpenInsider HTML...")
html = fetch_openinsider_html()
print(f"Fetched {len(html)} bytes\n")

# Parse it
print("Parsing HTML...")
df = parse_openinsider(html)

print(f"\n=== RESULTS ===")
print(f"Rows: {len(df)}")
print(f"\nColumns found: {list(df.columns)}")
print(f"\nFirst few rows:")
print(df.head())
print(f"\nTrade Type values: {df['Trade Type'].unique() if 'Trade Type' in df.columns else 'N/A'}")
