"""Scoring module for insider trading signals."""
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ..config import (
    DATABASE_URL,
    WEIGHTS,
    WINDOWS,
    THRESHOLDS
)

def score_role(title: str) -> float:
    """Score insider role based on title.
    
    Args:
        title: Insider's title/role
        
    Returns:
        Score 0-100 based on role importance
    """
    title = title.upper()
    
    if 'CEO' in title or 'CHIEF EXECUTIVE' in title:
        return WEIGHTS['role']['CEO']
    elif 'CFO' in title or 'CHIEF FINANCIAL' in title:
        return WEIGHTS['role']['CFO']
    elif 'DIRECTOR' in title:
        return WEIGHTS['role']['Director']
    elif 'OFFICER' in title or 'VP' in title or 'PRESIDENT' in title:
        return WEIGHTS['role']['Officer']
    else:
        return WEIGHTS['role']['Other']

def score_trade_type(code: str) -> float:
    """Score trade type based on Form 4 transaction code.
    
    Args:
        code: SEC Form 4 transaction code
        
    Returns:
        Score 0-100 based on trade type significance
    """
    return WEIGHTS['trade_type'].get(code, 0)

def score_trade_size(value: float, percentile: float) -> float:
    """Score trade size based on value and percentile rank.
    
    Args:
        value: Dollar value of trade
        percentile: Percentile rank vs historical trades
        
    Returns:
        Score 0-100 based on trade size
    """
    if value < THRESHOLDS['min_value']:
        return 0
    
    # Weight by both absolute size and relative size
    abs_score = min(100, value / 1_000_000 * 20)  # $5M+ gets max score
    pct_score = percentile * 100
    
    return (abs_score + pct_score) / 2

def score_cluster(
    ticker: str,
    date: datetime,
    engine: create_engine,
    window: int = WINDOWS['cluster']
) -> float:
    """Score insider cluster effect.
    
    Args:
        ticker: Stock ticker
        date: Trade date
        engine: SQLAlchemy engine
        window: Look-back/forward window in days
        
    Returns:
        Score 0-100 based on cluster strength
    """
    start = date - timedelta(days=window)
    end = date + timedelta(days=window)
    
    query = f"""
    SELECT COUNT(*) as num_trades, 
           COUNT(DISTINCT insider_name) as num_insiders,
           SUM(CASE WHEN transaction_type LIKE 'P%' THEN 1 ELSE 0 END) as num_buys,
           SUM(CASE WHEN transaction_type LIKE 'S%' THEN 1 ELSE 0 END) as num_sells
    FROM form4_transactions
    WHERE issuer_ticker = '{ticker}'
    AND transaction_date BETWEEN '{start}' AND '{end}'
    """
    
    with engine.connect() as conn:
        result = pd.read_sql(query, conn).iloc[0]
    
    if result['num_trades'] == 0:
        return 0
        
    # Score based on:
    # 1. Number of trades (max 10)
    # 2. Number of distinct insiders (max 5)
    # 3. Ratio of buys to sells
    trade_score = min(100, result['num_trades'] * 10)
    insider_score = min(100, result['num_insiders'] * 20)
    
    if result['num_buys'] + result['num_sells'] > 0:
        ratio = result['num_buys'] / (result['num_buys'] + result['num_sells'])
        ratio_score = ratio * 100
    else:
        ratio_score = 0
        
    return (trade_score + insider_score + ratio_score) / 3

def calculate_final_score(signals: Dict[str, float]) -> float:
    """Calculate final 0-100 score from individual signals.
    
    Args:
        signals: Dict of signal scores
        
    Returns:
        Final weighted score 0-100
    """
    weights = {
        'role': 0.2,
        'trade_type': 0.2,
        'size': 0.3,
        'cluster': 0.2,
        'catalyst': 0.15,
        'politician': 0.15
    }
    
    score = 0
    for signal, weight in weights.items():
        if signal in signals:
            score += signals[signal] * weight
            
    return min(100, max(0, score))
