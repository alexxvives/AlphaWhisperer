# InvestorAI - Quick Reference

## 🚀 Run the System

### Standard Mode (One-Time Check)
```powershell
python insider_alerts.py
```

### Continuous Monitoring (Recommended)
```powershell
python insider_alerts.py --loop --interval-minutes 30
```

### Test All Signals
```powershell
python test_all_signals.py
```

### Test Telegram
```powershell
python test_telegram.py
```

## 📊 System Status

### ✅ Working Features
- **OpenInsider Scraping**: 6 signal types detecting insider activity
- **Telegram Alerts**: Sending to "ALPHA WHISPERER" group
- **Ownership Tracking**: Shows % ownership changes
- **Price Analysis**: 5-day and 1-month % changes
- **52-Week Ranges**: Distance from highs/lows
- **Short Interest**: Detects squeeze potential (>15% = 🔥)
- **Company Data**: Sector, market cap, P/E ratio, descriptions
- **Confidence Scoring**: 1-5 star ratings with reasoning
- **AI Insights**: BUY/SELL/HOLD recommendations
- **Strategic Investors**: Detects corporate buyers (e.g., NVIDIA investing)

### ⚠️ Pending Enhancements
- **NewsAPI**: Key invalid, needs regeneration at https://newsapi.org/
- **Congressional Trades**: Framework ready, needs QuiverQuant API ($10-30/month)

## 🔧 Configuration Files

### .env
```env
# Core settings
TELEGRAM_CHAT_ID=-1003315248155        # ALPHA WHISPERER group
USE_TELEGRAM=true                       # Enabled
USE_NEWS_CONTEXT=true                   # Enabled (key needs fixing)
USE_CAPITOL_TRADES=false                # Disabled until API configured

# Signal thresholds
LOOKBACK_DAYS=7                         # Check last 7 days
CLUSTER_DAYS=5                          # Cluster window
MIN_LARGE_BUY=250000                    # $250K minimum for large buys
MIN_CEO_CFO_BUY=100000                  # $100K minimum for C-suite
MIN_CLUSTER_BUY_VALUE=300000            # $300K minimum for clusters
```

## 📱 Telegram Group

**Name**: ALPHA WHISPERER  
**Chat ID**: -1003315248155  
**Bot**: @InvestorAI_Bot (8138624261:AAFHoeuLIhV8b6PRsyIrBNKhPiW66F2UovY)

## 🎯 Signal Types (6 Total)

1. **Cluster Buying** ⭐⭐⭐⭐
   - 3+ insiders buying within 5 days
   - Total value > $300K
   - Strong signal: Multiple insiders = conviction

2. **CEO/CFO Buy** ⭐⭐⭐
   - C-suite executive buying
   - Minimum $100K purchase
   - High-level insider knowledge

3. **Large Single Buy** ⭐⭐⭐
   - Any insider buying $250K+
   - Significant capital commitment
   - Strong confidence signal

4. **First Buy 12 Months** ⭐⭐
   - Insider's first purchase in a year
   - Minimum $50K
   - Timing suggests opportunity

5. **Strategic Investor Buy** ⭐⭐⭐⭐⭐
   - Corporate entity buying (e.g., "NVIDIA CORPORATION")
   - Any amount
   - Partnership/acquisition interest

6. **Bearish Cluster Selling** ⚠️
   - Multiple insiders selling
   - Warning signal (rarely triggers)

## 💡 AI Insight Patterns

### STRONG BUY Triggers
- 🏛️ Congressional Alignment: Politicians + insiders buying
- 🔥 Short Squeeze Setup: High short interest + insider buying
- 🏢 Strategic Investment: Corporate buyer detected
- 📊 Multiple Factors: Cluster + dip + value

### BUY Triggers
- 💎 Dip Buying: Near 52-week low + insider buying
- ✅ High Confidence: 4/5 star score

### CAUTION Triggers
- ⚠️ Falling Knife: Negative momentum despite insider buying
- ⏳ Wait for Confirmation: Price declining sharply

## 📈 Confidence Scoring

### Factors (Max 5 Stars)
- **Signal Type**: +2.0 (Cluster/Strategic), +1.5 (CEO/CFO), +1.0 (Large)
- **Purchase Size**: +1.0 ($1M+), +0.5 ($500K+)
- **Ownership Increase**: +1.0 (>10%), +0.5 (>5%)
- **Price Location**: +1.0 (<20% from 52w low), +0.5 (<40%)
- **Short Interest**: +0.5 (>15%)
- **Valuation**: +0.5 (P/E 5-15)
- **Congressional**: +0.5 (Politicians buying same stock)

### Typical Scores
- **Cluster Buying near 52w low**: 4-5 stars
- **CEO/CFO Buy with high short interest**: 3-4 stars
- **Large single buy**: 2-3 stars
- **First buy in 12m**: 1-2 stars

## 🔍 Message Format

```markdown
🚨 *Signal Type*

*TICKER* - Company Name

👥 3 insiders
💰 $1,500,000
📅 Window: 5 days

📊 *Trades:*
• 10/28: John Smith - $600,000 (+2.1%)
• 10/29: Jane Doe - $500,000 (+1.5%)
• 10/30: Bob Johnson - $400,000 (+1.8%)

📊 *Price Action:*
• 5-day: 🔴 -3.2%
• 1-month: 🔴 -8.5%

📏 *52-Week Range:*
• High: $150.25
• Low: $98.50
• Current: $112.30
• 14.0% above 52w low

🏢 *About:*
Company develops software solutions...

📈 *Market Data:*
• Sector: Technology
• Market Cap: $5.2B
• P/E Ratio: 12.4
• Short Interest: 🔥18.5%

👔 *Insider Role:*
CEOs control company strategy...

⭐⭐⭐⭐ *Confidence: 4/5*
_Multiple insiders buying; $1M+ purchase; Buying near 52-week low_

🧠 *AI Insight:*
💎 DIP BUYING OPPORTUNITY: Stock is trading just 14.0% above its 52-week low...

🚀 RECOMMENDATION: STRONG BUY - Multiple bullish factors align.
```

## 🛠️ Troubleshooting

### No Alerts Showing Up
1. Check OpenInsider is accessible: https://openinsider.com
2. Verify signals exist in last 7 days
3. Check thresholds in .env aren't too high
4. Run test: `python test_all_signals.py`

### Telegram Not Working
1. Verify bot token: Test with `python test_telegram.py`
2. Check chat ID: Should be `-1003315248155`
3. Ensure `USE_TELEGRAM=true` in .env
4. Bot must be added to group and given admin rights

### NewsAPI Errors
1. Regenerate key at https://newsapi.org/
2. Update `NEWS_API_KEY` in .env
3. Free tier: 100 requests/day limit

### Import Errors
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Reinstall packages
pip install -r requirements.txt
```

## 📊 Example Live Commands

### Check for New Signals Once
```powershell
python insider_alerts.py
```

### Run Continuously (Every 30 Minutes)
```powershell
# Recommended for production
python insider_alerts.py --loop --interval-minutes 30
```

### Run Continuously (Every Hour)
```powershell
python insider_alerts.py --loop --interval-minutes 60
```

### Stop Monitoring
Press `Ctrl+C` in the terminal

## 🎓 Understanding the Signals

### Why Cluster Buying Matters
When 3+ insiders buy within days, it's **not coincidence**. They often discuss opportunities internally before buying. Clusters suggest:
- Major catalyst coming
- Company undervalued
- Strategic shift planned

### Why Strategic Investors Matter
Corporate buyers (e.g., NVIDIA buying a chip startup) signal:
- Partnership discussions
- Acquisition interest
- Technology validation
- Strategic importance

### Why Short Squeeze Setups Matter
When insiders buy AND >15% shares are sold short:
- Insiders know shorts are wrong
- If price rises, shorts must cover
- Covering creates buying pressure
- Can cause explosive upside

### Why Congressional Alignment Matters (When Enabled)
Politicians have access to:
- Committee hearings (not public)
- Policy discussions
- Regulatory changes
- Industry insights

When they buy the same stock as insiders = **exceptionally strong signal**

## 📝 Key Files

```
InvestorAI/
├── insider_alerts.py          # Main script (1896 lines)
├── .env                        # Configuration
├── requirements.txt            # Python dependencies
├── test_telegram.py           # Test Telegram
├── test_all_signals.py        # Test all signal types
├── test_congressional.py      # Test Congressional scraper
├── README.md                   # Main documentation
└── CONGRESSIONAL_INTEGRATION.md # Congressional feature docs
```

## 🚦 Quick Health Check

```powershell
# 1. Check Python environment
.\.venv\Scripts\python.exe --version
# Should show: Python 3.11.1

# 2. Test Telegram
python test_telegram.py
# Should send test message to ALPHA WHISPERER

# 3. Check for live signals
python insider_alerts.py
# Should show: "Scanning OpenInsider..." and list any detected signals

# 4. Verify all dependencies
pip list
# Should show: pandas, beautifulsoup4, requests, yfinance, newsapi-python, python-telegram-bot
```

## 🎯 Production Deployment

### Option 1: Manual Runs (Simple)
```powershell
# Run every morning at 9am (set Windows Task Scheduler)
python insider_alerts.py
```

### Option 2: Continuous Monitoring (Recommended)
```powershell
# Run in background terminal, checks every 30 minutes
python insider_alerts.py --loop --interval-minutes 30
```

### Option 3: Windows Service (Advanced)
Use `nssm` (Non-Sucking Service Manager) to run as Windows service

## 💰 Cost Summary

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
- **QuiverQuant**: https://www.quiverquant.com/
- **Telegram Bot Setup**: Search @BotFather in Telegram
- **ALPHA WHISPERER Group**: Already configured (chat_id: -1003315248155)

## 📞 Support

System created for: Alex  
Email alerts to: alexxvives@gmail.com  
Telegram group: ALPHA WHISPERER (-1003315248155)

---

**Last Updated**: November 2025  
**Version**: 2.0 (with Congressional framework)  
**Status**: Production Ready ✅
