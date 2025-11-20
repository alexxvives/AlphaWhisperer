"""
Calculate and store P&L for all politician-ticker pairs in database
"""

import sqlite3
from politician_pnl import calculate_politician_pnl
from insider_alerts import init_database
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def store_pnl_in_database():
    """Calculate P&L for all politicians and store in politician_pnl table"""
    
    # Initialize database (creates politician_pnl table if needed)
    init_database()
    
    logger.info("Calculating P&L for all politicians...")
    
    # Calculate P&L for all politicians
    pnl_data = calculate_politician_pnl()
    
    if not pnl_data:
        logger.warning("No P&L data calculated!")
        return
    
    logger.info(f"Calculated P&L for {len(pnl_data)} positions")
    
    # Store in database
    conn = sqlite3.connect('data/congressional_trades.db')
    cursor = conn.cursor()
    
    # Clear existing data
    cursor.execute("DELETE FROM politician_pnl")
    
    inserted = 0
    for position in pnl_data:
        try:
            cursor.execute("""
                INSERT INTO politician_pnl 
                (politician_id, politician_name, party, state, ticker, company_name,
                 shares_held, avg_cost_basis, current_price, position_value,
                 unrealized_pnl, realized_pnl, total_pnl, return_percent, 
                 trades_count, status, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position['politician_id'],
                position['politician_name'],
                position['party'],
                position['state'],
                position['ticker'],
                position['company_name'],
                position['shares_held'],
                position['avg_cost_basis'],
                position['current_price'],
                position['position_value'],
                position['unrealized_pnl'],
                position['realized_pnl'],
                position['total_pnl'],
                position['return_percent'],
                position['trades_count'],
                position['status'],
                datetime.now().isoformat()
            ))
            inserted += 1
        except Exception as e:
            logger.error(f"Error inserting position {position['politician_name']}-{position['ticker']}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Stored {inserted} positions in politician_pnl table")
    
    # Show summary
    conn = sqlite3.connect('data/congressional_trades.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n" + "="*90)
    print("TOP 10 POLITICIANS BY TOTAL P&L")
    print("="*90)
    
    cursor.execute("""
        SELECT politician_name, party, state,
               SUM(total_pnl) as total_pnl,
               SUM(unrealized_pnl) as unrealized,
               SUM(realized_pnl) as realized,
               COUNT(*) as positions
        FROM politician_pnl
        GROUP BY politician_id
        ORDER BY total_pnl DESC
        LIMIT 10
    """)
    
    print(f"\n{'#':<4} {'Politician':<25} {'Party':<6} {'Total P&L':<15} {'Unrealized':<15} {'Realized':<15} {'Positions':<10}")
    print("-" * 90)
    
    for i, row in enumerate(cursor.fetchall(), 1):
        total_str = f"${row['total_pnl']:,.0f}"
        unreal_str = f"${row['unrealized']:,.0f}"
        real_str = f"${row['realized']:,.0f}"
        
        print(f"{i:<4} {row['politician_name'][:24]:<25} {row['party']:<6} {total_str:<15} {unreal_str:<15} {real_str:<15} {row['positions']:<10}")
    
    print("\n" + "="*90)
    print("TOP 10 BEST PERFORMING STOCKS (by Total P&L)")
    print("="*90)
    
    cursor.execute("""
        SELECT politician_name, ticker, company_name, total_pnl, return_percent, status
        FROM politician_pnl
        ORDER BY total_pnl DESC
        LIMIT 10
    """)
    
    print(f"\n{'Politician':<25} {'Ticker':<8} {'Company':<25} {'P&L':<15} {'Return %':<12} {'Status':<8}")
    print("-" * 90)
    
    for row in cursor.fetchall():
        company = (row['company_name'] or '')[:24]
        pnl_str = f"${row['total_pnl']:,.0f}"
        ret_str = f"{row['return_percent']:.1f}%"
        
        print(f"{row['politician_name'][:24]:<25} {row['ticker']:<8} {company:<25} {pnl_str:<15} {ret_str:<12} {row['status']:<8}")
    
    print("\n" + "="*90)
    print("TOP 10 WORST PERFORMING STOCKS (by Total P&L)")
    print("="*90)
    
    cursor.execute("""
        SELECT politician_name, ticker, company_name, total_pnl, return_percent, status
        FROM politician_pnl
        ORDER BY total_pnl ASC
        LIMIT 10
    """)
    
    print(f"\n{'Politician':<25} {'Ticker':<8} {'Company':<25} {'P&L':<15} {'Return %':<12} {'Status':<8}")
    print("-" * 90)
    
    for row in cursor.fetchall():
        company = (row['company_name'] or '')[:24]
        pnl_str = f"${row['total_pnl']:,.0f}"
        ret_str = f"{row['return_percent']:.1f}%"
        
        print(f"{row['politician_name'][:24]:<25} {row['ticker']:<8} {company:<25} {pnl_str:<15} {ret_str:<12} {row['status']:<8}")
    
    conn.close()
    
    print("\n" + "="*90)


if __name__ == "__main__":
    print("="*90)
    print("CALCULATING AND STORING POLITICIAN P&L DATA")
    print("="*90)
    print("\nThis will:")
    print("1. Calculate P&L for all politician-ticker pairs")
    print("2. Store results in politician_pnl table")
    print("3. Show top performers and losers\n")
    
    store_pnl_in_database()
    
    print("\nDone! P&L data stored in politician_pnl table")
    print("="*90)
