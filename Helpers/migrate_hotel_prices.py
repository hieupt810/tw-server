#!/usr/bin/env python3
"""
Migration script to add min_price and max_price properties to Hotel nodes in Neo4j.

This script extracts numeric prices from the price_range string field and adds them
as separate min_price and max_price properties for more efficient filtering.

Usage: python migrate_hotel_prices.py
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.utils import add_price_fields_to_neo4j_hotels

def main():
    print("Starting hotel price fields migration...")
    print("This will add min_price and max_price properties to Hotel nodes in Neo4j.")
    
    # Confirm before proceeding
    confirm = input("Do you want to proceed? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Migration cancelled.")
        return
    
    try:
        result = add_price_fields_to_neo4j_hotels()
        if 'error' in result:
            print(f"Migration failed: {result['error']}")
        else:
            print(f"Migration completed successfully!")
            print(f"Hotels updated: {result['updated']}")
            print(f"Errors: {result['errors']}")
    except Exception as e:
        print(f"Migration failed with exception: {str(e)}")

if __name__ == "__main__":
    main() 