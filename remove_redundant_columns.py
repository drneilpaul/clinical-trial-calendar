#!/usr/bin/env python3
"""
Script to remove redundant columns from the database.
This will remove the 'site' and 'origin_site' columns from the patients table,
keeping only 'patient_practice' as the source of truth.
"""

import os
import sys
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """Get Supabase client"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        print("❌ Error: SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set")
        sys.exit(1)
    
    return create_client(url, key)

def check_table_structure(client: Client):
    """Check current table structure"""
    try:
        # Get a sample record to see current columns
        response = client.table('patients').select("*").limit(1).execute()
        if response.data:
            print("📋 Current table structure:")
            for key in response.data[0].keys():
                print(f"  - {key}")
        else:
            print("⚠️  No data found in patients table")
    except Exception as e:
        print(f"❌ Error checking table structure: {e}")
        return False
    return True

def remove_columns(client: Client):
    """Remove redundant columns from the patients table"""
    try:
        print("🗑️  Removing redundant columns...")
        
        # Note: Supabase doesn't support DROP COLUMN directly via Python client
        # You'll need to run these SQL commands in your Supabase SQL editor
        
        sql_commands = [
            "ALTER TABLE patients DROP COLUMN IF EXISTS site;",
            "ALTER TABLE patients DROP COLUMN IF EXISTS origin_site;"
        ]
        
        print("📝 Run these SQL commands in your Supabase SQL editor:")
        print("=" * 60)
        for cmd in sql_commands:
            print(cmd)
        print("=" * 60)
        
        print("\n✅ After running these commands:")
        print("  - 'site' column will be removed")
        print("  - 'origin_site' column will be removed") 
        print("  - 'patient_practice' will remain as the single source of truth")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def verify_removal(client: Client):
    """Verify columns have been removed"""
    try:
        response = client.table('patients').select("*").limit(1).execute()
        if response.data:
            remaining_columns = list(response.data[0].keys())
            print(f"\n📋 Remaining columns: {remaining_columns}")
            
            if 'site' not in remaining_columns and 'origin_site' not in remaining_columns:
                print("✅ Successfully removed redundant columns!")
                if 'patient_practice' in remaining_columns:
                    print("✅ 'patient_practice' column is present and ready to use")
                else:
                    print("⚠️  Warning: 'patient_practice' column not found")
            else:
                print("⚠️  Some redundant columns may still be present")
        else:
            print("⚠️  No data found to verify")
    except Exception as e:
        print(f"❌ Error verifying removal: {e}")

def main():
    """Main function"""
    print("🔧 Database Column Cleanup Tool")
    print("=" * 40)
    
    # Get Supabase client
    client = get_supabase_client()
    
    # Check current structure
    if not check_table_structure(client):
        return
    
    # Show removal instructions
    remove_columns(client)
    
    print("\n🔄 After running the SQL commands, run this script again to verify")
    print("   python remove_redundant_columns.py --verify")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        client = get_supabase_client()
        verify_removal(client)
    else:
        main()
