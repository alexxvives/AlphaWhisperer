import sqlite3

conn = sqlite3.connect('data/alphaWhisperer.db')
cursor = conn.cursor()

# Total purchases last 30 days
cursor.execute('SELECT COUNT(*) FROM congressional_trades WHERE trade_type = "Purchase" AND published_date >= date("now", "-30 days")')
print(f'Total purchases last 30 days: {cursor.fetchone()[0]}')

# Recent purchases
cursor.execute('''
    SELECT politician_name, ticker, size_range, published_date, party 
    FROM congressional_trades 
    WHERE trade_type = "Purchase" 
    AND published_date >= date("now", "-30 days") 
    ORDER BY published_date DESC 
    LIMIT 20
''')
rows = cursor.fetchall()
print('\nRecent purchases (last 30 days):')
for r in rows:
    print(f'  {r[0]} ({r[4]}) - {r[1]} - {r[2]} - Published: {r[3]}')

conn.close()
