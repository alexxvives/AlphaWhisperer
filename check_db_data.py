import insider_alerts

# Get all Congressional trades from database
trades = insider_alerts.get_ticker_trades_from_db("NFG")
print(f"Found {len(trades)} trades for NFG in database\n")

if trades:
    first_trade = trades[0]
    print("First trade keys:", list(first_trade.keys()))
    print("\nFirst trade data:")
    for key, value in first_trade.items():
        print(f"  {key}: {value}")
    
    print(f"\npolitician_id value: '{first_trade.get('politician_id', 'KEY NOT FOUND')}'")
    print(f"Type: {type(first_trade.get('politician_id'))}")
else:
    print("No trades found for NFG")
