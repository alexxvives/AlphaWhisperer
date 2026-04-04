#!/bin/bash
# =========================================================
# AlphaWhisperer — DigitalOcean Droplet Deploy Script
# Run this ONCE on your droplet: bash deploy_droplet.sh
#
# Droplet: 146.190.217.218
# =========================================================
set -e

APP_DIR="/opt/InvestorAI"
REPO_URL="https://github.com/alexxvives/AlphaWhisperer.git"
PYTHON="python3"

echo "=== AlphaWhisperer Droplet Setup ==="

# --- 1. System dependencies ---
echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git

# --- 2. Clone repository ---
echo "[2/7] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Existing install found — pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# --- 3. Virtual environment ---
echo "[3/7] Creating virtual environment..."
$PYTHON -m venv .venv
.venv/bin/pip install --upgrade pip -q

# --- 4. Python dependencies ---
echo "[4/7] Installing Python packages..."
.venv/bin/pip install -r requirements.txt -q

# --- 5. Create data and logs directories ---
echo "[5/7] Creating directories..."
mkdir -p data logs

# --- 6. Copy .env ---
echo "[6/7] Environment file..."
if [ ! -f ".env" ]; then
    echo ""
    echo "  *** ACTION REQUIRED ***"
    echo "  Copy your .env file to the droplet:"
    echo "    scp .env root@146.190.217.218:/opt/InvestorAI/.env"
    echo ""
    echo "  .env must contain:"
    echo "    SMTP_USER, SMTP_PASSWORD, SMTP_TO"
    echo "    BOT_TOKEN, CHAT_ID"
    echo "    GITHUB_TOKEN   (for GPT-4o-mini AI insights)"
    echo "    USE_TELEGRAM=true"
    echo ""
else
    echo "  .env found — OK"
fi

# --- 7. Cron jobs ---
echo "[7/7] Setting up cron jobs..."

# Remove old AlphaWhisperer crons (idempotent)
crontab -l 2>/dev/null | grep -v "InvestorAI" | crontab - 2>/dev/null || true

# Add fresh cron entries
(crontab -l 2>/dev/null; cat << 'CRONS'
# AlphaWhisperer — daily alerts at 08:00 UTC
0 8 * * * cd /opt/InvestorAI && .venv/bin/python run_daily_alerts.py >> logs/daily.log 2>&1
# AlphaWhisperer — weekly politician refresh on Sunday at 21:00 UTC
0 21 * * 0 cd /opt/InvestorAI && .venv/bin/python refresh_politician_list.py >> logs/refresh.log 2>&1
CRONS
) | crontab -

echo ""
echo "=== Setup complete ==="
echo ""
echo "Cron jobs installed:"
crontab -l | grep InvestorAI
echo ""
echo "Manual run to test:"
echo "  cd $APP_DIR && .venv/bin/python run_daily_alerts.py"
echo ""
echo "View logs:"
echo "  tail -f $APP_DIR/logs/daily.log"
