# Signal Detection Documentation

This document describes all insider trading signal detection logic implemented in `insider_alerts.py`.

## Overview

The system monitors two data sources:
1. **OpenInsider.com** - Corporate insider trades (CEOs, CFOs, directors, etc.)
2. **CapitolTrades.com** - Congressional stock trades (Senate & House members)

Signals are detected from trades within a **7-day lookback window** (or 30 days for Congressional clusters).

---

## Corporate Insider Signals

### 1. Cluster Buying
**Criteria:**
- **Minimum insiders:** 3+ distinct insiders buying same ticker
- **Minimum total value:** $500,000 combined
- **Lookback window:** 7 days (trade_date)
- **Excluded transactions:** Exercise of options (automatic, not discretionary)

**Why it matters:**
Multiple insiders buying at the same time suggests strong confidence in company prospects. They have access to non-public information about upcoming products, earnings, contracts, etc.

**Example:**
- PROP: 3 insiders bought $2.98M total (Nov 14, 2025)
  - VP & CFO: $1.76M
  - VP: $665K
  - VP: $561K

---

### 2. C-Suite Buy
**Criteria:**
- **Title:** CEO, CFO, or COO (Chief Executive Officer, Chief Financial Officer, Chief Operating Officer)
- **Minimum value:** $100,000
- **Lookback window:** 7 days (trade_date)
- **Excluded transactions:** Exercise of options

**Why it matters:**
Top executives have the most comprehensive view of company performance. Large purchases by CEO/CFO/COO are strong bullish signals.

**Example:**
- XYZ: CEO bought $250K (discretionary purchase, not options exercise)

---

### 3. Large Single Buy
**Criteria:**
- **Any insider title** (CEO, Director, VP, etc.)
- **Minimum value:** $500,000
- **Lookback window:** 7 days (trade_date)
- **Excluded transactions:** Exercise of options

**Why it matters:**
Very large purchases indicate exceptional confidence. Insiders wouldn't risk substantial capital unless they expect significant upside.

**Example:**
- ABC: Director bought $750K worth of shares

---

### 4. Corporation Purchase
**Criteria:**
- **Buyer type:** Corporation/institutional entity (not individual insider)
- **Lookback window:** 7 days (trade_date)
- **Minimum value:** None (any amount triggers signal)

**Detected entities:**
- "Corp", "Corporation", "Inc.", "LLC", "LP", "Ltd"
- "Trust", "Foundation", "Fund"
- "Holdings", "Partners", "Capital", "Ventures", "Investments"
- "Family Office", "Management Company"

**Why it matters:**
Corporate entities buying shares often indicates strategic investment or insider knowledge through board representation. These are typically very large, calculated purchases.

**Example:**
- DEF: XYZ Capital LLC purchased $5M worth of shares

---

## Congressional Signals

### 5. Congressional Cluster Buy
**Criteria:**
- **Minimum politicians:** 3+ distinct politicians buying same ticker
- **Lookback window:** 30 days (published_date, not traded_date)
- **Trade type:** BUY only
- **Bipartisan bonus:** Extra attention if both Democrats and Republicans buying

**Why it matters:**
Multiple politicians buying the same stock suggests:
- Upcoming policy/regulatory changes favorable to the company
- Information from committee briefings or hearings
- Bipartisan agreement makes it even more credible

**Recent examples:**
- **GOOGL (Alphabet):** 6 politicians (Nov 2025)
  - Julie Johnson (D)
  - Ro Khanna (D)
  - Cleo Fields (D)
  - Michael McCaul (R)
  - Gil Cisneros (D)
  - Lisa McClain (R)

- **AAPL (Apple):** 4 politicians (Nov 2025)
  - Ro Khanna (D)
  - Cleo Fields (D)
  - Gil Cisneros (D)
  - Lisa McClain (R)

- **TSM (Taiwan Semiconductor):** 4 politicians (Nov 2025)
  - Ro Khanna (D)
  - Cleo Fields (D)
  - Jared Moskowitz (D)
  - Gil Cisneros (D)

---

### 6. Large Congressional Buy
**Criteria:**
- **Minimum size:** $100,000+
- **Lookback window:** 7 days (published_date)
- **Trade type:** BUY only
- **Size ranges detected:** 100K–250K, 250K–500K, 500K–1M, 1M–5M, 5M–25M, >25M

**Why it matters:**
Large individual purchases by politicians signal:
- High conviction in specific stock
- Insider knowledge from committee work or industry contacts
- Willingness to risk significant capital on specific bet

**Recent examples:**
- **Markwayne Mullin (R) - MSFT:** $250K–$500K (Published Nov 21, 2025)
- **Cleo Fields (D) - NFLX:** $100K–$250K (Published Nov 20, 2025)
- **Kevin Hern (R) - RY (Royal Bank of Canada):** $1M–$5M (Published Nov 17, 2025)

---

## Tracked Ticker Activity

### 7. Custom Ticker Tracking
**Criteria:**
- **Tickers:** User-defined list in `tracked_tickers` table
- **Trade type:** Any OpenInsider trade (P, S, exercise, etc.)
- **Lookback window:** 7 days (trade_date)
- **Minimum value:** None (all trades reported)

**Why it matters:**
Allows monitoring specific stocks of interest. All insider activity is reported regardless of signal strength, providing early awareness of insider behavior.

**Configuration:**
Tickers stored in SQLite database table `tracked_tickers`:
```sql
CREATE TABLE tracked_tickers (
    ticker TEXT PRIMARY KEY,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example notifications:**
- "AAPL: 3 trades detected in last 7 days (2 buys, 1 sale)"
- Links to OpenInsider page for detailed analysis

---

## Detection Workflow

1. **Scraping (every 12 hours):**
   - OpenInsider: 7-day screener with pagination (stops after 50 consecutive duplicates)
   - CapitolTrades: 30-day Congressional trades with pagination

2. **Storage:**
   - All trades stored in SQLite database (`alphaWhisperer.db`)
   - Duplicate detection via composite keys (ticker + insider + date + value)

3. **Signal Detection:**
   - Load ALL trades from database (not just newly scraped)
   - Run all signal detection functions on full dataset
   - Example: 958 trades analyzed → 139 signals detected

4. **Deduplication:**
   - Track sent alerts in `sent_alerts` table
   - Only send new signals (not sent in last 30 days)

5. **Prioritization:**
   - Top 3 signals sent (by value/confidence)
   - ALL tracked ticker activity sent (unlimited)

---

## Configuration

### Environment Variables
```bash
# Signal thresholds
MIN_CLUSTER_INSIDERS=3              # Cluster buying minimum
MIN_CLUSTER_VALUE=500000            # Cluster buying total value
MIN_CSUITE_VALUE=100000             # C-Suite buy minimum
MIN_LARGE_SINGLE_BUY=500000         # Large single buy minimum

# Lookback windows
LOOKBACK_DAYS=7                     # Corporate insider window
CONGRESSIONAL_LOOKBACK_DAYS=30      # Congressional cluster window

# Features
USE_CAPITOL_TRADES=true             # Enable Congressional signals
```

### Database Tables
- `openinsider_trades` - Corporate insider trades
- `congressional_trades` - Congressional stock trades
- `tracked_tickers` - User-defined ticker watchlist
- `sent_alerts` - Deduplication tracking

---

## Signal Confidence Levels

**Highest Confidence:**
1. Bipartisan Congressional Cluster (politics aside, they agree)
2. Cluster Buying with 5+ insiders
3. CEO purchase >$1M

**High Confidence:**
4. Congressional Cluster (3+ politicians)
5. Large Congressional Buy (>$250K)
6. C-Suite Buy (>$100K)
7. Cluster Buying (3+ insiders)

**Medium Confidence:**
8. Large Single Buy (>$500K)
9. Corporation Purchase (strategic investor)

**Monitoring:**
10. Tracked Ticker Activity (user-defined, informational)

---

## Future Enhancements

### Planned Features:
1. **Congressional committee tracking:** Match trades to relevant committee assignments
   - Example: Senator on Banking Committee buying bank stocks
   
2. **Historical performance tracking:** Track which politicians have best returns
   - Weight signals based on past success rate

3. **Options activity:** Add signals for large options purchases/sales
   - Current system excludes option exercises

4. **Sentiment analysis:** Detect bearish vs bullish patterns
   - Currently focused on bullish signals only

5. **Cluster selling:** Detect coordinated insider selling
   - Partially implemented, needs refinement

---

## Testing

### Manual Testing:
```bash
# Run once without sending emails
python run_daily_alerts.py --once

# Check detected signals
# Expected output:
# - Loaded: ~950+ trades from database
# - Signals: 100-150 total
# - Congressional: 10+ (if recent activity)
```

### Expected Results (November 2025):
- Cluster Buying: 10-15 signals
- C-Suite Buy: 10-15 signals
- Large Single Buy: 60-80 signals
- Corporation Purchase: 30-50 signals
- Congressional Cluster: 5-10 signals
- Large Congressional Buy: 1-3 signals

---

## Debugging

### Check Congressional Detection:
```bash
python check_congressional.py
```

Output:
- Total trades in database
- Recent trade counts (7/30 days)
- Cluster analysis
- Large purchase identification

### Check Scraping:
```bash
# Logs show scraping efficiency
INFO: Scraped page 1: 10 new, 796 duplicates (stopped - 50 consecutive duplicates)
```

### Check Database:
```bash
python -c "import sqlite3; conn = sqlite3.connect('data/alphaWhisperer.db'); 
cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM openinsider_trades'); 
print(f'Total trades: {cursor.fetchone()[0]}'); conn.close()"
```

---

## Change Log

### November 27, 2025 (Latest):
- **Added Congressional trades to tracked ticker monitoring**
  - Tracked tickers now check both OpenInsider AND Congressional tables
  - Lookback changed from "today only" to last 7 days for both sources
  - Example: ABBV showed 3 trades (OpenInsider + Congressional combined)

- **Added TEST mode for safe testing** (`--test` flag)
  - Prevents marking signals as sent during testing
  - Allows multiple test runs without "wasting" signal detection
  - Usage: `python run_daily_alerts.py --once --test`
  - Log shows: `[TEST MODE] Would mark alert as sent: ...`

### November 26, 2025:
- **Implemented 7-day paginated scraping** (replaced latest-100 approach)
- **Fixed database loading bug** (now loads all 958 trades for detection)
- **Replaced Congressional detection** with two new signals:
  - Congressional Cluster (3+ politicians, 30-day window)
  - Large Congressional Buy (>$100K, 7-day window)
- **Added duplicate detection** with 50 consecutive threshold for early termination

### Previous:
- Initial implementation with 5 signal types
- Congressional trades integration
- Tracked ticker functionality
