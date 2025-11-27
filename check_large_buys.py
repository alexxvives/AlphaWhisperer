import sqlite3

conn = sqlite3.connect('data/alphaWhisperer.db')
cursor = conn.cursor()

# Large buys (>$100K) in last 7 days
# Size ranges: 1K–15K, 15K–50K, 50K–100K, 100K–250K, 250K–500K, 500K–1M, 1M–5M, 5M–25M, >25M
cursor.execute('''
    SELECT politician_name, ticker, size_range, published_date, party, company_name
    FROM congressional_trades 
    WHERE trade_type = "BUY" 
    AND published_date >= date("now", "-7 days")
    AND (size_range LIKE '%100K%' OR size_range LIKE '%250K%' OR size_range LIKE '%500K%' 
         OR size_range LIKE '%1M%' OR size_range LIKE '%5M%' OR size_range LIKE '%25M%'
         OR size_range LIKE '>%')
    ORDER BY published_date DESC
''')
rows = cursor.fetchall()
print(f'Large Congressional buys last 7 days (>$100K): {len(rows)}')
for r in rows:
    print(f'  {r[0]} ({r[4]}) - {r[1]} ({r[5]}) - {r[2]} - Published: {r[3]}')

# Large buys (>$100K) in last 30 days
cursor.execute('''
    SELECT politician_name, ticker, size_range, published_date, party, company_name
    FROM congressional_trades 
    WHERE trade_type = "BUY" 
    AND published_date >= date("now", "-30 days")
    AND (size_range LIKE '%100K%' OR size_range LIKE '%250K%' OR size_range LIKE '%500K%' 
         OR size_range LIKE '%1M%' OR size_range LIKE '%5M%' OR size_range LIKE '%25M%'
         OR size_range LIKE '>%')
    ORDER BY published_date DESC
    LIMIT 20
''')
rows = cursor.fetchall()
print(f'\nLarge Congressional buys last 30 days (>$100K): {len(rows)} (showing first 20)')
for r in rows:
    print(f'  {r[0]} ({r[4]}) - {r[1]} ({r[5]}) - {r[2]} - Published: {r[3]}')

conn.close()
