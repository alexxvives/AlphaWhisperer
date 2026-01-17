# InvestorAI - Algorithm & Architecture Overview

## 🎯 Project Vision

InvestorAI is an intelligent trading alert system that tracks insider trading activity from both corporate insiders (CEOs, CFOs, Directors) and Congressional members (Senate & House), automatically detecting high-conviction buying/selling patterns and delivering actionable intelligence via Telegram and email.

---

## 🧠 How the Algorithm Works (High-Level)

### Data Pipeline

```
┌─────────────────┐
│  Data Sources   │
│  - OpenInsider  │──────┐
│  - CapitolTrades│      │
└─────────────────┘      ▼
                   ┌─────────────┐
                   │   Scrapers  │
                   │  (Selenium/ │
                   │   Requests) │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │  Database   │
                   │  (SQLite)   │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │   Signal    │
                   │  Detection  │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Enrichment  │
                   │ (Price, AI, │
                   │  Context)   │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │  Alerts     │
                   │ (Telegram/  │
                   │   Email)    │
                   └─────────────┘
```

### 1. Data Collection

**Corporate Insider Trades (OpenInsider.com)**
- Scrapes latest insider trades using pandas HTML parser + BeautifulSoup fallback
- Extracts: Ticker, Insider Name, Title, Transaction Type (P=Purchase, S=Sale), Value, Date, Ownership %
- Stores in `openinsider_trades` table
- Updates every scan cycle (configurable, typically 30-60 minutes)

**Congressional Trades (CapitolTrades.com)**
- Uses Selenium WebDriver to scrape JavaScript-rendered pages (FREE - no API required)
- Extracts: Politician Name, Party, Chamber, State, Ticker, Trade Type, Size Range, Dates
- Stores in `congressional_trades` table
- Historical scraping: Can backfill entire database (500+ pages = ~10,000 trades)
- Daily updates: Scrapes last 7 days worth of new trades

### 2. Signal Detection (Pattern Recognition)

The system implements **8 distinct signal types** across two categories:

#### Corporate Insider Signals

**A. Cluster Buying** ⭐⭐⭐⭐⭐
- **Logic**: 3+ distinct insiders buying same ticker within 5 days
- **Minimum**: $500K total combined value
- **Why it matters**: Coordinated buying = strong conviction from multiple insiders with privileged information
- **Example**: 3 VPs of NVDA each buy $400K+ within 3 days → Cluster Buy signal

**B. C-Suite Buy** ⭐⭐⭐⭐
- **Logic**: CEO, CFO, or COO makes discretionary purchase
- **Minimum**: $100K purchase value
- **Why it matters**: Top executives have comprehensive company knowledge and material non-public information
- **Example**: Tesla CFO buys $250K worth of TSLA stock

**C. Large Single Buy** ⭐⭐⭐⭐
- **Logic**: Any insider purchases $500K+ in single transaction
- **Minimum**: $500K value
- **Why it matters**: Exceptional capital commitment indicates very high confidence
- **Example**: Board Director buys $750K of company stock

**D. Strategic Investor Buy** ⭐⭐⭐⭐⭐
- **Logic**: Corporate entity (not individual) purchases shares
- **Detection**: "Corp", "LLC", "Holdings", "Fund", "Capital" in buyer name
- **Why it matters**: Strategic investment or partnership signal
- **Example**: "NVIDIA CORPORATION" buys stake in semiconductor company

#### Congressional Signals

**E. Congressional Cluster Buy** ⭐⭐⭐⭐
- **Logic**: 3+ politicians buy same ticker within 30 days
- **Bonus**: "Bipartisan" tag if both D and R involved
- **Why it matters**: Multiple politicians with access to policy/regulatory information agree on opportunity
- **Example**: 6 House members (3D, 3R) buy GOOGL in November → Bipartisan Cluster

**F. Large Congressional Buy** ⭐⭐⭐⭐
- **Logic**: Single politician purchases $100K+ of a stock
- **Size ranges tracked**: $100K-$250K, $250K-$500K, $500K-$1M, $1M-$5M, $5M+
- **Why it matters**: Significant personal capital at risk = high conviction based on insider knowledge
- **Example**: Senator buys $1M-$5M of defense contractor stock before major contract announcement

**G. Tracked Ticker Activity** ⭐⭐⭐
- **Logic**: Any insider activity on user-specified tickers
- **Configuration**: Users track tickers via Telegram bot (`@bot $AAPL`)
- **Why it matters**: Personalized monitoring for positions you care about
- **Example**: You track MSFT, any insider buy/sell triggers @mention in Telegram

**H. Bearish Cluster Selling** ⚠️
- **Logic**: 3+ insiders selling within 5 days, $1M+ total
- **Why it matters**: Exit signal - multiple insiders dumping stock simultaneously
- **Example**: CEO, CFO, and 2 directors all sell large positions in same week

### 3. Data Enrichment

For each detected signal, the system enriches with contextual data:

**Company Fundamentals** (via yfinance API)
- Market Cap: Company size classification (Mega/Large/Mid/Small Cap)
- Sector: Industry categorization
- P/E Ratio: Valuation metric
- 52-Week Range: Current price vs. yearly high/low
- Description: Business overview

**Price Action Analysis**
- Current Price: Real-time quote
- 5-Day Change: Short-term momentum (+ or - %)
- 1-Month Change: Medium-term trend (+ or - %)
- Distance from 52W High/Low: Buying at bottom vs. top indicator

**Short Interest Detection**
- Scrapes Finviz.com for short % of float
- Flags high short interest (>15%) as potential squeeze opportunity
- Example: "🔥 HIGH SHORT INTEREST (22.4%) - Potential Squeeze"

**Ownership Tracking**
- Calculates % ownership change per trade
- Shows insider increasing/decreasing stake
- Example: "CEO increased stake by +2.5% ($1.2M purchase)"

**Congressional Context**
- Shows ALL recent Congressional activity for the ticker (last 30 days)
- Format: "🏛️ Recent Congressional Trading: Josh Gottheimer (D) bought 16 Oct, Tom Kean (R) bought 18 Oct"
- Provides full political intelligence landscape

### 4. AI Insights & Scoring

**Confidence Score** (1-5 stars)
```python
Base Score: 2.5 stars

+1.0  = Cluster buying (3+ insiders)
+0.5  = C-suite insider (CEO/CFO/COO)
+0.5  = Large purchase ($500K+)
+0.5  = Congressional alignment (politicians buying same stock)
+0.5  = Strategic investor (corporate entity)
-0.5  = High short interest (>15% - risky)
+0.5  = Bipartisan Congressional buy

Max: 5 stars
Min: 1 star
```

**AI Insight Generation**
Uses rule-based AI to generate BUY/SELL/HOLD recommendations:

**STRONG BUY triggers:**
- Cluster buying + C-suite + Large value ($1M+)
- Bipartisan Congressional cluster
- Congressional alignment with corporate insiders
- Strategic investor entering

**BUY triggers:**
- C-suite buy ($100K+)
- Large single buy ($500K+)
- Congressional cluster (3+)

**HOLD triggers:**
- Single large purchase but high short interest
- Mixed signals (buying but near 52W high)

**SELL triggers:**
- Bearish cluster selling
- Multiple insiders exiting positions

**Reasoning provided:**
- "Multiple insiders coordinating purchases suggests material non-public information about upcoming catalysts"
- "Congressional bipartisan agreement extremely rare - indicates strong cross-party consensus on company prospects"
- "CEO increased personal stake by 5% - demonstrates exceptional confidence in near-term outlook"

### 5. Alert Delivery

**Telegram Format** (Rich Markdown)
```
🚨 Cluster Buying

$NVDA - NVIDIA Corporation
Technology | $2.8T Market Cap

📊 SIGNAL DETAILS
3 insiders bought $2.98M total
Last 5 days

👥 INSIDERS
• 14Nov: VP & CFO - $1.76M (+2.5%)
• 15Nov: VP Operations - $665K (+1.2%)  
• 16Nov: VP Engineering - $561K (+0.8%)

💹 MARKET DATA
Current: $485.20 (+2.3% today)
5-day: +8.4% 📈
1-month: +15.2% 📈
52W: $385 - $505 (84% of high)

🏛️ CONGRESSIONAL ACTIVITY
Josh Gottheimer (D) bought 16 Oct
Tom Kean (R) bought 18 Oct

🔥 HIGH SHORT INTEREST: 18.2%

⭐⭐⭐⭐⭐ 5/5 Confidence
STRONG BUY

🧠 AI INSIGHT
Multiple C-suite insiders coordinating large purchases 
within narrow timeframe. Congressional alignment detected
(bipartisan). Combined signals suggest material catalyst
ahead (earnings beat, product launch, or acquisition).

[View on OpenInsider]
```

**Email Format** (HTML Table)
- Professional HTML formatting
- Sortable table with all trades
- Links to OpenInsider source
- Plain text fallback

**De-duplication**
- Tracks sent alerts in `alert_history` table
- Prevents re-sending same signal within 30 days
- Configurable expiration period
- Example: AAPL cluster buy on Nov 15 won't trigger again until Dec 15

### 6. Position Tracking & Exit Signals

**User Position Tracking**
- Users can reply to alerts: `AAPL @175.50` (entering position)
- System monitors open positions hourly
- Tracks entry price, current price, P/L %

**Exit Signal Detection**
- Stop Loss: -10% from entry
- Momentum Loss: -8% in 5 days  
- Bearish Cluster: 3+ insiders selling $1M+

**Exit Alerts**
```
⚠️ EXIT SIGNAL DETECTED

$AAPL
Signal: Bearish Cluster Selling

Entry: $175.50
Current: $168.20
P/L: 📉 -4.2%

3 insiders sold $1.5M in 3 days

⚡ Consider closing position
```

---

## 📊 Database Schema

**Primary Tables:**

1. **openinsider_trades**
   - Stores all corporate insider transactions
   - Columns: ticker, insider_name, title, transaction_type, value, shares, date, ownership_pct
   - Indexes: ticker, date, title

2. **congressional_trades**
   - Stores all Congressional stock trades
   - Columns: politician_name, party, chamber, state, ticker, trade_type, size_range, traded_date, published_date
   - Indexes: ticker, politician_name, published_date

3. **alert_history**
   - Tracks sent alerts to prevent duplicates
   - Columns: alert_id, ticker, signal_type, sent_at, expires_at
   - Expires records older than 30 days

4. **tracked_tickers**
   - User-specific ticker watchlist
   - Columns: user_id, username, ticker, added_date
   - Used for personalized @mentions

5. **positions**
   - User positions for exit monitoring
   - Columns: user_id, ticker, entry_price, entry_date, shares, status
   - Updated by Telegram bot

6. **politician_pnl**
   - Calculated P&L for all politicians
   - Columns: politician_name, ticker, avg_cost, current_price, unrealized_pnl, realized_pnl, return_pct
   - Updated daily by calculate_pnl.py

---

## 🔧 Key Technologies

**Data Collection:**
- `requests` + `pandas` for OpenInsider scraping
- `selenium` + `webdriver-manager` for CapitolTrades (JavaScript rendering)
- `BeautifulSoup4` as parsing fallback

**Data Storage:**
- SQLite3 (embedded database, no server required)
- Row-level locking for concurrent access
- Automatic schema migrations

**Market Data:**
- `yfinance` for stock prices, fundamentals, historical data
- Finviz.com for short interest (web scraping)
- Caching to minimize API calls

**Communication:**
- `python-telegram-bot` for Telegram integration
- `smtplib` for email delivery
- Markdown formatting for rich messages

**Scheduling:**
- Windows Task Scheduler (local automation)
- GitHub Actions (cloud automation)
- Polling mode for Telegram bot (works in serverless)

---

## 🚀 Execution Flow

**Daily Automated Run** (8:00 AM via `run_daily_alerts.py`)

```python
1. Check Telegram messages
   - Process @bot commands (@bot $AAPL, @bot list, @bot remove)
   - Update tracked_tickers table

2. Scrape Congressional data
   - scrape_all_congressional_trades_to_db(days=7)
   - Fetches last 7 days of new trades
   - ~5 pages, ~100 trades, 30 seconds

3. Scrape Corporate Insider data  
   - fetch_openinsider_html() + parse_openinsider()
   - Fetches latest 100 insider trades from OpenInsider.com
   - ~5 seconds

4. Detect Signals
   - detect_congressional_cluster_buy()
   - detect_large_congressional_buy()
   - detect_signals() for corporate signals
   - Returns list of TradingSignal objects

5. Enrich Signals
   - get_company_context() for each ticker
   - Fetch price, fundamentals, short interest
   - Add Congressional context

6. Filter & Score
   - calculate_confidence_score() for each signal
   - generate_ai_insight() for each signal
   - Apply minimum confidence threshold (3+ stars)

7. Check De-duplication
   - is_alert_already_sent() checks alert_history
   - Skip if same ticker+signal sent in last 30 days

8. Send Alerts
   - send_telegram_alert() with rich markdown
   - send_email_alert() as backup
   - @mention users tracking specific tickers

9. Update Database
   - mark_alert_as_sent() logs to alert_history
   - cleanup_expired_alerts() removes old records

10. Monitor Positions
    - Check user positions for exit signals
    - Send exit alerts if triggered
```

---

## 🎯 Configuration & Customization

**Environment Variables** (`.env` file)

```bash
# Data Sources
LOOKBACK_DAYS=7                          # Corporate insider lookback window
CONGRESSIONAL_LOOKBACK_DAYS=30           # Congressional cluster lookback

# Signal Thresholds
MIN_CLUSTER_INSIDERS=3                   # Minimum insiders for cluster
MIN_CLUSTER_BUY_VALUE=500000             # $500K minimum cluster value
MIN_CEO_CFO_BUY=100000                   # $100K minimum C-suite buy
MIN_LARGE_BUY=500000                     # $500K minimum large buy
MIN_CONGRESSIONAL_CLUSTER=3              # Minimum politicians for cluster
MIN_CONGRESSIONAL_BUY_SIZE=100000        # $100K minimum Congressional buy

# Communication
USE_TELEGRAM=true
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_BOT_USERNAME=your_bot

USE_EMAIL=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password

# Features
USE_CAPITOL_TRADES=true                  # Enable Congressional scraping
USE_NEWS_CONTEXT=false                   # NewsAPI (requires valid key)
USE_AI_INSIGHTS=true                     # Enable AI recommendations
```

---

## 📈 Performance & Scale

**Typical Processing Times:**
- Congressional scrape (7 days): ~30 seconds
- OpenInsider scrape: ~5 seconds
- Signal detection (100 trades): <1 second
- Enrichment per ticker: ~2 seconds
- Alert formatting & sending: <1 second per alert

**Total Runtime:** 1-2 minutes for full daily scan

**Database Size:**
- 10,000 Congressional trades: ~5 MB
- 5,000 Corporate trades: ~3 MB
- 1,000 Alert history: ~500 KB
- Total: ~10 MB for 1 year of data

**Rate Limits:**
- yfinance: ~1-2 requests/second (we add 0.5s delays)
- Finviz: No official limit (we cache aggressively)
- CapitolTrades: No API, scraping is respectful with delays

---

## 🔐 Security & Privacy

- **No sensitive data stored**: Only public trade records
- **API keys in .env**: Never committed to git
- **SQLite file permissions**: Read/write only for user
- **Telegram end-to-end**: Messages encrypted in transit
- **Email TLS**: All email sent via encrypted SMTP

---

## 📚 File Structure

```
InvestorAI/
├── insider_alerts.py          # Main engine (2000+ lines)
├── run_daily_alerts.py        # Daily automation runner
├── telegram_tracker.py        # Long-running bot for ticker tracking
├── telegram_tracker_polling.py # Polling-based bot (for GitHub Actions)
├── telegram_bot.py            # Interactive bot with position tracking
├── position_tracker.py        # Position management logic
├── monitor_positions.py       # Exit signal monitoring
├── politician_pnl.py          # Calculate politician P&L
├── calculate_pnl.py           # Store P&L in database
├── get_telegram_id.py         # Utility to get chat IDs
├── requirements.txt           # Python dependencies
├── .env                       # Configuration (DO NOT COMMIT)
├── .env.example              # Template for .env
├── README.md                  # User guide
├── ALGORITHM_OVERVIEW.md      # This file - technical deep dive
├── data/
│   ├── alphaWhisperer.db     # Main SQLite database
│   └── ticker_tracking.db    # Ticker watchlist database
├── logs/
│   └── *.log                 # Application logs
├── src/
│   ├── config.py             # Configuration management
│   ├── ingest/               # Data ingestion modules
│   ├── processing/           # Signal processing
│   ├── outputs/              # Alert formatting
│   └── backtest/             # Backtesting engine
└── tests/
    └── *.py                  # Test suite
```

---

## 🎓 Key Algorithms Explained

### Cluster Detection Algorithm

```python
def detect_cluster_buying(trades, min_insiders=3, days=5, min_value=500000):
    """
    Group trades by ticker, filter to purchases within `days` window,
    count distinct insiders, sum total value, flag if >= thresholds
    """
    for ticker in trades:
        recent = [t for t in trades[ticker] if t.days_ago <= days]
        insiders = set([t.insider_name for t in recent])
        total_value = sum([t.value for t in recent])
        
        if len(insiders) >= min_insiders and total_value >= min_value:
            return ClusterBuySignal(ticker, insiders, recent, total_value)
```

### Confidence Scoring Algorithm

```python
def calculate_confidence_score(alert, context):
    score = 2.5  # Base
    reasons = []
    
    # Cluster buying
    if alert.type == "cluster" and alert.insider_count >= 3:
        score += 1.0
        reasons.append("Multiple insiders buying")
    
    # C-suite
    if any(title in ["CEO", "CFO", "COO"] for title in alert.titles):
        score += 0.5
        reasons.append("C-suite insider")
    
    # Large value
    if alert.total_value >= 1_000_000:
        score += 0.5
        reasons.append("$1M+ purchase")
    
    # Congressional alignment
    cong_buys = [t for t in context.congressional if t.type == "BUY"]
    if len(cong_buys) >= 2:
        score += 0.5
        reasons.append(f"{len(cong_buys)} Congressional buy(s)")
    
    # Short interest risk
    if context.short_interest > 15:
        score -= 0.5
        reasons.append("High short interest (risky)")
    
    score = max(1, min(5, score))  # Clamp to 1-5
    return int(score), "; ".join(reasons)
```

### De-duplication Algorithm

```python
def is_alert_already_sent(ticker, signal_type):
    """
    Check if (ticker, signal_type) combo exists in alert_history
    with expires_at > now(). If yes, skip. If no, send.
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 1 FROM alert_history
            WHERE ticker = ? AND signal_type = ?
            AND expires_at > datetime('now')
        """, (ticker, signal_type)).fetchone()
        
        return row is not None
```

---

## 🧪 Testing & Validation

**Unit Tests** (`tests/`)
- Signal detection logic
- Data parsing edge cases
- Scoring calculations

**Integration Tests**
- End-to-end scrape → detect → alert flow
- Database consistency checks

**Validation Methods**
- Manual cross-reference with OpenInsider.com
- Congressional data verified against CapitolTrades.com
- Price data validated against Yahoo Finance

---

## 📝 Future Enhancements

**Planned Features:**
- Machine learning for signal weighting
- Backtesting engine for historical performance
- SEC Form 4 direct parsing (bypass OpenInsider)
- Options activity tracking
- Analyst rating changes correlation
- Earnings date proximity detection
- Portfolio management interface
- Mobile app

---

## 📄 License & Disclaimer

This system is for **educational and informational purposes only**. Insider trading data is public information, but:
- Not financial advice
- Past insider activity doesn't guarantee future returns
- Always do your own research
- Consult a licensed financial advisor

The algorithm detects patterns in public data but cannot predict market movements or guarantee profits.

---

## 🤝 Contributing

Key areas for contribution:
1. Additional signal types
2. Better AI insight generation
3. Performance optimizations
4. Additional data sources
5. UI/visualization improvements

---

**Built with ❤️ for intelligent trading**
