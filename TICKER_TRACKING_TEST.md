# Ticker Tracking Test Guide

## Overview

The ticker tracking feature allows users to register stock tickers they want to monitor. When a signal is detected for a tracked ticker, they receive personalized notifications.

## Database Location

**File:** `data/ticker_tracking.db`

**Schema:**
```sql
CREATE TABLE tracked_tickers (
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    ticker TEXT,
    added_date TEXT
)
```

## How to Test

### 1. Track a Ticker via Telegram

Send a message in the Telegram group where the bot is an admin:

```
@bot $AAPL
```

**Expected Response:**
```
✓ Now tracking AAPL for @your_username
```

### 2. View Tracked Tickers

```
@bot list
```

**Expected Response:**
```
📊 Your tracked tickers:
• AAPL
• TSLA
• NVDA
```

### 3. Remove a Ticker

```
@bot remove $AAPL
```

**Expected Response:**
```
✓ Stopped tracking AAPL for @your_username
```

### 4. Verify Database

Check what's stored in the database:

```powershell
# View all tracked tickers
.venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('data/ticker_tracking.db'); print('\n'.join([str(row) for row in conn.execute('SELECT * FROM tracked_tickers').fetchall()]))"
```

### 5. Test Alert Notification

Once you've tracked a ticker:

1. **Wait for a real signal** (Congressional or Corporate Insider trade)
2. **Or manually trigger a test:**

```python
# test_ticker_alert.py
import insider_alerts
from insider_alerts import TradingSignal

# Create a fake signal for a tracked ticker
alert = TradingSignal(
    ticker="AAPL",  # Use your tracked ticker
    signal_type="Test Signal",
    trades=[],
    company_name="Apple Inc.",
    company_sector="Technology",
    market_cap="3T"
)

# Send via Telegram
insider_alerts.send_telegram_alert(alert, dry_run=False)
```

Run: `.venv\Scripts\python.exe test_ticker_alert.py`

**Expected:** Users tracking AAPL should receive a personalized notification mentioning they're tracking this ticker.

## Bot Commands Reference

| Command | Description | Example |
|---------|-------------|---------|
| `@bot $TICKER` | Track a stock | `@bot $NVDA` |
| `@bot remove $TICKER` | Stop tracking | `@bot remove $NVDA` |
| `@bot list` | View tracked tickers | `@bot list` |

## Troubleshooting

### Bot not responding?

1. Check bot is admin in the Telegram group
2. Verify `telegram_tracker.py` is running:
   ```powershell
   .venv\Scripts\python.exe telegram_tracker.py
   ```
3. Check logs for errors

### Database not updating?

```powershell
# Check if database file exists
Test-Path data/ticker_tracking.db

# View database schema
.venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('data/ticker_tracking.db'); print(conn.execute('SELECT sql FROM sqlite_master WHERE type=\"table\"').fetchall())"
```

### Test message patterns

The bot looks for:
- Case-insensitive: `@bot`, `@BOT`, `@Bot`
- With dollar sign: `@bot $AAPL`
- Without dollar sign: `@bot AAPL` (also works)

## Integration Flow

1. **User sends message** → `telegram_tracker.py` listens
2. **Bot detects `@bot` mention** → Parses ticker symbol
3. **Saves to database** → `ticker_tracking.db`
4. **Daily alerts run** → `insider_alerts.py` checks tracked tickers
5. **Signal matches tracked ticker** → Personalized notification sent

## Notes

- Tickers are stored per-user (user_id + ticker combination)
- Same ticker can be tracked by multiple users
- Database is separate from Congressional/OpenInsider databases
- Bot must be running to respond to messages (or use webhook)
