# InvestorAI - Intelligent Insider Trading Alert System

An AI-powered system that monitors insider trading activity from corporate insiders and Congressional members, detecting high-conviction patterns and delivering actionable intelligence via Telegram and email.

> 📖 **[Read the Algorithm Overview](ALGORITHM_OVERVIEW.md)** for a complete technical deep-dive into how the system works.

## 🚀 Quick Overview

**What it does:**
- Monitors **corporate insider trades** (CEOs, CFOs, Directors) from OpenInsider.com
- Tracks **Congressional stock trades** (Senate & House) from CapitolTrades.com  
- Detects **8 signal patterns** (Cluster Buying, C-Suite Buys, Large Purchases, etc.)
- Enriches signals with **market data** (price, fundamentals, short interest)
- Generates **AI insights** with BUY/SELL/HOLD recommendations + confidence scores
- Delivers **instant alerts** via Telegram & email
- Tracks **your positions** and sends exit signals

**Key Features:**
- ✅ Cluster buying detection (3+ insiders)
- ✅ Congressional bipartisan signals
- ✅ Strategic investor identification
- ✅ Short squeeze detection (high short interest)
- ✅ Ownership % tracking
- ✅ Position monitoring with exit alerts
- ✅ Telegram ticker tracking (@bot $AAPL)
- ✅ Smart de-duplication (no spam)

---

## 📦 Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and edit with your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Telegram (Recommended - FREE, instant notifications)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
USE_TELEGRAM=true

# Email (Backup/Alternative)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_TO=recipient@example.com

# Signal Thresholds (customize as needed)
LOOKBACK_DAYS=7
MIN_CLUSTER_BUY_VALUE=500000
MIN_CEO_CFO_BUY=100000
MIN_LARGE_BUY=500000
```

**To get Telegram credentials:**

1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow instructions → Copy your bot token
3. Search for **@userinfobot**, send `/start` → Copy your chat ID
4. Start a conversation with your bot by searching for it and sending `/start`

**For Gmail:**
- Generate an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA)
- Don't use your regular Gmail password

---

## 🎯 Usage

### One-Time Check (Manual)
```bash
python insider_alerts.py --once
```

### Continuous Monitoring (Background)
```bash
python insider_alerts.py --loop --interval-minutes 30
```

### Daily Automation (Recommended)
```bash
python run_daily_alerts.py
```

This runs:
1. Telegram bot message processing (ticker tracking commands)
2. Congressional trade scraping
3. Corporate insider scraping  
4. Signal detection
5. Alert sending
6. Position monitoring
7. Cleanup of expired alerts

**Schedule it:**
- **Windows:** Task Scheduler (daily at 8:00 AM)
- **Linux/Mac:** Crontab (`0 8 * * * /path/to/run_daily_alerts.py`)
- **Cloud:** GitHub Actions (see `.github/workflows/`)

---

## 📱 Telegram Features

### Ticker Tracking

Track specific stocks and get @mentioned when insider activity occurs:

```
@your_bot $AAPL           # Start tracking Apple
@your_bot list             # View your tracked tickers
@your_bot remove $AAPL     # Stop tracking Apple
```

When insider trades happen for tracked tickers, you'll get personalized @mentions in the alert.

### Position Tracking

Track your trades and get exit signal alerts:

```
AAPL @175.50              # Enter position at $175.50
CLOSE AAPL @180.50        # Close position at $180.50
/positions                # View all open positions
```

The system monitors your positions hourly and sends alerts when:
- Price drops 10%+ (Stop Loss)
- Price declines 8%+ in 5 days (Momentum Loss)
- 3+ insiders start selling (Bearish Cluster)

---

## 📊 Signal Types

**Corporate Insider Signals:**
1. **Cluster Buying** - 3+ insiders buying within 5 days ($500K+ total)
2. **C-Suite Buy** - CEO/CFO/COO purchase ($100K+ minimum)
3. **Large Single Buy** - Any insider buying $500K+
4. **Strategic Investor** - Corporate entity purchasing shares

**Congressional Signals:**
5. **Congressional Cluster** - 3+ politicians buying same stock (30-day window)
6. **Large Congressional Buy** - Single politician purchases $100K+

**Exit Signals:**
7. **Bearish Cluster Selling** - 3+ insiders selling ($1M+ total)
8. **Tracked Ticker Activity** - Custom watchlist monitoring

See [ALGORITHM_OVERVIEW.md](ALGORITHM_OVERVIEW.md) for detailed logic and examples.

---

## 🔧 Configuration

All thresholds are configurable via `.env`:

```env
# Data Sources
LOOKBACK_DAYS=7                       # Corporate lookback window
CONGRESSIONAL_LOOKBACK_DAYS=30        # Congressional cluster window

# Corporate Insider Thresholds
MIN_CLUSTER_INSIDERS=3                # Minimum for cluster
MIN_CLUSTER_BUY_VALUE=500000          # $500K cluster minimum
MIN_CEO_CFO_BUY=100000                # $100K C-suite minimum
MIN_LARGE_BUY=500000                  # $500K large buy minimum

# Congressional Thresholds  
MIN_CONGRESSIONAL_CLUSTER=3           # Minimum politicians
MIN_CONGRESSIONAL_BUY_SIZE=100000     # $100K minimum size

# Features
USE_CAPITOL_TRADES=true               # Enable Congressional data
USE_AI_INSIGHTS=true                  # Enable AI recommendations
USE_NEWS_CONTEXT=false                # NewsAPI (needs valid key)
```

---

## 📁 Project Structure

```
InvestorAI/
├── insider_alerts.py              # Main detection engine (2000+ lines)
├── run_daily_alerts.py           # Daily automation runner
├── telegram_tracker.py           # Ticker tracking bot (long-running)
├── telegram_tracker_polling.py   # Polling bot (serverless-friendly)
├── telegram_bot.py               # Interactive bot with position tracking
├── position_tracker.py           # Position management
├── monitor_positions.py          # Exit signal monitoring
├── politician_pnl.py             # P&L calculation for politicians
├── calculate_pnl.py              # Store P&L in database
├── get_telegram_id.py            # Utility to get Telegram chat IDs
├── requirements.txt              # Python dependencies
├── .env                          # Configuration (DO NOT COMMIT)
├── README.md                     # This file
├── ALGORITHM_OVERVIEW.md         # Technical deep-dive
├── data/
│   └── alphaWhisperer.db        # SQLite database
└── logs/
    └── *.log                     # Application logs
```

---

## 🧪 Example Alert

```
🚨 Cluster Buying

$NVDA - NVIDIA Corporation
Technology | $2.8T Market Cap

📊 SIGNAL DETAILS
3 insiders bought $2.98M total (Last 5 days)

👥 INSIDERS
• 14Nov: VP & CFO - $1.76M (+2.5% ownership)
• 15Nov: VP Operations - $665K (+1.2% ownership)  
• 16Nov: VP Engineering - $561K (+0.8% ownership)

💹 MARKET DATA
Current: $485.20 (+2.3% today)
5-day: +8.4% 📈
1-month: +15.2% 📈
52W Range: $385 - $505 (84% of high)

🏛️ CONGRESSIONAL ACTIVITY
Josh Gottheimer (D) bought 16 Oct
Tom Kean (R) bought 18 Oct

🔥 HIGH SHORT INTEREST: 18.2% (Potential Squeeze)

⭐⭐⭐⭐⭐ 5/5 Confidence
💡 STRONG BUY

🧠 AI INSIGHT
Multiple C-suite insiders coordinating large purchases 
within narrow timeframe. Congressional bipartisan alignment 
detected. Combined signals suggest material catalyst ahead 
(earnings beat, product launch, or acquisition).
```

---

## 🤔 FAQ

**Q: Is this legal?**  
A: Yes. All data is publicly available. The system merely aggregates and analyzes public insider trading disclosures.

**Q: Does it guarantee profits?**  
A: No. Insider buying is a positive signal but doesn't guarantee stock performance. Always do your own research.

**Q: How much does it cost?**  
A: $0/month. All data sources are free (web scraping). APIs used (yfinance, Finviz) have no cost.

**Q: Does it work outside US markets?**  
A: Currently optimized for US stocks (OpenInsider, CapitolTrades are US-only). Can be adapted for other markets.

**Q: How accurate are the signals?**  
A: Signals detect patterns in public data. Insider buying is statistically correlated with outperformance, but not guaranteed.

**Q: Can I backtest strategies?**  
A: Yes. The database stores historical trades. A backtesting module is in `src/backtest/` (work in progress).

---

## 🚨 Disclaimer

This software is for **educational and informational purposes only**. It is not financial advice. Insider trading data is public information, but:

- Past insider activity doesn't guarantee future returns
- Markets are unpredictable and risky
- Always conduct your own research
- Consult a licensed financial advisor before making investment decisions

The creators assume no liability for trading losses or investment decisions made based on system outputs.

---

## 📜 License

MIT License - See LICENSE file for details.

---

## 🤝 Contributing

Contributions welcome! Areas of interest:
- Additional signal types
- Machine learning for scoring
- Additional data sources
- UI/visualization improvements
- Performance optimizations

---

## 📧 Support

For issues, questions, or feature requests, please open a GitHub issue.

---

**Built with ❤️ for intelligent investing**

