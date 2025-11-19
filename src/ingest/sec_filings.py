"""SEC Form 8-K filing ingestion and parsing."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine
from bs4 import BeautifulSoup

from ..config import DATABASE_URL, RAW_DIR
from .utils import search_company_filings, download_filing

# Configure logging
logger = logging.getLogger(__name__)

def extract_8k_data(filing_text: str) -> Dict:
    """Extract data from Form 8-K filing.
    
    Args:
        filing_text: Raw 8-K filing text
        
    Returns:
        Dict containing parsed 8-K data
    """
    # Parse HTML
    soup = BeautifulSoup(filing_text, 'html.parser')
    
    # Get document info
    filing = {
        'accession_number': '',  # Extract from metadata
        'filing_date': None,     # Extract from metadata
        'company_name': '',      # Extract from header
        'company_cik': '',       # Extract from header
        'events': []
    }
    
    # Find 8-K items (events)
    items = []
    for item in soup.find_all(['p', 'div'], text=lambda t: t and 'Item ' in t):
        text = item.get_text().strip()
        
        # Common 8-K item types
        if any(x in text.lower() for x in [
            'results of operations',
            'financial statements',
            'material agreements',
            'changes in officers',
            'regulation fd disclosure',
            'other events'
        ]):
            # Get item number
            item_num = text.split('.')[0].strip()
            
            # Get description (next paragraph)
            desc = item.find_next(['p', 'div']).get_text().strip()
            
            items.append({
                'item_type': item_num,
                'description': desc[:500]  # Truncate long descriptions
            })
    
    filing['events'] = items
    return filing

def save_to_database(filing: Dict, engine: create_engine):
    """Save Form 8-K data to database.
    
    Args:
        filing: Parsed 8-K data
        engine: SQLAlchemy database engine
    """
    # Add events
    for event in filing['events']:
        event_data = pd.DataFrame([{
            'filing_date': filing['filing_date'],
            'company_cik': filing['company_cik'],
            'event_date': filing['filing_date'],  # Usually same as filing
            'item_type': event['item_type'],
            'description': event['description'],
            'form_url': f"https://www.sec.gov/Archives/edgar/data/{filing['company_cik']}/{filing['accession_number']}.txt"
        }])
        
        event_data.to_sql(
            'form8k_events',
            engine,
            if_exists='append',
            index=False
        )

def ingest_8k_filings(
    cik: Optional[str] = None,
    days_back: int = 30,
    save_raw: bool = True
):
    """Ingest recent Form 8-K filings for a company.
    
    Args:
        cik: Company CIK (optional)
        days_back: Number of days to look back
        save_raw: Whether to save raw filing texts
    """
    engine = create_engine(DATABASE_URL)
    
    # Set up date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Create raw files directory if needed
    if save_raw:
        raw_dir = RAW_DIR / 'form8k'
        raw_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Search for 8-K filings
        results = search_company_filings(
            cik=cik if cik else '',
            filing_type='8-K',
            start_date=start_date,
            end_date=end_date
        )
        
        for filing in results['filings']:
            try:
                # Download filing
                file_path = download_filing(
                    filing['accessionNumber'],
                    filing['cik'],
                    '8-K',
                    raw_dir if save_raw else '/tmp'
                )
                
                # Parse filing
                with open(file_path, 'r') as f:
                    filing_data = extract_8k_data(f.read())
                    
                # Add metadata
                filing_data.update({
                    'accession_number': filing['accessionNumber'],
                    'filing_date': datetime.strptime(
                        filing['filingDate'], 
                        '%Y-%m-%d'
                    ),
                    'company_cik': filing['cik'],
                    'company_name': filing['companyName']
                })
                
                # Save to database
                save_to_database(filing_data, engine)
                
                logger.info(
                    f"Processed 8-K filing {filing['accessionNumber']} "
                    f"for {filing_data['company_name']}"
                )
                
                # Clean up if not saving
                if not save_raw:
                    file_path.unlink()
                    
            except Exception as e:
                logger.error(
                    f"Error processing filing {filing['accessionNumber']}: {str(e)}"
                )
                continue
                
    except Exception as e:
        logger.error(f"Error ingesting 8-K filings: {str(e)}")
        raise
        
if __name__ == "__main__":
    ingest_8k_filings()
