import streamlit as st
import pandas as pd

st.title("SiteforVisit Column Debug Test")

# File upload
trials_file = st.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])

def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dayfirst=True)
    else:
        return pd.read_excel(uploaded_file, engine="openpyxl")

if trials_file:
    st.write("## File Analysis")
    
    # Load file
    trials_df = load_file(trials_file)
    st.write(f"Original columns: {list(trials_df.columns)}")
    
    # Clean columns
    trials_df.columns = trials_df.columns.str.strip()
    st.write(f"After .strip(): {list(trials_df.columns)}")
    
    # Check for SiteforVisit
    st.write(f"'SiteforVisit' in columns: {'SiteforVisit' in trials_df.columns}")
    
    # Show each column in detail
    st.write("## Detailed Column Analysis:")
    for i, col in enumerate(trials_df.columns):
        is_match = col == "SiteforVisit"
        st.write(f"Column {i}: '{col}' (len={len(col)}) {'✓ MATCH!' if is_match else ''}")
        st.write(f"  - ASCII values: {[ord(c) for c in col]}")
    
    # Show first few rows
    st.write("## Data Preview:")
    st.dataframe(trials_df.head())
