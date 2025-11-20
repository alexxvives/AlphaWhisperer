"""
Monitor open positions for bearish exit signals
Run this periodically (e.g., hourly) to check tracked positions
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import yfinance as yf

from position_tracker import (
    get_open_positions, 
    record_exit_signal,
    get_unnotified_exit_signals,
    mark_signals_notified
)
from insider_alerts import (
    fetch_openinsider_data,
    normalize_dataframe,
    filter_by_lookback,
    detect_bearish_cluster_selling,
    send_telegram_message
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_position_for_exits(position: Dict) -> List[Dict]:
    """
    Check a position for bearish exit signals
    
    Args:
        position: Position dictionary with ticker, entry_price, etc.
        
    Returns:
        List of exit signal dictionaries
    """
    ticker = position['ticker']
    logger.info(f"Checking {ticker} for exit signals...")
    
    exit_signals = []
    
    try:
        # Fetch recent insider data
        df = fetch_openinsider_data()
        if df is None or df.empty:
            logger.warning(f"No insider data available for {ticker}")
            return exit_signals
        
        df = normalize_dataframe(df)
        df = filter_by_lookback(df, lookback_days=7)
        
        # Filter to this ticker only
        ticker_df = df[df['Ticker'].str.upper() == ticker.upper()]
        
        if ticker_df.empty:
            logger.info(f"No recent insider activity for {ticker}")
            return exit_signals
        
        # Check for bearish cluster selling
        bearish_signals = detect_bearish_cluster_selling(ticker_df)
        
        if bearish_signals:
            logger.warning(f"⚠️ BEARISH SIGNAL detected for {ticker}: {len(bearish_signals)} cluster selling events")
            
            for alert in bearish_signals:
                details = alert.details
                num_insiders = details.get('num_insiders', 0)
                total_value = details.get('total_value', 0)
                
                exit_signals.append({
                    'signal_type': 'Bearish Cluster Selling',
                    'details': f"{num_insiders} insiders selling ${total_value:,.0f} total",
                    'severity': 'HIGH'
                })
        
        # Check for price drops (technical exit)
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            
            if not hist.empty and len(hist) >= 2:
                current_price = hist['Close'].iloc[-1]
                entry_price = position['entry_price']
                
                # Check for significant loss (-10% or worse)
                loss_pct = ((current_price - entry_price) / entry_price) * 100
                
                if loss_pct <= -10:
                    logger.warning(f"⚠️ STOP LOSS triggered for {ticker}: {loss_pct:.1f}%")
                    exit_signals.append({
                        'signal_type': 'Stop Loss (-10%)',
                        'details': f"Price dropped from ${entry_price:.2f} to ${current_price:.2f}",
                        'severity': 'CRITICAL',
                        'current_price': current_price
                    })
                
                # Check for momentum loss (5-day decline)
                if len(hist) >= 5:
                    price_5d_ago = hist['Close'].iloc[-5]
                    decline_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100
                    
                    if decline_5d <= -8:
                        logger.warning(f"⚠️ MOMENTUM LOSS for {ticker}: {decline_5d:.1f}% in 5 days")
                        exit_signals.append({
                            'signal_type': 'Momentum Loss',
                            'details': f"Price declined {decline_5d:.1f}% in 5 days",
                            'severity': 'MEDIUM',
                            'current_price': current_price
                        })
        
        except Exception as e:
            logger.error(f"Error checking price for {ticker}: {e}")
    
    except Exception as e:
        logger.error(f"Error checking exit signals for {ticker}: {e}")
    
    return exit_signals


def monitor_all_positions():
    """Monitor all open positions and send alerts for exit signals"""
    logger.info("=" * 60)
    logger.info("POSITION MONITORING - Checking for exit signals")
    logger.info("=" * 60)
    
    positions = get_open_positions()
    
    if not positions:
        logger.info("No open positions to monitor")
        return
    
    logger.info(f"Monitoring {len(positions)} open positions...")
    
    new_signals_count = 0
    
    for position in positions:
        ticker = position['ticker']
        entry_price = position['entry_price']
        
        logger.info(f"\n📊 Position: {ticker} @ ${entry_price:.2f}")
        
        # Check for exit signals
        exit_signals = check_position_for_exits(position)
        
        # Record new signals
        for signal in exit_signals:
            try:
                # Get current price from signal or fetch it
                current_price = signal.get('current_price')
                if not current_price:
                    stock = yf.Ticker(ticker)
                    current_price = stock.history(period="1d")['Close'].iloc[-1]
                
                record_exit_signal(
                    position['id'],
                    signal['signal_type'],
                    current_price,
                    signal['details']
                )
                new_signals_count += 1
                
            except Exception as e:
                logger.error(f"Error recording exit signal: {e}")
    
    logger.info(f"\n✅ Monitoring complete. {new_signals_count} new exit signals detected.")
    
    # Send Telegram notifications for unnotified signals
    send_exit_notifications()


def send_exit_notifications():
    """Send Telegram notifications for unnotified exit signals"""
    signals = get_unnotified_exit_signals()
    
    if not signals:
        logger.info("No exit signals to notify")
        return
    
    logger.info(f"Sending {len(signals)} exit signal notifications...")
    
    for signal in signals:
        ticker = signal['ticker']
        signal_type = signal['signal_type']
        entry_price = signal['entry_price']
        current_price = signal['current_price']
        profit_pct = signal['profit_pct']
        details = signal['details']
        
        # Determine emoji based on signal severity
        if 'CRITICAL' in signal_type or 'Stop Loss' in signal_type:
            emoji = "🚨"
        elif 'HIGH' in signal_type or 'Cluster' in signal_type:
            emoji = "⚠️"
        else:
            emoji = "⚡"
        
        # Format profit/loss
        pnl_emoji = "📈" if profit_pct > 0 else "📉"
        pnl_text = f"{profit_pct:+.1f}%"
        
        message = f"""
{emoji} **EXIT SIGNAL DETECTED**

**Ticker:** {ticker}
**Signal:** {signal_type}

**Entry:** ${entry_price:.2f}
**Current:** ${current_price:.2f}
**P/L:** {pnl_emoji} {pnl_text}

**Details:** {details}

**Detected:** {signal['detected_at']}

⚡ Consider closing this position or reviewing your strategy.
"""
        
        try:
            send_telegram_message(message, parse_mode='Markdown')
            logger.info(f"✅ Sent exit notification for {ticker}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
    
    # Mark all signals as notified
    signal_ids = [s['id'] for s in signals]
    mark_signals_notified(signal_ids)
    
    logger.info(f"Notification batch complete: {len(signals)} signals sent")


if __name__ == "__main__":
    monitor_all_positions()
