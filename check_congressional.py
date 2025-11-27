import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/alphaWhisperer.db')
cursor = conn.cursor()

# Total trades
cursor.execute('SELECT COUNT(*) FROM congressional_trades')
print(f'Total Congressional trades in DB: {cursor.fetchone()[0]}')

# Last 30 days
cursor.execute('SELECT COUNT(*) FROM congressional_trades WHERE published_date >= date("now", "-30 days")')
print(f'Last 30 days: {cursor.fetchone()[0]}')

# Last 7 days
cursor.execute('SELECT COUNT(*) FROM congressional_trades WHERE published_date >= date("now", "-7 days")')
print(f'Last 7 days: {cursor.fetchone()[0]}')

# Buys last 7 days
cursor.execute('''
    SELECT COUNT(*) FROM congressional_trades 
    WHERE trade_type = "BUY" AND published_date >= date("now", "-7 days")
''')
print(f'Buys last 7 days: {cursor.fetchone()[0]}')

# Large buys last 7 days (>$100K - check size_range field)
cursor.execute('''
    SELECT politician_name, ticker, traded_date, published_date, size_range, party
    FROM congressional_trades 
    WHERE trade_type = "BUY" 
    AND published_date >= date("now", "-7 days")
    ORDER BY published_date DESC
    LIMIT 20
''')
rows = cursor.fetchall()
print(f'\nCongressional buys last 7 days:')
for r in rows:
    print(f'  {r[0]} ({r[5]}) - {r[1]} - {r[4]} - Trade: {r[2]}, Published: {r[3]}')

# Cluster buys (3+ politicians, last 30 days)
cursor.execute('''
    SELECT ticker, COUNT(DISTINCT politician_name) as pol_count, 
           GROUP_CONCAT(DISTINCT politician_name || ' (' || party || ')') as politicians
    FROM congressional_trades 
    WHERE trade_type = "BUY" 
    AND published_date >= date("now", "-30 days")
    GROUP BY ticker 
    HAVING pol_count >= 3
    ORDER BY pol_count DESC
    LIMIT 10
''')
rows = cursor.fetchall()
print(f'\nCongressional cluster buys (3+ politicians, last 30 days):')
for r in rows:
    print(f'  {r[0]}: {r[1]} politicians - {r[2][:100]}...')

conn.close()
