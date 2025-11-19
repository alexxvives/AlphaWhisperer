"""SEC Form 4 filing ingestion and parsing."""
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

def extract_form4_data(filing_text: str) -> Dict:
    """Extract data from Form 4 XML content.
    
    Args:
        filing_text: Raw Form 4 filing text
        
    Returns:
        Dict containing parsed Form 4 data
    """
    # First try to find XML in <XML> tags
    try:
        xml_start = filing_text.index('<XML>')
        xml_end = filing_text.index('</XML>')
        xml_content = filing_text[xml_start:xml_end + 6]
    except ValueError:
        # Fallback to SEC-DOCUMENT if needed
        try:
            xml_start = filing_text.index('<SEC-DOCUMENT>')
            xml_end = filing_text.index('</SEC-DOCUMENT>')
            xml_content = filing_text[xml_start:xml_end + 14]
        except ValueError:
            raise ValueError("Could not find XML content in filing")
    
    # Parse XML with lxml parser
    soup = BeautifulSoup(xml_content, 'lxml-xml')
    
    # Get document info from ownershipDocument root
    ownership = soup.find('ownershipDocument')
    if not ownership:
        raise ValueError("Could not find ownershipDocument in XML")
        
    filing = {
        'filing_date': datetime.strptime(
            ownership.find('periodOfReport').text,
            '%Y-%m-%d'
        ),
        'document_type': ownership.find('documentType').text,
        'accession_number': ownership.get('accessionNumber', '')  # May be in parent doc
    }
    
    # Get reporting owner info
    owner = soup.find('reportingOwner')
    filing.update({
        'insider_name': owner.find('rptOwnerName').text,
        'insider_cik': owner.find('rptOwnerCik').text,
        'insider_title': owner.find('officerTitle').text if owner.find('officerTitle') else None,
        'is_director': bool(owner.find('directorFlag')),
        'is_officer': bool(owner.find('officerFlag')),
    })
    
    # Get issuer info
    issuer = soup.find('issuer')
    filing.update({
        'company_name': issuer.find('issuerName').text,
        'company_cik': issuer.find('issuerCik').text,
        'ticker': issuer.find('issuerTradingSymbol').text,
    })
    
    # Get transaction info
    filing['transactions'] = []
    
    for entry in soup.find_all(['nonDerivativeTransaction', 'derivativeTransaction']):
        security = entry.find('securityTitle').find('value').text
        
        # Get amounts
        shares = entry.find('transactionShares')
        price = entry.find('transactionPricePerShare')
        owned = entry.find('sharesOwnedFollowingTransaction')
        
        if all([shares, price, owned]):  # Only include complete transactions
            trans = {
                'security_title': security,
                'date': datetime.strptime(
                    entry.find('transactionDate').find('value').text,
                    '%Y-%m-%d'
                ),
                'type': entry.find('transactionCode').text,
                'shares': float(shares.find('value').text),
                'price': float(price.find('value').text),
                'owned_after': float(owned.find('value').text),
            }
            
            # Calculate total value
            trans['value'] = trans['shares'] * trans['price']
            
            filing['transactions'].append(trans)
    
    return filing

def save_to_database(filing: Dict, engine: create_engine):
    """Save Form 4 data to database.
    
    Args:
        filing: Parsed Form 4 data
        engine: SQLAlchemy database engine
    """
    # Update company info
    company_data = pd.DataFrame([{
        'cik': filing['company_cik'],
        'ticker': filing['ticker'],
        'name': filing['company_name'],
    }])
    
    company_data.to_sql(
        'companies',
        engine,
        if_exists='replace',
        index=False
    )
    
    # Update insider info
    insider_data = pd.DataFrame([{
        'cik': filing['insider_cik'],
        'name': filing['insider_name'],
        'company_cik': filing['company_cik'],
        'current_title': filing['insider_title'],
        'is_officer': filing['is_officer'],
        'is_director': filing['is_director'],
    }])
    
    insider_data.to_sql(
        'insiders',
        engine,
        if_exists='replace',
        index=False
    )
    
    # Add transactions
    for trans in filing['transactions']:
        trans_data = pd.DataFrame([{
            'filing_date': filing['filing_date'],
            'transaction_date': trans['date'],
            'insider_id': 1,  # TODO: Get actual insider ID
            'company_cik': filing['company_cik'],
            'transaction_type': trans['type'],
            'shares': trans['shares'],
            'price': trans['price'],
            'value': trans['value'],
            'owned_after': trans['owned_after'],
            'form_url': f"https://www.sec.gov/Archives/edgar/data/{filing['company_cik']}/{filing['accession_number']}.txt"
        }])
        
        trans_data.to_sql(
            'form4_transactions',
            engine,
            if_exists='append',
            index=False
        )

def ingest_form4_filings(
    cik: Optional[str] = None,
    days_back: int = 30,
    save_raw: bool = True
):
    """Ingest recent Form 4 filings for a company.
    
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
        raw_dir = RAW_DIR / 'form4'
        raw_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Search for Form 4 filings
        results = search_company_filings(
            cik=cik if cik else '',
            filing_type='4',
            start_date=start_date,
            end_date=end_date
        )
        
        for filing in results['filings']:
            try:
                # Download filing
                file_path = download_filing(
                    filing['accessionNumber'],
                    filing['cik'],
                    '4',
                    raw_dir if save_raw else '/tmp'
                )
                
                # Parse filing
                with open(file_path, 'r') as f:
                    filing_data = extract_form4_data(f.read())
                
                # Save to database
                save_to_database(filing_data, engine)
                
                logger.info(
                    f"Processed Form 4 filing {filing['accessionNumber']} "
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
        logger.error(f"Error ingesting Form 4 filings: {str(e)}")
        raise
        
if __name__ == "__main__":
    ingest_form4_filings()
