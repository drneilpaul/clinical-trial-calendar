"""
Validation script for Phase 1 financial calculations
Run this after implementing the optimized calculate_financial_totals()

This version displays results in Streamlit UI instead of terminal.
"""
import pandas as pd
import numpy as np
import streamlit as st

def validate_financial_totals(calendar_df, test_name="Phase 1", show_in_ui=True):
    """
    Validate financial calculations are correct.
    
    Args:
        calendar_df: Calendar DataFrame to validate
        test_name: Name for the test (for display)
        show_in_ui: If True, shows results in Streamlit UI. If False, uses print() for terminal.
    
    Returns:
        bool: True if validation passed, False otherwise
    """
    errors = []
    fy_errors = []
    
    # Create expander for validation results (can be collapsed)
    if show_in_ui:
        with st.expander(f"🔍 Phase 1 Validation: {test_name} - Financial Totals", expanded=False):
            st.markdown("**Validating optimized financial calculations...**")
            
            # Display performance timings if available
            try:
                if 'performance_timings' in st.session_state and st.session_state.performance_timings:
                    st.divider()
                    st.markdown("**⏱️ Performance Metrics:**")
                    
                    # Key functions to show
                    key_functions = [
                        'calculate_financial_totals',
                        'process_all_patients',
                        'build_calendar_dataframe',
                        'fill_calendar_with_visits',
                        '_build_calendar_impl'
                    ]
                    
                    for func_name in key_functions:
                        if func_name in st.session_state.performance_timings:
                            timing = st.session_state.performance_timings[func_name]
                            emoji = timing['emoji']
                            elapsed = timing['elapsed']
                            st.write(f"{emoji} `{func_name}`: **{elapsed:.2f}s**")
                    
                    # Show Phase 1 improvement if we have calculate_financial_totals timing
                    if 'calculate_financial_totals' in st.session_state.performance_timings:
                        elapsed = st.session_state.performance_timings['calculate_financial_totals']['elapsed']
                        if elapsed < 0.5:
                            st.success(f"✅ Phase 1 optimization working! Financial calculations: {elapsed:.2f}s (expected: 0.25-0.5s)")
                        else:
                            st.info(f"ℹ️ Financial calculations: {elapsed:.2f}s")
                    
                    st.divider()
            except Exception:
                pass  # Silently fail if session state not available
            
            # Check 1: Monthly totals reset at month boundaries
            st.write("✓ Checking monthly total resets...")
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
                st.error(f"❌ Found {len(errors)} monthly total errors")
                for err in errors[:5]:
                    st.write(f"   - {err}")
                if len(errors) > 5:
                    st.write(f"   ... and {len(errors) - 5} more errors")
            else:
                st.success("✅ All monthly totals correct")
            
            # Check 2: FY totals reset on April 1st
            st.write("\n✓ Checking FY total resets...")
            calendar_df['FY'] = calendar_df['FYStart']
            
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
                st.error(f"❌ Found {len(fy_errors)} FY total errors")
                for err in fy_errors[:5]:
                    st.write(f"   - {err}")
                if len(fy_errors) > 5:
                    st.write(f"   ... and {len(fy_errors) - 5} more errors")
            else:
                st.success("✅ All FY totals correct")
            
            # Check 3: Dates still in chronological order
            st.write("\n✓ Checking date order...")
            if calendar_df['Date'].is_monotonic_increasing:
                st.success("✅ Dates in correct chronological order")
            else:
                errors.append("Dates not in chronological order")
                st.error("❌ Dates NOT in chronological order")
            
            # Check 4: No NaN values in totals
            st.write("\n✓ Checking for NaN values...")
            nan_monthly = calendar_df['Monthly Total'].isna().sum()
            nan_fy = calendar_df['FY Total'].isna().sum()
            
            if nan_monthly > 0 or nan_fy > 0:
                errors.append(f"Found {nan_monthly} NaN in Monthly Total, {nan_fy} in FY Total")
                st.error(f"❌ Found NaN values: {nan_monthly} monthly, {nan_fy} FY")
            else:
                st.success("✅ No NaN values in totals")
            
            # Final result
            st.divider()
            if errors or fy_errors:
                st.error(f"❌ VALIDATION FAILED with {len(errors) + len(fy_errors)} errors")
                return False
            else:
                st.success("✅ VALIDATION PASSED - All checks successful")
                return True
    else:
        # Fallback to terminal output if not in Streamlit context
        print(f"\n{'='*60}")
        print(f"VALIDATING {test_name}: Financial Totals")
        print(f"{'='*60}\n")
        
        # Check 1: Monthly totals reset at month boundaries
        print("✓ Checking monthly total resets...")
        calendar_df['Month'] = calendar_df['Date'].dt.to_period('M')
        for month in calendar_df['Month'].unique():
            month_data = calendar_df[calendar_df['Month'] == month].sort_values('Date')
            
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
        
        for fy in calendar_df['FY'].dropna().unique():
            fy_data = calendar_df[calendar_df['FY'] == fy].sort_values('Date')
            
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

