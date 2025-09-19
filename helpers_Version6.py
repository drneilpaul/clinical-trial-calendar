import pandas as pd
from dateutil.parser import parse

def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dayfirst=True)
    else:
        return pd.read_excel(uploaded_file, engine="openpyxl")

def normalize_columns(df):
    if df is not None:
        df.columns = df.columns.str.strip()
    return df

def parse_dates_column(df, col, errors="raise"):
    if col not in df.columns:
        return df, []
    failed_rows = []
    def try_parse(val):
        try:
            return parse(str(val), dayfirst=True)
        except Exception:
            failed_rows.append(val)
            return pd.NaT
    df[col] = df[col].apply(try_parse)
    return df, failed_rows