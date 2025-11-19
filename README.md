# Insider Trading Alert System

A production-ready Python script that monitors insider trading activity from OpenInsider.com and sends email alerts when high-conviction signals are detected.

## Features

- **Real-time monitoring** of insider Form 4 filings from OpenInsider
- **7 powerful signals** for detecting significant insider activity
- **Email alerts** with detailed trade information and links
- **Smart de-duplication** to avoid repeat alerts
- **Robust parsing** with fallback mechanisms for HTML changes
- **Configurable thresholds** for all detection rules
- **Run modes**: single execution or continuous monitoring

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

### 3. Run the Script

```bash
# Single execution
python insider_alerts.py --once

# Continuous monitoring (every 30 minutes)
python insider_alerts.py --loop

# Custom interval (every 60 minutes)
python insider_alerts.py --loop --interval-minutes 60

# Dry run (no emails sent, logs only)
python insider_alerts.py --once --dry-run

# Verbose logging
python insider_alerts.py --once --verbose

# Process trades since specific date
python insider_alerts.py --once --since 2025-11-01
```

## Detection Signals

### 1. Cluster Buying
**Trigger**: ≥3 insiders from the same ticker buy within 5 days, total value ≥$300K

**Why it matters**: Multiple insiders buying simultaneously suggests strong conviction about the company's prospects.

### 2. CEO/CFO Buy
**Trigger**: CEO or CFO buys ≥$100K

**Why it matters**: Top executives have the best visibility into company performance and future prospects.

### 3. Large Single Buy
**Trigger**: Any insider buys ≥$250K

**Why it matters**: Significant dollar amounts indicate strong personal conviction.

### 4. First Buy in 12 Months
**Trigger**: Insider's first purchase in 365 days, ≥$50K

**Why it matters**: Breaking a long period of inactivity suggests a major inflection point.

### 5. Buy Near 52-Week Low
**Trigger**: Insider buys when price ≤110% of 52-week low

**Why it matters**: Insiders buying at depressed prices may signal a bottom.

### 6. Sector Cluster (Optional)
**Trigger**: ≥5 insiders across 3+ tickers in same sector, combined ≥$1M within 5 days

**Why it matters**: Broad sector buying may indicate industry-wide positive developments.

### 7. Bearish Cluster Selling (Optional)
**Trigger**: ≥3 insiders from same ticker sell within 5 days, total ≥$1M

**Why it matters**: Coordinated selling by multiple insiders may signal concerns.

## Configuration

All thresholds are configurable in `.env`:

```env
LOOKBACK_DAYS=7              # Days of history to analyze
CLUSTER_DAYS=5               # Window for cluster detection
MIN_LARGE_BUY=250000         # Minimum for large buy signal
MIN_CEO_CFO_BUY=100000       # Minimum for CEO/CFO buy
MIN_CLUSTER_BUY_VALUE=300000 # Minimum total for cluster buy
MIN_FIRST_BUY_12M=50000      # Minimum for first buy signal
MIN_SECTOR_CLUSTER_VALUE=1000000  # Minimum for sector cluster
MIN_BEARISH_CLUSTER_VALUE=1000000 # Minimum for bearish cluster
```

## Troubleshooting

### Gmail Authentication Errors

**Problem**: "Username and Password not accepted"

**Solution**: 
1. Enable 2-factor authentication on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Use the app password in `SMTP_PASS`, not your regular password

### No Alerts Being Sent

Check:
1. Verify `.env` configuration
2. Run with `--verbose --dry-run` to see detected signals
3. Check `logs/insider_alerts.log` for errors
4. Ensure signals meet threshold requirements

## License

MIT License

