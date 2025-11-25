# Ticker Tracking Feature - User Guide

## Overview

The Ticker Tracking feature allows Telegram group members to follow specific stocks and get @mentioned whenever insider trading activity occurs for their tracked tickers.

## How It Works

### For Users (Group Members)

#### Track a Ticker
```
@alphawhisperer_bot $AAPL
```
The bot will respond:
```
✅ Now tracking $AAPL!

I'll notify you whenever there's insider trading activity for this stock.

To stop tracking: @alphawhisperer_bot remove $AAPL
```

#### Stop Tracking
```
@alphawhisperer_bot remove $NVDA
```
Response:
```
✅ Stopped tracking $NVDA

You'll no longer receive alerts for this ticker.
```

#### View Your List
```
@alphawhisperer_bot list
```
Response:
```
📊 Your tracked tickers:
$AAPL, $NVDA, $TSLA

You'll be notified of any insider trades for these stocks.
```

### What Happens When Trades Occur

When insider activity is detected for a tracked ticker, the bot sends the normal alert BUT also @mentions all users tracking that ticker:

**Example Alert:**
```
🚨 Cluster Buying

$NVDA - NVIDIA Corporation

👤 @john_doe, @jane_smith

📊 Trades:
22Nov
J. Smith (Insider) - $1.2M (+2.5%)

[rest of alert with chart...]
```

## For Administrators

### Setup

1. **Install Dependencies**
   ```bash
   pip install python-telegram-bot
   ```

2. **Add Bot to Telegram Group**
   - Open your Telegram group
   - Click "Add Members"
   - Search for your bot (@alphawhisperer_bot)
   - Add the bot to the group

3. **Grant Bot Permissions**
   - Make sure bot can:
     - Read messages (to detect @mentions)
     - Send messages
     - Tag users (for @mentions)

4. **Configure Environment**
   Edit `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_BOT_USERNAME=alphawhisperer_bot
   TELEGRAM_CHAT_ID=your_group_chat_id
   USE_TELEGRAM=true
   ```

5. **Run the Tracker Bot**
   ```bash
   # Start the tracker bot (separate from main alerts)
   python telegram_tracker.py
   ```

   This bot runs continuously, listening for @mentions in the group.

6. **Run the Main Alert System**
   ```bash
   # In a separate terminal/process
   python insider_alerts.py --loop --interval-minutes 30
   ```

### How the Integration Works

1. **User Tracking**:
   - Users mention the bot with a ticker
   - Bot stores: user_id, username, first_name, ticker, date
   - Data stored in SQLite: `data/ticker_tracking.db`

2. **Alert Generation**:
   - Main system (`insider_alerts.py`) detects insider trades
   - Before sending Telegram alert, queries tracker database
   - If users tracking this ticker exist, adds @mentions to message

3. **Database Schema**:
   ```sql
   CREATE TABLE user_tickers (
       id INTEGER PRIMARY KEY,
       user_id TEXT NOT NULL,       -- Telegram user ID
       username TEXT,                -- @username
       first_name TEXT,              -- Display name
       ticker TEXT NOT NULL,         -- Stock symbol
       added_date TEXT NOT NULL,     -- When they started tracking
       UNIQUE(user_id, ticker)
   )
   ```

### Running Both Bots

You need TWO separate processes:

**Terminal 1 - Tracker Bot (listens for @mentions):**
```bash
python telegram_tracker.py
```

**Terminal 2 - Alert System (monitors insider trades):**
```bash
python insider_alerts.py --loop --interval-minutes 30
```

### Windows Service Setup (Optional)

To run both automatically on startup:

1. **Create batch file `start_bots.bat`:**
   ```batch
   @echo off
   cd C:\Users\alexx\Desktop\Projects\InvestorAI
   
   REM Start tracker bot
   start "Ticker Tracker" .venv\Scripts\python.exe telegram_tracker.py
   
   REM Start alert system
   start "Insider Alerts" .venv\Scripts\python.exe insider_alerts.py --loop --interval-minutes 30
   ```

2. **Add to Windows Startup:**
   - Press Win+R
   - Type: `shell:startup`
   - Copy `start_bots.bat` into this folder

### Monitoring

**Check Active Trackers:**
```python
import sqlite3
conn = sqlite3.connect("data/ticker_tracking.db")
cursor = conn.cursor()

# All tracked tickers
cursor.execute("SELECT ticker, COUNT(*) as users FROM user_tickers GROUP BY ticker")
print(cursor.fetchall())

# All users and their tickers
cursor.execute("SELECT username, ticker FROM user_tickers ORDER BY username")
print(cursor.fetchall())
```

**Check Logs:**
```bash
# Tracker bot logs
python telegram_tracker.py  # Shows logs in console

# Alert system logs
Get-Content logs\insider_alerts.log -Tail 50
```

## Troubleshooting

### Bot Doesn't Respond to @mentions

**Check:**
1. Bot added to group? (Search for bot in group members)
2. Bot has message read permission?
3. Tracker bot running? (`python telegram_tracker.py`)
4. Correct bot username in `.env`? (`TELEGRAM_BOT_USERNAME`)

**Test:**
```bash
# Run tracker bot with debug logging
python telegram_tracker.py
```
Try mentioning bot in group. Should see logs like:
```
INFO - Added ticker AAPL for user john_doe (12345678)
```

### Users Not Getting @mentioned in Alerts

**Check:**
1. User successfully tracked ticker? (Check with `@bot list`)
2. Main alert system running? (`insider_alerts.py`)
3. Database file exists? (`data/ticker_tracking.db`)
4. User has username set? (Telegram Settings → Username)

**Debug:**
```python
# Check if user is in database
import sqlite3
conn = sqlite3.connect("data/ticker_tracking.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM user_tickers WHERE ticker = 'NVDA'")
print(cursor.fetchall())
```

### Database Not Found Error

**Solution:**
```bash
# Run tracker bot once to create database
python telegram_tracker.py
# Press Ctrl+C after a few seconds
# Database will be created at data/ticker_tracking.db
```

## Best Practices

1. **Monitor Database Size**:
   - Each user-ticker pair = 1 row
   - 100 users tracking 10 tickers each = 1,000 rows
   - Very lightweight, no cleanup needed

2. **User Limits**:
   - No built-in limit on tickers per user
   - Consider adding if needed (e.g., max 20 tickers/user)

3. **Privacy**:
   - Only stores: user_id, username, first_name, ticker
   - No message content or trading data
   - Users can remove tickers anytime

4. **Bot Mentions**:
   - Only mentions users tracking that specific ticker
   - Won't spam users for unrelated tickers
   - Users without usernames get first name only (no @mention)

## Example Workflow

**Day 1:**
```
User1: @alphawhisperer_bot $NVDA
Bot: ✅ Now tracking $NVDA!

User2: @alphawhisperer_bot $NVDA
Bot: ✅ Now tracking $NVDA!

User3: @alphawhisperer_bot $AAPL
Bot: ✅ Now tracking $AAPL!
```

**Day 2 - NVDA insider trade detected:**
```
Bot: 🚨 Large Single Buy
     
     $NVDA - NVIDIA Corporation
     
     👤 @user1, @user2
     
     📊 Trades:
     23Nov
     J. Huang (CEO) - $5.0M
     
     [chart image]
```

**Day 3 - AAPL insider trade detected:**
```
Bot: 🚨 Cluster Buying
     
     $AAPL - Apple Inc
     
     👤 @user3
     
     📊 Trades:
     [...]
```

## Support

**Issues?**
1. Check logs: `python telegram_tracker.py` and `logs/insider_alerts.log`
2. Verify database: `data/ticker_tracking.db` exists
3. Test bot connection: Send `@alphawhisperer_bot list` in group
4. Check permissions: Bot needs to read messages in group

**Feature Requests?**
- Add max tickers per user limit
- Add notifications when someone else tracks same ticker
- Add leaderboard (most tracked tickers)
- Add statistics (most active users)

---

**Version**: 1.0  
**Last Updated**: November 2025
