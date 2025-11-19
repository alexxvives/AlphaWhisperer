#!/usr/bin/env python3
"""
Insider Trading Alert System

Monitors OpenInsider.com for significant insider trading activity and sends
email alerts when high-conviction signals are detected.

Author: Senior Python Engineer
Version: 1.0.0
"""

import argparse
import json
import logging
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import requests
import schedule
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Load environment variables
load_dotenv()

# Configure logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "insider_alerts.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# State management
STATE_DIR = Path("state")
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "seen_alerts.json"

# Configuration from environment
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_TO = os.getenv("ALERT_TO", "")

LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
CLUSTER_DAYS = int(os.getenv("CLUSTER_DAYS", "5"))
MIN_LARGE_BUY = float(os.getenv("MIN_LARGE_BUY", "250000"))
MIN_CEO_CFO_BUY = float(os.getenv("MIN_CEO_CFO_BUY", "100000"))
MIN_CLUSTER_BUY_VALUE = float(os.getenv("MIN_CLUSTER_BUY_VALUE", "300000"))
MIN_FIRST_BUY_12M = float(os.getenv("MIN_FIRST_BUY_12M", "50000"))
MIN_SECTOR_CLUSTER_VALUE = float(os.getenv("MIN_SECTOR_CLUSTER_VALUE", "1000000"))
MIN_BEARISH_CLUSTER_VALUE = float(os.getenv("MIN_BEARISH_CLUSTER_VALUE", "1000000"))

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# OpenInsider URL
OPENINSIDER_URL = "https://openinsider.com/latest-insider-trading"

# Title normalization mapping
TITLE_MAPPING = {
    "chief executive officer": "CEO",
    "chief exec officer": "CEO",
    "ceo": "CEO",
    "president and ceo": "CEO",
    "pres. & ceo": "CEO",
    "chief financial officer": "CFO",
    "chief fin officer": "CFO",
    "cfo": "CFO",
    "vp & cfo": "CFO",
    "chief operating officer": "COO",
    "coo": "COO",
    "chief technology officer": "CTO",
    "cto": "CTO",
    "director": "Director",
    "dir": "Director",
    "board member": "Director",
    "chairman": "Chairman",
    "chair": "Chairman",
    "president": "President",
    "pres": "President",
}


class InsiderAlert:
    """Represents an insider trading alert."""
    
    def __init__(
        self,
        signal_type: str,
        ticker: str,
        company_name: str,
        trades: pd.DataFrame,
        details: Dict,
    ):
        self.signal_type = signal_type
        self.ticker = ticker
        self.company_name = company_name
        self.trades = trades
        self.details = details
        self.alert_id = self._generate_alert_id()
        
    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        trade_str = "_".join([
            f"{row['Ticker']}_{row['Insider Name']}_{row['Trade Date']}"
            for _, row in self.trades.iterrows()
        ])
        return f"{self.signal_type}_{trade_str}"


@retry(
    retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def fetch_openinsider_html(url: str = OPENINSIDER_URL) -> str:
    """
    Fetch HTML content from OpenInsider with retry logic.
    
    Args:
        url: OpenInsider URL to fetch
        
    Returns:
        HTML content as string
        
    Raises:
        requests.RequestException: On request failure after retries
    """
    logger.info(f"Fetching data from {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    
    logger.info(f"Successfully fetched {len(response.text)} bytes")
    return response.text


def parse_openinsider_pandas(html: str) -> Optional[pd.DataFrame]:
    """
    Parse OpenInsider table using pandas.read_html (preferred method).
    
    Args:
        html: HTML content
        
    Returns:
        DataFrame of trades or None if parsing fails
    """
    try:
        logger.debug("Attempting pandas.read_html parsing")
        from io import StringIO
        tables = pd.read_html(StringIO(html))
        
        # Find table with expected columns
        expected_cols = ["Ticker", "Insider Name", "Trade Type"]
        
        for table in tables:
            # Normalize column names
            table.columns = [str(col).strip() for col in table.columns]
            
            # Check if this looks like the trades table
            if any(col in table.columns for col in expected_cols):
                logger.info(f"Found trades table with pandas: {len(table)} rows")
                return table
                
        logger.warning("No matching table found with pandas")
        return None
        
    except Exception as e:
        logger.warning(f"pandas.read_html failed: {e}")
        return None


def parse_openinsider_bs4(html: str) -> Optional[pd.DataFrame]:
    """
    Parse OpenInsider table using BeautifulSoup (fallback method).
    
    Args:
        html: HTML content
        
    Returns:
        DataFrame of trades or None if parsing fails
    """
    try:
        logger.debug("Attempting BeautifulSoup parsing")
        soup = BeautifulSoup(html, "lxml")
        
        # Find table with trade data
        # OpenInsider uses specific table structure
        table = soup.find("table", {"class": "tinytable"})
        
        if not table:
            # Try finding any table with expected headers
            for t in soup.find_all("table"):
                header_text = t.get_text().lower()
                if "ticker" in header_text and "insider name" in header_text:
                    table = t
                    break
        
        if not table:
            logger.warning("Could not find trades table with BeautifulSoup")
            return None
        
        # Extract headers
        headers = []
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        
        if not headers:
            logger.warning("Could not extract table headers")
            return None
        
        # Extract rows
        rows = []
        for tr in table.find_all("tr")[1:]:  # Skip header row
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        
        if not rows:
            logger.warning("No data rows found")
            return None
        
        # Create DataFrame
        df = pd.DataFrame(rows, columns=headers)
        logger.info(f"Parsed {len(df)} rows with BeautifulSoup")
        return df
        
    except Exception as e:
        logger.error(f"BeautifulSoup parsing failed: {e}")
        return None


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and clean the trades DataFrame.
    
    Args:
        df: Raw trades DataFrame
        
    Returns:
        Cleaned and normalized DataFrame
    """
    logger.debug(f"Normalizing DataFrame with {len(df)} rows")
    
    # Standardize column names
    column_mapping = {
        "X": "Filing Type",
        "Filing Date": "Filing Date",
        "Trade Date": "Trade Date",
        "Ticker": "Ticker",
        "Company Name": "Company Name",
        "Insider Name": "Insider Name",
        "Title": "Title",
        "Trade Type": "Trade Type",
        "Price": "Price",
        "Qty": "Qty",
        "Owned": "Owned",
        "ΔOwn": "Delta Own",
        "Value": "Value",
    }
    
    # Rename columns that exist
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)
    
    # Ensure required columns exist
    required_cols = ["Ticker", "Insider Name", "Trade Type", "Trade Date"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        logger.warning(f"Missing required columns: {missing_cols}")
        for col in missing_cols:
            df[col] = None
    
    # Clean and convert data types
    
    # Dates
    for date_col in ["Trade Date", "Filing Date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    
    # Numeric columns - remove commas and dollar signs
    numeric_cols = ["Price", "Qty", "Owned", "Value"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(r"[\$,]", "", regex=True)
                .str.replace(r"[^\d.-]", "", regex=True)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # Normalize trade types
    if "Trade Type" in df.columns:
        df["Trade Type"] = df["Trade Type"].str.strip().str.title()
        df["Trade Type"] = df["Trade Type"].replace({
            "P - Purchase": "Buy",
            "Purchase": "Buy",
            "S - Sale": "Sale",
            "S": "Sale",
            "P": "Buy",
        })
    
    # Normalize titles
    if "Title" in df.columns:
        df["Title Normalized"] = df["Title"].str.lower().map(TITLE_MAPPING)
        df["Title Normalized"] = df["Title Normalized"].fillna(df["Title"])
    else:
        df["Title Normalized"] = None
    
    # Filter out invalid trade types
    valid_types = ["Buy", "Sale"]
    if "Trade Type" in df.columns:
        before_count = len(df)
        df = df[df["Trade Type"].isin(valid_types)].copy()
        after_count = len(df)
        if before_count != after_count:
            logger.info(f"Filtered out {before_count - after_count} rows with invalid trade types")
    
    # Remove rows with missing critical data
    before_count = len(df)
    df = df.dropna(subset=["Ticker", "Trade Date", "Trade Type"])
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Removed {before_count - after_count} rows with missing critical data")
    
    # Check for 10b5-1 planned trades
    if "Filing Type" in df.columns:
        df["Is_Planned"] = df["Filing Type"].str.contains("10b5-1", case=False, na=False)
    else:
        df["Is_Planned"] = False
    
    # Create unique key for de-duplication
    df["Unique_Key"] = (
        df["Ticker"].astype(str) + "_" +
        df["Insider Name"].astype(str) + "_" +
        df["Trade Date"].astype(str) + "_" +
        df["Trade Type"].astype(str) + "_" +
        df["Qty"].astype(str) + "_" +
        df["Price"].astype(str)
    )
    
    # Remove duplicates
    before_count = len(df)
    df = df.drop_duplicates(subset=["Unique_Key"], keep="first")
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Removed {before_count - after_count} duplicate rows")
    
    # Filter out planned trades
    before_count = len(df)
    df = df[~df["Is_Planned"]].copy()
    after_count = len(df)
    if before_count != after_count:
        logger.info(f"Filtered out {before_count - after_count} planned (10b5-1) trades")
    
    logger.info(f"Normalized DataFrame: {len(df)} rows remain")
    return df


def parse_openinsider(html: str) -> pd.DataFrame:
    """
    Parse OpenInsider HTML with fallback methods.
    
    Args:
        html: HTML content from OpenInsider
        
    Returns:
        Normalized DataFrame of trades
        
    Raises:
        ValueError: If parsing fails with all methods
    """
    # Try pandas first (faster and more reliable)
    df = parse_openinsider_pandas(html)
    
    # Fall back to BeautifulSoup if pandas fails
    if df is None:
        df = parse_openinsider_bs4(html)
    
    if df is None:
        raise ValueError("Failed to parse OpenInsider table with all methods")
    
    # Normalize the data
    df = normalize_dataframe(df)
    
    return df


def filter_by_lookback(df: pd.DataFrame, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Filter trades to only include those within the lookback window.
    
    Args:
        df: Trades DataFrame
        lookback_days: Number of days to look back
        
    Returns:
        Filtered DataFrame
    """
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    filtered = df[df["Trade Date"] >= cutoff_date].copy()
    logger.info(f"Filtered to {len(filtered)} trades within {lookback_days} days")
    return filtered


def detect_cluster_buying(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect cluster buying: ≥3 insiders from same ticker buy within cluster window,
    total value ≥ MIN_CLUSTER_BUY_VALUE.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Filter to buys only
    buys = df[df["Trade Type"] == "Buy"].copy()
    
    if buys.empty:
        return alerts
    
    # Group by ticker
    for ticker in buys["Ticker"].unique():
        ticker_buys = buys[buys["Ticker"] == ticker].sort_values("Trade Date")
        
        # Check rolling window
        for i, row in ticker_buys.iterrows():
            window_start = row["Trade Date"] - timedelta(days=CLUSTER_DAYS)
            window_end = row["Trade Date"]
            
            window_trades = ticker_buys[
                (ticker_buys["Trade Date"] >= window_start) &
                (ticker_buys["Trade Date"] <= window_end)
            ]
            
            # Check if cluster criteria met
            unique_insiders = window_trades["Insider Name"].nunique()
            total_value = window_trades["Value"].sum()
            
            if unique_insiders >= 3 and total_value >= MIN_CLUSTER_BUY_VALUE:
                company_name = window_trades["Company Name"].iloc[0] if "Company Name" in window_trades.columns else ticker
                
                alert = InsiderAlert(
                    signal_type="Cluster Buying",
                    ticker=ticker,
                    company_name=company_name,
                    trades=window_trades,
                    details={
                        "num_insiders": unique_insiders,
                        "total_value": total_value,
                        "window_days": CLUSTER_DAYS,
                        "window_start": window_start,
                        "window_end": window_end,
                    }
                )
                alerts.append(alert)
                break  # Only alert once per ticker
    
    logger.info(f"Detected {len(alerts)} cluster buying signals")
    return alerts


def detect_ceo_cfo_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect CEO/CFO buy: Any CEO or CFO buys ≥ MIN_CEO_CFO_BUY.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Filter to CEO/CFO buys
    exec_buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Title Normalized"].isin(["CEO", "CFO"])) &
        (df["Value"] >= MIN_CEO_CFO_BUY)
    ].copy()
    
    for _, row in exec_buys.iterrows():
        company_name = row.get("Company Name", row["Ticker"])
        
        alert = InsiderAlert(
            signal_type="CEO/CFO Buy",
            ticker=row["Ticker"],
            company_name=company_name,
            trades=pd.DataFrame([row]),
            details={
                "insider": row["Insider Name"],
                "title": row["Title Normalized"],
                "value": row["Value"],
                "trade_date": row["Trade Date"],
            }
        )
        alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} CEO/CFO buy signals")
    return alerts


def detect_large_single_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect large single buy: Any insider buys ≥ MIN_LARGE_BUY.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    large_buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Value"] >= MIN_LARGE_BUY)
    ].copy()
    
    for _, row in large_buys.iterrows():
        company_name = row.get("Company Name", row["Ticker"])
        
        alert = InsiderAlert(
            signal_type="Large Single Buy",
            ticker=row["Ticker"],
            company_name=company_name,
            trades=pd.DataFrame([row]),
            details={
                "insider": row["Insider Name"],
                "title": row.get("Title Normalized", row.get("Title", "Unknown")),
                "value": row["Value"],
                "trade_date": row["Trade Date"],
                "qty": row["Qty"],
                "price": row["Price"],
            }
        )
        alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} large single buy signals")
    return alerts


def detect_first_buy_12m(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect first buy in 12 months: Insider's first purchase in 365 days, ≥ MIN_FIRST_BUY_12M.
    
    Note: This requires historical data. We'll check if this is the only buy for this
    insider+ticker combination in our dataset.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    buys = df[
        (df["Trade Type"] == "Buy") &
        (df["Value"] >= MIN_FIRST_BUY_12M)
    ].copy()
    
    # Group by ticker and insider
    for (ticker, insider), group in buys.groupby(["Ticker", "Insider Name"]):
        # Check if this is the only buy in our dataset (proxy for first in 12m)
        all_buys_for_insider = df[
            (df["Ticker"] == ticker) &
            (df["Insider Name"] == insider) &
            (df["Trade Type"] == "Buy")
        ]
        
        if len(all_buys_for_insider) == 1:
            row = group.iloc[0]
            company_name = row.get("Company Name", ticker)
            
            alert = InsiderAlert(
                signal_type="First Buy in 12 Months",
                ticker=ticker,
                company_name=company_name,
                trades=pd.DataFrame([row]),
                details={
                    "insider": insider,
                    "title": row.get("Title Normalized", row.get("Title", "Unknown")),
                    "value": row["Value"],
                    "trade_date": row["Trade Date"],
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} first buy in 12 months signals")
    return alerts


def detect_bearish_cluster_selling(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect bearish cluster selling: ≥3 insiders from same ticker sell within cluster window,
    total value ≥ MIN_BEARISH_CLUSTER_VALUE.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Filter to sales only
    sales = df[df["Trade Type"] == "Sale"].copy()
    
    if sales.empty:
        return alerts
    
    # Group by ticker
    for ticker in sales["Ticker"].unique():
        ticker_sales = sales[sales["Ticker"] == ticker].sort_values("Trade Date")
        
        # Check rolling window
        for i, row in ticker_sales.iterrows():
            window_start = row["Trade Date"] - timedelta(days=CLUSTER_DAYS)
            window_end = row["Trade Date"]
            
            window_trades = ticker_sales[
                (ticker_sales["Trade Date"] >= window_start) &
                (ticker_sales["Trade Date"] <= window_end)
            ]
            
            # Check if cluster criteria met
            unique_insiders = window_trades["Insider Name"].nunique()
            total_value = window_trades["Value"].sum()
            
            if unique_insiders >= 3 and total_value >= MIN_BEARISH_CLUSTER_VALUE:
                company_name = window_trades["Company Name"].iloc[0] if "Company Name" in window_trades.columns else ticker
                
                alert = InsiderAlert(
                    signal_type="Bearish Cluster Selling",
                    ticker=ticker,
                    company_name=company_name,
                    trades=window_trades,
                    details={
                        "num_insiders": unique_insiders,
                        "total_value": total_value,
                        "window_days": CLUSTER_DAYS,
                        "window_start": window_start,
                        "window_end": window_end,
                    }
                )
                alerts.append(alert)
                break  # Only alert once per ticker
    
    logger.info(f"Detected {len(alerts)} bearish cluster selling signals")
    return alerts


def detect_signals(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Run all signal detection functions.
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of all InsiderAlert objects
    """
    logger.info("Running signal detection")
    
    all_alerts = []
    
    # Run each detector
    all_alerts.extend(detect_cluster_buying(df))
    all_alerts.extend(detect_ceo_cfo_buy(df))
    all_alerts.extend(detect_large_single_buy(df))
    all_alerts.extend(detect_first_buy_12m(df))
    all_alerts.extend(detect_bearish_cluster_selling(df))
    
    logger.info(f"Total signals detected: {len(all_alerts)}")
    return all_alerts


def load_seen_alerts() -> Set[str]:
    """Load set of previously seen alert IDs."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("seen_alerts", []))
        except Exception as e:
            logger.warning(f"Could not load state file: {e}")
    return set()


def save_seen_alerts(seen: Set[str]):
    """Save set of seen alert IDs."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"seen_alerts": list(seen)}, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save state file: {e}")


def format_email_html(alert: InsiderAlert) -> str:
    """
    Format alert as HTML email body.
    
    Args:
        alert: InsiderAlert object
        
    Returns:
        HTML string
    """
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            h2 {{ color: #2c3e50; }}
            .summary {{ background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .summary-item {{ margin: 5px 0; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th {{ background-color: #3498db; color: white; padding: 10px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 8px; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #7f8c8d; }}
        </style>
    </head>
    <body>
        <h2>🚨 Insider Alert: {alert.signal_type}</h2>
        
        <div class="summary">
            <div class="summary-item"><strong>Ticker:</strong> {alert.ticker}</div>
            <div class="summary-item"><strong>Company:</strong> {alert.company_name}</div>
            <div class="summary-item"><strong>Signal:</strong> {alert.signal_type}</div>
            <div class="summary-item"><strong>Alert Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    """
    
    # Add signal-specific details
    if "num_insiders" in alert.details:
        html += f"""
            <div class="summary-item"><strong>Number of Insiders:</strong> {alert.details['num_insiders']}</div>
            <div class="summary-item"><strong>Total Value:</strong> ${alert.details['total_value']:,.2f}</div>
            <div class="summary-item"><strong>Window:</strong> {alert.details['window_days']} days</div>
        """
    elif "value" in alert.details:
        html += f"""
            <div class="summary-item"><strong>Insider:</strong> {alert.details['insider']}</div>
            <div class="summary-item"><strong>Title:</strong> {alert.details['title']}</div>
            <div class="summary-item"><strong>Value:</strong> ${alert.details['value']:,.2f}</div>
        """
    
    html += """
        </div>
        
        <h3>Trade Details</h3>
        <table>
            <tr>
                <th>Date</th>
                <th>Insider</th>
                <th>Title</th>
                <th>Type</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Value</th>
            </tr>
    """
    
    # Add trade rows
    for _, row in alert.trades.iterrows():
        trade_date = row["Trade Date"].strftime('%Y-%m-%d') if pd.notna(row["Trade Date"]) else "N/A"
        qty = f"{row['Qty']:,.0f}" if pd.notna(row['Qty']) else "N/A"
        price = f"${row['Price']:,.2f}" if pd.notna(row['Price']) else "N/A"
        value = f"${row['Value']:,.2f}" if pd.notna(row['Value']) else "N/A"
        title = row.get("Title", "Unknown")
        
        html += f"""
            <tr>
                <td>{trade_date}</td>
                <td>{row['Insider Name']}</td>
                <td>{title}</td>
                <td>{row['Trade Type']}</td>
                <td>{qty}</td>
                <td>{price}</td>
                <td>{value}</td>
            </tr>
        """
    
    html += f"""
        </table>
        
        <p><a href="{OPENINSIDER_URL}">View on OpenInsider</a></p>
        
        <div class="footer">
            <p>This alert was generated by the Insider Trading Alert System.</p>
            <p>Alert ID: {alert.alert_id}</p>
        </div>
    </body>
    </html>
    """
    
    return html


def format_email_text(alert: InsiderAlert) -> str:
    """
    Format alert as plain text email body.
    
    Args:
        alert: InsiderAlert object
        
    Returns:
        Plain text string
    """
    text = f"""
INSIDER ALERT: {alert.signal_type}
{'=' * 60}

Ticker: {alert.ticker}
Company: {alert.company_name}
Signal: {alert.signal_type}
Alert Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    # Add signal-specific details
    if "num_insiders" in alert.details:
        text += f"""
Number of Insiders: {alert.details['num_insiders']}
Total Value: ${alert.details['total_value']:,.2f}
Window: {alert.details['window_days']} days
"""
    elif "value" in alert.details:
        text += f"""
Insider: {alert.details['insider']}
Title: {alert.details['title']}
Value: ${alert.details['value']:,.2f}
"""
    
    text += "\nTRADE DETAILS:\n" + "=" * 60 + "\n"
    
    # Add trade rows
    for _, row in alert.trades.iterrows():
        trade_date = row["Trade Date"].strftime('%Y-%m-%d') if pd.notna(row["Trade Date"]) else "N/A"
        qty = f"{row['Qty']:,.0f}" if pd.notna(row['Qty']) else "N/A"
        price = f"${row['Price']:,.2f}" if pd.notna(row['Price']) else "N/A"
        value = f"${row['Value']:,.2f}" if pd.notna(row['Value']) else "N/A"
        
        text += f"""
Date: {trade_date}
Insider: {row['Insider Name']}
Title: {row.get('Title', 'Unknown')}
Type: {row['Trade Type']}
Qty: {qty} @ {price} = {value}
---
"""
    
    text += f"""
View on OpenInsider: {OPENINSIDER_URL}

Alert ID: {alert.alert_id}
"""
    
    return text


def send_email_alert(alert: InsiderAlert, dry_run: bool = False) -> bool:
    """
    Send email alert for detected signal.
    
    Args:
        alert: InsiderAlert object
        dry_run: If True, log email but don't send
        
    Returns:
        True if email sent successfully
    """
    subject = f"[Insider Alert] {alert.ticker} — {alert.signal_type}"
    
    # Format email body
    text_body = format_email_text(alert)
    html_body = format_email_html(alert)
    
    if dry_run:
        logger.info(f"DRY RUN - Would send email: {subject}")
        logger.debug(f"Email body:\n{text_body}")
        return True
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_TO
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def process_alerts(alerts: List[InsiderAlert], dry_run: bool = False):
    """
    Process list of alerts: check if new, send emails, update state.
    
    Args:
        alerts: List of InsiderAlert objects
        dry_run: If True, don't send emails or update state
    """
    if not alerts:
        logger.info("No alerts to process")
        return
    
    # Load seen alerts
    seen_alerts = load_seen_alerts()
    
    new_alerts = []
    for alert in alerts:
        if alert.alert_id not in seen_alerts:
            new_alerts.append(alert)
            seen_alerts.add(alert.alert_id)
    
    logger.info(f"Found {len(new_alerts)} new alerts (out of {len(alerts)} total)")
    
    # Send emails for new alerts
    for alert in new_alerts:
        send_email_alert(alert, dry_run=dry_run)
    
    # Save updated state
    if not dry_run and new_alerts:
        save_seen_alerts(seen_alerts)


def run_once(since_date: Optional[str] = None, dry_run: bool = False, verbose: bool = False):
    """
    Run a single check for insider trading alerts.
    
    Args:
        since_date: Optional date string (YYYY-MM-DD) to filter trades
        dry_run: If True, don't send emails
        verbose: If True, enable debug logging
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 60)
    logger.info("Starting insider trading alert check")
    logger.info("=" * 60)
    
    try:
        # Fetch data
        html = fetch_openinsider_html()
        
        # Parse data
        df = parse_openinsider(html)
        
        # Filter by date
        if since_date:
            since_dt = datetime.strptime(since_date, "%Y-%m-%d")
            df = df[df["Trade Date"] >= since_dt]
            logger.info(f"Filtered to trades since {since_date}: {len(df)} rows")
        else:
            df = filter_by_lookback(df)
        
        # Detect signals
        alerts = detect_signals(df)
        
        # Process alerts
        process_alerts(alerts, dry_run=dry_run)
        
        logger.info("Check completed successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during check: {e}", exc_info=True)
        raise


def run_loop(interval_minutes: int = 30, dry_run: bool = False, verbose: bool = False):
    """
    Run continuous monitoring with scheduled checks.
    
    Args:
        interval_minutes: Minutes between checks
        dry_run: If True, don't send emails
        verbose: If True, enable debug logging
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"Starting continuous monitoring (every {interval_minutes} minutes)")
    logger.info("Press Ctrl+C to stop")
    
    # Schedule job
    schedule.every(interval_minutes).minutes.do(
        run_once,
        since_date=None,
        dry_run=dry_run,
        verbose=verbose
    )
    
    # Run immediately on start
    run_once(since_date=None, dry_run=dry_run, verbose=verbose)
    
    # Keep running
    try:
        while True:
            schedule.run_pending()
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Insider Trading Alert System - Monitor OpenInsider for high-conviction signals"
    )
    
    # Run mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit"
    )
    mode_group.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously with scheduled checks"
    )
    
    # Options
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=30,
        help="Minutes between checks in loop mode (default: 30)"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only process trades since this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't send emails, only log alerts"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not args.dry_run and not all([SMTP_USER, SMTP_PASS, ALERT_TO]):
        logger.error("Email configuration missing. Set SMTP_USER, SMTP_PASS, and ALERT_TO in .env")
        sys.exit(1)
    
    # Run appropriate mode
    try:
        if args.once:
            run_once(
                since_date=args.since,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
        else:  # loop
            run_loop(
                interval_minutes=args.interval_minutes,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
