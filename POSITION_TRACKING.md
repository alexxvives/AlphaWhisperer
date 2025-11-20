# Position Tracking & Exit Signal Monitoring

## Overview

Track your positions and get automatic alerts when bearish exit signals are detected. This helps you know when to sell based on insider activity and technical indicators.

## How It Works

### 1. **Add Position via Telegram**
Reply to any alert (or send a message) with:
```
TICKER @PRICE
```

**Examples:**
- `AAPL @175.50`
- `NVDA @ 485.20`
- `TSLA @250.75`

The bot will confirm and start monitoring this position for exit signals.

### 2. **Automatic Monitoring**
The system checks your open positions every hour for:

**Bearish Insider Signals:**
- ✋ **Bearish Cluster Selling** - 3+ insiders selling within 5 days, $1M+ total

**Technical Exit Signals:**
- 🚨 **Stop Loss** - Price drops 10% or more from entry
- ⚡ **Momentum Loss** - Price declines 8%+ in 5 days

### 3. **Exit Alerts**
When an exit signal is detected, you'll receive a Telegram notification:

```
⚠️ EXIT SIGNAL DETECTED

Ticker: AAPL
Signal: Bearish Cluster Selling

Entry: $175.50
Current: $168.20
P/L: 📉 -4.2%

Details: 3 insiders selling $1.2M total

Detected: 2025-11-19 14:30:00

⚡ Consider closing this position or reviewing your strategy.
```

### 4. **Close Position**
When you exit, notify the bot:
```
CLOSE TICKER @PRICE
```

**Example:**
- `CLOSE AAPL @180.50`

The bot will calculate your profit/loss and stop monitoring.

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `TICKER @PRICE` | Add position to track | `AAPL @175.50` |
| `CLOSE TICKER @PRICE` | Close position | `CLOSE AAPL @180.50` |
| `/positions` | View all open positions | `/positions` |

## Exit Signal Types

### Bearish Cluster Selling (HIGH SEVERITY)
- **Trigger:** 3+ insiders selling same ticker within 5 days
- **Minimum:** $1M total value
- **Why it matters:** Multiple insiders dumping stock = they know something negative

### Stop Loss (CRITICAL SEVERITY)
- **Trigger:** Price drops 10% or more from entry
- **Why it matters:** Protects capital, limits losses to manageable level

### Momentum Loss (MEDIUM SEVERITY)
- **Trigger:** 8%+ decline in 5 days
- **Why it matters:** Trend reversal, losing upward momentum

## Setup

### 1. Install Dependencies
```bash
pip install python-telegram-bot
```

### 2. Set Environment Variable
Add to your `.env` file:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 3. Run the Bot (Optional - for interactive replies)
```bash
python telegram_bot.py
```

### 4. Run Monitoring (Scheduled)
Add to cron/Task Scheduler to run every hour:
```bash
python monitor_positions.py
```

**Windows Task Scheduler:**
- Trigger: Daily, repeat every 1 hour
- Action: `python.exe C:\path\to\monitor_positions.py`

## Database

Positions are stored in `data/positions.db` (SQLite):

**Tables:**
- `positions` - All positions (open and closed)
- `exit_signals` - Exit signals detected for each position

## Example Workflow

1. **Receive Bullish Alert:**
   ```
   📬 Insider Alert: NVDA — C-Suite Buy
   CEO bought $500K worth of shares
   ```

2. **Enter Position:**
   Reply with: `NVDA @485.20`
   
3. **Bot Confirms:**
   ```
   ✅ Position Added
   I'll monitor NVDA for exit signals
   ```

4. **System Monitors Hourly:**
   - Checks insider data for bearish selling
   - Tracks price vs. your entry
   - Detects momentum loss

5. **Exit Signal Detected:**
   ```
   ⚠️ EXIT SIGNAL: NVDA
   Bearish Cluster Selling detected
   3 insiders sold $1.5M in 3 days
   Current: $472.30 (-2.7%)
   ```

6. **You Exit:**
   Reply with: `CLOSE NVDA @475.00`
   
7. **Bot Confirms:**
   ```
   ✅ Position Closed
   Entry: $485.20
   Exit: $475.00
   P/L: 📉 -2.1%
   ```

## Files

- `position_tracker.py` - Database operations for positions
- `monitor_positions.py` - Hourly monitoring script
- `telegram_bot.py` - Interactive Telegram bot (optional)
- `data/positions.db` - SQLite database

## Notes

- Position tracking is **separate from alerts** - you manually add positions you want to track
- Multiple positions per ticker are allowed (different entry dates)
- Exit signals are sent only once per detection
- Stop monitoring happens automatically when position is closed
- Database stores full P/L history for analysis

## Future Enhancements

- [ ] Trailing stop loss (move stop up as price rises)
- [ ] Target price alerts (notify when reaching profit target)
- [ ] Portfolio view (aggregate P/L across all positions)
- [ ] Export trades to CSV for tax reporting
- [ ] Integration with brokerage APIs for auto-tracking
