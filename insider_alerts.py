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

# Telegram Configuration (optional)
USE_TELEGRAM = os.getenv("USE_TELEGRAM", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # Comma-separated for multiple accounts

# News API Configuration (optional - for context enrichment)
USE_NEWS_CONTEXT = os.getenv("USE_NEWS_CONTEXT", "false").lower() == "true"
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Congressional Trading (CapitolTrades)
USE_CAPITOL_TRADES = os.getenv("USE_CAPITOL_TRADES", "true").lower() == "true"
MIN_CONGRESSIONAL_CLUSTER = int(os.getenv("MIN_CONGRESSIONAL_CLUSTER", "2"))
CONGRESSIONAL_LOOKBACK_DAYS = int(os.getenv("CONGRESSIONAL_LOOKBACK_DAYS", "7"))

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


def get_company_context(ticker: str) -> Dict[str, any]:
    """
    Get comprehensive company context including financials, price action, and news.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary with company context or empty dict if error
    """
    context = {
        "description": None,
        "sector": None,
        "industry": None,
        "market_cap": None,
        "pe_ratio": None,
        "short_interest": None,
        "price_change_5d": None,
        "price_change_1m": None,
        "current_price": None,
        "week_52_high": None,
        "week_52_low": None,
        "distance_from_52w_high": None,
        "distance_from_52w_low": None,
        "news": [],
        "congressional_trades": []
    }
    
    try:
        import yfinance as yf
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Company info
        context["description"] = info.get("longBusinessSummary", "")
        context["sector"] = info.get("sector", "")
        context["industry"] = info.get("industry", "")
        context["market_cap"] = info.get("marketCap")
        context["pe_ratio"] = info.get("trailingPE")
        context["short_interest"] = info.get("shortPercentOfFloat")
        
        # 52-week range
        context["week_52_high"] = info.get("fiftyTwoWeekHigh")
        context["week_52_low"] = info.get("fiftyTwoWeekLow")
        context["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        
        # Calculate distance from 52w high/low
        if context["current_price"] and context["week_52_high"]:
            context["distance_from_52w_high"] = ((context["current_price"] - context["week_52_high"]) / context["week_52_high"]) * 100
        
        if context["current_price"] and context["week_52_low"]:
            context["distance_from_52w_low"] = ((context["current_price"] - context["week_52_low"]) / context["week_52_low"]) * 100
        
        # Get historical data for price changes
        try:
            hist = stock.history(period="1mo")
            if not hist.empty and len(hist) > 0:
                # 5-day change
                if len(hist) >= 5:
                    price_5d_ago = hist['Close'].iloc[-6] if len(hist) > 5 else hist['Close'].iloc[0]
                    current = hist['Close'].iloc[-1]
                    context["price_change_5d"] = ((current - price_5d_ago) / price_5d_ago) * 100
                
                # 1-month change
                price_1m_ago = hist['Close'].iloc[0]
                current = hist['Close'].iloc[-1]
                context["price_change_1m"] = ((current - price_1m_ago) / price_1m_ago) * 100
        except Exception as e:
            logger.warning(f"Could not fetch price history for {ticker}: {e}")
        
        logger.info(f"Fetched company info for {ticker}")
        
    except Exception as e:
        logger.warning(f"Could not fetch company info for {ticker}: {e}")
    
    # Get news if enabled
    if USE_NEWS_CONTEXT and NEWS_API_KEY:
        try:
            from newsapi import NewsApiClient
            
            newsapi = NewsApiClient(api_key=NEWS_API_KEY)
            
            # Search for company news (last 7 days)
            response = newsapi.get_everything(
                q=f"{ticker}",
                language='en',
                sort_by='relevancy',
                page_size=3,
                from_param=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            )
            
            if response.get('articles'):
                context["news"] = [
                    {
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("url", ""),
                        "published_at": article.get("publishedAt", "")
                    }
                    for article in response['articles'][:3]
                ]
                logger.info(f"Fetched {len(context['news'])} news articles for {ticker}")
        
        except Exception as e:
            logger.warning(f"Could not fetch news for {ticker}: {e}")
    
    # Get congressional trades
    context["congressional_trades"] = get_congressional_trades(ticker)
    
    return context


def get_congressional_trades(ticker: str = None) -> List[Dict]:
    """
    Scrape recent Congressional trades from CapitolTrades.
    Uses Selenium to render JavaScript content.
    
    Returns ALL recent trades (not filtered by ticker) - provides broader market context
    about what politicians are buying/selling.
    
    Args:
        ticker: Not used - kept for API compatibility
        
    Returns:
        List of all recent congressional trades with politician info and tickers
    """
    if not USE_CAPITOL_TRADES:
        return []
    
    trades = []
    driver = None
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        import time
        
        # Configure Chrome for headless mode (runs in background without window)
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Initialize Chrome driver (webdriver-manager handles driver download automatically)
        logger.info(f"Fetching recent Congressional trades...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(15)
        
        # Visit general trades page - shows most recent trades across all stocks
        url = "https://www.capitoltrades.com/trades"
        driver.get(url)
        
        # Wait for page to load and JavaScript to render
        time.sleep(4)
        
        # Get rendered HTML
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Find all table rows
        all_rows = soup.find_all('tr')
        
        for row in all_rows:
            try:
                # Extract politician name from link
                politician_link = row.find('a', href=lambda x: x and '/politicians/' in str(x))
                if not politician_link:
                    continue
                
                politician_name = politician_link.get_text(strip=True)
                
                # Get row text
                row_text = row.get_text()
                
                # Extract party and chamber from row
                party_chamber = ""
                if 'Republican' in row_text:
                    party_chamber = " (R)"
                elif 'Democrat' in row_text:
                    party_chamber = " (D)"
                
                if 'House' in row_text:
                    party_chamber += "-House"
                elif 'Senate' in row_text:
                    party_chamber += "-Senate"
                
                # Determine transaction type
                if 'buy' in row_text.lower() or 'purchase' in row_text.lower():
                    trade_type = 'BUY'
                elif 'sell' in row_text.lower() or 'sale' in row_text.lower():
                    trade_type = 'SELL'
                else:
                    continue
                
                # Extract ticker symbol - look for issuer link
                ticker_found = None
                issuer_link = row.find('a', href=lambda x: x and '/issuers/' in str(x))
                if issuer_link:
                    # Get ticker from the issuer text (often format: "Company Name TICK:US")
                    issuer_text = issuer_link.get_text(strip=True)
                    import re
                    # Look for ticker:exchange pattern first (e.g., "MMM:US", "FI:US")
                    ticker_match = re.search(r'([A-Z]{1,5}):(?:US|NYSE|NASDAQ)', issuer_text)
                    if ticker_match:
                        ticker_found = ticker_match.group(1)
                    else:
                        # Fall back to last sequence of caps (often the ticker at end)
                        caps_sequences = re.findall(r'\b([A-Z]{2,5})\b', issuer_text)
                        if caps_sequences:
                            ticker_found = caps_sequences[-1]  # Use last one (usually the ticker)
                
                # Extract date, size (amount range), and price from cells
                cells = row.find_all('td')
                date_str = "Recent"
                size_range = None
                price = None
                
                import re
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    
                    # Match date patterns like "30 Oct", "15 Nov"
                    if any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                        # Extract just the date part
                        match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', cell_text)
                        if match:
                            date_str = match.group(1)
                    
                    # Match size patterns like "1K-15K", "100K-250K", "15K-50K", "50K-100K"
                    # Note: CapitolTrades uses en-dash (–) not regular hyphen (-)
                    if not size_range:
                        size_match = re.search(r'(\d+[KM][-–]\d+[KM])', cell_text, re.IGNORECASE)
                        if size_match:
                            size_range = size_match.group(1)
                    
                    # Match price patterns like "$66.69", "$148.21", "$110,589.00"
                    if not price:
                        price_match = re.search(r'\$(\d+(?:,\d+)?(?:\.\d{2})?)', cell_text)
                        if price_match:
                            price = price_match.group(0)
                
                trades.append({
                    'politician': politician_name + party_chamber,
                    'type': trade_type,
                    'date': date_str,
                    'ticker': ticker_found or 'N/A',
                    'size': size_range,
                    'price': price
                })
                
            except Exception as e:
                logger.debug(f"Could not parse row: {e}")
                continue
        
        # Limit to 15 most recent
        trades = trades[:15]
        
        if trades:
            logger.info(f"Found {len(trades)} recent Congressional trades")
        else:
            logger.info(f"No Congressional trades found")
        
    except ImportError as e:
        logger.error(f"Selenium not installed. Run: pip install selenium webdriver-manager")
        logger.error(f"Error: {e}")
    except Exception as e:
        logger.warning(f"Could not fetch Congressional trades: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    finally:
        # Always close browser
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return trades


def get_insider_role_description(title: str) -> str:
    """
    Get detailed description of insider's role and significance.
    
    Args:
        title: Insider's title
        
    Returns:
        Description string
    """
    role_descriptions = {
        "CEO": "Chief Executive Officer - Top decision maker, deeply familiar with company strategy and performance",
        "CFO": "Chief Financial Officer - Manages finances, has deep insight into company's financial health",
        "COO": "Chief Operating Officer - Oversees daily operations, understands operational performance",
        "CTO": "Chief Technology Officer - Leads technology strategy, knows product roadmap",
        "President": "Senior leader, often involved in strategic decisions and operations",
        "Director": "Board member - Has fiduciary duty and access to confidential strategic information",
        "VP": "Vice President - Senior executive with significant inside knowledge",
        "10% Owner": "Large shareholder with substantial influence and privileged access to information",
        "Officer": "Corporate officer with executive responsibilities and insider knowledge",
        "Unknown": "Insider with access to material non-public information"
    }
    
    title_normalized = title.upper()
    
    for key, description in role_descriptions.items():
        if key.upper() in title_normalized:
            return description
    
    return role_descriptions["Unknown"]


def generate_ai_insight(alert: InsiderAlert, context: Dict, confidence: int) -> str:
    """
    Generate AI-powered insight analyzing the situation and providing actionable recommendation.
    
    Args:
        alert: InsiderAlert object
        context: Company context dictionary
        confidence: Confidence score (1-5)
        
    Returns:
        Detailed insight string with analysis and recommendation
    """
    insights = []
    recommendation = "HOLD"  # Default
    reasoning = []
    
    # Analyze Congressional alignment - check if any politician bought THIS ticker
    congressional_trades = context.get("congressional_trades", [])
    # Filter for buys of THIS specific ticker
    ticker = alert.ticker
    congressional_buys_this_stock = [
        t for t in congressional_trades 
        if t.get("type", "").upper() in ["BUY", "PURCHASE"] 
        and t.get("ticker", "").upper() == ticker.upper()
    ]
    
    if congressional_buys_this_stock:
        num_congress = len(congressional_buys_this_stock)
        politicians = [f"{t['politician']}" for t in congressional_buys_this_stock[:3]]  # First 3
        politicians_str = ", ".join(politicians)
        if num_congress > 3:
            politicians_str += f", and {num_congress - 3} others"
        
        insights.append(f"🏛️ CONGRESSIONAL ALIGNMENT: {num_congress} politician(s) recently bought {ticker} ({politicians_str}). "
                       f"Members of Congress have access to policy discussions, committee hearings, and regulatory insights not available to the public. "
                       f"When Congressional buys align with corporate insider buying, it creates an exceptionally strong signal - "
                       f"both groups with privileged information are betting on the same outcome.")
        recommendation = "STRONG BUY"
        reasoning.append(f"{num_congress} Congressional buy(s) of {ticker} + insider buying")
    
    # Analyze short squeeze potential
    short_interest = context.get("short_interest")
    if short_interest and short_interest > 0.15:  # >15% short
        if alert.signal_type in ["Cluster Buying", "Strategic Investor Buy", "CEO/CFO Buy"]:
            insights.append(f"🔥 SHORT SQUEEZE SETUP: {short_interest*100:.1f}% of shares are sold short. "
                          f"Insiders are buying heavily while shorts bet against the stock. "
                          f"If the stock rises, short sellers will be forced to buy shares to cover their positions, "
                          f"creating a feedback loop that could rocket the price higher.")
            recommendation = "STRONG BUY"
            reasoning.append("High short interest + insider buying = squeeze potential")
    
    # Analyze dip buying
    dist_from_low = context.get("distance_from_52w_low")
    if dist_from_low is not None and dist_from_low < 20:  # Within 20% of 52w low
        insights.append(f"💎 DIP BUYING OPPORTUNITY: Stock is trading just {dist_from_low:.1f}% above its 52-week low. "
                       f"Insiders are buying at/near the bottom, signaling they believe the worst is over. "
                       f"This is classic 'smart money' behavior - buying when pessimism is highest.")
        if recommendation != "STRONG BUY":
            recommendation = "BUY"
        reasoning.append("Buying near 52-week low")
    
    # Analyze insider conviction
    if alert.signal_type == "Cluster Buying":
        num_insiders = alert.details.get("num_insiders", 0)
        insights.append(f"👥 INSIDER CONSENSUS: {num_insiders} different insiders are buying simultaneously. "
                       f"When multiple insiders act together, it's rarely a coincidence. "
                       f"They have access to non-public information and collectively see major upside ahead.")
        reasoning.append("Multiple insiders = strong conviction")
    elif alert.signal_type == "Strategic Investor Buy":
        investor = alert.details.get("investor", "")
        insights.append(f"🏢 STRATEGIC INVESTMENT: {investor} is taking a position. "
                       f"Corporate investors conduct months of due diligence before investing. "
                       f"This could signal a strategic partnership, acquisition interest, or validation of the technology/business model.")
        recommendation = "STRONG BUY"
        reasoning.append("Corporate strategic investment")
    
    # Analyze valuation + buying
    pe_ratio = context.get("pe_ratio")
    if pe_ratio and 5 < pe_ratio < 15:
        insights.append(f"📊 UNDERVALUED + INSIDER BUYING: P/E ratio of {pe_ratio:.1f} suggests the stock is attractively valued. "
                       f"Insiders are buying when the stock is already cheap - double signal of opportunity.")
        reasoning.append("Attractive valuation")
    
    # Price momentum consideration
    price_change_5d = context.get("price_change_5d")
    price_change_1m = context.get("price_change_1m")
    if price_change_5d is not None and price_change_1m is not None:
        if price_change_5d < -5 and price_change_1m < -10:
            insights.append(f"⚠️ CATCHING A FALLING KNIFE: Stock is down {abs(price_change_1m):.1f}% over the last month. "
                           f"While insiders may be right long-term, short-term momentum is negative. "
                           f"Consider waiting for price stabilization or dollar-cost averaging.")
            if recommendation == "BUY":
                recommendation = "WAIT FOR CONFIRMATION"
            reasoning.append("Negative momentum - caution advised")
    
    # Final recommendation based on confidence
    if confidence >= 4 and not insights:
        insights.append(f"✅ HIGH CONVICTION SIGNAL: This {alert.signal_type.lower()} scores {confidence}/5 on our confidence scale. "
                       f"Multiple positive factors align, suggesting significant insider conviction about future prospects.")
        recommendation = "BUY"
    elif confidence <= 2:
        insights.append(f"⚠️ LOWER CONVICTION: This signal scores {confidence}/5. "
                       f"While insiders are buying, the size and context suggest moderate rather than exceptional opportunity.")
        recommendation = "MONITOR"
        reasoning.append("Lower confidence score")
    
    # Default insight if none triggered
    if not insights:
        insights.append(f"📈 INSIDER ACCUMULATION: {alert.signal_type} detected. "
                       f"Insiders are putting their own money on the line, which historically signals undervaluation. "
                       f"However, no exceptional catalysts identified. Standard insider buy opportunity.")
        recommendation = "HOLD/ACCUMULATE"
    
    # Build final insight
    insight_text = " ".join(insights)
    
    # Add recommendation
    if recommendation == "STRONG BUY":
        action = "🚀 RECOMMENDATION: STRONG BUY - Multiple bullish factors align. Consider taking a position."
    elif recommendation == "BUY":
        action = "✅ RECOMMENDATION: BUY - Positive setup with good risk/reward. Entry recommended."
    elif recommendation == "HOLD/ACCUMULATE":
        action = "📊 RECOMMENDATION: HOLD/ACCUMULATE - Solid opportunity. Build position gradually."
    elif recommendation == "MONITOR":
        action = "👀 RECOMMENDATION: MONITOR - Watch for additional confirmation before entering."
    elif recommendation == "WAIT FOR CONFIRMATION":
        action = "⏳ RECOMMENDATION: WAIT - Let price stabilize before entering. Set alerts."
    else:
        action = "📌 RECOMMENDATION: HOLD - Neutral signal. Existing holders maintain position."
    
    insight_text += f"\n\n{action}"
    
    if reasoning:
        insight_text += f"\n\nKey factors: {', '.join(reasoning)}"
    
    return insight_text


def calculate_confidence_score(alert: InsiderAlert, context: Dict) -> tuple[int, str]:
    """
    Calculate confidence score (1-5 stars) based on multiple factors.
    
    Scoring factors:
    - Signal type (cluster > CEO/CFO > large buy)
    - Buy amount (larger = better)
    - Ownership increase % (bigger stake = more conviction)
    - Price action (buying dip = better)
    - Short interest (high short + buy = squeeze potential)
    - P/E ratio (undervalued = better)
    
    Args:
        alert: InsiderAlert object
        context: Company context dictionary
        
    Returns:
        Tuple of (score 1-5, explanation string)
    """
    score = 0
    reasons = []
    
    # Signal type scoring (0-2 points)
    if alert.signal_type == "Cluster Buying":
        score += 2
        reasons.append("Multiple insiders buying")
    elif alert.signal_type == "Strategic Investor Buy":
        score += 2
        reasons.append("Corporate strategic investment")
    elif alert.signal_type == "CEO/CFO Buy":
        score += 1.5
        reasons.append("C-suite executive buying")
    elif alert.signal_type == "Large Single Buy":
        score += 1
        reasons.append("Significant purchase size")
    
    # Purchase size (0-1 points)
    total_value = alert.details.get("total_value") or alert.details.get("value", 0)
    if total_value >= 1_000_000:
        score += 1
        reasons.append("$1M+ purchase")
    elif total_value >= 500_000:
        score += 0.5
    
    # Ownership increase (0-1 points)
    try:
        if not alert.trades.empty and "Delta Own" in alert.trades.columns:
            # Clean and convert Delta Own values
            delta_vals = alert.trades["Delta Own"].astype(str).str.replace('%', '').str.replace('+', '')
            delta_vals = pd.to_numeric(delta_vals, errors='coerce')
            avg_delta = delta_vals.mean()
            
            if pd.notna(avg_delta) and avg_delta > 10:
                score += 1
                reasons.append(f"+{avg_delta:.0f}% ownership increase")
            elif pd.notna(avg_delta) and avg_delta > 5:
                score += 0.5
    except Exception as e:
        logger.debug(f"Could not calculate ownership delta: {e}")
    
    # Price action - buying the dip (0-1 points)
    if context.get("distance_from_52w_low") is not None:
        dist_from_low = context["distance_from_52w_low"]
        if dist_from_low < 20:  # Within 20% of 52w low
            score += 1
            reasons.append("Buying near 52-week low")
        elif dist_from_low < 40:
            score += 0.5
    
    # Short interest squeeze potential (0-0.5 points)
    if context.get("short_interest") and context["short_interest"] > 0.15:  # >15% short
        score += 0.5
        reasons.append(f"High short interest ({context['short_interest']*100:.1f}%)")
    
    # Valuation (0-0.5 points)
    if context.get("pe_ratio") and 5 < context["pe_ratio"] < 15:
        score += 0.5
        reasons.append("Attractive valuation")
    
    # Congressional alignment (0-0.5 points) - MAJOR SIGNAL
    # Check if politicians bought THIS specific ticker
    congressional_trades = context.get("congressional_trades", [])
    ticker = alert.ticker
    congressional_buys_this_stock = [
        t for t in congressional_trades 
        if t.get("type", "").upper() in ["BUY", "PURCHASE"]
        and t.get("ticker", "").upper() == ticker.upper()
    ]
    if congressional_buys_this_stock:
        score += 0.5
        num_pols = len(congressional_buys_this_stock)
        reasons.append(f"{num_pols} Congressional buy(s) of {ticker}")
    
    # Cap at 5, round to nearest 0.5
    score = min(5, round(score * 2) / 2)
    
    explanation = "; ".join(reasons) if reasons else "Standard insider buy"
    
    return int(score), explanation


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


def detect_strategic_investor_buy(df: pd.DataFrame) -> List[InsiderAlert]:
    """
    Detect Strategic Investor Buy: When a corporation (not an individual) buys stock.
    Examples: NVIDIA buying SERV, Amazon buying RIVN, etc.
    
    This is highly bullish as it signals:
    - Strategic partnerships/acquisitions
    - Deep due diligence by corporate teams
    - Potential integration/collaboration
    
    Args:
        df: Trades DataFrame
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    # Corporate name indicators
    corporate_indicators = [
        'Corp', 'Corporation', 'Inc', 'Incorporated', 'LLC', 'Ltd', 
        'Limited', 'LP', 'LLP', 'Company', 'Co.', 'Group', 
        'Holdings', 'Partners', 'Capital', 'Ventures', 'Fund',
        'Trust', 'Management', 'Investments', 'Technologies'
    ]
    
    # Filter to buys only
    buys = df[df["Trade Type"] == "Buy"].copy()
    
    # Identify corporate buyers by name patterns
    for _, row in buys.iterrows():
        insider_name = str(row["Insider Name"])
        
        # Check if name contains corporate indicators
        is_corporate = any(indicator in insider_name for indicator in corporate_indicators)
        
        # Also check if it's all caps (common for corporate names like "NVIDIA")
        words = insider_name.split()
        has_all_caps_word = any(word.isupper() and len(word) > 2 for word in words)
        
        if is_corporate or has_all_caps_word:
            company_name = row.get("Company Name", row["Ticker"])
            
            alert = InsiderAlert(
                signal_type="Strategic Investor Buy",
                ticker=row["Ticker"],
                company_name=company_name,
                trades=pd.DataFrame([row]),
                details={
                    "investor": insider_name,
                    "value": row["Value"],
                    "trade_date": row["Trade Date"],
                    "qty": row["Qty"],
                    "price": row["Price"],
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} strategic investor buy signals")
    return alerts


def detect_congressional_cluster_buy(congressional_trades: List[Dict]) -> List[InsiderAlert]:
    """
    Detect Congressional Cluster Buy: 2+ politicians buy same ticker within 7 days.
    
    This is a strong signal because:
    - Multiple politicians with insider info act together
    - Often indicates upcoming policy/regulatory changes
    - Bipartisan agreement is especially powerful
    
    Args:
        congressional_trades: List of Congressional trade dictionaries
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    if not congressional_trades:
        return alerts
    
    # Filter to buys only
    buys = [t for t in congressional_trades if t.get('type', '').upper() in ['BUY', 'PURCHASE']]
    
    if len(buys) < 2:
        return alerts
    
    # Group by ticker
    ticker_groups = {}
    for trade in buys:
        ticker = trade.get('ticker', 'N/A')
        if ticker != 'N/A':
            if ticker not in ticker_groups:
                ticker_groups[ticker] = []
            ticker_groups[ticker].append(trade)
    
    # Check for clusters (MIN_CONGRESSIONAL_CLUSTER+ politicians buying same ticker)
    for ticker, trades in ticker_groups.items():
        if len(trades) >= MIN_CONGRESSIONAL_CLUSTER:
            # Check if bipartisan
            politicians = [t.get('politician', '') for t in trades]
            has_dem = any('(D)' in p for p in politicians)
            has_rep = any('(R)' in p for p in politicians)
            is_bipartisan = has_dem and has_rep
            
            # Create DataFrame for display (map Congressional fields to expected columns)
            trades_data = []
            for trade in trades:
                # Parse date - handle formats like "16 Oct" or "2025-11-18"
                date_str = trade.get('date', 'Recent')
                try:
                    if '-' in date_str:
                        trade_date = pd.to_datetime(date_str)
                    else:
                        # Format like "16 Oct" - add current year
                        trade_date = pd.to_datetime(f"{date_str} {datetime.now().year}", format='%d %b %Y')
                except:
                    trade_date = datetime.now()
                
                # Use size range as value display (e.g., "1K-15K", "100K-250K")
                size_display = trade.get('size', '')
                
                trades_data.append({
                    "Ticker": ticker,
                    "Insider Name": trade.get('politician', 'Unknown'),
                    "Trade Date": trade_date,
                    "Title": trade.get('chamber', 'Congress'),
                    "Value": 0,  # Not used for Congressional (we use size_range)
                    "Size Range": size_display,
                    "Price": trade.get('price', ''),
                    "Delta Own": ""
                })
            trades_df = pd.DataFrame(trades_data)
            
            signal_type = "Congressional Cluster Buy"
            if is_bipartisan:
                signal_type = "Bipartisan Congressional Buy"
            
            alert = InsiderAlert(
                signal_type=signal_type,
                ticker=ticker,
                company_name=ticker,  # We don't have company name from Congressional data
                trades=trades_df,
                details={
                    "num_politicians": len(trades),
                    "politicians": politicians[:5],  # First 5
                    "bipartisan": is_bipartisan,
                    "dates": [t.get('date', 'Recent') for t in trades]
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} Congressional cluster buy signals")
    return alerts


def detect_high_conviction_congressional_buy(congressional_trades: List[Dict]) -> List[InsiderAlert]:
    """
    Detect High-Conviction Congressional Buy: Single politician with strong signal.
    
    Triggers when:
    - Known successful trader (track record)
    - Large purchase ($100K+)
    - Committee-aligned purchase
    
    Note: For MVP, we filter by purchase size. Future enhancement: track record & committee data.
    
    Args:
        congressional_trades: List of Congressional trade dictionaries
        
    Returns:
        List of InsiderAlert objects
    """
    alerts = []
    
    if not congressional_trades:
        return alerts
    
    # Filter to buys only
    buys = [t for t in congressional_trades if t.get('type', '').upper() in ['BUY', 'PURCHASE']]
    
    # Known high-performing traders (can expand this list)
    top_traders = [
        'Nancy Pelosi', 'Josh Gottheimer', 'Michael McCaul',
        'Tommy Tuberville', 'Dan Crenshaw', 'Brian Higgins'
    ]
    
    for trade in buys:
        politician = trade.get('politician', '')
        ticker = trade.get('ticker', 'N/A')
        
        if ticker == 'N/A':
            continue
        
        # Check if this politician is a known successful trader
        is_top_trader = any(trader in politician for trader in top_traders)
        
        if is_top_trader:
            # Create DataFrame for display (map Congressional fields to expected columns)
            # Parse date - handle formats like "16 Oct" or "2025-11-18"
            date_str = trade.get('date', 'Recent')
            try:
                if '-' in date_str:
                    trade_date = pd.to_datetime(date_str)
                else:
                    # Format like "16 Oct" - add current year
                    trade_date = pd.to_datetime(f"{date_str} {datetime.now().year}", format='%d %b %Y')
            except:
                trade_date = datetime.now()
            
            # Use size range as value display (e.g., "1K-15K", "100K-250K")
            size_display = trade.get('size', '')
            
            trades_data = {
                "Ticker": ticker,
                "Insider Name": politician,
                "Trade Date": trade_date,
                "Title": trade.get('chamber', 'Congress'),
                "Value": 0,  # Not used for Congressional (we use size_range)
                "Size Range": size_display,
                "Price": trade.get('price', ''),
                "Delta Own": ""
            }
            trades_df = pd.DataFrame([trades_data])
            
            alert = InsiderAlert(
                signal_type="High-Conviction Congressional Buy",
                ticker=ticker,
                company_name=ticker,
                trades=trades_df,
                details={
                    "politician": politician,
                    "date": trade.get('date', 'Recent'),
                    "known_trader": True
                }
            )
            alerts.append(alert)
    
    logger.info(f"Detected {len(alerts)} high-conviction Congressional buy signals")
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
    
    # Corporate insider signals
    all_alerts.extend(detect_cluster_buying(df))
    all_alerts.extend(detect_ceo_cfo_buy(df))
    all_alerts.extend(detect_large_single_buy(df))
    all_alerts.extend(detect_first_buy_12m(df))
    all_alerts.extend(detect_bearish_cluster_selling(df))
    all_alerts.extend(detect_strategic_investor_buy(df))
    
    # Congressional signals (if enabled)
    if USE_CAPITOL_TRADES:
        try:
            logger.info("Fetching Congressional trades for signal detection")
            congressional_trades = get_congressional_trades()
            
            if congressional_trades:
                all_alerts.extend(detect_congressional_cluster_buy(congressional_trades))
                all_alerts.extend(detect_high_conviction_congressional_buy(congressional_trades))
        except Exception as e:
            logger.error(f"Error detecting Congressional signals: {e}", exc_info=True)
    
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


def format_telegram_message(alert: InsiderAlert) -> str:
    """Format alert as Telegram message with markdown."""
    # Escape special characters for Telegram MarkdownV2
    def escape_md(text):
        """Escape special characters for Telegram MarkdownV2."""
        if not isinstance(text, str):
            text = str(text)
        chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text
    
    msg = f"🚨 *{escape_md(alert.signal_type)}*\n\n"
    company_esc = escape_md(alert.company_name)
    ticker_esc = escape_md(alert.ticker)
    msg += f"*{ticker_esc}* \\- {company_esc}\n\n"
    
    # Signal details
    if "num_insiders" in alert.details:
        msg += f"👥 {alert.details['num_insiders']} insiders\n"
        msg += f"💰 ${alert.details['total_value']:,.0f}\n"
        msg += f"📅 Window: {alert.details['window_days']} days\n"
    elif "investor" in alert.details:
        # Strategic investor (corporate buyer)
        investor_esc = escape_md(alert.details['investor'])
        msg += f"🏢 {investor_esc}\n"
        msg += f"💰 ${alert.details['value']:,.0f}\n"
        if "trade_date" in alert.details:
            date_str = alert.details['trade_date'].strftime('%Y-%m-%d')
            msg += f"📅 {escape_md(date_str)}\n"
        msg += f"\n💡 *Why this matters:*\n"
        msg += f"Corporate investors signal strategic partnerships or acquisition interest\\. "
        msg += f"They conduct deep due diligence before investing\\.\n"
    elif "value" in alert.details:
        insider_esc = escape_md(alert.details['insider'])
        title_esc = escape_md(alert.details['title'])
        msg += f"👤 {insider_esc} \\({title_esc}\\)\n"
        msg += f"💰 ${alert.details['value']:,.0f}\n"
        if "trade_date" in alert.details:
            date_str = alert.details['trade_date'].strftime('%Y-%m-%d')
            msg += f"📅 {escape_md(date_str)}\n"
    
    # Top trades (max 3 for brevity)
    msg += f"\n📊 *Trades:*\n"
    for idx, (_, row) in enumerate(alert.trades.head(3).iterrows()):
        date = row["Trade Date"].strftime('%m/%d') if pd.notna(row["Trade Date"]) else "?"
        
        # Format insider name - for Congressional trades, shorten to "Initial. LastName (Party)"
        insider_name = row['Insider Name']
        if '(' in insider_name and ')' in insider_name:  # Congressional format: "Name (D)-House"
            # Extract party letter
            party_match = insider_name.split('(')[1].split(')')[0] if '(' in insider_name else ''
            # Get name parts
            name_part = insider_name.split('(')[0].strip()
            name_parts = name_part.split()
            if len(name_parts) >= 2:
                # Format as "J. Gottheimer (D)"
                formatted_name = f"{name_parts[0][0]}. {' '.join(name_parts[1:])} ({party_match})"
            else:
                formatted_name = f"{name_part} ({party_match})"
            insider = escape_md(formatted_name[:30])
        else:
            insider = escape_md(insider_name[:25])
        
        date_esc = escape_md(date)
        
        # Build trade line
        trade_line = f"• {date_esc}: {insider}"
        
        # For Congressional trades, show size range and price
        if "Size Range" in row and pd.notna(row.get("Size Range")) and row.get("Size Range"):
            size_range = escape_md(str(row["Size Range"]))
            trade_line += f" \\- {size_range}"
            # Add price if available
            if "Price" in row and pd.notna(row.get("Price")) and row.get("Price"):
                price_val = escape_md(str(row["Price"]))
                trade_line += f" @ {price_val}"
        # For corporate insider trades, show dollar value
        elif pd.notna(row['Value']) and row['Value'] > 0:
            value_esc = escape_md(f"${row['Value']:,.0f}")
            trade_line += f" \\- {value_esc}"
        
        # Add ownership change % if available and not empty (corporate insiders only)
        if "Delta Own" in row and pd.notna(row["Delta Own"]):
            delta_own = row["Delta Own"]
            # Only add if it's a meaningful value (not empty string)
            if isinstance(delta_own, str) and delta_own.strip():
                trade_line += f" \\({escape_md(delta_own)}\\)"
            elif isinstance(delta_own, (int, float)):
                trade_line += f" \\({delta_own:+.1f}%\\)"
        
        msg += trade_line + "\n"
    
    if len(alert.trades) > 3:
        msg += f"• \\.\\.\\.\\+{len(alert.trades) - 3} more\n"
    
    # Add company context if available
    try:
        context = get_company_context(alert.ticker)
        
        # Price Action
        if context.get("price_change_5d") is not None or context.get("price_change_1m") is not None:
            msg += f"\n📊 *Price Action:*\n"
            if context.get("price_change_5d") is not None:
                change_5d = context["price_change_5d"]
                emoji = "🟢" if change_5d > 0 else "🔴"
                change_5d_str = f"{change_5d:+.1f}"
                msg += f"• 5\\-day: {emoji} {escape_md(change_5d_str)}%\n"
            if context.get("price_change_1m") is not None:
                change_1m = context["price_change_1m"]
                emoji = "🟢" if change_1m > 0 else "🔴"
                change_1m_str = f"{change_1m:+.1f}"
                msg += f"• 1\\-month: {emoji} {escape_md(change_1m_str)}%\n"
        
        # 52-week range
        if context.get("week_52_high") and context.get("week_52_low") and context.get("current_price"):
            msg += f"\n📏 *52\\-Week Range:*\n"
            high_str = f"{context['week_52_high']:.2f}"
            low_str = f"{context['week_52_low']:.2f}"
            curr_str = f"{context['current_price']:.2f}"
            msg += f"• High: \\${escape_md(high_str)}\n"
            msg += f"• Low: \\${escape_md(low_str)}\n"
            msg += f"• Current: \\${escape_md(curr_str)}\n"
            
            if context.get("distance_from_52w_low") is not None:
                dist_low = context["distance_from_52w_low"]
                dist_low_str = f"{dist_low:.1f}"
                msg += f"• {escape_md(dist_low_str)}% above 52w low\n"
        
        # Company description (first sentence only)
        if context.get("description"):
            desc = context["description"].split('.')[0] + '.'
            if len(desc) > 150:
                desc = desc[:147] + '...'
            msg += f"\n🏢 *About:*\n{escape_md(desc)}\n"
        
        # Market data
        if context.get("market_cap") or context.get("pe_ratio") or context.get("sector") or context.get("short_interest"):
            msg += f"\n📈 *Market Data:*\n"
            if context.get("sector"):
                msg += f"• Sector: {escape_md(context['sector'])}\n"
            if context.get("market_cap"):
                mc_billions = context["market_cap"] / 1e9
                mc_str = f"{mc_billions:.1f}"
                msg += f"• Market Cap: \\${escape_md(mc_str)}B\n"
            if context.get("pe_ratio"):
                pe_str = f"{context['pe_ratio']:.1f}"
                msg += f"• P/E Ratio: {escape_md(pe_str)}\n"
            if context.get("short_interest"):
                si_pct = context["short_interest"] * 100
                si_pct_str = f"{si_pct:.1f}"
                emoji = "🔥" if si_pct > 15 else ""
                msg += f"• Short Interest: {emoji}{escape_md(si_pct_str)}%\n"
        
        # Recent news
        if context.get("news") and len(context["news"]) > 0:
            msg += f"\n📰 *Recent News:*\n"
            for news_item in context["news"][:2]:  # Top 2 headlines
                title = news_item["title"][:80] + "..." if len(news_item["title"]) > 80 else news_item["title"]
                msg += f"• {escape_md(title)}\n"
        
        # Insider role context (for single insider signals)
        if "title" in alert.details and alert.details.get("title"):
            role_desc = get_insider_role_description(alert.details["title"])
            msg += f"\n👔 *Insider Role:*\n{escape_md(role_desc)}\n"
        
        # Congressional trades (if available) - shows ALL recent trades for market intelligence
        if context.get("congressional_trades"):
            congressional_trades = context["congressional_trades"]
            buys = [t for t in congressional_trades if t.get("type", "").upper() in ["BUY", "PURCHASE"]]
            sells = [t for t in congressional_trades if t.get("type", "").upper() in ["SELL", "SALE"]]
            
            if buys or sells:
                msg += f"\n🏛️ *Congressional Market Activity:*\n"
                msg += f"_Recent trades across all stocks for context\\.\\.\\._\n\n"
                
                if buys:
                    msg += f"📈 *Buys:*\n"
                    for trade in buys[:5]:  # Show max 5 buys
                        pol = escape_md(trade.get("politician", "Unknown")[:35])
                        ticker_disp = escape_md(trade.get("ticker", "N/A"))
                        date = escape_md(trade.get("date", ""))
                        msg += f"• {ticker_disp}: {pol} \\- {date}\n"
                    if len(buys) > 5:
                        msg += f"• \\.\\.\\.\\+{len(buys) - 5} more\n"
                
                if sells:
                    msg += f"\n📉 *Sells:*\n"
                    for trade in sells[:3]:  # Show max 3 sells
                        pol = escape_md(trade.get("politician", "Unknown")[:35])
                        ticker_disp = escape_md(trade.get("ticker", "N/A"))
                        date = escape_md(trade.get("date", ""))
                        msg += f"• {ticker_disp}: {pol} \\- {date}\n"
                    if len(sells) > 3:
                        msg += f"• \\.\\.\\.\\+{len(sells) - 3} more\n"
        
        # Confidence Score (moved here, right before AI insight)
        confidence_score, score_reason = calculate_confidence_score(alert, context)
        stars = "⭐" * confidence_score
        msg += f"\n{stars} *Confidence: {confidence_score}/5*\n"
        msg += f"_{escape_md(score_reason)}_\n"
        
        # AI-Powered Insight - The "so what?" analysis
        ai_insight = generate_ai_insight(alert, context, confidence_score)
        msg += f"\n🧠 *AI Insight:*\n{escape_md(ai_insight)}\n"
    
    except Exception as e:
        logger.warning(f"Could not add context to message: {e}")
    
    # Provide plain HTTP link (Telegram blocks clickable HTTP, but users can copy/paste)
    ticker_url = f"http://openinsider.com/search?q={alert.ticker}"
    msg += f"\n🔗 View on OpenInsider:\n`{ticker_url}`"
    return msg


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


def send_telegram_alert(alert: InsiderAlert, dry_run: bool = False) -> bool:
    """Send Telegram alert via Bot API to one or more accounts."""
    if not USE_TELEGRAM:
        return False
    
    if dry_run:
        logger.info(f"DRY RUN - Would send Telegram: {alert.ticker} - {alert.signal_type}")
        return True
    
    try:
        import asyncio
        from telegram import Bot
        from telegram.constants import ParseMode
        
        # Support multiple chat IDs (comma-separated)
        chat_ids = [cid.strip() for cid in TELEGRAM_CHAT_ID.split(",")]
        
        # Format message
        message_text = format_telegram_message(alert)
        
        # Send via Telegram Bot API (async)
        async def send_message():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            success_count = 0
            
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to chat_id {chat_id}: {e}")
            
            return success_count
        
        # Run async function
        success_count = asyncio.run(send_message())
        
        if success_count > 0:
            logger.info(f"Telegram sent successfully to {success_count}/{len(chat_ids)} accounts: {alert.ticker}")
            return True
        else:
            logger.error(f"Failed to send Telegram to any account: {alert.ticker}")
            return False
        
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")
        return False


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
    
    # Send alerts for new signals
    for alert in new_alerts:
        # Try Telegram first if enabled
        if USE_TELEGRAM:
            telegram_sent = send_telegram_alert(alert, dry_run=dry_run)
            if telegram_sent:
                logger.info(f"Alert sent via Telegram: {alert.ticker}")
        
        # Always send email as backup or primary
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
    if not args.dry_run:
        has_email = all([SMTP_USER, SMTP_PASS, ALERT_TO])
        has_telegram = USE_TELEGRAM and all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID])
        
        if not has_email and not has_telegram:
            logger.error("Alert configuration missing. Set either email (SMTP_*) or Telegram (TELEGRAM_*) credentials in .env")
            sys.exit(1)
        
        if USE_TELEGRAM and not has_telegram:
            logger.warning("USE_TELEGRAM=true but Telegram credentials missing. Falling back to email only.")
    
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
