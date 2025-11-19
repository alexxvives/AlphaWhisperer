"""Streamlit dashboard for insider trading analytics."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sqlalchemy import create_engine

from ..config import DATABASE_URL, THRESHOLDS
from ..processing.scoring import calculate_final_score

# Page config
st.set_page_config(
    page_title="InvestorAI Dashboard",
    page_icon="📈",
    layout="wide"
)

# Database connection
@st.cache_resource
def get_db_connection():
    return create_engine(DATABASE_URL)

# Data loading
@st.cache_data(ttl=3600)
def load_recent_trades(days: int = 30):
    engine = get_db_connection()
    query = f"""
    SELECT t.*, 
           s.role_score,
           s.trade_type_score,
           s.size_score,
           s.cluster_score,
           s.catalyst_score,
           s.politician_score,
           s.final_score
    FROM form4_transactions t
    JOIN scores s ON t.id = s.transaction_id
    WHERE t.transaction_date >= DATE('now', '-{days} days')
    ORDER BY s.final_score DESC
    """
    return pd.read_sql(query, engine)

# Sidebar filters
st.sidebar.header("Filters")

# Date range
days = st.sidebar.slider(
    "Days Lookback",
    min_value=7,
    max_value=365,
    value=30
)

# Score threshold
min_score = st.sidebar.slider(
    "Minimum Score",
    min_value=0,
    max_value=100,
    value=THRESHOLDS['min_score']
)

# Load data
df = load_recent_trades(days)
filtered_df = df[df['final_score'] >= min_score]

# Main content
st.title("InvestorAI Dashboard")

# Key metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Signals",
        len(filtered_df)
    )
    
with col2:
    st.metric(
        "Avg Score",
        f"{filtered_df['final_score'].mean():.1f}"
    )
    
with col3:
    st.metric(
        "Total Value",
        f"${filtered_df['value'].sum():,.0f}"
    )
    
with col4:
    buy_ratio = len(filtered_df[filtered_df['transaction_type'].str.startswith('P')]) / len(filtered_df)
    st.metric(
        "Buy Ratio",
        f"{buy_ratio:.1%}"
    )

# Top signals table
st.header("Top Signals")
st.dataframe(
    filtered_df[[
        'transaction_date',
        'issuer_ticker',
        'insider_name',
        'insider_title',
        'transaction_type',
        'shares',
        'price',
        'value',
        'final_score'
    ]].style.format({
        'price': '${:.2f}',
        'value': '${:,.0f}',
        'final_score': '{:.1f}'
    })
)

# Score distribution
st.header("Score Distribution")
fig = px.histogram(
    filtered_df,
    x='final_score',
    nbins=20,
    title="Distribution of Signal Scores"
)
st.plotly_chart(fig)

# Signal components
st.header("Signal Components")
scores_df = filtered_df[[
    'role_score',
    'trade_type_score', 
    'size_score',
    'cluster_score',
    'catalyst_score',
    'politician_score'
]].mean()

fig = go.Figure(data=[
    go.Bar(
        x=scores_df.index,
        y=scores_df.values,
        text=[f"{x:.1f}" for x in scores_df.values],
        textposition='auto',
    )
])
fig.update_layout(
    title="Average Signal Component Scores",
    xaxis_title="Signal Component",
    yaxis_title="Score (0-100)"
)
st.plotly_chart(fig)

# Top tickers
st.header("Most Active Tickers")
ticker_stats = filtered_df.groupby('issuer_ticker').agg({
    'final_score': ['count', 'mean'],
    'value': 'sum'
}).round(1)
ticker_stats.columns = ['Num Signals', 'Avg Score', 'Total Value']
st.dataframe(ticker_stats.sort_values('Num Signals', ascending=False))
