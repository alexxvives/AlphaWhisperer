"""Features module for computing insider trading signals."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

from ..config import (
    DATABASE_URL,
    WEIGHTS,
    WINDOWS,
    THRESHOLDS
)

logger = logging.getLogger(__name__)

def compute_all_signals():
    """Compute signals for all unscored transactions."""
    engine = create_engine(DATABASE_URL)
    
    # Get unscored transactions
    query = """
    SELECT t.*
    FROM form4_transactions t
    LEFT JOIN scores s ON t.id = s.transaction_id
    WHERE s.id IS NULL
    """
    
    transactions = pd.read_sql(query, engine)
    
    if transactions.empty:
        logger.info("No new transactions to score")
        return
        
    logger.info(f"Computing signals for {len(transactions)} transactions")
    
    # Process each transaction
    for _, trans in transactions.iterrows():
        try:
            # Compute individual signals
            signals = {
                'role_score': get_role_score(trans, engine),
                'trade_type_score': get_trade_type_score(trans),
                'size_score': get_size_score(trans, engine),
                'cluster_score': get_cluster_score(trans, engine),
                'catalyst_score': get_catalyst_score(trans, engine),
                'politician_score': get_politician_score(trans, engine)
            }
            
            # Calculate final score
            signals['final_score'] = calculate_final_score(signals)
            
            # Save scores
            save_scores(trans['id'], signals, engine)
            
            logger.info(
                f"Scored transaction {trans['id']} - "
                f"Final score: {signals['final_score']:.1f}"
            )
            
        except Exception as e:
            logger.error(f"Error scoring transaction {trans['id']}: {str(e)}")
            continue

def get_role_score(trans: pd.Series, engine: create_engine) -> float:
    """Score insider's role importance."""
    query = """
    SELECT current_title, is_officer, is_director 
    FROM insiders 
    WHERE id = :insider_id
    """
    
    insider = pd.read_sql(
        text(query),
        engine,
        params={'insider_id': trans['insider_id']}
    ).iloc[0]
    
    title = insider['current_title'].upper() if insider['current_title'] else ''
    
    if 'CEO' in title or 'CHIEF EXECUTIVE' in title:
        return WEIGHTS['role']['CEO']
    elif 'CFO' in title or 'CHIEF FINANCIAL' in title:
        return WEIGHTS['role']['CFO']
    elif insider['is_director']:
        return WEIGHTS['role']['Director']
    elif insider['is_officer'] or 'PRESIDENT' in title or 'VP' in title:
        return WEIGHTS['role']['Officer']
    else:
        return WEIGHTS['role']['Other']

def get_trade_type_score(trans: pd.Series) -> float:
    """Score the transaction type."""
    code = trans['transaction_type']
    return WEIGHTS['trade_type'].get(code, 0)

def get_size_score(trans: pd.Series, engine: create_engine) -> float:
    """Score the trade size."""
    value = trans['value']
    
    if value < THRESHOLDS['min_value']:
        return 0
        
    # Get percentile of this trade vs last 90 days
    query = """
    SELECT value 
    FROM form4_transactions
    WHERE transaction_date >= DATE(:date, '-90 days')
    """
    
    historical = pd.read_sql(
        text(query),
        engine,
        params={'date': trans['transaction_date']}
    )
    
    if not historical.empty:
        percentile = (historical['value'] < value).mean()
    else:
        percentile = 0.5
        
    # Score based on absolute and relative size
    abs_score = min(100, value / 1_000_000 * 20)  # $5M+ gets max score
    pct_score = percentile * 100
    
    return (abs_score + pct_score) / 2

def get_cluster_score(trans: pd.Series, engine: create_engine) -> float:
    """Score clustering of insider trades."""
    window = WINDOWS['cluster']
    query = """
    SELECT 
        COUNT(*) as num_trades,
        COUNT(DISTINCT insider_id) as num_insiders,
        SUM(CASE WHEN transaction_type LIKE 'P%' THEN 1 ELSE 0 END) as buys,
        SUM(CASE WHEN transaction_type LIKE 'S%' THEN 1 ELSE 0 END) as sells
    FROM form4_transactions
    WHERE company_cik = :company_cik
    AND transaction_date BETWEEN DATE(:date, :before) AND DATE(:date, :after)
    """
    
    cluster = pd.read_sql(
        text(query),
        engine,
        params={
            'company_cik': trans['company_cik'],
            'date': trans['transaction_date'],
            'before': f'-{window} days',
            'after': f'+{window} days'
        }
    ).iloc[0]
    
    if cluster['num_trades'] == 0:
        return 0
        
    # Score components
    trade_score = min(100, cluster['num_trades'] * 10)
    insider_score = min(100, cluster['num_insiders'] * 20)
    
    total = cluster['buys'] + cluster['sells']
    if total > 0:
        buy_ratio = cluster['buys'] / total
        ratio_score = buy_ratio * 100
    else:
        ratio_score = 0
        
    return (trade_score + insider_score + ratio_score) / 3

def get_catalyst_score(trans: pd.Series, engine: create_engine) -> float:
    """Score proximity to material events."""
    window = WINDOWS['catalyst']
    query = """
    SELECT 
        COUNT(*) as num_events,
        MIN(ABS(JULIANDAY(event_date) - JULIANDAY(:trade_date))) as days_to_event
    FROM form8k_events
    WHERE company_cik = :company_cik
    AND event_date BETWEEN DATE(:date, :before) AND DATE(:date, :after)
    """
    
    events = pd.read_sql(
        text(query),
        engine,
        params={
            'company_cik': trans['company_cik'],
            'trade_date': trans['transaction_date'],
            'date': trans['transaction_date'],
            'before': f'-{window} days',
            'after': f'+{window} days'
        }
    ).iloc[0]
    
    if events['num_events'] == 0:
        return 0
        
    # Score based on number of events and proximity
    event_score = min(100, events['num_events'] * 25)
    proximity_score = max(0, 100 * (1 - events['days_to_event'] / window))
    
    return (event_score + proximity_score) / 2

def get_politician_score(trans: pd.Series, engine: create_engine) -> float:
    """Score overlap with Congress trades."""
    window = WINDOWS['politician']
    query = """
    SELECT 
        COUNT(*) as num_trades,
        COUNT(DISTINCT representative) as num_reps,
        SUM(CASE WHEN transaction_type LIKE 'P%' THEN 1 ELSE 0 END) as buys,
        SUM(CASE WHEN transaction_type LIKE 'S%' THEN 1 ELSE 0 END) as sells
    FROM congress_trades
    WHERE ticker = (
        SELECT ticker FROM companies WHERE cik = :company_cik
    )
    AND transaction_date BETWEEN DATE(:date, :before) AND DATE(:date, :after)
    """
    
    politics = pd.read_sql(
        text(query),
        engine,
        params={
            'company_cik': trans['company_cik'],
            'date': trans['transaction_date'],
            'before': f'-{window} days',
            'after': f'+{window} days'
        }
    ).iloc[0]
    
    if politics['num_trades'] == 0:
        return 0
        
    # Score components
    trade_score = min(100, politics['num_trades'] * 25)
    rep_score = min(100, politics['num_reps'] * 33)  # 3+ reps = max score
    
    total = politics['buys'] + politics['sells']
    if total > 0:
        # Higher score if politicians are doing same type of trade
        insider_type = 'buys' if trans['transaction_type'].startswith('P') else 'sells'
        alignment = politics[insider_type] / total
        align_score = alignment * 100
    else:
        align_score = 0
        
    return (trade_score + rep_score + align_score) / 3

def calculate_final_score(signals: Dict[str, float]) -> float:
    """Calculate final 0-100 score from components."""
    # Base weights from config
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
        score_key = f"{signal}_score"
        if score_key in signals:
            score += signals[score_key] * weight
            
    return min(100, max(0, score))

def save_scores(
    transaction_id: int,
    signals: Dict[str, float],
    engine: create_engine
):
    """Save computed scores to database."""
    scores_df = pd.DataFrame([{
        'transaction_id': transaction_id,
        'role_score': signals['role_score'],
        'trade_type_score': signals['trade_type_score'],
        'size_score': signals['size_score'],
        'cluster_score': signals['cluster_score'],
        'catalyst_score': signals['catalyst_score'],
        'politician_score': signals['politician_score'],
        'final_score': signals['final_score']
    }])
    
    scores_df.to_sql('scores', engine, if_exists='append', index=False)

if __name__ == "__main__":
    compute_all_signals()
