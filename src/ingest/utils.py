"""Shared utilities for SEC API requests and data handling."""
import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union
from datetime import datetime, timedelta

import requests
import backoff
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SEC API Configuration
SEC_USER_AGENT = os.getenv('SEC_USER_AGENT')
SEC_EMAIL = os.getenv('SEC_EMAIL')

# API URLs
SEC_BASE_URL = 'https://www.sec.gov'
EDGAR_BASE_URL = 'https://data.sec.gov'
SUBMISSIONS_BASE_URL = 'https://data.sec.gov/submissions'
COMPANY_BASE_URL = 'https://data.sec.gov/api/xbrl/companyfacts'
FILING_ARCHIVE_URL = 'https://www.sec.gov/Archives/edgar/data'

# Sample CIKs for testing (top tech companies)
TEST_CIKS = [
    '320193',   # Apple
    '789019',   # Microsoft
    '1652044',  # Alphabet (Google)
    '1018724',  # Amazon
    '1326801',  # Meta (Facebook)
    '1418091',  # Nvidia
]

# Rate limiting settings
MIN_REQUEST_INTERVAL = 0.1  # 10 requests per second max
last_request_time = 0

class SECRateLimitError(Exception):
    """Exception for SEC API rate limit issues."""
    pass

def wait_for_rate_limit():
    """Ensure we don't exceed SEC rate limits."""
    global last_request_time
    
    current_time = time.time()
    time_since_last_request = current_time - last_request_time
    
    if time_since_last_request < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last_request)
    
    last_request_time = time.time()

@backoff.on_exception(
    backoff.expo,
    (requests.exceptions.RequestException, SECRateLimitError),
    max_tries=5
)
def sec_request(
    url: str,
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None
) -> requests.Response:
    """Make a rate-limited request to SEC API.
    
    Args:
        url: SEC API endpoint URL
        params: Query parameters
        headers: Additional headers
        
    Returns:
        Response object
        
    Raises:
        SECRateLimitError: If rate limit is exceeded
        requests.exceptions.RequestException: For other request errors
    """
    if not SEC_USER_AGENT:
        raise ValueError("SEC_USER_AGENT environment variable not set")
    if not SEC_EMAIL:
        raise ValueError("SEC_EMAIL environment variable not set")
    
    # Enforce rate limiting
    wait_for_rate_limit()
    
    # Set base headers
    request_headers = {
        'User-Agent': SEC_USER_AGENT,
        'Accept-Encoding': 'gzip, deflate',
        'Accept': 'application/json',
    }
    
    # Set host based on URL
    if 'data.sec.gov' in url:
        request_headers['Host'] = 'data.sec.gov'
    else:
        request_headers['Host'] = 'www.sec.gov'
        
    # Add custom headers
    if headers:
        request_headers.update(headers)
        
    # Add EDGAR parameters
    request_params = {'email': SEC_EMAIL}
    if params:
        request_params.update(params)
    
    # Make request
    try:
        response = requests.get(url, params=request_params, headers=request_headers)
        
        # Check for rate limit response
        if response.status_code == 429:
            raise SECRateLimitError("SEC rate limit exceeded")
        if response.status_code == 403:
            raise SECRateLimitError("Access denied - check User-Agent format")
            
        response.raise_for_status()
        return response
        
    except requests.exceptions.RequestException as e:
        logger.error(f"SEC API request failed: {str(e)}")
        raise

def get_company_facts(cik: str) -> Dict:
    """Get company information from SEC company facts API.
    
    Args:
        cik: Company CIK number (leading zeros stripped)
        
    Returns:
        Dict of company information
    """
    url = f"{COMPANY_BASE_URL}/CIK{cik.zfill(10)}.json"
    response = sec_request(url)
    return response.json()

def get_company_submissions(cik: str) -> Dict:
    """Get company filing history.
    
    Args:
        cik: Company CIK number
        
    Returns:
        Dict of filing history data
    """
    url = f"{SUBMISSIONS_BASE_URL}/CIK{cik.zfill(10)}.json"
    response = sec_request(url)
    return response.json()

def download_filing(
    accession_number: str,
    cik: str,
    filing_type: str,
    save_dir: Union[str, Path]
) -> Path:
    """Download a specific SEC filing document.
    
    Args:
        accession_number: SEC accession number
        cik: Company CIK
        filing_type: Type of filing (e.g., '4', '8-K')
        save_dir: Directory to save the file
        
    Returns:
        Path to downloaded file
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Format accession number
    acc_no = accession_number.replace('-', '')
    
    # Construct URL
    url = (
        f"{FILING_ARCHIVE_URL}/{cik}/{acc_no}/"
        f"{accession_number}.txt"
    )
    
    # Download file
    response = sec_request(url)
    
    # Save to file
    file_path = save_dir / f"{cik}_{accession_number}_{filing_type}.txt"
    with open(file_path, 'wb') as f:
        f.write(response.content)
        
    return file_path

def search_company_filings(
    cik: Optional[str] = None,
    filing_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    count: int = 100
) -> Dict:
    """Search for company filings using SEC EDGAR.
    
    Args:
        cik: Company CIK number (optional)
        filing_type: Type of filing to search for (optional)
        start_date: Start of date range
        end_date: End of date range
        count: Number of results to return
        
    Returns:
        Dict containing filing information
    """
    # If no CIK provided, use test CIKs
    ciks_to_search = [cik] if cik else TEST_CIKS
    
    all_filings = []
    for company_cik in ciks_to_search:
        try:
            # Get company submissions data
            url = f"{SUBMISSIONS_BASE_URL}/CIK{company_cik.zfill(10)}.json"
            response = sec_request(url)
            data = response.json()
            
            # Process filings from recent history
            filings = data.get('filings', {}).get('recent', {})
            if not filings:
                continue
                
            # Get parallel arrays
            accessions = filings.get('accessionNumber', [])
            dates = filings.get('filingDate', [])
            forms = filings.get('form', [])
            
            # Process each filing
            for acc, date, form in zip(accessions, dates, forms):
                # Skip if wrong form type
                if filing_type and form != filing_type:
                    continue
                    
                # Parse date
                filing_date = datetime.strptime(date, '%Y-%m-%d')
                
                # Filter by date range
                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue
                
                filing = {
                    'accessionNumber': acc,
                    'filingDate': date,
                    'form': form,
                    'cik': company_cik,
                    'companyName': data.get('name', '')
                }
                all_filings.append(filing)
                
                if len(all_filings) >= count:
                    break
                    
        except Exception as e:
            logger.warning(f"Error getting filings for CIK {company_cik}: {e}")
            continue
            
        if len(all_filings) >= count:
            break
            
    return {'filings': all_filings[:count]}
