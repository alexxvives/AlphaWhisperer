import sqlite3

conn = sqlite3.connect('data/alphaWhisperer.db')
cursor = conn.cursor()

# Check schema first
cursor.execute("PRAGMA table_info(openinsider_trades)")
schema = cursor.fetchall()
print('Schema:')
for col in schema:
    print(f'  {col[1]} ({col[2]})')
print()

# Check PROP trades in database
cursor.execute('''
    SELECT *
    FROM openinsider_trades 
    WHERE ticker = "PROP" 
    ORDER BY trade_date DESC 
    LIMIT 10
''')

rows = cursor.fetchall()
print(f'Found {len(rows)} PROP trades in database:')
print('-' * 120)
for r in rows:
    print(r)

conn.close()
