# 🚀 Quick Start Guide

## ✅ What's Already Configured

Your email is **ready to go**:
- Email: `alexxvives@gmail.com`
- Password: Configured in `.env`
- You'll receive email alerts automatically

## 📱 Add Telegram (Optional, 5 Minutes)

Telegram is **FREE** and gives you instant phone notifications.

### Step 1: Create Bot (2 min)
1. Open Telegram
2. Search: `@BotFather`
3. Send: `/newbot`
4. Name your bot: "Insider Alerts"
5. Username: "alexx_insider_bot" (or any name ending in 'bot')
6. **Copy the token** (looks like: `1234567890:ABC...`)

### Step 2: Get Your Chat ID (1 min)
1. Search: `@userinfobot`
2. Send: `/start`
3. **Copy your ID** (a number like: `123456789`)

### Step 3: Start Your Bot (30 sec)
1. Search for your bot username
2. Send: `/start`

### Step 4: Update .env (1 min)
Edit `.env` file:
```env
TELEGRAM_BOT_TOKEN=paste_your_token_here
TELEGRAM_CHAT_ID=paste_your_id_here
USE_TELEGRAM=true
```

See `TELEGRAM_SETUP.md` for detailed instructions.

---

## 🎯 Run It Now

### Test Mode (No Real Alerts)
```bash
python insider_alerts.py --once --dry-run
```

### Send Real Alert (One-Time)
```bash
python insider_alerts.py --once
```

### Continuous Monitoring (Every 30 min)
```bash
python insider_alerts.py --loop --interval-minutes 30
```

---

## 🔧 Customize Thresholds

Edit `.env` to adjust what triggers alerts:

```env
MIN_CEO_CFO_BUY=100000        # CEO/CFO must buy $100K+
MIN_LARGE_BUY=250000          # Large buy threshold
MIN_CLUSTER_BUY_VALUE=300000  # Cluster must total $300K+
LOOKBACK_DAYS=7               # Check last 7 days
```

---

## 📊 What You'll Get

### Email Format:
- HTML with formatted table
- All trade details
- Links to OpenInsider
- Signal explanation

### Telegram Format:
- Clean, mobile-friendly
- Emojis for quick scanning
- Top 3 trades
- Instant push notification

---

## 🎬 Next Steps

1. **Test email now**: `python insider_alerts.py --once --dry-run`
2. **Set up Telegram** (optional): Follow steps above
3. **Schedule it**: 
   - Windows: Task Scheduler
   - Linux/Mac: crontab
   - Or use: `python insider_alerts.py --loop`

4. **Monitor for 24 hours** and adjust thresholds if needed

---

## 💡 Pro Tips

- Start with `--dry-run` to test without sending
- Use `--verbose` to see what's happening
- Check `logs/insider_alerts.log` for history
- Lower thresholds = more alerts (may be noisy)
- Higher thresholds = fewer, higher quality alerts

---

## ⚡ One Command to Start

```bash
# Test everything works
python insider_alerts.py --once --dry-run --verbose

# Then run for real
python insider_alerts.py --loop
```

That's it! You'll now get insider trading alerts via email (and Telegram if configured).
