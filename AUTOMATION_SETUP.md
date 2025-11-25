# Daily Automation Setup

## ONE-FILE AUTOMATION

Run both insider alerts AND ticker tracking with a single command:

**File to automate:** `run_daily_alerts.py`

This runs:
1. Signal detection (Congressional + Corporate Insider)
2. Alert sending (Email + Telegram)
3. Deduplication (prevents repeat alerts for 7 days)
4. Cleanup (removes expired alert history)

**Note:** Ticker tracking bot (`telegram_tracker.py`) runs separately and continuously to respond to user messages.

---

## Windows Task Scheduler (Recommended)

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, press Enter

2. **Create Basic Task**
   - Click "Create Basic Task" in the right panel
   - Name: `InvestorAI Daily Alerts`
   - Description: `Run insider alerts detection and send notifications`

3. **Trigger**
   - Select "Daily"
   - Start date: Today
   - Time: `08:00:00` (8:00 AM)
   - Recur every: `1` days

4. **Action**
   - Select "Start a program"
   - Program/script: `C:\Users\alexx\Desktop\Projects\InvestorAI\.venv\Scripts\python.exe`
   - Add arguments: `run_daily_alerts.py`
   - Start in: `C:\Users\alexx\Desktop\Projects\InvestorAI`

5. **Finish**
   - Check "Open Properties dialog" to configure additional settings
   - Under "General" tab:
     - Check "Run whether user is logged on or not"
     - Check "Run with highest privileges"
   - Under "Conditions" tab:
     - Uncheck "Start only if computer is on AC power" (if laptop)
   - Click OK

---

## Ticker Tracking Bot (Continuous)

The Telegram bot needs to run continuously to respond to `@bot` commands.

**YES, you can automate this with Windows Task Scheduler too!**

### Option 1: Windows Task Scheduler (Recommended - Auto-Start)

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, press Enter

2. **Create Basic Task**
   - Click "Create Basic Task"
   - Name: `Telegram Ticker Tracker`
   - Description: `Continuous Telegram bot for ticker tracking`

3. **Trigger**
   - Select "When the computer starts"
   - (This makes it auto-start on boot)

4. **Action**
   - Select "Start a program"
   - Program/script: `C:\Users\alexx\Desktop\Projects\InvestorAI\.venv\Scripts\pythonw.exe`
   - Add arguments: `telegram_tracker.py`
   - Start in: `C:\Users\alexx\Desktop\Projects\InvestorAI`
   
   **Note:** Using `pythonw.exe` (with 'w') runs without a visible console window

5. **Finish & Configure**
   - Check "Open Properties dialog"
   - Under "General" tab:
     - Check "Run whether user is logged on or not"
     - Check "Run with highest privileges"
   - Under "Settings" tab:
     - Uncheck "Stop the task if it runs longer than" (let it run indefinitely)
     - Check "If the running task does not end when requested, force it to stop"
   - Click OK

**To manually start/stop:**
```powershell
# Start
schtasks /run /tn "Telegram Ticker Tracker"

# Stop (kill the process)
Stop-Process -Name pythonw -Force

# Check if running
Get-Process pythonw -ErrorAction SilentlyContinue
```

### Option 2: Background Process (Simple Testing)

```powershell
# Start in background (visible in Task Manager only)
Start-Process -FilePath ".venv\Scripts\pythonw.exe" -ArgumentList "telegram_tracker.py" -WindowStyle Hidden

# Check if running
Get-Process pythonw | Where-Object { $_.Path -like "*InvestorAI*" }

# Stop
Stop-Process -Name pythonw -Force
```

### Option 3: Windows Service with NSSM (Advanced)

For true Windows Service (survives logoff, auto-restart on failure):

```powershell
# Download and install NSSM
# From https://nssm.cc/download or: choco install nssm

# Install service
cd C:\Users\alexx\Desktop\Projects\InvestorAI
nssm install TelegramTracker ".venv\Scripts\python.exe" "telegram_tracker.py"
nssm set TelegramTracker AppDirectory "C:\Users\alexx\Desktop\Projects\InvestorAI"
nssm set TelegramTracker DisplayName "Telegram Ticker Tracker"
nssm set TelegramTracker Description "Continuous bot for tracking stock tickers"
nssm set TelegramTracker Start SERVICE_AUTO_START

# Start service
nssm start TelegramTracker

# Service controls
net start TelegramTracker    # Start
net stop TelegramTracker     # Stop
sc query TelegramTracker     # Check status

# Uninstall service (if needed)
nssm stop TelegramTracker
nssm remove TelegramTracker confirm
```

---

## Verification & Monitoring

### Check if Tasks are Running

**View in Task Scheduler GUI:**
1. Open Task Scheduler (`Win + R` → `taskschd.msc`)
2. In left panel, navigate to "Task Scheduler Library"
3. Find your tasks:
   - `InvestorAI Daily Alerts`
   - `Telegram Ticker Tracker`
4. Check "Status" column:
   - **Running** = Currently executing
   - **Ready** = Scheduled, waiting for trigger
   - **Disabled** = Task is disabled
5. Click on a task to see:
   - "Last Run Time"
   - "Last Run Result" (0x0 = success)
   - "Next Run Time"

**Check via PowerShell:**
```powershell
# Check if daily alerts task exists and is enabled
Get-ScheduledTask -TaskName "InvestorAI Daily Alerts" | Select-Object TaskName, State, LastRunTime, NextRunTime

# Check if ticker tracker task exists and is enabled
Get-ScheduledTask -TaskName "Telegram Ticker Tracker" | Select-Object TaskName, State, LastRunTime, NextRunTime

# Check if telegram bot process is actually running
Get-Process pythonw -ErrorAction SilentlyContinue | Format-Table Id, ProcessName, StartTime, Path

# Check if any python processes are running from InvestorAI
Get-Process python* | Where-Object { $_.Path -like "*InvestorAI*" } | Format-Table Id, ProcessName, StartTime, Path
```

**View Task History:**
1. In Task Scheduler, right-click on a task
2. Select "Properties"
3. Go to "History" tab
4. Check for recent execution events
   - Event ID 100 = Task started
   - Event ID 102 = Task completed successfully
   - Event ID 103 = Task failed

### Test Your Tasks Manually

**Test Daily Alerts (without waiting for 8am):**
```powershell
# Method 1: Run via Task Scheduler
schtasks /run /tn "InvestorAI Daily Alerts"

# Method 2: Run directly
cd C:\Users\alexx\Desktop\Projects\InvestorAI
.venv\Scripts\python.exe run_daily_alerts.py --once

# Check logs after running
Get-Content logs\daily_alerts.log -Tail 50
```

**Test Ticker Tracker:**
```powershell
# Check if it's running
Get-Process pythonw -ErrorAction SilentlyContinue

# If not running, start it manually
schtasks /run /tn "Telegram Ticker Tracker"

# Verify it's running (should see pythonw.exe)
Get-Process pythonw

# Test by sending "@bot list" in Telegram
# Bot should respond if running
```

### Monitor Logs

**Check execution logs:**
```powershell
# View daily alerts log
Get-Content logs\daily_alerts.log -Tail 100

# View real-time log (if alerts are running)
Get-Content logs\daily_alerts.log -Wait -Tail 50

# Check for errors
Select-String -Path logs\daily_alerts.log -Pattern "ERROR" | Select-Object -Last 10
```

### Troubleshooting

**Task says "Running" but nothing happens:**
- Check Windows Event Viewer: `eventvwr.msc` → Windows Logs → Application
- Look for errors related to Python or your task

**Task fails immediately:**
1. Verify paths are correct (use absolute paths)
2. Check "Last Run Result" in Task Scheduler
3. Common error codes:
   - `0x1` = Incorrect function (check path to python.exe)
   - `0x2` = File not found (check script path)
   - `0xFFFFFFFF` = Access denied (run as administrator)

**Telegram bot not responding:**
```powershell
# Kill any stuck processes
Stop-Process -Name pythonw -Force

# Restart the task
schtasks /run /tn "Telegram Ticker Tracker"

# Wait 5 seconds and check
Start-Sleep -Seconds 5
Get-Process pythonw
```

**Force a test run right now:**
```powershell
# Run daily alerts immediately (ignore schedule)
cd C:\Users\alexx\Desktop\Projects\InvestorAI
.venv\Scripts\python.exe run_daily_alerts.py --once --dry-run

# Check if signals were detected (won't send emails with --dry-run)
```

### Expected Behavior

**Daily Alerts Task:**
- Runs at 8:00 AM every day
- Takes 2-10 minutes to complete
- Status changes: Ready → Running → Ready
- Sends emails/Telegram if signals detected
- Creates log entries in `logs/daily_alerts.log`

**Ticker Tracker Task:**
- Starts when computer boots
- Stays "Running" indefinitely
- Python process `pythonw.exe` visible in Task Manager
- Responds to Telegram `@bot` commands
- Should NOT complete (it's continuous)

### Quick Health Check Script

Save this as `check_automation.ps1`:
```powershell
Write-Host "`n=== InvestorAI Automation Status ===" -ForegroundColor Cyan

# Check daily alerts task
$dailyTask = Get-ScheduledTask -TaskName "InvestorAI Daily Alerts" -ErrorAction SilentlyContinue
if ($dailyTask) {
    Write-Host "`n[Daily Alerts]" -ForegroundColor Green
    Write-Host "  Status: $($dailyTask.State)"
    Write-Host "  Last Run: $($dailyTask.LastRunTime)"
    Write-Host "  Next Run: $($dailyTask.NextRunTime)"
} else {
    Write-Host "`n[Daily Alerts] NOT CONFIGURED" -ForegroundColor Red
}

# Check ticker tracker task
$trackerTask = Get-ScheduledTask -TaskName "Telegram Ticker Tracker" -ErrorAction SilentlyContinue
if ($trackerTask) {
    Write-Host "`n[Ticker Tracker]" -ForegroundColor Green
    Write-Host "  Status: $($trackerTask.State)"
    Write-Host "  Last Run: $($trackerTask.LastRunTime)"
} else {
    Write-Host "`n[Ticker Tracker] NOT CONFIGURED" -ForegroundColor Red
}

# Check if bot is running
$botProcess = Get-Process pythonw -ErrorAction SilentlyContinue
if ($botProcess) {
    Write-Host "`n[Bot Process]" -ForegroundColor Green
    Write-Host "  Running: YES (PID: $($botProcess.Id))"
    Write-Host "  Started: $($botProcess.StartTime)"
} else {
    Write-Host "`n[Bot Process] NOT RUNNING" -ForegroundColor Yellow
    Write-Host "  Start it with: schtasks /run /tn 'Telegram Ticker Tracker'"
}

Write-Host "`n==================================`n" -ForegroundColor Cyan
```

Run: `.venv\Scripts\powershell.exe .\check_automation.ps1`

---

## Verification

After setting up automation:

1. **Test the scheduled task manually:**
   - In Task Scheduler, right-click the task
   - Select "Run"
   - Check email/Telegram for alerts

2. **Check logs:**
   - Task Scheduler keeps execution history
   - Or check your email/Telegram at 8 AM the next day

3. **Troubleshooting:**
   - Make sure paths are absolute
   - Ensure the virtual environment is activated (use `.venv\Scripts\python.exe`)
   - Check Windows Event Viewer if task fails
