"""
Calculate Profit & Loss for Congressional Politicians' Stock Trades
Uses full trading history from politician_full_history table
Tracks unrealized gains (still holding) and realized gains (sold positions)
"""

import sqlite3
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Tuple
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for prices to avoid repeated API calls
_price_cache = {}


def get_current_price(ticker: str) -> float:
    """Get current stock price from yfinance with caching and retry"""
    if ticker in _price_cache:
        return _price_cache[ticker]
    
    try:
        # Add delay to avoid rate limiting (increased from 0.1 to 0.5)
        time.sleep(0.5)
        
        stock = yf.Ticker(ticker)
        
        # Use history instead of info to avoid rate limits
        hist = stock.history(period='5d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            _price_cache[ticker] = price
            return price
            
    except Exception as e:
        logger.debug(f"Could not fetch price for {ticker}: {e}")
        # If rate limited, wait longer
        if "Too Many Requests" in str(e) or "Rate" in str(e):
            logger.warning(f"Rate limited, waiting 60 seconds...")
            time.sleep(60)
    
    _price_cache[ticker] = None
    return None


def get_historical_price(ticker: str, date_str: str) -> float:
    """
    Get historical closing price for a ticker on a specific date with caching
    date_str format: "8 Oct" or "23 Oct" (assumes current year or previous year)
    """
    cache_key = f"{ticker}_{date_str}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    
    try:
        from datetime import datetime, timedelta
        
        # Add delay to avoid rate limiting (increased from 0.1 to 0.5)
        time.sleep(0.5)
        
        # Parse the date string (e.g., "8 Oct")
        current_year = datetime.now().year
        
        # Try current year first
        try:
            date = datetime.strptime(f"{date_str} {current_year}", "%d %b %Y")
        except:
            # If that fails, try previous year
            date = datetime.strptime(f"{date_str} {current_year - 1}", "%d %b %Y")
        
        # If date is in the future, use previous year
        if date > datetime.now():
            date = datetime.strptime(f"{date_str} {current_year - 1}", "%d %b %Y")
        
        # Fetch historical data (get a few days range to handle weekends/holidays)
        start_date = date - timedelta(days=5)
        end_date = date + timedelta(days=2)
        
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)
        
        if not hist.empty:
            # Get closest date
            closest_date = min(hist.index, key=lambda x: abs(x.date() - date.date()))
            price = float(hist.loc[closest_date]['Close'])
            logger.debug(f"Historical price for {ticker} on {date_str}: ${price:.2f}")
            _price_cache[cache_key] = price
            return price
    except Exception as e:
        logger.debug(f"Could not fetch historical price for {ticker} on {date_str}: {e}")
    
    _price_cache[cache_key] = None
    return None


def parse_size_range(size_range: str) -> Tuple[float, float]:
    """
    Parse size range like '1K-15K' or '15K-50K' into min/max values
    Returns (min_value, max_value) in dollars
    """
    if not size_range:
        return None, None
    
    try:
        size_range = size_range.upper().strip()
        parts = size_range.replace('–', '-').split('-')
        if len(parts) != 2:
            return None, None
        
        min_str, max_str = parts
        
        def parse_value(s):
            s = s.strip()
            if s.endswith('K'):
                return float(s[:-1]) * 1000
            elif s.endswith('M'):
                return float(s[:-1]) * 1000000
            else:
                return float(s)
        
        min_val = parse_value(min_str)
        max_val = parse_value(max_str)
        
        return min_val, max_val
    except Exception as e:
        logger.debug(f"Could not parse size range '{size_range}': {e}")
        return None, None


def calculate_politician_pnl(politician_id: str = None) -> List[Dict]:
    """
    Calculate P&L for a specific politician or all politicians using full history
    
    Returns list of position summaries with:
    - politician info
    - ticker, company_name
    - total_shares (estimated from all buys minus sells)
    - avg_cost_basis
    - current_price
    - position_value
    - unrealized_pnl, realized_pnl
    - pnl_percent
    """
    conn = sqlite3.connect('data/alphaWhisperer.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all trades from congressional_trades table
    if politician_id:
        query = """
            SELECT * FROM congressional_trades 
            WHERE politician_id = ?
            ORDER BY traded_date ASC
        """
        cursor.execute(query, (politician_id,))
    else:
        query = """
            SELECT * FROM congressional_trades 
            ORDER BY politician_id, traded_date ASC
        """
        cursor.execute(query)
    
    trades = cursor.fetchall()
    conn.close()
    
    if not trades:
        return []
    
    logger.info(f"Processing {len(trades)} trades...")
    
    # Track positions by politician + ticker
    # positions[politician_id][ticker] = {shares: float, cost_basis: float, trades: []}
    positions = {}
    
    processed = 0
    for trade in trades:
        pol_id = trade['politician_id']
        ticker = trade['ticker']
        trade_type = trade['trade_type']
        price = trade['price']
        size_range = trade['size_range']
        traded_date = trade['traded_date']
        
        # If price is missing, fetch historical price for the trade date
        if not price and traded_date:
            price = get_historical_price(ticker, traded_date)
            if not price:
                logger.debug(f"Skipping {ticker} - no price data available")
                continue
        
        if not price or not size_range:
            continue
        
        # Parse size and estimate shares
        min_val, max_val = parse_size_range(size_range)
        if not min_val or not max_val:
            continue
        
        midpoint_value = (min_val + max_val) / 2
        estimated_shares = midpoint_value / price
        
        # Initialize politician positions dict
        if pol_id not in positions:
            positions[pol_id] = {}
        
        # Initialize ticker position
        if ticker not in positions[pol_id]:
            positions[pol_id][ticker] = {
                'politician_name': trade['politician_name'],
                'party': trade['party'],
                'state': trade['state'],
                'ticker': ticker,
                'company_name': trade['company_name'],
                'shares': 0,
                'cost_basis': 0,
                'realized_pnl': 0,
                'trades_count': 0
            }
        
        pos = positions[pol_id][ticker]
        
        if trade_type == 'BUY':
            pos['shares'] += estimated_shares
            pos['cost_basis'] += midpoint_value
            pos['trades_count'] += 1
            
        elif trade_type == 'SELL':
            if pos['shares'] > 0:
                # Calculate realized P&L
                avg_cost_per_share = pos['cost_basis'] / pos['shares']
                realized = estimated_shares * (price - avg_cost_per_share)
                pos['realized_pnl'] += realized
                
                # Reduce position
                pos['shares'] -= estimated_shares
                if pos['shares'] < 0:
                    pos['shares'] = 0
            
            pos['trades_count'] += 1
        
        processed += 1
        if processed % 1000 == 0:
            logger.info(f"  Processed {processed}/{len(trades)} trades...")
    
    logger.info(f"Finished processing trades. Calculating current values...")
    
    # Now calculate current values and format results
    results = []
    total_positions = sum(len(positions[pol_id]) for pol_id in positions)
    calculated = 0
    
    for pol_id in positions:
        for ticker in positions[pol_id]:
            pos = positions[pol_id][ticker]
            
            # Skip if no shares held and no realized gains
            if pos['shares'] == 0 and pos['realized_pnl'] == 0:
                continue
            
            # Get current price
            current_price = get_current_price(ticker)
            if not current_price:
                logger.warning(f"Could not get price for {ticker}")
                continue
            
            # Calculate unrealized P&L on remaining position
            unrealized_pnl = 0
            position_value = 0
            avg_cost = 0
            
            if pos['shares'] > 0 and pos['cost_basis'] > 0:
                avg_cost = pos['cost_basis'] / pos['shares']
                position_value = pos['shares'] * current_price
                unrealized_pnl = position_value - pos['cost_basis']
            
            # Total P&L
            total_pnl = unrealized_pnl + pos['realized_pnl']
            
            # Calculate return %
            total_invested = pos['cost_basis'] if pos['cost_basis'] > 0 else 1
            return_percent = (total_pnl / total_invested) * 100
            
            results.append({
                'politician_id': pol_id,
                'politician_name': pos['politician_name'],
                'party': pos['party'],
                'state': pos['state'],
                'ticker': ticker,
                'company_name': pos['company_name'],
                'shares_held': pos['shares'],
                'avg_cost_basis': avg_cost,
                'current_price': current_price,
                'position_value': position_value,
                'unrealized_pnl': unrealized_pnl,
                'realized_pnl': pos['realized_pnl'],
                'total_pnl': total_pnl,
                'return_percent': return_percent,
                'trades_count': pos['trades_count'],
                'status': 'OPEN' if pos['shares'] > 0 else 'CLOSED'
            })
            
            calculated += 1
            if calculated % 100 == 0:
                logger.info(f"  Calculated prices for {calculated}/{total_positions} positions...")
    
    logger.info(f"P&L calculation complete: {len(results)} positions")
    return results


def get_politician_summary(politician_id: str = None) -> List[Dict]:
    """
    Get P&L summary by politician
    Returns total unrealized and realized P&L for each politician
    """
    pnl_data = calculate_politician_pnl(politician_id)
    
    # Aggregate by politician
    summaries = {}
    
    for position in pnl_data:
        pol_id = position['politician_id']
        
        if pol_id not in summaries:
            summaries[pol_id] = {
                'politician_id': pol_id,
                'politician_name': position['politician_name'],
                'party': position['party'],
                'state': position['state'],
                'total_unrealized_pnl': 0,
                'total_realized_pnl': 0,
                'total_pnl': 0,
                'open_positions': 0,
                'closed_positions': 0,
                'total_position_value': 0,
                'winning_positions': 0,
                'losing_positions': 0,
                'total_trades': 0
            }
        
        summ = summaries[pol_id]
        summ['total_unrealized_pnl'] += position['unrealized_pnl']
        summ['total_realized_pnl'] += position['realized_pnl']
        summ['total_pnl'] += position['total_pnl']
        summ['total_position_value'] += position['position_value']
        summ['total_trades'] += position['trades_count']
        
        if position['status'] == 'OPEN':
            summ['open_positions'] += 1
        else:
            summ['closed_positions'] += 1
        
        if position['total_pnl'] > 0:
            summ['winning_positions'] += 1
        else:
            summ['losing_positions'] += 1
    
    # Sort by total P&L
    result = sorted(summaries.values(), key=lambda x: x['total_pnl'], reverse=True)
    
    return result


if __name__ == "__main__":
    print("="*90)
    print("CONGRESSIONAL POLITICIANS P&L TRACKER (Full Trading History)")
    print("="*90)
    
    # Get summaries for all politicians
    summaries = get_politician_summary()
    
    print(f"\nAll Politicians Ranked by Total P&L:\n")
    print(f"{'#':<4} {'Politician':<25} {'Party':<6} {'Total P&L':<15} {'Unrealized':<15} {'Realized':<15} {'Open':<6} {'Closed':<7}")
    print("-" * 90)
    
    for i, summary in enumerate(summaries, 1):
        total_str = f"${summary['total_pnl']:,.0f}"
        unreal_str = f"${summary['total_unrealized_pnl']:,.0f}"
        real_str = f"${summary['total_realized_pnl']:,.0f}"
        
        print(f"{i:<4} {summary['politician_name'][:24]:<25} {summary['party']:<6} {total_str:<15} {unreal_str:<15} {real_str:<15} {summary['open_positions']:<6} {summary['closed_positions']:<7}")
    
    if summaries:
        print("\n" + "="*90)
        print(f"Detailed Positions for Top Performer: {summaries[0]['politician_name']}")
        print("="*90)
        
        detailed = calculate_politician_pnl(summaries[0]['politician_id'])
        
        print(f"\n{'Ticker':<8} {'Company':<20} {'Status':<8} {'Shares':<10} {'Avg Cost':<12} {'Current':<12} {'P&L':<15} {'P&L %':<10}")
        print("-" * 95)
        
        for pos in sorted(detailed, key=lambda x: x['total_pnl'], reverse=True)[:15]:
            company = (pos['company_name'] or '')[:19]
            shares_str = f"{pos['shares_held']:.0f}" if pos['shares_held'] > 0 else "-"
            cost_str = f"${pos['avg_cost_basis']:.2f}" if pos['avg_cost_basis'] > 0 else "-"
            curr_str = f"${pos['current_price']:.2f}"
            pnl_str = f"${pos['total_pnl']:,.0f}"
            pnl_pct_str = f"{pos['return_percent']:.1f}%"
            
            print(f"{pos['ticker']:<8} {company:<20} {pos['status']:<8} {shares_str:<10} {cost_str:<12} {curr_str:<12} {pnl_str:<15} {pnl_pct_str:<10}")
