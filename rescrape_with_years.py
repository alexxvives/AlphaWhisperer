"""
Backup the old database and rescrape Congressional trades with year information.
This will create a fresh database with properly dated trades.
"""

import os
import shutil
from datetime import datetime
from insider_alerts import init_database, scrape_all_congressional_trades_to_db

def backup_and_rescrape():
    """Backup old database and rescrape with years"""
    
    db_path = "data/congressional_trades.db"
    
    # Create backup if database exists
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"data/congressional_trades_OLD.db"
        
        print(f"Renaming existing database...")
        print(f"  From: {db_path}")
        print(f"  To: {backup_path}")
        
        # Remove old backup if exists
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except:
                pass
        
        # Rename current to OLD
        os.rename(db_path, backup_path)
        print(f"✓ Database renamed\n")
    
    # Initialize new database with updated schema
    print("Initializing new database with year columns...")
    init_database()
    print("✓ Database initialized\n")
    
    # Rescrape trades (default: ALL TIME - 3 years filter)
    print("Starting rescrape of Congressional trades...")
    print("This will scrape ALL trades from the last 3 years with year information.")
    print("This may take 10-15 minutes...\n")
    
    scrape_all_congressional_trades_to_db(days=None, max_pages=500)
    
    print("\n" + "="*80)
    print("✓ RESCRAPE COMPLETE")
    print("="*80)
    print("\nThe database now contains trades with year information.")
    print("You can now run the signal detection with proper date filtering.")

if __name__ == "__main__":
    backup_and_rescrape()
