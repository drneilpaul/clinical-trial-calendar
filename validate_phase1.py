"""
Validation script for Phase 1 financial calculations
Run this after implementing the optimized calculate_financial_totals()
"""
import pandas as pd
import numpy as np

def validate_financial_totals(calendar_df, test_name="Phase 1"):
    """Validate financial calculations are correct"""
    print(f"\n{'='*60}")
    print(f"VALIDATING {test_name}: Financial Totals")
    print(f"{'='*60}\n")
    
    errors = []
    
    # Check 1: Monthly totals reset at month boundaries
    print("✓ Checking monthly total resets...")
    calendar_df['Month'] = calendar_df['Date'].dt.to_period('M')
    for month in calendar_df['Month'].unique():
        month_data = calendar_df[calendar_df['Month'] == month].sort_values('Date')
        
        # Last day of month should equal sum of all daily totals
        expected_total = month_data['Daily Total'].sum()
        actual_total = month_data['Monthly Total'].iloc[-1]
        
        if not np.isclose(expected_total, actual_total, rtol=1e-5):
            errors.append(
                f"Month {month}: Expected {expected_total:.2f}, got {actual_total:.2f}"
            )
    
    if errors:
        print(f"  ❌ Found {len(errors)} monthly total errors")
        for err in errors[:5]:
            print(f"    - {err}")
    else:
        print("  ✅ All monthly totals correct")
    
    # Check 2: FY totals reset on April 1st
    print("\n✓ Checking FY total resets...")
    calendar_df['FY'] = calendar_df['FYStart']
    fy_errors = []
    
    for fy in calendar_df['FY'].dropna().unique():
        fy_data = calendar_df[calendar_df['FY'] == fy].sort_values('Date')
        
        # Last day of FY should equal sum of all daily totals
        expected_total = fy_data['Daily Total'].sum()
        actual_total = fy_data['FY Total'].iloc[-1]
        
        if not np.isclose(expected_total, actual_total, rtol=1e-5):
            fy_errors.append(
                f"FY {fy}: Expected {expected_total:.2f}, got {actual_total:.2f}"
            )
    
    if fy_errors:
        print(f"  ❌ Found {len(fy_errors)} FY total errors")
        for err in fy_errors[:5]:
            print(f"    - {err}")
    else:
        print("  ✅ All FY totals correct")
    
    # Check 3: Dates still in chronological order
    print("\n✓ Checking date order...")
    if calendar_df['Date'].is_monotonic_increasing:
        print("  ✅ Dates in correct chronological order")
    else:
        errors.append("Dates not in chronological order")
        print("  ❌ Dates NOT in chronological order")
    
    # Check 4: No NaN values in totals
    print("\n✓ Checking for NaN values...")
    nan_monthly = calendar_df['Monthly Total'].isna().sum()
    nan_fy = calendar_df['FY Total'].isna().sum()
    
    if nan_monthly > 0 or nan_fy > 0:
        errors.append(f"Found {nan_monthly} NaN in Monthly Total, {nan_fy} in FY Total")
        print(f"  ❌ Found NaN values: {nan_monthly} monthly, {nan_fy} FY")
    else:
        print("  ✅ No NaN values in totals")
    
    # Final result
    print(f"\n{'='*60}")
    if errors or fy_errors:
        print(f"❌ VALIDATION FAILED with {len(errors) + len(fy_errors)} errors")
        return False
    else:
        print("✅ VALIDATION PASSED - All checks successful")
        return True

