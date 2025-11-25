import insider_alerts
from datetime import datetime, timedelta

# Force fresh fetch by clearing cache timestamp
conn = insider_alerts.get_db()
conn.execute("DELETE FROM cache_metadata WHERE key = 'last_congressional_fetch'")
conn.commit()
conn.close()

print("Cache cleared. Fetching fresh Congressional trades...\n")

# Now get trades - should fetch fresh
all_trades = insider_alerts.get_congressional_trades()
print(f"Total Congressional trades after fresh fetch: {len(all_trades)}\n")

# Check for NFG trades
nfg_trades = [t for t in all_trades if t.get('ticker') == 'NFG']
print(f"NFG trades found: {len(nfg_trades)}")

if nfg_trades:
    print("\nFirst NFG trade:")
    for key, value in nfg_trades[0].items():
        print(f"  {key}: {value}")
    
    print(f"\npolitician_id: '{nfg_trades[0].get('politician_id', 'NOT FOUND')}'")
