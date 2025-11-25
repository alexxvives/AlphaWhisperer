# InvestorAI - Intelligent Insider Trading Alert System

A production-ready AI-powered Python system that monitors insider trading activity from OpenInsider.com and delivers rich, actionable intelligence via Telegram and email.

## 🚀 Features

### Core Intelligence
- **Real-time monitoring** of insider Form 4 filings from OpenInsider.com
- **6 powerful signal types** detecting high-conviction insider activity
- **AI-powered insights** with BUY/SELL/HOLD recommendations
- **Multi-factor confidence scoring** (1-5 stars) based on signal strength
- **Congressional trading integration** (framework ready for API)

### Rich Market Context
- **Ownership tracking**: Shows % ownership changes per trade
- **Price action analysis**: 5-day and 1-month % changes with trend indicators
- **52-week range analysis**: Distance from highs/lows
- **Short squeeze detection**: Flags high short interest (>15%)
- **Company fundamentals**: Market cap, P/E ratio, sector, descriptions
- **News integration**: Recent headlines (when API configured)
- **Strategic investor detection**: Identifies corporate buyers (e.g., NVIDIA investing)

### Communication
- **Telegram alerts** with rich markdown formatting
- **Email alerts** as backup
- **Smart de-duplication** to avoid repeat alerts
- **Configurable thresholds** for all detection rules

### Reliability
- **Robust parsing** with pandas + BeautifulSoup fallback
- **Continuous monitoring** with configurable intervals
- **Comprehensive logging** for debugging
- **Production-tested** with error handling

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
```

### 2. Configure Email Settings

Edit `.env` with your SMTP credentials:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_TO=recipient@example.com
```

**Gmail Users**: Generate an [App Password](https://myaccount.google.com/apppasswords) instead of using your regular password.

### 3. Configure Telegram (Recommended)

Telegram provides rich formatting, unlimited messages, and instant delivery:

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow instructions
3. Copy your bot token
4. Search for `@userinfobot` and send `/start`
5. Copy your chat_id
6. Update `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   TELEGRAM_BOT_USERNAME=your_bot_username
   USE_TELEGRAM=true
   ```

#### Ticker Tracking Feature

Members of your Telegram group can track specific tickers and get @mentioned when insider trades occur:

**How to use:**
- Track a ticker: `@alphawhisperer_bot $AAPL`
- Stop tracking: `@alphawhisperer_bot remove $AAPL`
- View your list: `@alphawhisperer_bot list`

When insider activity happens for tracked tickers, the bot will send the normal alert AND @mention all users tracking that ticker.

**Setup:**
1. Add the bot to your Telegram group
2. Make sure the bot has permission to read messages
3. Run the tracker bot: `python telegram_tracker.py`
4. Group members can now track tickers with @mentions

**Example:**
```
User: @alphawhisperer_bot $NVDA
Bot: ✅ Now tracking $NVDA!
     I'll notify you whenever there's insider trading activity for this stock.

[Later when NVDA insider trade detected]
Bot: 🚨 Cluster Buying
     $NVDA - NVIDIA Corporation
     
     👤 @john_doe, @jane_smith
     
     [rest of alert...]
```

### 4. Run the Script

```bash
# Single execution
python insider_alerts.py

# Continuous monitoring (every 30 minutes) - RECOMMENDED
python insider_alerts.py --loop --interval-minutes 30

# Custom interval (every 60 minutes)
python insider_alerts.py --loop --interval-minutes 60
```

### 5. Test the System

```bash
# Test Telegram connection
python test_telegram.py

# Test all signal types
python test_all_signals.py
```

## 🎯 Detection Signals

### Corporate Insider Signals (6 Types)

### 1. Cluster Buying ⭐⭐⭐⭐
**Trigger**: ≥3 insiders from the same ticker buy within 5 days, total value ≥$300K

**Why it matters**: Multiple insiders buying simultaneously suggests strong internal conviction. When 3+ insiders coordinate purchases, it's rarely a coincidence - they often see a major catalyst ahead.

**AI Analysis**: Detects insider consensus, evaluates price action, checks for Congressional alignment

### 2. CEO/CFO Buy ⭐⭐⭐
**Trigger**: CEO or CFO buys ≥$100K

**Why it matters**: C-suite executives have the deepest knowledge of company strategy, financials, and future prospects. Their personal investments carry exceptional weight.

**AI Analysis**: Examines role significance, purchase size relative to salary, timing vs. price action

### 3. Large Single Buy ⭐⭐⭐
**Trigger**: Any insider buys ≥$250K

**Why it matters**: Large dollar amounts represent significant personal capital commitment, indicating strong conviction regardless of title.

**AI Analysis**: Evaluates purchase size, ownership %, company fundamentals

### 4. First Buy in 12 Months ⭐⭐
**Trigger**: Insider's first purchase in 365 days, ≥$50K

**Why it matters**: Breaking a long period of inactivity suggests the insider sees a major inflection point or exceptional value.

**AI Analysis**: Compares current price to historical range, examines market conditions

### 5. Strategic Investor Buy ⭐⭐⭐⭐⭐
**Trigger**: Corporate entity (e.g., "NVIDIA CORPORATION") buying shares

**Why it matters**: Corporate investors conduct months of due diligence. Their investments often signal strategic partnerships, acquisition interest, or technology validation.

**AI Analysis**: Identifies investor significance, potential strategic rationale

### 6. Bearish Cluster Selling ⚠️
**Trigger**: ≥3 insiders from same ticker sell within 5 days, total ≥$1M

**Why it matters**: Coordinated selling by multiple insiders may signal concerns about future prospects (though less reliable than buys due to diversification needs).

**AI Analysis**: Examines selling patterns, company performance, sector trends

### Congressional Trading Signals (3 Types) 🏛️

**Note**: Congressional signals are generated as standalone alerts when detected. ALL recent Congressional trades are also displayed with every corporate insider alert for context.

#### 1. Congressional Cluster Buy ⭐⭐⭐⭐
**Trigger**: ≥2 politicians buy the same ticker within 7 days

**Why it matters**: Multiple Congress members buying the same stock suggests insider knowledge about upcoming legislation, regulations, or policy changes that could benefit the company. Clustering indicates consensus.

**Detection**: System groups all recent Congressional buys by ticker and date, triggering alerts when 2+ politicians converge on the same stock.

#### 2. Bipartisan Congressional Buy ⭐⭐⭐⭐⭐
**Trigger**: Politicians from BOTH parties (D + R) buy the same ticker

**Why it matters**: When Democrats AND Republicans agree to buy the same stock, it's an exceptionally powerful signal. Bipartisan consensus on upcoming policy/regulatory changes that will benefit the company is rare and highly predictive.

**Detection**: Automatically flags cluster buys where both "(D)" and "(R)" politicians are involved.

#### 3. High-Conviction Congressional Buy ⭐⭐⭐⭐
**Trigger**: Known successful trader makes a purchase

**Why it matters**: Certain Congress members have exceptional trading track records. Purchases by these "power traders" warrant special attention.

**Tracked Politicians** (current list, expanding):
- Nancy Pelosi
- Josh Gottheimer
- Michael McCaul
- Tommy Tuberville
- Dan Crenshaw
- Brian Higgins

**Detection**: Filters Congressional buys to only alert on trades from this curated list of known successful traders.

### How Congressional Integration Works

1. **Data Source**: Selenium scraper fetches recent trades from CapitolTrades.com (FREE - no API costs)
2. **Signal Detection**: Runs alongside corporate insider detection every scan cycle
3. **Context Display**: ALL recent Congressional trades shown with every corporate insider alert (provides market intelligence)
4. **Standalone Alerts**: High-quality Congressional signals (clusters, bipartisan, high-conviction) trigger their own alerts
5. **AI Integration**: When a politician's purchase matches a corporate insider alert ticker, AI flags "CONGRESSIONAL ALIGNMENT" for extra conviction

**Configuration**:
```env
USE_CAPITOL_TRADES=true               # Enable Congressional scraping
MIN_CONGRESSIONAL_CLUSTER=2           # Minimum politicians for cluster (default: 2)
CONGRESSIONAL_LOOKBACK_DAYS=7         # Days to look back for clustering (default: 7)
```

## 🧠 AI-Powered Insights

The system generates contextual analysis for each signal:

### Pattern Detection
- **Short Squeeze Setups**: High short interest + insider buying = potential squeeze
- **Dip Buying**: Insiders buying near 52-week lows = bottom fishing
- **Congressional Alignment**: Politicians + insiders buying = exceptionally strong signal
- **Falling Knives**: Warns when negative momentum conflicts with insider buying

### Recommendations
- **STRONG BUY**: Multiple bullish factors align (short squeeze, Congressional alignment, strategic investment)
- **BUY**: Positive setup with good risk/reward
- **HOLD/ACCUMULATE**: Solid opportunity, build position gradually
- **MONITOR**: Watch for additional confirmation
- **WAIT**: Let price stabilize before entering

### Confidence Scoring (1-5 Stars)

**Factors Analyzed**:
- Signal type strength (Cluster/Strategic = +2.0, CEO/CFO = +1.5)
- Purchase size ($1M+ = +1.0, $500K+ = +0.5)
- Ownership increase (>10% = +1.0, >5% = +0.5)
- Price location (<20% from 52w low = +1.0)
- Short interest (>15% = +0.5)
- Valuation (P/E 5-15 = +0.5)
- Congressional alignment (politicians buying = +0.5)

**Typical Scores**:
- ⭐⭐⭐⭐⭐ (5/5): Cluster + Congressional + dip buying + high short interest
- ⭐⭐⭐⭐ (4/5): Cluster buying near 52w low OR CEO/CFO + strategic factors
- ⭐⭐⭐ (3/5): Large single buy with decent fundamentals
- ⭐⭐ (2/5): First buy in 12m or smaller purchases
- ⭐ (1/5): Minimal conviction signals

## ⚙️ Configuration

### Core Settings (.env)

```env
# Telegram (Recommended - Free, Unlimited, Rich Formatting)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
USE_TELEGRAM=true

# Email (Backup)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_TO=recipient@example.com

# NewsAPI (Optional - 100 requests/day free)
NEWS_API_KEY=get_from_newsapi.org
USE_NEWS_CONTEXT=true

# Congressional Trading (Optional - Requires API)
USE_CAPITOL_TRADES=false     # Set true when QuiverQuant API configured

# Detection Thresholds
LOOKBACK_DAYS=7              # Days of history to analyze
CLUSTER_DAYS=5               # Window for cluster detection
MIN_LARGE_BUY=250000         # Minimum for large buy signal ($250K)
MIN_CEO_CFO_BUY=100000       # Minimum for CEO/CFO buy ($100K)
MIN_CLUSTER_BUY_VALUE=300000 # Minimum total for cluster buy ($300K)
MIN_FIRST_BUY_12M=50000      # Minimum for first buy signal ($50K)
```

### Advanced Features

#### Congressional Trading Integration
Cross-reference insider buys with Congressional stock purchases for exceptionally strong signals.

**Status**: Framework complete, awaiting API configuration

**Setup**:
1. Sign up for [QuiverQuant API](https://api.quiverquant.com/) (~$20/month)
2. Update `.env`:
   ```env
   USE_CAPITOL_TRADES=true
   QUIVER_API_KEY=your_api_key
   ```
3. See `CONGRESSIONAL_INTEGRATION.md` for implementation details

**Benefits**:
- Detects when politicians + insiders both buy same stock
- Politicians have access to policy/regulatory insights
- Boosts confidence score by +0.5
- Triggers STRONG BUY recommendation

## 📊 Example Telegram Alert

```markdown
🚨 *Cluster Buying*

*NVDA* - NVIDIA Corporation

👥 3 insiders
💰 $2,500,000
📅 Window: 5 days

📊 *Trades:*
• 10/28: John Smith - $1,000,000 (+2.5%)
• 10/29: Jane Doe - $900,000 (+1.8%)
• 10/30: Bob Johnson - $600,000 (+1.2%)

📊 *Price Action:*
• 5-day: 🔴 -3.2%
• 1-month: 🔴 -8.5%

📏 *52-Week Range:*
• High: $150.25
• Low: $98.50
• Current: $112.30
• 14.0% above 52w low

🏢 *About:*
NVIDIA Corporation designs graphics processing units for gaming and data centers.

📈 *Market Data:*
• Sector: Technology
• Market Cap: $450.2B
• P/E Ratio: 12.4
• Short Interest: 🔥18.5%

👔 *Insider Role:*
CEOs control company strategy and have deepest knowledge of future plans...

⭐⭐⭐⭐ *Confidence: 4/5*
_Multiple insiders buying; $1M+ purchase; Buying near 52-week low; High short interest (18.5%)_

🧠 *AI Insight:*
🔥 SHORT SQUEEZE SETUP: 18.5% of shares are sold short. Insiders are buying heavily while 
shorts bet against the stock. If the stock rises, short sellers will be forced to buy shares 
to cover their positions, creating a feedback loop that could rocket the price higher.

💎 DIP BUYING OPPORTUNITY: Stock is trading just 14.0% above its 52-week low. Insiders are 
buying at/near the bottom, signaling they believe the worst is over. This is classic 'smart 
money' behavior - buying when pessimism is highest.

🚀 RECOMMENDATION: STRONG BUY - Multiple bullish factors align. Consider taking a position.

Key factors: High short interest + insider buying = squeeze potential, Multiple insiders = 
strong conviction, Buying near 52-week low
```

## 🛠️ Troubleshooting

### Gmail Authentication Errors

**Problem**: "Username and Password not accepted"

**Solution**: 
1. Enable 2-factor authentication on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Use the app password in `SMTP_PASS`, not your regular password

### Telegram Not Sending

**Problem**: No messages in Telegram

**Solution**:
1. Test connection: `python test_telegram.py`
2. Verify bot token and chat_id in `.env`
3. Ensure `USE_TELEGRAM=true`
4. Check bot has permission to post in channel/group

### No Alerts Being Generated

**Check**:
1. Verify `.env` configuration
2. Run: `python test_all_signals.py` to see if detection works
3. Check `logs/insider_alerts.log` for errors
4. Ensure signals meet threshold requirements
5. Visit https://openinsider.com to confirm recent activity

### NewsAPI Errors

**Problem**: News section empty or errors

**Solution**:
1. Regenerate API key at https://newsapi.org/
2. Update `NEWS_API_KEY` in `.env`
3. Free tier: 100 requests/day limit
4. Can disable: `USE_NEWS_CONTEXT=false`

## 📁 Project Structure

```
InvestorAI/
├── insider_alerts.py              # Main script (1896 lines)
├── .env                            # Configuration
├── requirements.txt                # Python dependencies
├── test_telegram.py               # Test Telegram connection
├── test_all_signals.py            # Test signal detection
├── test_congressional.py          # Test Congressional scraper
├── README.md                       # This file
├── QUICK_REFERENCE.md             # Quick command reference
└── CONGRESSIONAL_INTEGRATION.md   # Congressional feature docs
```

## 🚀 Production Deployment

### Recommended Setup

```powershell
# Windows (PowerShell)
cd C:\Users\alexx\Desktop\Projects\InvestorAI
.\.venv\Scripts\python.exe insider_alerts.py --loop --interval-minutes 30
```

This will:
- Check OpenInsider every 30 minutes
- Send Telegram alerts for new signals
- Log all activity to `logs/insider_alerts.log`
- Run continuously until stopped (Ctrl+C)

### Alternative: Windows Task Scheduler

For daily runs instead of continuous:
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 9:00 AM (market open)
4. Action: Start Program
5. Program: `C:\Users\alexx\Desktop\Projects\InvestorAI\.venv\Scripts\python.exe`
6. Arguments: `insider_alerts.py`
7. Start in: `C:\Users\alexx\Desktop\Projects\InvestorAI`

## 💰 Cost Analysis

| Feature | Service | Cost |
|---------|---------|------|
| OpenInsider | Free | $0 |
| yfinance | Free | $0 |
| Telegram | Free | $0 |
| NewsAPI | Free Tier | $0 |
| **Current Total** | | **$0/month** |
| | | |
| Congressional Data | QuiverQuant | ~$20/month |
| **With Congressional** | | **~$20/month** |

## 🔗 Useful Links

- **OpenInsider**: https://openinsider.com
- **NewsAPI**: https://newsapi.org/
- **QuiverQuant API**: https://api.quiverquant.com/
- **yfinance Documentation**: https://pypi.org/project/yfinance/
- **Telegram Bot API**: https://core.telegram.org/bots/api

## 📚 Additional Documentation

- `QUICK_REFERENCE.md` - Command reference and troubleshooting
- `CONGRESSIONAL_INTEGRATION.md` - Congressional trading feature details
- `logs/insider_alerts.log` - Runtime logs and debugging info

## 📝 License

MIT License

---

**Version**: 2.0 (AI-Powered with Congressional Framework)  
**Status**: Production Ready ✅  
**Last Updated**: November 2025

