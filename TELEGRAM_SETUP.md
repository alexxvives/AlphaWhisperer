# Telegram Setup Guide

## Quick Setup (5 minutes)

### Step 1: Create Your Bot

1. Open Telegram app
2. Search for **@BotFather** (official Telegram bot)
3. Send `/start`
4. Send `/newbot`
5. Follow prompts:
   - Choose a name (e.g., "Insider Alerts Bot")
   - Choose a username (must end in 'bot', e.g., "alexx_insider_bot")
6. **Copy the bot token** (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Get Your Chat ID

1. Search for **@userinfobot** in Telegram
2. Send `/start`
3. **Copy your ID** (a number like: `123456789`)

### Step 3: Start Conversation with Your Bot

1. Search for your bot by username (the one you created)
2. Send `/start` to your bot
3. This activates the chat so bot can send you messages

### Step 4: Configure .env

Edit `.env` file:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
USE_TELEGRAM=true
```

### Step 5: Test It

```bash
python insider_alerts.py --once --dry-run
```

If you see "Would send Telegram" in logs, it's configured correctly!

Then try a real send:
```bash
python insider_alerts.py --once
```

## Troubleshooting

**"Unauthorized" error:**
- Make sure you sent `/start` to your bot first
- Check bot token is correct

**"Chat not found" error:**
- Make sure chat_id is correct
- Make sure you started a conversation with the bot

**No message received:**
- Check bot isn't blocked in Telegram
- Verify USE_TELEGRAM=true in .env

## Message Format

You'll receive messages like:

```
🚨 CEO/CFO Buy

AAPL - Apple Inc.

👤 Tim Cook (CEO)
💰 $150,250
📅 2025-11-15

📊 Trades:
• 11/15: Tim Cook - $150,250

🔗 View on OpenInsider
```

## Benefits

- ✅ **FREE** - No costs, unlimited messages
- ✅ **Fast** - Instant push notifications
- ✅ **Reliable** - 99.9% uptime
- ✅ **Convenient** - Works on phone, desktop, web
- ✅ **Private** - Only you receive messages
