"""Initialize SQLite database with required tables."""
import sqlite3
from pathlib import Path
from ..config import DATA_DIR

def init_db():
    """Create SQLite database and tables."""
    db_path = DATA_DIR / 'insider.db'
    
    # Create data directory if it doesn't exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Companies table
    c.execute('''
    CREATE TABLE IF NOT EXISTS companies (
        cik TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        name TEXT NOT NULL,
        sector TEXT,
        industry TEXT,
        market_cap REAL,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insiders table
    c.execute('''
    CREATE TABLE IF NOT EXISTS insiders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cik TEXT NOT NULL,
        name TEXT NOT NULL,
        company_cik TEXT NOT NULL,
        current_title TEXT,
        is_officer BOOLEAN,
        is_director BOOLEAN,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (company_cik) REFERENCES companies(cik),
        UNIQUE(cik, company_cik)
    )
    ''')
    
    # Form 4 Transactions table
    c.execute('''
    CREATE TABLE IF NOT EXISTS form4_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_date DATE NOT NULL,
        transaction_date DATE NOT NULL,
        insider_id INTEGER NOT NULL,
        company_cik TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        shares REAL NOT NULL,
        price REAL NOT NULL,
        value REAL NOT NULL,
        owned_after REAL,
        form_url TEXT,
        FOREIGN KEY (insider_id) REFERENCES insiders(id),
        FOREIGN KEY (company_cik) REFERENCES companies(cik)
    )
    ''')
    
    # Form 8-K Events table
    c.execute('''
    CREATE TABLE IF NOT EXISTS form8k_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_date DATE NOT NULL,
        company_cik TEXT NOT NULL,
        event_date DATE NOT NULL,
        item_type TEXT NOT NULL,
        description TEXT,
        form_url TEXT,
        FOREIGN KEY (company_cik) REFERENCES companies(cik)
    )
    ''')
    
    # Congressional trades table
    c.execute('''
    CREATE TABLE IF NOT EXISTS congress_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_date DATE NOT NULL,
        transaction_date DATE NOT NULL,
        representative TEXT NOT NULL,
        ticker TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        amount_min REAL,
        amount_max REAL,
        description TEXT,
        source_url TEXT
    )
    ''')
    
    # Scores table
    c.execute('''
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL,
        role_score REAL NOT NULL,
        trade_type_score REAL NOT NULL,
        size_score REAL NOT NULL,
        cluster_score REAL NOT NULL,
        catalyst_score REAL NOT NULL,
        politician_score REAL NOT NULL,
        final_score REAL NOT NULL,
        calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (transaction_id) REFERENCES form4_transactions(id)
    )
    ''')
    
    # Indexes for performance
    c.execute('CREATE INDEX IF NOT EXISTS idx_form4_date ON form4_transactions(transaction_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_form4_company ON form4_transactions(company_cik)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_form8k_company ON form8k_events(company_cik)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_scores_transaction ON scores(transaction_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_congress_date ON congress_trades(transaction_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_congress_ticker ON congress_trades(ticker)')
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized at {db_path}")

if __name__ == "__main__":
    init_db()
