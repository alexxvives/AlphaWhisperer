from insider_alerts import get_db

with get_db() as conn:
    rows = conn.execute('''
        SELECT ticker, trade_type, COUNT(*) as count 
        FROM congressional_trades 
        GROUP BY ticker, trade_type 
        ORDER BY count DESC 
        LIMIT 15
    ''').fetchall()
    
    print("Congressional trades in database:")
    print("-" * 50)
    for row in rows:
        print(f"{row[0]:8} {row[1]:4} - {row[2]} trades")
    
    print("\n" + "=" * 50)
    total = conn.execute("SELECT COUNT(*) FROM congressional_trades").fetchone()[0]
    print(f"Total trades in database: {total}")
