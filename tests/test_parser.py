"""
Tests for insider_alerts.py

Run with: python -m pytest tests/test_parser.py -v
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest
from insider_alerts import (
    detect_bearish_cluster_selling,
    detect_ceo_cfo_buy,
    detect_cluster_buying,
    detect_first_buy_12m,
    detect_large_single_buy,
    normalize_dataframe,
    parse_openinsider_bs4,
    parse_openinsider_pandas,
)


@pytest.fixture
def sample_html():
    """Load sample HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_openinsider.html"
    with open(fixture_path, "r") as f:
        return f.read()


@pytest.fixture
def parsed_df(sample_html):
    """Parse sample HTML into DataFrame."""
    # Try pandas first
    df = parse_openinsider_pandas(sample_html)
    if df is None:
        df = parse_openinsider_bs4(sample_html)
    
    assert df is not None, "Failed to parse sample HTML"
    
    # Normalize
    df = normalize_dataframe(df)
    return df


def test_parse_with_pandas(sample_html):
    """Test parsing with pandas.read_html."""
    df = parse_openinsider_pandas(sample_html)
    
    assert df is not None
    assert len(df) > 0
    assert "Ticker" in df.columns or "ticker" in df.columns.str.lower()


def test_parse_with_bs4(sample_html):
    """Test parsing with BeautifulSoup fallback."""
    df = parse_openinsider_bs4(sample_html)
    
    assert df is not None
    assert len(df) > 0
    assert len(df.columns) > 0


def test_normalize_dataframe(sample_html):
    """Test data normalization and cleaning."""
    # Parse first
    df = parse_openinsider_pandas(sample_html)
    if df is None:
        df = parse_openinsider_bs4(sample_html)
    
    # Normalize
    df_normalized = normalize_dataframe(df)
    
    # Check required columns exist
    assert "Ticker" in df_normalized.columns
    assert "Trade Type" in df_normalized.columns
    assert "Trade Date" in df_normalized.columns
    assert "Unique_Key" in df_normalized.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_any_dtype(df_normalized["Trade Date"])
    assert pd.api.types.is_numeric_dtype(df_normalized["Value"])
    assert pd.api.types.is_numeric_dtype(df_normalized["Qty"])
    
    # Check trade type normalization
    assert set(df_normalized["Trade Type"].unique()).issubset({"Buy", "Sale"})
    
    # Check no duplicates
    assert len(df_normalized) == df_normalized["Unique_Key"].nunique()


def test_filter_planned_trades(parsed_df):
    """Test that 10b5-1 planned trades are filtered out."""
    # AMZN sale should be filtered (10b5-1 in fixture)
    amzn_trades = parsed_df[parsed_df["Ticker"] == "AMZN"]
    assert len(amzn_trades) == 0, "10b5-1 planned trades should be filtered"


def test_filter_duplicates(sample_html):
    """Test that duplicate entries are removed."""
    # AAPL CEO buy appears twice in fixture
    df = parse_openinsider_pandas(sample_html)
    if df is None:
        df = parse_openinsider_bs4(sample_html)
    df_normalized = normalize_dataframe(df)
    
    aapl_cook = df_normalized[
        (df_normalized["Ticker"] == "AAPL") &
        (df_normalized["Insider Name"].str.contains("Cook", case=False, na=False))
    ]
    
    # Should only be one entry after deduplication
    assert len(aapl_cook) == 1, "Duplicate trades should be removed"


def test_detect_cluster_buying(parsed_df):
    """Test cluster buying detection (≥3 insiders, same ticker, ≥$300k)."""
    alerts = detect_cluster_buying(parsed_df)
    
    # Should detect MSFT cluster (3 insiders, total ~$400k)
    msft_alerts = [a for a in alerts if a.ticker == "MSFT"]
    assert len(msft_alerts) > 0, "Should detect MSFT cluster buying"
    
    if msft_alerts:
        alert = msft_alerts[0]
        assert alert.signal_type == "Cluster Buying"
        assert alert.details["num_insiders"] >= 3
        assert alert.details["total_value"] >= 300000


def test_detect_ceo_cfo_buy(parsed_df):
    """Test CEO/CFO buy detection (≥$100k)."""
    alerts = detect_ceo_cfo_buy(parsed_df)
    
    # Should detect AAPL CEO buy ($150k)
    aapl_alerts = [a for a in alerts if a.ticker == "AAPL"]
    assert len(aapl_alerts) > 0, "Should detect AAPL CEO buy"
    
    # Should NOT detect META CEO buy (only $3.5k)
    meta_alerts = [a for a in alerts if a.ticker == "META"]
    assert len(meta_alerts) == 0, "Should not detect small META CEO buy"


def test_detect_large_single_buy(parsed_df):
    """Test large single buy detection (≥$250k)."""
    alerts = detect_large_single_buy(parsed_df)
    
    # Should detect GOOGL buy ($280k)
    googl_alerts = [a for a in alerts if a.ticker == "GOOGL"]
    assert len(googl_alerts) > 0, "Should detect GOOGL large buy"
    
    if googl_alerts:
        alert = googl_alerts[0]
        assert alert.details["value"] >= 250000


def test_detect_first_buy_12m(parsed_df):
    """Test first buy in 12 months detection."""
    alerts = detect_first_buy_12m(parsed_df)
    
    # TSLA should trigger (only buy for Musk, >$50k)
    tsla_alerts = [a for a in alerts if a.ticker == "TSLA"]
    assert len(tsla_alerts) > 0, "Should detect TSLA first buy"


def test_detect_bearish_cluster_selling(parsed_df):
    """Test bearish cluster selling (≥3 insiders, ≥$1M total)."""
    alerts = detect_bearish_cluster_selling(parsed_df)
    
    # NFLX should trigger (3 insiders, ~$1.49M total)
    nflx_alerts = [a for a in alerts if a.ticker == "NFLX"]
    assert len(nflx_alerts) > 0, "Should detect NFLX bearish cluster"
    
    if nflx_alerts:
        alert = nflx_alerts[0]
        assert alert.signal_type == "Bearish Cluster Selling"
        assert alert.details["num_insiders"] >= 3
        assert alert.details["total_value"] >= 1000000


def test_title_normalization(parsed_df):
    """Test that titles are properly normalized."""
    # Check that various CEO formats are normalized
    ceo_titles = parsed_df[parsed_df["Title Normalized"] == "CEO"]
    assert len(ceo_titles) > 0, "Should have normalized CEO titles"
    
    # Check that various CFO formats are normalized
    cfo_titles = parsed_df[parsed_df["Title Normalized"] == "CFO"]
    assert len(cfo_titles) > 0, "Should have normalized CFO titles"


def test_value_parsing(parsed_df):
    """Test that dollar values are correctly parsed."""
    # All values should be numeric
    assert parsed_df["Value"].dtype in [float, int, "float64", "int64"]
    
    # Values should be reasonable (no commas, dollar signs, etc.)
    assert parsed_df["Value"].min() >= 0
    assert parsed_df["Value"].max() < 1e9  # Sanity check


def test_empty_dataframe_handling():
    """Test that signal detectors handle empty DataFrames gracefully."""
    empty_df = pd.DataFrame(columns=[
        "Ticker", "Trade Type", "Trade Date", "Value", 
        "Insider Name", "Title Normalized", "Qty", "Price", "Company Name"
    ])
    
    # Should return empty lists, not crash
    assert detect_cluster_buying(empty_df) == []
    assert detect_ceo_cfo_buy(empty_df) == []
    assert detect_large_single_buy(empty_df) == []
    assert detect_first_buy_12m(empty_df) == []
    assert detect_bearish_cluster_selling(empty_df) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
