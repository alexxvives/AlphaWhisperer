# InvestorAI - Complete Algorithm Architecture & Logic Flow

## 🎯 Project Vision

InvestorAI is an intelligent trading alert system that tracks insider trading activity from three independent sources: corporate insiders (CEOs, CFOs, Directors), Congressional members (Senate & House), and elite superinvestors (hedge funds filing 13Fs). It automatically detects high-conviction buying patterns, analyzes temporal convergence, ranks signals using composite scoring, and delivers ONLY the top 3 strongest signals daily via Telegram and email.

**Key Innovation**: Unlike traditional snapshot-based systems ("who bought today?"), InvestorAI tracks **temporal convergence patterns** across 30-day windows, detecting when different actor types buy the same stock in sequence (e.g., Congressman Day 1 → Insider Day 3 → Fund Day 7), then ranks these patterns to report only the absolute strongest signals.

---

## 🧠 Complete Algorithm Logic Flow (Step-by-Step)

### PHASE 1: DATA COLLECTION & INGESTION

#### Step 1.1: Corporate Insider Data (OpenInsider.com)
**Execution**: `fetch_openinsider_last_week()` + `store_openinsider_trades()`

**Process**:
1. Send HTTP GET request to `https://www.openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=7&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1`
2. Parse HTML tables using `pandas.read_html()` (fast) with BeautifulSoup fallback
3. Extract columns: Ticker, Insider Name, Title, Transaction Type (P=Purchase, S=Sale), Value, Shares, Date, Ownership %
4. Store in `openinsider_trades` table (SQLite with WAL mode for concurrency)
5. Return DataFrame of trades from last 7 days

**Database Schema** (openinsider_trades):
```sql
CREATE TABLE openinsider_trades (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    company_name TEXT,
    insider_name TEXT NOT NULL,
    insider_title TEXT,
    trade_type TEXT,  -- 'P' (purchase) or 'S' (sale)
    trade_date TEXT,
    value REAL,
    qty INTEGER,
    owned INTEGER,
    delta_own REAL,
    price REAL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(ticker, trade_date)
);
```

**Data Deduplication**: Check for existing (ticker, insider_name, trade_date, value) combinations before inserting.

**Output**: DataFrame with ~100-200 trades, stored in database for signal detection.

---

#### Step 1.2: Congressional Trading Data (CapitolTrades.com)
**Execution**: `scrape_all_congressional_trades_to_db()` (if `USE_CAPITOL_TRADES=true`)

**Process**:
1. Launch Selenium WebDriver (Chrome headless mode) to handle JavaScript rendering
2. Navigate to `https://www.capitoltrades.com/trades?per_page=96`
3. Wait for dynamic content load (WebDriverWait for table presence)
4. Extract trade cards using BeautifulSoup: Politician Name, Party, Chamber, State, Ticker, Trade Type (BUY/SELL), Size Range ($1K-$15K, $15K-$50K, $50K-$100K, $100K-$250K, etc.), Traded Date, Published Date
5. Paginate through last 7 days of data (~5-10 pages)
6. Store in `congressional_trades` table
7. Close Selenium driver

**Database Schema** (congressional_trades):
```sql
CREATE TABLE congressional_trades (
    id INTEGER PRIMARY KEY,
    politician_name TEXT NOT NULL,
    party TEXT,  -- 'Democratic', 'Republican', 'Independent'
    chamber TEXT,  -- 'Senate' or 'House'
    state TEXT,
    ticker TEXT NOT NULL,
    trade_type TEXT,  -- 'BUY' or 'SELL'
    size_range TEXT,  -- '$100,000 - $250,000', etc.
    traded_date TEXT,
    published_date TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(ticker, politician_name, published_date)
);
```

**Elite Filter** (Applied later during detection):
Only these 15 proven traders trigger signals:
- Nancy Pelosi, Josh Gottheimer, Ro Khanna, Michael McCaul, Tommy Tuberville
- Markwayne Mullin, Dan Crenshaw, Brian Higgins, Richard Blumenthal
- Debbie Wasserman Schultz, Tom Kean Jr, Gil Cisneros, Cleo Fields
- Marjorie Taylor Greene, Lisa McClain

**Output**: ~50-100 Congressional trades stored in database, ready for Elite filtering.

---

#### Step 1.3: Superinvestor Holdings (Dataroma.com)
**Execution**: `scrape_all_superinvestors()` from `dataroma_scraper.py` (optional, run weekly/monthly)

**Process**:
1. For each of 10 elite managers, send GET request to `https://www.dataroma.com/m/holdings.php?m={manager_code}`
2. Add User-Agent headers to bypass 406 bot blocking
3. Parse HTML with BeautifulSoup, find holdings table (try multiple IDs: 'grid', 'holdings', 'portfolio' as fallback)
4. Extract: Ticker, Company Name, Portfolio %, Shares Held, Value (USD), Quarter
5. Use `pandas.read_html()` to parse table rows
6. Store in `dataroma_holdings` table

**Elite Superinvestors Tracked**:
- BRK: Warren Buffett - Berkshire Hathaway
- BAM: Bill Ackman - Pershing Square
- BG: Seth Klarman - Baupost Group
- APPALOOSA: David Tepper - Appaloosa
- SOLO: Stanley Druckenmiller - Duquesne Family Office
- THIRD: Dan Loeb - Third Point
- LOEWS: Allan Mecham - Arlington Value
- OAKMARK: Bill Nygren - Oakmark Funds
- PRIMECAP: PRIMECAP Management
- TWEEDY: Tweedy Browne

**Database Schema** (dataroma_holdings):
```sql
CREATE TABLE dataroma_holdings (
    id INTEGER PRIMARY KEY,
    manager_code TEXT NOT NULL,
    manager_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    company_name TEXT,
    portfolio_pct REAL,
    shares_held INTEGER,
    value_usd REAL,
    quarter TEXT,
    last_updated TEXT,
    INDEX(ticker, manager_code)
);
```

**Output**: ~200-400 holdings across 10 managers (Berkshire working, others need HTML refinement).

---

### PHASE 2: SIGNAL DETECTION (9 TYPES)

#### Step 2.1: Load Data for Detection
**Execution**: `load_openinsider_trades_from_db(lookback_days=7)`

**Process**:
1. Query `openinsider_trades` table: `SELECT * FROM openinsider_trades WHERE trade_date >= date('now', '-7 days')`
2. Load into pandas DataFrame for vectorized analysis
3. Sort by ticker, trade_date for pattern detection

**Output**: DataFrame with ~500-1000 trades from last 7 days.

---

#### Step 2.2: Detect Corporate Insider Signals
**Execution**: `detect_signals(df)` calls multiple detection functions

**2.2.A: Cluster Buying** (`detect_cluster_buying()`)
- **Logic**: Group trades by ticker, filter to last 5 days, count distinct insiders, sum total value
- **Threshold**: 3+ insiders AND $500K+ total value
- **Algorithm**:
  ```python
  for ticker in trades_by_ticker:
      recent = trades[trades['days_ago'] <= 5]
      insiders = set(recent['Insider Name'])
      total_value = recent['Value ($)'].sum()
      
      if len(insiders) >= 3 and total_value >= 500000:
          yield ClusterBuySignal(ticker, insiders, recent, total_value)
  ```
- **Output**: List of InsiderAlert objects with signal_type="Cluster Buying"

**2.2.B: C-Suite Buy** (`detect_ceo_cfo_buy()`)
- **Logic**: Filter trades where Title contains 'CEO', 'CFO', 'COO', 'CHIEF'
- **Threshold**: $100K+ purchase value
- **Output**: InsiderAlert with signal_type="C-Suite Buy"

**2.2.C: Large Single Buy** (`detect_large_single_buy()`)
- **Logic**: Any insider purchase >= $500K
- **Output**: InsiderAlert with signal_type="Large Single Buy"

**2.2.D: Strategic Investor Buy** (`detect_strategic_investor_buy()`)
- **Logic**: Insider Name contains 'Corp', 'LLC', 'Holdings', 'Fund', 'Capital'
- **Significance**: Corporate entities buying = strategic investment/partnership signal
- **Output**: InsiderAlert with signal_type="Corporation Purchase"

**2.2.E: Bearish Cluster Selling** (`detect_bearish_cluster_selling()`)
- **Logic**: 3+ insiders selling within 5 days, $1M+ total
- **Output**: InsiderAlert with signal_type="Bearish Cluster Selling"

---

#### Step 2.3: Detect Elite Congressional Signals
**Execution**: `detect_congressional_cluster_buy()` + `detect_large_congressional_buy()`

**2.3.A: Elite Congressional Cluster**
- **Logic**: 
  1. Query `congressional_trades` table for BUYs in last 30 days
  2. Filter to Elite 15 politicians only (ignore all others)
  3. Group by ticker, count distinct Elite traders
  4. Require 2+ Elite traders buying same ticker
- **SQL**:
  ```sql
  SELECT ticker, COUNT(DISTINCT politician_name) as elite_count
  FROM congressional_trades
  WHERE trade_type = 'BUY'
    AND published_date >= date('now', '-30 days')
    AND (politician_name LIKE '%Nancy Pelosi%' OR politician_name LIKE '%Josh Gottheimer%' ...)
  GROUP BY ticker
  HAVING elite_count >= 2
  ```
- **Bipartisan Bonus**: If both Democratic and Republican parties present, signal_type = "Bipartisan Elite Congressional Cluster"
- **Output**: InsiderAlert with full timeline of Elite buys

**2.3.B: Elite Congressional Buy**
- **Logic**:
  1. Filter Elite trader buys with size_range >= '$100,000 - $250,000'
  2. Parse size ranges to midpoint values
  3. Require $100K+ estimated value
- **Output**: InsiderAlert with signal_type="Elite Congressional Buy"

---

#### Step 2.4: Detect Trinity Signals (Convergence)
**Execution**: `detect_trinity_signal_alerts()` (if `DATAROMA_AVAILABLE=True`)

**Process**:
1. Call `detect_trinity_signals()` from dataroma_scraper.py
2. SQL joins across three tables:
   ```sql
   -- Find tickers present in ALL three sources
   SELECT DISTINCT i.ticker
   FROM (SELECT DISTINCT ticker FROM openinsider_trades WHERE trade_type='P' AND trade_date >= date('now','-30 days')) AS i
   INNER JOIN (SELECT DISTINCT ticker FROM congressional_trades WHERE trade_type='BUY' AND published_date >= date('now','-30 days') AND [elite_filter]) AS c
     ON i.ticker = c.ticker
   INNER JOIN dataroma_holdings AS d
     ON i.ticker = d.ticker
   ```
3. For each convergent ticker, call `detect_temporal_convergence(ticker, lookback_days=30)`

**Temporal Convergence Analysis**:
```python
def detect_temporal_convergence(ticker, lookback_days=30):
    # Get all activity with dates
    congressional_buys = query_congressional_trades(ticker, last_30_days)
    insider_buys = query_insider_trades(ticker, last_30_days)
    superinvestor_holdings = query_dataroma_holdings(ticker)
    
    # Build timeline
    timeline = [
        ('Congressional', earliest_cong_date, count_cong),
        ('Corporate Insider', earliest_insider_date, count_insider),
        ('Superinvestor', latest_fund_date, count_funds)
    ]
    timeline.sort(by_date)
    
    # Calculate convergence score (1-10)
    score = 5  # Base for Trinity
    
    if sequence == ['Congressional', 'Corporate Insider', 'Superinvestor']:
        score += 3  # SEQUENTIAL (ideal pattern)
    
    if date_span <= 14 days:
        score += 2  # TIGHT window
    
    if bipartisan_congressional:
        score += 1  # Cross-party agreement
    
    return {
        'convergence_score': score,
        'pattern': 'SEQUENTIAL (Ideal)' | 'TIGHT' | 'CONCURRENT',
        'timeline': timeline,
        'window_days': date_span
    }
```

**Output**: InsiderAlert with signal_type="Trinity Signal", details include convergence_score, temporal_pattern, timeline.

---

### PHASE 3: DATA ENRICHMENT

**Execution**: `get_company_context(ticker)` called for each signal

**Process**:
1. Fetch from yfinance API: `yf.Ticker(ticker).info`
2. Extract:
   - Market Cap (classify: Small <$2B, Mid $2B-$10B, Large $10B-$100B, Mega >$100B)
   - Sector (Technology, Healthcare, Finance, etc.)
   - P/E Ratio, EPS, Revenue
   - Current Price, 52-week High/Low
   - 5-day change %, 1-month change %
3. Scrape Finviz.com for short interest %
4. Calculate distance from 52W high/low (buying at dip vs. peak indicator)
5. Query Congressional context: All recent Congressional trades for this ticker (last 30 days)

**Output**: Context dict added to alert for enrichment and scoring.

---

### PHASE 4: COMPOSITE SCORING & RANKING

**Execution**: `calculate_composite_signal_score(alert, context)`

**Multi-Factor Scoring Algorithm** (5-20 point range):

**Factor 1: Signal Type Hierarchy (0-10 points)**
```python
signal_type_scores = {
    'Trinity Signal': 10,                          # Highest conviction
    'Bipartisan Elite Congressional Cluster': 9.5,
    'Elite Congressional Cluster': 9,
    'Elite Congressional Buy': 8,
    'Cluster Buying': 7,
    'Corporation Purchase': 7,
    'C-Suite Buy': 6,
    'Large Single Buy': 5,
    'Strategic Investor Buy': 5,
    'Bearish Cluster Selling': 3
}
score += signal_type_scores.get(alert.signal_type, 4)
```

**Factor 2: Temporal Convergence Bonus (0-3 points)** (Trinity Signals only)
```python
if alert.signal_type == 'Trinity Signal':
    pattern = alert.details.get('temporal_pattern')
    
    if 'SEQUENTIAL (Ideal)' in pattern:
        score += 3  # Congress → Insider → Fund sequence
    elif 'TIGHT' in pattern:
        score += 2  # All within 14 days
    else:
        score += 1  # Concurrent within 30 days
```

**Factor 3: Dollar Value Score (0-3 points)**
```python
total_value = get_total_trade_value(alert)

if total_value >= 5_000_000:
    score += 3
elif total_value >= 1_000_000:
    score += 2
elif total_value >= 500_000:
    score += 1.5
elif total_value >= 100_000:
    score += 1
else:
    score += 0.5
```

**Factor 4: Insider Seniority Bonus (0-2 points)**
```python
titles = alert.trades['Title'].str.upper().tolist()

if any('CEO' in t or 'CFO' in t or 'COO' in t or 'CHIEF' in t for t in titles):
    score += 2  # Top executives
elif any('VP' in t or 'DIRECTOR' in t or 'PRESIDENT' in t for t in titles):
    score += 1  # Senior management
else:
    score += 0.5  # Other insiders
```

**Factor 5: Market Cap Multiplier (0.8-1.2x)**
```python
market_cap = context.get('market_cap', 0)

if market_cap < 2_000_000_000:  # <$2B
    score *= 1.2  # Small cap = higher impact potential
elif market_cap < 10_000_000_000:  # $2B-$10B
    score *= 1.1  # Mid cap
elif market_cap > 100_000_000_000:  # >$100B
    score *= 0.9  # Mega cap = harder to move
# else 1.0x (Large cap $10B-$100B)
```

**Factor 6: Short Interest Adjustment (-2 to +1)**
```python
short_pct = context.get('short_interest', 0)

if 5 <= short_pct < 15:
    score += 1  # Potential squeeze opportunity
elif short_pct > 30:
    score -= 2  # Very high risk
# else 0 (neutral)
```

**Factor 7: Bipartisan Bonus (0-1 points)**
```python
if 'Bipartisan' in alert.signal_type:
    score += 1  # Cross-party consensus = rare = bullish
```

**Final Score**: `round(score, 2)` → typically 5-20 range, higher = stronger signal

**Example Calculation**:
```
Alert: Trinity Signal, NVDA, $2M insider buys, Sequential pattern, 12-day window
  Signal Type (Trinity):         10.0
  Temporal (Sequential + Tight):  5.0  (+3 sequential, +2 tight)
  Dollar Value ($2M):             2.0
  Insider Seniority (C-Suite):    2.0
  Market Cap (Mega $2.8T):      × 0.9 = 17.1
  Short Interest (8%):           +1.0
  Bipartisan: No                  0.0
  ----------------------------------------
  TOTAL:                         18.1 points (TOP TIER)
```

---

### PHASE 5: TOP-1 SIGNAL FILTER (Highest Conviction Only)

**Execution**: `select_top_signals(alerts, top_n=1, enrich_context=True)`

**Process**:
1. If `len(alerts) <= TOP_SIGNALS_PER_DAY`, return all (no filtering needed)
2. Else:
   - Calculate composite score for each alert (with market context enrichment)
   - Create list of (score, alert) tuples
   - Sort by score descending: `scored_alerts.sort(key=lambda x: x[0], reverse=True)`
   - Log full ranking to console/logs:
     ```
     COMPOSITE SCORING RESULTS
     1. NVDA - Trinity Signal: 18.1 points ✅ SELECTED
     ---
     Filtered out 19 lower-scoring signals:
     2. AAPL - Cluster Buying: 16.8 points
     3. TSLA - Elite Congressional Buy: 14.2 points
     4. MSFT - Large Single Buy: 11.3 points
     5. GOOGL - Corporation Purchase: 10.8 points
     ...
     ```
   - Return top 1 alert: `[alert for _, alert in scored_alerts[:1]]`

**Output**: Exactly 1 InsiderAlert object (highest-scoring signal of the day).

**Rationale**: Reporting only the #1 signal eliminates noise and focuses on absolute highest conviction. Users get ONE clear actionable signal per day instead of 3.

---

### PHASE 6: ALERT GENERATION & DELIVERY

#### Step 6.1: Send Pre-Filter Summary Email
**Execution**: `send_signal_summary_email(all_alerts)` (before filtering)

**Purpose**: Show user ALL detected signals with scores to verify ranking algorithm accuracy.

**Email Format**:
```
Subject: [Insider Whisper] Signal Summary - 20 Detected

Total Signals Detected: 20
Top Signals Selected: Top 3

ALL SIGNALS RANKED BY COMPOSITE SCORE:

🏆 #1 - $NVDA - Trinity Signal
    Composite Score: 18.1 points
    Value: $2,000,000
    Status: ✅ SELECTED FOR REPORTING

🥈 #2 - $AAPL - Cluster Buying
    Composite Score: 16.8 points
    Value: $3,500,000
    Status: ✅ SELECTED FOR REPORTING

🥉 #3 - $TSLA - Elite Congressional Buy
    Composite Score: 14.2 points
    Value: $250,000
    Status: ✅ SELECTED FOR REPORTING

#4 - $MSFT - Large Single Buy
    Composite Score: 11.3 points
    Value: $750,000
    Status: ❌ FILTERED OUT

[... remaining 16 signals ...]

Next Step: The top 3 signals will be sent in separate detailed alert emails.
```

**Output**: Single email with full ranking for audit/verification.

---

#### Step 6.2: Send Individual Alert for Top 1
**Execution**: `process_alerts(top_1_alert)` → `send_telegram_alert()` + `send_email_alert()`

**For The Top Signal**:
1. **Deduplication Check**: `is_alert_already_sent(alert_id)` → skip if sent in last 30 days
   - Alert ID format: `{signal_type}_{ticker}_{insiders}_{dates}` (e.g., "C-Suite_NVDA_JensenHuang_17/01")
   - Prevents repeating same signal day after day when scanning last 7 days
   - Example: If "ACVA C-Suite Buy" sent today (Jan 17), won't send again until Feb 16 (30 days)
   - Even if same insider keeps buying, signal is blocked for 30 days
2. Format Telegram message (rich Markdown):
   ```
   🚨 Trinity Signal

   $NVDA - NVIDIA Corporation
   Technology | $2.8T Market Cap

   📊 SIGNAL DETAILS
   Convergence Score: 9/10 (SEQUENTIAL pattern)
   Timeline:
     • 2026-01-10: Congressional (2 Elite traders buy)
     • 2026-01-13: Corporate Insider (3 executives buy $2M total)
     • 2026-01-17: Superinvestor (Warren Buffett adds position)

   👥 CORPORATE INSIDERS
   • CFO - $1.2M (+1.5%)
   • VP Operations - $500K (+0.8%)
   • VP Engineering - $300K (+0.5%)

   🏛️ ELITE CONGRESSIONAL
   • Nancy Pelosi (D) - $250K-$500K
   • Josh Gottheimer (D) - $100K-$250K

   💼 SUPERINVESTORS
   • Warren Buffett - Berkshire Hathaway

   💹 MARKET DATA
   Current: $485.20 (+2.3% today)
   5-day: +8.4% 📈
   1-month: +15.2% 📈
   52W: $385 - $505 (84% of high)

   ⭐⭐⭐⭐⭐ 5/5 Confidence
   STRONG BUY

   🧠 AI INSIGHT
   Trinity Signal with SEQUENTIAL pattern: Congress bought first (policy advantage),
   followed by corporate insiders (material non-public information), confirmed by
   legendary superinvestor Warren Buffett. This tri-source convergence within 7 days
   represents highest conviction signal.

   [View on OpenInsider]
   ```

3. Send Telegram alert to configured chat_id
4. Send HTML email alert with same content (formatted as table)
5. Mark as sent: `mark_alert_as_sent(alert_id, ticker, signal_type)` → insert into `sent_alerts` table with `expires_at = now() + 30 days`

**Output**: 1 detailed alert delivered via Telegram + Email (only the absolute highest-conviction signal).

---

#### Step 6.3: Deduplication & State Management (Prevents Repeated Signals)

**Database Table** (sent_alerts):
```sql
CREATE TABLE sent_alerts (
    id INTEGER PRIMARY KEY,
    alert_id TEXT UNIQUE,
    ticker TEXT,
    signal_type TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    INDEX(ticker, signal_type, expires_at)
);
```

**Deduplication Logic** (Prevents Same Signal Repeating Daily):
```sql
SELECT 1 FROM sent_alerts
WHERE alert_id = ?
  AND expires_at > datetime('now')
LIMIT 1
```

**Why This Matters**:
- System scans last 7 days of trades on each run
- Without deduplication, same insider buy would trigger alert every day for 7 days
- Alert ID uniquely identifies: signal type + ticker + insiders + dates
- Once sent, blocked for 30 days even if insider keeps buying
- Example: "ACVA C-Suite Buy" (George Chamoun $125K on Jan 12) sent Jan 17 → won't send again until Feb 16

**Cleanup**: `cleanup_expired_alerts()` deletes rows where `expires_at < now()` (runs daily to keep database clean).

---

### PHASE 7: EXECUTION SUMMARY & LOGGING

**Final Output** (Console/Logs):
```
============================================================
CHECK COMPLETED SUCCESSFULLY
============================================================

DATA COLLECTION:
- OpenInsider: 156 trades scraped, 12 new stored
- Congressional: 67 trades scraped, 0 new (all duplicates)
- Dataroma: 41 holdings (Berkshire), 0 Trinity Signals found

SIGNAL DETECTION:
- Total signals detected: 20
- Cluster Buying: 1
- C-Suite Buy: 2
- Large Single Buy: 9
- Corporation Purchase: 6
- Elite Congressional Buy: 2

COMPOSITE SCORING & FILTERING:
- Top 3 selected from 20 signals
- Composite scores: 18.1, 16.8, 14.2 points
- Filtered out: 17 lower-scoring signals

ALERT DELIVERY:
- Pre-filter summary email: ✅ Sent (20 signals)
- Signal #1 (NVDA Trinity): ✅ Sent
- Signal #2 (AAPL Cluster): ✅ Sent
- Signal #3 (TSLA Elite Cong): ✅ Sent

Total runtime: 142 seconds
============================================================
```

---

```
┌─────────────────┐
│  Data Sources   │
│  - OpenInsider  │──────┐
│  - CapitolTrades│      │
│  - Dataroma     │      │
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
                   │  (9 types)  │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │  Temporal   │
                   │ Correlation │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Enrichment  │
                   │ (Price, AI, │
                   │  Context)   │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Composite   │
                   │   Scoring   │
                   │  (Top 3)    │
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

**Superinvestor Holdings (Dataroma.com)**
- Scrapes quarterly 13F filings from elite fund managers (FREE - no API required)
- Tracks: Warren Buffett (Berkshire), Bill Ackman (Pershing), Seth Klarman (Baupost), David Tepper (Appaloosa), Stanley Druckenmiller, Dan Loeb (Third Point), and 4 others
- Extracts: Ticker, Portfolio %, Shares Held, Value, Quarter
- Stores in `dataroma_holdings` table
- Updates: Quarterly (13F filings released 45 days after quarter end)

### 2. Signal Detection (Pattern Recognition)

The system implements **8 distinct signal types** across three categories (Bearish Cluster Selling removed - focus on BUY opportunities only):

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

#### Congressional Signals (Elite Filter)

The system tracks **only proven high-performance politicians** to eliminate noise. Party affiliation is irrelevant for individual trades - a smart trade is a smart trade. Party only matters for "Bipartisan Cluster" signals (extra conviction when both D and R buy same stock).

**Elite Watchlist (Top 15 Traders):**
- Nancy Pelosi, Josh Gottheimer, Ro Khanna, Michael McCaul, Tommy Tuberville
- Markwayne Mullin, Dan Crenshaw, Brian Higgins, Richard Blumenthal
- Debbie Wasserman Schultz, Tom Kean Jr, Gil Cisneros, Cleo Fields
- Marjorie Taylor Greene, Lisa McClain

**E. Elite Congressional Buy** ⭐⭐⭐⭐⭐
- **Logic**: Elite trader purchases $100K+ of a stock
- **Filter**: ONLY tracks the 15 proven traders above (ignores all others)
- **Size ranges tracked**: $100K-$250K, $250K-$500K, $500K-$1M, $1M-$5M, $5M+
- **Why it matters**: These politicians have demonstrated consistent outperformance and significant capital at risk
- **Example**: Nancy Pelosi buys $250K-$500K of NVDA → High-conviction signal

**F. Elite Congressional Cluster** ⭐⭐⭐⭐⭐
- **Logic**: 2+ elite traders buy same ticker within 30 days, any trade size
- **Bonus**: "Bipartisan Elite Cluster" if both D and R involved (rare = extremely bullish)
- **Why it matters**: Multiple proven traders converging on same opportunity = strong consensus
- **Example**: Josh Gottheimer (D) + Michael McCaul (R) both buy GOOGL → Bipartisan cluster

**H. Tracked Ticker Activity** ⭐⭐⭐
- **Logic**: Any insider activity on user-specified tickers
- **Configuration**: Users track tickers via Telegram bot (`@bot $AAPL`)
- **Why it matters**: Personalized monitoring for positions you care about
- **Example**: You track MSFT, any insider buy/sell triggers @mention in Telegram

**Note**: Bearish Cluster Selling signal has been removed - system focuses exclusively on BUY opportunities and high-conviction signals.

#### Trinity Signals (Superinvestor Convergence) 🔺

**I. Trinity Signal** ⭐⭐⭐⭐⭐⭐
- **Logic**: Corporate Insider + Elite Congressional buying SAME ticker that Superinvestor currently holds (within 30 days)
- **Data Source**: Dataroma.com 13F filings (quarterly holdings of elite fund managers - shows current positions, NOT recent buys)
- **Temporal Analysis**: Tracks when insiders/Congress buy stocks that legendary investors already own
- **Why it matters**: HIGHEST CONVICTION - when insiders and politicians buy what Warren Buffett/Bill Ackman already hold
- **Important**: Superinvestor "hold" means they currently own the stock (from latest 13F filing), NOT that they recently bought it. 13F filings are quarterly snapshots of what funds own.
- **Scoring**: Composite score (1-10) based on temporal pattern:
  - **SEQUENTIAL (Ideal)**: Congress buys → Insider buys → Fund already holds (+3 points)
  - **TIGHT**: Both Congressional + Insider buys within 14 days, Fund holds (+2 points)
  - **CONCURRENT**: Congressional + Insider buying same month, Fund holds (+1 point)
- **Example**: Warren Buffett owns NVDA (from Q4 13F filing) → Nancy Pelosi buys NVDA $250K → 3 days later, NVDA CFO buys $1M
- **Superinvestors tracked**: Warren Buffett (Berkshire Hathaway), Bill Ackman (Pershing Square), Seth Klarman (Baupost), David Tepper (Appaloosa), Stanley Druckenmiller, Dan Loeb (Third Point), and 4 others

### 3. Temporal Correlation Detection

**The Innovation**: Unlike traditional systems that only check "who is buying today," InvestorAI tracks **temporal sequences** across 30-day windows.

**Key Question**: If a Congressman buys on Day 1, a corporate insider buys Day 3, and a hedge fund adds Day 7 - do we capture this?

**Answer**: YES! The system uses `detect_temporal_convergence()` to:
1. Query all three data sources (Congressional, Corporate Insider, Superinvestor) for each ticker
2. Build timeline sorted by date: `[(Congressional, 2026-01-10, 2 buyers), (Corporate Insider, 2026-01-13, 3 buyers), (Superinvestor, 2026-01-17, 1 holder)]`
3. Calculate pattern score:
   - **Sequential pattern** (ideal): Congress → Insider → Fund = +3 points
   - **Reverse pattern** (less bullish): Fund → Insider → Congress = -1 point
   - **Tight window** (<14 days) = +2 points
   - **Bipartisan Congressional** = +1 point
4. Return convergence score (1-10) and timeline for alert formatting

**Why This Matters**:
- Traditional systems: "Show me who bought today" (snapshot)
- InvestorAI: "Show me convergent buying patterns over 30 days" (temporal intelligence)
- Captures leading indicators: Congress often trades BEFORE corporate insiders (policy advantage)

### 4. Data Enrichment

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
- Elite Congressional buy ($100K+)
- Elite Congressional cluster (2+ Elite traders)

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

### 5. Advanced Composite Scoring & Signal Selection

**The Challenge**: 20+ signals per day is information overload. Users need ONLY the strongest signals.

**Solution**: Multi-factor composite scoring algorithm ranks all signals, filters to **top 3 per day**.

**Composite Score Components** (5-20 point range):

**1. Signal Type Hierarchy (0-10 points)**
```
Trinity Signal:                   10
Elite Congressional Cluster:       9
Elite Congressional Buy:           8
Cluster Buying:                    7
Corporation Purchase:              7
C-Suite Buy:                       6
Large Single Buy:                  5
Strategic Investor:                5
Bearish Selling:                   3
```

**2. Temporal Convergence Bonus (0-3 points)**
- Sequential pattern (Congress → Insider → Fund): +3
- Tight window (<14 days all buying): +2
- Concurrent buying: +1

**3. Dollar Value Score (0-3 points)**
- $5M+: 3
- $1M-$5M: 2
- $500K-$1M: 1.5
- $100K-$500K: 1

**4. Insider Seniority Bonus (0-2 points)**
- CEO/CFO/COO: +2
- VP/Director: +1
- Other: +0.5

**5. Market Cap Multiplier (0.8-1.2x)**
- Small cap (<$2B): 1.2x (higher impact potential)
- Mid cap ($2B-$10B): 1.1x
- Large cap ($10B-$100B): 1.0x
- Mega cap (>$100B): 0.9x (harder to move)

**6. Short Interest Adjustment (-2 to +1)**
- <5%: 0 (neutral)
- 5-15%: +1 (squeeze potential)
- 15-30%: 0 (risky)
- >30%: -2 (very risky)

**7. Bipartisan Bonus (0-1 points)** *(Minor factor)*
- Bipartisan Congressional: +1

**Note**: The bipartisan bonus is minor (1 point max out of ~20 total score). Smart trades are smart regardless of party affiliation. This bonus only applies when BOTH Democrats AND Republicans buy the same stock within 30 days, which is relatively rare.

**Example Calculation**:
```
Alert: Trinity Signal, NVDA, $2M insider buys, Sequential pattern (14d window)
Score breakdown:
  Signal Type (Trinity):        10.0
  Temporal (Sequential + Tight): 5.0
  Dollar Value ($2M):            2.0
  Insider Seniority (C-Suite):   2.0
  Market Cap (Mega):           × 0.9
  Short Interest (8%):          +1.0
  -----------------------------------
  TOTAL:                        18.0 points (TOP TIER)
```

**Filtering Process**:
1. Detect all signals (e.g., 20 signals found)
2. Calculate composite score for each
3. Sort by score (descending)
4. Return top 3 highest-scoring signals
5. Log filtered signals for audit

**Configuration**: `TOP_SIGNALS_PER_DAY=1` in .env (set to 0 for unlimited, 1 = highest signal only)

### 6. Alert Delivery

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

3. **dataroma_holdings**
   - Stores superinvestor 13F holdings (quarterly)
   - Columns: manager_code, manager_name, ticker, company_name, portfolio_pct, shares_held, value_usd, quarter, last_updated
   - Indexes: ticker, manager_code, quarter
   - Source: Dataroma.com scraping

4. **alert_history**
   - Tracks sent alerts for deduplication
   - Columns: ticker, signal_type, sent_at, expires_at
   - Prevents re-sending same signal within 30 days

5. **tracked_tickers**
   - User-tracked tickers via Telegram bot
   - Columns: user_id, ticker, added_at
   - Enables personalized monitoring

---

## 🔧 Key Technologies

**Data Collection:**
- `requests` + `pandas` for OpenInsider scraping
- `requests` + `BeautifulSoup4` for Dataroma superinvestor holdings
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

4. Scrape Superinvestor Holdings (weekly/monthly)
   - scrape_all_superinvestors() from dataroma_scraper.py
   - Fetches 13F holdings for 10 elite fund managers
   - ~30-60 seconds (rate-limited to be respectful)

5. Detect Signals
   - detect_congressional_cluster_buy()
   - detect_large_congressional_buy()
   - detect_signals() for corporate signals
   - detect_trinity_signal_alerts() for convergence
   - Returns list of InsiderAlert objects (9 signal types)

6. Temporal Correlation Analysis
   - detect_temporal_convergence() for each Trinity Signal
   - Builds timeline of buys across 30-day window
   - Scores sequential patterns (Congress → Insider → Fund)

7. Enrich Signals
   - get_company_context() for each ticker
   - Fetch price, fundamentals, short interest
   - Add Congressional context

8. Composite Scoring & Top-N Filter
   - calculate_composite_signal_score() for each signal
   - Multi-factor scoring (signal type, temporal, value, seniority, market cap, short interest)
   - select_top_signals() filters to top 3 highest-scoring
   - **KEY FEATURE**: Reduces 20+ signals → 3 best per day

9. Generate AI Insights
   - generate_ai_insight() for each top signal
   - BUY/SELL/HOLD recommendation with reasoning

10. Check De-duplication
   - is_alert_already_sent() checks alert_history
   - Skip if same ticker+signal sent in last 30 days

11. Send Alerts
   - send_telegram_alert() with rich markdown
   - send_email_alert() as backup
   - @mention users tracking specific tickers

12. Update Database
   - mark_alert_as_sent() logs to alert_history
   - cleanup_expired_alerts() removes old records
```

---

## ⚡ Live Detection Results (Jan 17, 2026)

**Congressional Data Status:**
- ✅ Scraper running successfully  
- 📊 Last 30 days: 12 total trades, 7 buys
- 🎯 Elite Filter Results: **4 Elite Congressional Buy signals** detected
- 🎄 No new trades in last 7 days (holiday period)

**Why Congressional alerts showed "0":**
The system was working correctly - there simply were no new Congressional trades filed in the last 7 days. Politicians were on holiday break (Dec 18 → Jan 17 = 30 day gap). The Elite filter successfully reduced noise by focusing only on the Top 15 proven traders.

**Today's Full Detection:**
- Cluster Buying: 2
- C-Suite Buy: 5  
- Large Single Buy: 69
- Corporation Purchase: 45
- Elite Congressional Buy: 1
- **Total: 122 signals detected → 56 after deduplication**
- **Top 1 filter applied: Highest-scoring signal selected for reporting**

**Note**: System now filters to **TOP 1 signal per day** (not 3). Composite scoring ranks all signals, reports only #1 highest-conviction opportunity. All 3 top signals in this run (AKTS, ASST, SPT) were already sent within last 30 days, so no new signals delivered. Deduplication working correctly.

---

## 🎯 Configuration & Customization

```env
# Lookback Windows
LOOKBACK_DAYS=7                          # Corporate insider lookback window
CONGRESSIONAL_LOOKBACK_DAYS=30           # Congressional cluster lookback

# Signal Thresholds
MIN_CLUSTER_INSIDERS=3                   # Minimum insiders for cluster
MIN_CLUSTER_BUY_VALUE=500000             # $500K minimum cluster value
MIN_CEO_CFO_BUY=100000                   # $100K minimum C-suite buy
MIN_LARGE_BUY=500000                     # $500K minimum large buy
MIN_CONGRESSIONAL_CLUSTER=2              # Minimum Elite politicians for cluster
MIN_CONGRESSIONAL_BUY_SIZE=100000        # $100K minimum Elite Congressional buy

# Advanced Signal Selection (NEW)
TOP_SIGNALS_PER_DAY=1                    # Maximum signals to report (0=unlimited, 1=highest only)
                                         # Composite scoring ranks all signals, sends ONLY #1

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
├── requirements.txt               # Main detection engine (2000+ lines)
├── run_daily_alerts.py           # Daily automation runner
├── telegram_tracker_polling.py   # Ticker tracking bot (GitHub Actions)
├── requirements.txt              # Python dependencies
├── .env                          # Configuration (DO NOT COMMIT)
├── .env.example                  # Template for .env
├── README.md                     # User guide
├── ALGORITHM_OVERVIEW.md         # This file - technical deep dive
├── data/
│   └── alphaWhisperer.db        # SQLite database
├── logs/
│   └── *.log                    # Application logs
└── .github/
    └── workflows/               # GitHub Actions automationders=3, days=5, min_value=500000):
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
