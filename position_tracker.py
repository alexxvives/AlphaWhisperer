"""
Position Tracker - Monitor open positions for exit signals
Triggered via Telegram bot reply: TICKER @PRICE
"""
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Database for tracking positions
DB_PATH = Path("data/positions.db")

def init_positions_db():
    """Initialize positions database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_date TEXT NOT NULL,
            status TEXT DEFAULT 'OPEN',
            exit_price REAL,
            exit_date TEXT,
            exit_reason TEXT,
            profit_pct REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, entry_date)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exit_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            signal_type TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            current_price REAL,
            details TEXT,
            notified INTEGER DEFAULT 0,
            FOREIGN KEY (position_id) REFERENCES positions(id)
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Positions database initialized at {DB_PATH}")


def add_position(ticker: str, entry_price: float) -> bool:
    """
    Add a new position to track
    
    Args:
        ticker: Stock ticker symbol
        entry_price: Entry price
        
    Returns:
        True if added successfully, False if already exists
    """
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    entry_date = datetime.now().strftime('%Y-%m-%d')
    
    try:
        cursor.execute("""
            INSERT INTO positions (ticker, entry_price, entry_date, status)
            VALUES (?, ?, ?, 'OPEN')
        """, (ticker.upper(), entry_price, entry_date))
        
        conn.commit()
        logger.info(f"Added position: {ticker} @ ${entry_price}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Position already exists: {ticker} on {entry_date}")
        return False
    finally:
        conn.close()


def get_open_positions() -> List[Dict]:
    """
    Get all open positions
    
    Returns:
        List of position dictionaries
    """
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, ticker, entry_price, entry_date, created_at
        FROM positions
        WHERE status = 'OPEN'
        ORDER BY entry_date DESC
    """)
    
    positions = []
    for row in cursor.fetchall():
        positions.append({
            'id': row[0],
            'ticker': row[1],
            'entry_price': row[2],
            'entry_date': row[3],
            'created_at': row[4]
        })
    
    conn.close()
    return positions


def close_position(ticker: str, exit_price: float, exit_reason: str = "Manual") -> bool:
    """
    Close a position
    
    Args:
        ticker: Stock ticker symbol
        exit_price: Exit price
        exit_reason: Reason for closing
        
    Returns:
        True if closed successfully
    """
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    exit_date = datetime.now().strftime('%Y-%m-%d')
    
    # Get the most recent open position for this ticker
    cursor.execute("""
        SELECT id, entry_price FROM positions
        WHERE ticker = ? AND status = 'OPEN'
        ORDER BY entry_date DESC
        LIMIT 1
    """, (ticker.upper(),))
    
    result = cursor.fetchone()
    if not result:
        logger.warning(f"No open position found for {ticker}")
        conn.close()
        return False
    
    position_id, entry_price = result
    profit_pct = ((exit_price - entry_price) / entry_price) * 100
    
    cursor.execute("""
        UPDATE positions
        SET status = 'CLOSED', exit_price = ?, exit_date = ?, 
            exit_reason = ?, profit_pct = ?
        WHERE id = ?
    """, (exit_price, exit_date, exit_reason, profit_pct, position_id))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Closed position: {ticker} @ ${exit_price} ({profit_pct:+.1f}%)")
    return True


def record_exit_signal(position_id: int, signal_type: str, current_price: float, details: str = ""):
    """
    Record an exit signal for a position
    
    Args:
        position_id: Position ID
        signal_type: Type of exit signal
        current_price: Current price when signal detected
        details: Additional details about the signal
    """
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    detected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        INSERT INTO exit_signals (position_id, signal_type, detected_at, current_price, details)
        VALUES (?, ?, ?, ?, ?)
    """, (position_id, signal_type, detected_at, current_price, details))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Recorded exit signal for position {position_id}: {signal_type}")


def get_unnotified_exit_signals() -> List[Dict]:
    """
    Get exit signals that haven't been notified yet
    
    Returns:
        List of exit signal dictionaries with position details
    """
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            es.id, es.position_id, es.signal_type, es.detected_at, 
            es.current_price, es.details,
            p.ticker, p.entry_price, p.entry_date
        FROM exit_signals es
        JOIN positions p ON es.position_id = p.id
        WHERE es.notified = 0 AND p.status = 'OPEN'
        ORDER BY es.detected_at DESC
    """)
    
    signals = []
    for row in cursor.fetchall():
        entry_price = row[7]
        current_price = row[4]
        profit_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price else 0
        
        signals.append({
            'id': row[0],
            'position_id': row[1],
            'signal_type': row[2],
            'detected_at': row[3],
            'current_price': row[4],
            'details': row[5],
            'ticker': row[6],
            'entry_price': row[7],
            'entry_date': row[8],
            'profit_pct': profit_pct
        })
    
    conn.close()
    return signals


def mark_signals_notified(signal_ids: List[int]):
    """Mark exit signals as notified"""
    if not signal_ids:
        return
    
    init_positions_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    placeholders = ','.join('?' * len(signal_ids))
    cursor.execute(f"""
        UPDATE exit_signals
        SET notified = 1
        WHERE id IN ({placeholders})
    """, signal_ids)
    
    conn.commit()
    conn.close()
    
    logger.info(f"Marked {len(signal_ids)} signals as notified")


def get_position_summary() -> str:
    """Get a summary of all positions"""
    positions = get_open_positions()
    
    if not positions:
        return "No open positions"
    
    summary = f"📊 **Open Positions ({len(positions)})**\n\n"
    for pos in positions:
        summary += f"• {pos['ticker']} @ ${pos['entry_price']:.2f} (entered {pos['entry_date']})\n"
    
    return summary


if __name__ == "__main__":
    # Test the position tracker
    logging.basicConfig(level=logging.INFO)
    
    # Initialize DB
    init_positions_db()
    
    # Add sample position
    add_position("AAPL", 175.50)
    add_position("NVDA", 485.20)
    
    # Get positions
    positions = get_open_positions()
    print(f"Open positions: {len(positions)}")
    for pos in positions:
        print(f"  {pos['ticker']} @ ${pos['entry_price']}")
    
    # Record exit signal
    if positions:
        record_exit_signal(
            positions[0]['id'],
            "Bearish Cluster Selling",
            180.25,
            "3 insiders selling in 5 days"
        )
    
    # Get unnotified signals
    signals = get_unnotified_exit_signals()
    print(f"\nUnnotified exit signals: {len(signals)}")
    for sig in signals:
        print(f"  {sig['ticker']}: {sig['signal_type']} @ ${sig['current_price']:.2f}")
