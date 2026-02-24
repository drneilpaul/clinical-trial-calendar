"""
One-time script to update study portfolio data.
Run with: python update_studies.py
"""
import os
import sys

# Need to load streamlit secrets
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'

# Load secrets from .streamlit/secrets.toml
import toml
secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
secrets = toml.load(secrets_path)
supabase_url = secrets['supabase']['url']
supabase_key = secrets['supabase']['key']

from supabase import create_client
client = create_client(supabase_url, supabase_key)

def update_table(table, match_col, match_val, updates):
    """Update records matching a condition."""
    resp = client.table(table).update(updates).eq(match_col, match_val).execute()
    count = len(resp.data) if resp.data else 0
    print(f"  Updated {count} row(s) in {table} where {match_col}='{match_val}'")
    return count

def delete_record(table, study, site):
    """Delete a specific study+site record."""
    resp = client.table(table).delete().eq('Study', study).eq('ContractSite', site).execute()
    count = len(resp.data) if resp.data else 0
    print(f"  Deleted {count} row(s) from {table}: {study} @ {site}")
    return count

# ============================================================
# A. RENAMES
# ============================================================

print("\n=== A1. Rename BaxDuo → BaxDuo Prevent-HF (all tables) ===")
for table in ['study_site_details', 'patients', 'actual_visits', 'trial_schedules']:
    update_table(table, 'Study', 'BaxDuo', {'Study': 'BaxDuo Prevent-HF'})

print("\n  Setting ProtocolNumber = D6973C00001 on study_site_details...")
resp = client.table('study_site_details').update({'ProtocolNumber': 'D6973C00001'}).eq('Study', 'BaxDuo Prevent-HF').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

print("\n=== A2. Rename NN9489-8035 → Ambition 3 ===")
for table in ['study_site_details']:
    update_table(table, 'Study', 'NN9489-8035', {
        'Study': 'Ambition 3',
        'ProtocolNumber': 'NN9489-8035',
        'Description': 'Phase III, amycretin vs tirzepatide in T2DM; 3-arm open-label; global ~1,100 pts; 60-week treatment'
    })

print("\n=== A3. Rename D7261C00007 → T2DM PreScreening ===")
update_table('study_site_details', 'Study', 'D7261C00007', {
    'Study': 'T2DM PreScreening',
    'ProtocolNumber': 'D7261C00007'
})

# ============================================================
# B. STATUS CHANGES
# ============================================================

print("\n=== B. Status Changes ===")

# EVOLUTION @ Ashfields: active → expression_of_interest
print("\nEVOLUTION → EOI:")
resp = client.table('study_site_details').update({'StudyStatus': 'expression_of_interest'}).eq('Study', 'EVOLUTION').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# ELEVATE-CKD @ both sites: EOI → eoi_didnt_get
print("\nELEVATE-CKD → eoi_didnt_get:")
resp = client.table('study_site_details').update({
    'StudyStatus': 'eoi_didnt_get',
    'Sponsor': 'Boehringer',
    'ProtocolNumber': 'RENA 71089'
}).eq('Study', 'ELEVATE-CKD').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# Syeos Obesity T2DM: EOI → eoi_didnt_get
print("\nSyeos Obesity T2DM → eoi_didnt_get:")
resp = client.table('study_site_details').update({'StudyStatus': 'eoi_didnt_get'}).eq('Study', 'Syeos Obesity T2DM').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# Vesalius @ Ashfields: active → completed
print("\nVesalius → completed:")
resp = client.table('study_site_details').update({'StudyStatus': 'completed'}).eq('Study', 'Vesalius').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# FluSniff @ Kiltearn: active → completed
print("\nFluSniff → completed:")
resp = client.table('study_site_details').update({'StudyStatus': 'completed'}).eq('Study', 'FluSniff').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# BI-Synchronize @ Kiltearn: active → completed
print("\nBI-Synchronize → completed:")
resp = client.table('study_site_details').update({'StudyStatus': 'completed'}).eq('Study', 'BI-Synchronize').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# ============================================================
# D. DATA ENRICHMENT
# ============================================================

print("\n=== D. Data Enrichment ===")

# Eluminate 4: set ProtocolNumber
print("\nEluminate 4 protocol number:")
resp = client.table('study_site_details').update({'ProtocolNumber': 'D7261C00004'}).eq('Study', 'Eluminate 4').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# Eluminate 5: update SampleSize
print("\nEluminate 5 sample size → 1630:")
resp = client.table('study_site_details').update({'SampleSize': 1630}).eq('Study', 'Eluminate 5').execute()
print(f"  Updated {len(resp.data) if resp.data else 0} row(s)")

# ============================================================
# C. REMOVALS
# ============================================================

print("\n=== C. Removals ===")

# Maritime @ Kiltearn: delete
print("\nMaritime @ Kiltearn:")
delete_record('study_site_details', 'Maritime', 'Kiltearn')

# BaxDuoWRI @ Ashfields: delete (now merged into BaxDuo Prevent-HF)
print("\nBaxDuoWRI @ Ashfields:")
delete_record('study_site_details', 'BaxDuoWRI', 'Ashfields')

# ============================================================
# VERIFICATION
# ============================================================

print("\n=== Verification ===")
resp = client.table('study_site_details').select('Study, ContractSite, StudyStatus, Sponsor, ProtocolNumber').order('Study').execute()
print(f"\nTotal records: {len(resp.data)}")
print(f"\n{'Study':<30} {'Site':<12} {'Status':<25} {'Sponsor':<30} {'Protocol'}")
print("-" * 130)
for r in resp.data:
    study = r.get('Study', '')[:29]
    site = (r.get('ContractSite') or '')[:11]
    status = (r.get('StudyStatus') or '')[:24]
    sponsor = (r.get('Sponsor') or '')[:29]
    protocol = r.get('ProtocolNumber') or ''
    print(f"{study:<30} {site:<12} {status:<25} {sponsor:<30} {protocol}")

print("\nDone!")
