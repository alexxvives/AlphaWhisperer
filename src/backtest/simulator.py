"""Backtesting engine for insider trading signals."""
"""Backtesting engine for insider trading signals."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf
from sqlalchemy import create_engine

from ..config import DATABASE_URL, WINDOWS, THRESHOLDS

class InsiderStrategy:
    """Backtester for insider trading signals."""
    
    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = THRESHOLDS['min_score'],
        holding_period: int = WINDOWS['backtest']['min_hold'],
        engine: Optional[create_engine] = None
    ):
        """Initialize backtester.
        
        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            min_score: Minimum signal score to trigger entry
            holding_period: Days to hold position
            engine: SQLAlchemy engine (optional)
        """
        self.start_date = start_date
        self.end_date = end_date
        self.min_score = min_score
        self.holding_period = holding_period
        self.engine = engine or create_engine(DATABASE_URL)
        
        # Load signals
        self.signals = self._load_signals()
        
        # Track positions and performance
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        
    def _load_signals(self) -> pd.DataFrame:
        """Load insider trading signals from database."""
        query = f"""
        SELECT t.*, s.final_score
        FROM form4_transactions t
        JOIN scores s ON t.id = s.transaction_id
        WHERE t.transaction_date BETWEEN '{self.start_date}' AND '{self.end_date}'
        AND s.final_score >= {self.min_score}
        ORDER BY t.transaction_date
        """
        return pd.read_sql(query, self.engine)
    
    def _get_price_data(self, ticker: str) -> pd.Series:
        """Get historical price data for ticker."""
        try:
            data = yf.download(
                ticker,
                start=self.start_date,
                end=self.end_date,
                progress=False
            )
            return data['Adj Close']
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            return pd.Series()
            
    def run(self, initial_capital: float = 1_000_000) -> Dict:
        """Run backtest simulation.
        
        Args:
            initial_capital: Starting capital amount
            
        Returns:
            Dict of performance metrics
        """
        capital = initial_capital
        self.equity_curve = [(self.start_date, capital)]
        
        # Group signals by date
        daily_signals = self.signals.groupby('transaction_date')
        
        # Simulate day by day
        current_date = self.start_date
        while current_date <= self.end_date:
            # Check for new signals
            if current_date in daily_signals.groups:
                day_signals = daily_signals.get_group(current_date)
                
                # Process each signal
                for _, signal in day_signals.iterrows():
                    # Skip if we already have a position
                    if signal.issuer_ticker in self.positions:
                        continue
                        
                    # Get price data
                    prices = self._get_price_data(signal.issuer_ticker)
                    if prices.empty:
                        continue
                        
                    entry_price = prices[current_date]
                    position_size = capital * 0.02  # 2% position size
                    
                    self.positions[signal.issuer_ticker] = {
                        'entry_date': current_date,
                        'entry_price': entry_price,
                        'shares': position_size / entry_price,
                        'signal_score': signal.final_score
                    }
            
            # Check existing positions
            positions_to_close = []
            for ticker, pos in self.positions.items():
                hold_days = (current_date - pos['entry_date']).days
                
                # Close if holding period reached
                if hold_days >= self.holding_period:
                    prices = self._get_price_data(ticker)
                    if not prices.empty:
                        exit_price = prices[current_date]
                        pnl = (exit_price - pos['entry_price']) * pos['shares']
                        capital += pnl
                        
                        self.trades.append({
                            'ticker': ticker,
                            'entry_date': pos['entry_date'],
                            'exit_date': current_date,
                            'holding_days': hold_days,
                            'entry_price': pos['entry_price'],
                            'exit_price': exit_price,
                            'shares': pos['shares'],
                            'pnl': pnl,
                            'return': pnl / (pos['entry_price'] * pos['shares']),
                            'signal_score': pos['signal_score']
                        })
                        positions_to_close.append(ticker)
            
            # Remove closed positions
            for ticker in positions_to_close:
                del self.positions[ticker]
                
            # Record equity
            self.equity_curve.append((current_date, capital))
            
            # Next day
            current_date += timedelta(days=1)
            
        # Calculate metrics
        returns = pd.DataFrame(
            self.equity_curve,
            columns=['date', 'equity']
        ).set_index('date')
        
        returns['returns'] = returns['equity'].pct_change()
        
        metrics = {
            'total_return': (capital - initial_capital) / initial_capital,
            'num_trades': len(self.trades),
            'win_rate': len([t for t in self.trades if t['pnl'] > 0]) / len(self.trades),
            'avg_return': np.mean([t['return'] for t in self.trades]),
            'sharpe': returns['returns'].mean() / returns['returns'].std() * np.sqrt(252),
            'max_drawdown': (returns['equity'] / returns['equity'].cummax() - 1).min()
        }
        
        return metrics
    
    def get_trades_df(self) -> pd.DataFrame:
        """Get DataFrame of all completed trades."""
        return pd.DataFrame(self.trades)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        return pd.DataFrame(
            self.equity_curve,
            columns=['date', 'equity']
        ).set_index('date')
