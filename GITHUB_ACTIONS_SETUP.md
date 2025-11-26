# GitHub Actions Automation Setup

This guide walks you through setting up **fully automated insider trading alerts** using GitHub Actions. Your system will run in the cloud 24/7 without requiring your computer to be on.

## 🚀 What You'll Get

- ✅ **Daily alerts at 8:00 AM UTC** - Automatic congressional & insider trade detection
- ✅ **Telegram bot responses every 5 minutes** - Track tickers with `@bot $AAPL`
- ✅ **100% free** - Uses GitHub's 2,000 free minutes/month (you'll use ~300 max)
- ✅ **Cloud-based** - No local computer needed
- ✅ **Database persistence** - SQLite stored as GitHub Actions artifacts

---

## 📋 Prerequisites

1. **GitHub Account** - Free account at [github.com](https://github.com)
2. **Your code pushed to GitHub** - This repository must be on GitHub
3. **Telegram Bot Token** - From [@BotFather](https://t.me/BotFather)
4. **Email credentials** - Gmail app password (for sending alerts)

---

## 🔐 Step 1: Configure GitHub Secrets

GitHub Secrets store sensitive credentials securely.

### 1.1 Navigate to Repository Settings

1. Go to your GitHub repository
2. Click **Settings** tab (top right)
3. In left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

### 1.2 Add Required Secrets

Add these secrets one by one:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_CHAT_IDS` | Comma-separated chat IDs to notify | `123456789,987654321` |
| `EMAIL_USER` | Your Gmail address | `yourname@gmail.com` |
| `EMAIL_PASSWORD` | Gmail app password (NOT your login password) | `abcd efgh ijkl mnop` |
| `EMAIL_RECIPIENTS` | Comma-separated email recipients | `trader1@gmail.com,trader2@gmail.com` |

**Important Notes:**
- For `EMAIL_PASSWORD`, use a Gmail **App Password**, not your account password
  - Generate at: https://myaccount.google.com/apppasswords
  - Requires 2-Step Verification enabled
- Get `TELEGRAM_CHAT_IDS`:
  ```bash
  # Run locally to get your chat ID:
  python get_telegram_id.py
  ```

---

## 📁 Step 2: Verify Workflow Files

Your repository should have these files (already created):

```
.github/
  workflows/
    daily-alerts.yml      # Runs at 8am UTC daily
    telegram-bot.yml      # Runs every 5 minutes
telegram_tracker_polling.py  # Polling-based Telegram bot
```

### 2.1 Review Daily Alerts Workflow

File: `.github/workflows/daily-alerts.yml`

**Key features:**
- Runs at `8:00 AM UTC` every day
- Downloads database from previous run
- Installs Python dependencies
- Runs `run_daily_alerts.py`
- Uploads database for next run
- Can be manually triggered from GitHub UI

### 2.2 Review Telegram Bot Workflow

File: `.github/workflows/telegram-bot.yml`

**Key features:**
- Runs every `5 minutes`
- Uses `getUpdates` polling (not long-running)
- Processes `@bot` commands
- Stores `last_update_id` in database
- Avoids duplicate message processing

---

## 🚀 Step 3: Enable GitHub Actions

### 3.1 Check if Actions Are Enabled

1. Go to repository **Settings** → **Actions** → **General**
2. Under "Actions permissions":
   - Select **"Allow all actions and reusable workflows"**
3. Under "Workflow permissions":
   - Select **"Read and write permissions"**
   - Check **"Allow GitHub Actions to create and approve pull requests"**
4. Click **Save**

### 3.2 Commit and Push Your Code

```bash
# Make sure all workflow files are committed
git add .github/workflows/*.yml
git add telegram_tracker_polling.py
git commit -m "Add GitHub Actions automation workflows"
git push origin main
```

---

## ▶️ Step 4: Test Your Workflows

### 4.1 Manual Trigger (Recommended First Test)

1. Go to **Actions** tab in your GitHub repository
2. In left sidebar, click **"Daily Insider Alerts"**
3. Click **"Run workflow"** dropdown (top right)
4. Select branch `main`
5. Click **"Run workflow"**

**Expected behavior:**
- Workflow starts running (yellow dot)
- After 2-5 minutes, completes (green checkmark)
- Check your email/Telegram for test alerts
- Click on workflow run to see logs

### 4.2 Test Telegram Bot

1. In **Actions** tab, click **"Telegram Bot Polling"**
2. Click **"Run workflow"** and run it
3. Send message in Telegram: `@bot $AAPL`
4. Wait 30 seconds, run workflow again
5. Bot should respond to your message

**Note:** Bot responds within 5 minutes (next scheduled run) in production.

---

## 📊 Step 5: Monitor Your Automation

### 5.1 View Workflow Runs

1. Go to **Actions** tab
2. See all workflow runs (history)
3. Click on any run to see detailed logs
4. Download artifacts (logs, database) if needed

### 5.2 Check Workflow Status

**Daily Alerts:**
- Should run once per day at 8:00 AM UTC
- Duration: ~2-5 minutes
- Uploads database artifact after each run

**Telegram Bot:**
- Runs every 5 minutes
- Duration: ~10-30 seconds
- Only uploads logs if error occurs

### 5.3 Download Database (Optional)

To inspect your database locally:

1. Go to **Actions** tab
2. Click on most recent successful workflow
3. Scroll to **Artifacts** section
4. Download `database` artifact
5. Extract `congressional_trades.db`

---

## 🔧 Troubleshooting

### Workflow Fails Immediately

**Check:**
1. All secrets are configured correctly
2. Secret names match exactly (case-sensitive)
3. Workflow has read/write permissions

**View error logs:**
1. Click on failed workflow run
2. Click on red X step
3. Expand log output

### No Alerts Being Sent

**Possible causes:**
1. No new insider trades detected (normal)
2. Email credentials incorrect
3. Telegram token/chat IDs wrong

**Test with manual signal:**
```bash
# Locally test alert sending:
python send_sample_signals.py
```

### Telegram Bot Not Responding

**Check:**
1. Workflow running every 5 minutes (Actions tab)
2. Bot token is correct in secrets
3. Messages contain `@bot` mention
4. Last workflow run succeeded (green checkmark)

**Test polling script locally:**
```bash
python telegram_tracker_polling.py
```

### Database Not Persisting

**Symptoms:**
- Tracked tickers disappear
- Duplicate alerts sent

**Solution:**
1. Check artifact upload/download steps succeed
2. Artifact named exactly `database`
3. Path is `data/congressional_trades.db`

---

## 📈 Usage Limits & Costs

### GitHub Actions Free Tier

- **2,000 minutes/month** included (free)
- Linux runners: 1x multiplier

### Your Expected Usage

- **Daily Alerts:** ~3 min/day × 30 days = **90 min/month**
- **Telegram Bot:** ~0.5 min/run × 12 runs/hour × 24 hours × 30 days = **216 min/month**
- **Total:** ~**306 minutes/month** (well within free tier)

---

## 🎯 Daily Usage Workflow

### Morning Alerts (Automatic)

1. **8:00 AM UTC** - GitHub Actions runs daily workflow
2. Downloads latest database
3. Scrapes Capitol Trades & OpenInsider
4. Detects signals (Congressional Buy, Insider Cluster, etc.)
5. Sends email + Telegram alerts
6. Uploads updated database

### Telegram Bot (Continuous)

Every 5 minutes:
1. Checks for new Telegram messages
2. Processes `@bot` commands
3. Updates tracked tickers in database
4. Saves last processed update_id

### User Commands

- **Track ticker:** `@bot $AAPL`
- **Track multiple:** `@bot $AAPL, $TSLA, $NVDA`
- **Remove ticker:** `@bot remove $AAPL`
- **List tracked:** `@bot list`

---

## 🔄 Updating Your Code

When you modify code:

```bash
# Make changes locally
git add .
git commit -m "Update alert logic"
git push origin main
```

**Changes take effect:**
- Next scheduled workflow run
- Or manually trigger from Actions tab

---

## 🛠️ Advanced Configuration

### Change Schedule Times

Edit `.github/workflows/daily-alerts.yml`:

```yaml
on:
  schedule:
    # Change this cron expression
    - cron: '0 8 * * *'  # 8am UTC = 3am EST / 12am PST
```

**Cron format:** `minute hour day month weekday`

Examples:
- `0 13 * * *` - 1:00 PM UTC (8:00 AM EST)
- `0 14 * * 1-5` - 2:00 PM UTC, Monday-Friday only
- `30 9 * * *` - 9:30 AM UTC

### Change Telegram Polling Frequency

Edit `.github/workflows/telegram-bot.yml`:

```yaml
on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
    # - cron: '*/10 * * * *'  # Every 10 minutes
    # - cron: '*/15 * * * *'  # Every 15 minutes
```

**Note:** More frequent = more GitHub Actions minutes used

### Add More Secrets

For new integrations:

1. Add secret in GitHub Settings
2. Reference in workflow YAML:
   ```yaml
   env:
     MY_NEW_SECRET: ${{ secrets.MY_NEW_SECRET }}
   ```
3. Use in Python:
   ```python
   import os
   secret = os.getenv("MY_NEW_SECRET")
   ```

---

## 📝 Workflow Files Explained

### daily-alerts.yml

```yaml
name: Daily Insider Alerts

on:
  schedule:
    - cron: '0 8 * * *'  # 8am UTC daily
  workflow_dispatch:      # Allow manual trigger

jobs:
  run-alerts:
    runs-on: ubuntu-latest
    
    steps:
      # 1. Get code from repository
      - name: Checkout code
        uses: actions/checkout@v4
      
      # 2. Install Python 3.11
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      # 3. Download database from previous run
      - name: Download database artifact
        uses: dawidd6/action-download-artifact@v3
        with:
          name: database
          path: data/
          workflow_conclusion: success
          if_no_artifact_found: warn
        continue-on-error: true
      
      # 4. Install Python packages
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      # 5. Run alerts script
      - name: Run daily alerts
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_IDS: ${{ secrets.TELEGRAM_CHAT_IDS }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_RECIPIENTS: ${{ secrets.EMAIL_RECIPIENTS }}
        run: python run_daily_alerts.py --once
      
      # 6. Save database for next run
      - name: Upload database artifact
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: database
          path: data/congressional_trades.db
          retention-days: 90
          overwrite: true
```

### telegram-bot.yml

```yaml
name: Telegram Bot Polling

on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
  workflow_dispatch:

jobs:
  poll-telegram:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      # Download database (same as daily-alerts)
      - name: Download database artifact
        uses: dawidd6/action-download-artifact@v3
        with:
          name: database
          path: data/
          workflow_conclusion: success
          if_no_artifact_found: warn
        continue-on-error: true
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Initialize database
        run: python -c "import insider_alerts; insider_alerts.init_database()"
      
      # Run polling script (exits after processing)
      - name: Run Telegram bot polling
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        run: python telegram_tracker_polling.py
      
      # Upload database with latest update_id
      - name: Upload database artifact
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: database
          path: data/congressional_trades.db
          retention-days: 90
          overwrite: true
```

---

## 🎓 How It Works

### Database Persistence Strategy

**Problem:** GitHub Actions runners are ephemeral (fresh VM each run)

**Solution:** Artifacts as database storage

1. **First run:** Creates new database
2. **End of run:** Uploads `congressional_trades.db` as artifact
3. **Next run:** Downloads artifact from previous run
4. **Continues:** Database persists across all runs

**Artifact lifecycle:**
- Retained for 90 days
- Overwritten on each run (latest version kept)
- Shared between daily-alerts and telegram-bot workflows

### Telegram Polling vs Long-Running

**Traditional (won't work in GitHub Actions):**
```python
# This runs forever - not allowed in GitHub Actions
app.run_polling()  # Blocks indefinitely
```

**Our solution (works in GitHub Actions):**
```python
# Runs once and exits - perfect for cron jobs
last_update_id = get_last_update_id()  # From database
updates = get_updates(offset=last_update_id + 1)  # Get new messages
process_updates(updates)  # Handle messages
save_last_update_id(new_id)  # Remember position
# Script exits, GitHub Actions completes
```

**Benefits:**
- Runs every 5 minutes via cron
- No long-running process needed
- Handles messages within 5-minute window
- Avoids duplicate processing (stores last_update_id)

---

## 🔒 Security Best Practices

1. **Never commit secrets** - Always use GitHub Secrets
2. **Use App Passwords** - Not your main Gmail password
3. **Limit permissions** - Only grant what's needed
4. **Review logs** - Check for exposed credentials
5. **Rotate tokens** - Change periodically

---

## 📞 Support & Resources

- **GitHub Actions Docs:** https://docs.github.com/en/actions
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **Cron Expression Helper:** https://crontab.guru/

---

## ✅ Final Checklist

Before going live:

- [ ] All GitHub Secrets configured
- [ ] Workflow files committed and pushed
- [ ] GitHub Actions enabled in repository settings
- [ ] Manually tested daily-alerts workflow (succeeded)
- [ ] Manually tested telegram-bot workflow (succeeded)
- [ ] Received test email alert
- [ ] Received test Telegram alert
- [ ] Bot responds to `@bot` commands
- [ ] Database artifact uploaded successfully
- [ ] Checked workflow logs for errors

---

## 🎉 You're Done!

Your insider trading alert system is now fully automated and running in the cloud!

**What happens next:**
- Every day at 8am UTC: Automatic trade detection and alerts
- Every 5 minutes: Telegram bot checks for new commands
- Zero maintenance required (unless you want to update code)

**Monitor your system:**
- GitHub Actions tab → View all runs
- Email inbox → Daily alert summaries
- Telegram → Real-time trade notifications

Happy trading! 📈
