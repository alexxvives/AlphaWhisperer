import sqlite3

conn = sqlite3.connect('data/alphaWhisperer.db')
cursor = conn.cursor()

# Last purchases (any time period)
cursor.execute('''
    SELECT politician_name, ticker, size_range, published_date, party, trade_type
    FROM congressional_trades 
    WHERE trade_type = "Purchase"
    ORDER BY published_date DESC 
    LIMIT 20
''')
rows = cursor.fetchall()
print('Last 20 Congressional purchases (any date):')
for r in rows:
    print(f'  {r[0]} ({r[4]}) - {r[1]} - {r[2]} - Published: {r[3]}')

# Check what trade types exist recently
cursor.execute('''
    SELECT trade_type, COUNT(*) 
    FROM congressional_trades 
    WHERE published_date >= date("now", "-30 days")
    GROUP BY trade_type
''')
rows = cursor.fetchall()
print('\nTrade types in last 30 days:')
for r in rows:
    print(f'  {r[0]}: {r[1]}')

conn.close()
