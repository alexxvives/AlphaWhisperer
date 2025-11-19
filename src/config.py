"""Global configuration settings for the InvestorAI application."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"

# Create directories if they don't exist
for dir_path in [DATA_DIR, CACHE_DIR, RAW_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_URL = f"sqlite:///{DATA_DIR}/insider.db"

# SEC API configuration
SEC_API_KEY = os.getenv("SEC_API_KEY", "")
SEC_EMAIL = os.getenv("SEC_EMAIL", "")
SEC_BASE_URL = "https://www.sec.gov"
SEC_SUBMISSIONS_URL = f"{SEC_BASE_URL}/cgi-bin/browse-edgar"
SEC_RATE_LIMIT = 10  # requests per second

# Scoring weights (0-100)
WEIGHTS = {
    "role": {
        "CEO": 100,
        "CFO": 95,
        "Director": 80,
        "Officer": 70,
        "Other": 50,
    },
    "trade_type": {
        "P-Purchase": 100,  # Open market purchase
        "S-Sale": 30,      # Open market sale
        "A-Grant": 20,     # Award/Grant
        "M-Exercise": 40,  # Option exercise
        "D-Sale": 10,      # Planned sale (Rule 10b5-1)
    },
    "size_percentile": 0.3,      # 30% weight for trade size
    "cluster_weight": 0.2,       # 20% weight for insider clustering
    "catalyst_weight": 0.15,     # 15% weight for event proximity
    "politician_weight": 0.15,   # 15% weight for politician overlap
}

# Time windows (days)
WINDOWS = {
    "cluster": 30,        # Look for other insider trades within ±30 days
    "catalyst": 14,       # Look for events within ±14 days of trade
    "politician": 30,     # Look for politician trades within ±30 days
    "backtest": {
        "min_hold": 30,   # Minimum holding period
        "max_hold": 365,  # Maximum holding period
    }
}

# Thresholds
THRESHOLDS = {
    "min_score": 70,     # Minimum score for alerts
    "min_value": 50000,  # Minimum transaction value ($)
}
