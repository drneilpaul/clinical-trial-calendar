import io
import pandas as pd
from typing import List

from helpers import get_financial_year, get_current_financial_year_boundaries

try:
    import xlsxwriter  # noqa: F401
    XLSX_ENGINE = "xlsxwriter"
except ImportError:
    XLSX_ENGINE = "openpyxl"


ACTIVITY_TYPES: List[str] = ["patient", "extra", "siv", "monitor"]


def _prepare_visits_dataframe(visits_df: pd.DataFrame) -> pd.DataFrame:
    if visits_df is None or visits_df.empty:
        return pd.DataFrame()

    df = visits_df.copy()

    if 'Date' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    if 'VisitType' not in df.columns:
        df['VisitType'] = 'patient'

    df['VisitType'] = df['VisitType'].astype(str).str.strip().str.lower()
    df.loc[df['VisitType'].isin(['', 'nan', 'none', 'null']), 'VisitType'] = 'patient'

    if 'IsActual' not in df.columns:
        df['IsActual'] = False

    # Remove tolerance window rows
    if 'Visit' in df.columns:
        df = df[~df['Visit'].isin(['-', '+'])]

    # Ensure required columns exist
    for column in ['SiteofVisit', 'Study']:
        if column not in df.columns:
            df[column] = ''

    return df


def _build_historical_actuals_sheet(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            'FinancialYear', 'Site', 'Study',
            'Patient Visits (Actual)', 'Visits with Extras (Actual)',
            'SIVs (Actual)', 'Monitor Visits (Actual)'
        ])

    actual_df = df[df.get('IsActual', False) == True].copy()
    if actual_df.empty:
        return pd.DataFrame(columns=[
            'FinancialYear', 'Site', 'Study',
            'Patient Visits (Actual)', 'Visits with Extras (Actual)',
            'SIVs (Actual)', 'Monitor Visits (Actual)'
        ])

    # OPTIMIZED: Use vectorized financial year calculation
    from helpers import get_financial_year_for_series
    actual_df['FinancialYear'] = get_financial_year_for_series(actual_df['Date'])
    actual_df = actual_df.dropna(subset=['FinancialYear'])

    pivot = actual_df.pivot_table(
        index=['FinancialYear', 'SiteofVisit', 'Study'],
        columns='VisitType',
        values='VisitName',
        aggfunc='count',
        fill_value=0
    )

    pivot = pivot.reindex(columns=ACTIVITY_TYPES, fill_value=0)
    pivot = pivot.rename(columns={
        'patient': 'Patient Visits (Actual)',
        'extra': 'Visits with Extras (Actual)',
        'siv': 'SIVs (Actual)',
        'monitor': 'Monitor Visits (Actual)'
    })

    pivot = pivot.reset_index().rename(columns={'SiteofVisit': 'Site'})
    pivot = pivot.sort_values(['FinancialYear', 'Site', 'Study']).reset_index(drop=True)
    return pivot


def _build_current_fy_split_sheet(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            'Site', 'Study',
            'Patient Visits (Actual)', 'Patient Visits (Predicted)', 'Patient Visits (Total)',
            'Visits with Extras (Actual)', 'Visits with Extras (Predicted)', 'Visits with Extras (Total)',
            'SIVs (Actual)', 'SIVs (Predicted)', 'SIVs (Total)',
            'Monitor Visits (Actual)', 'Monitor Visits (Predicted)', 'Monitor Visits (Total)'
        ])

    fy_start, fy_end = get_current_financial_year_boundaries()
    current_df = df[
        (df['Date'] >= fy_start) &
        (df['Date'] <= fy_end)
    ].copy()

    if current_df.empty:
        return pd.DataFrame(columns=[
            'Site', 'Study',
            'Patient Visits (Actual)', 'Patient Visits (Predicted)', 'Patient Visits (Total)',
            'Visits with Extras (Actual)', 'Visits with Extras (Predicted)', 'Visits with Extras (Total)',
            'SIVs (Actual)', 'SIVs (Predicted)', 'SIVs (Total)',
            'Monitor Visits (Actual)', 'Monitor Visits (Predicted)', 'Monitor Visits (Total)'
        ])

    current_df['Status'] = current_df['IsActual'].map(lambda x: 'Actual' if x else 'Predicted')

    pivot = current_df.pivot_table(
        index=['SiteofVisit', 'Study'],
        columns=['VisitType', 'Status'],
        values='VisitName',
        aggfunc='count',
        fill_value=0
    )

    # Ensure all combinations exist
    desired_columns = []
    for visit_type in ACTIVITY_TYPES:
        for status in ['Actual', 'Predicted']:
            desired_columns.append((visit_type, status))

    pivot = pivot.reindex(columns=pd.MultiIndex.from_tuples(desired_columns), fill_value=0)

    # Build flat columns with totals
    result = pd.DataFrame(index=pivot.index)
    for visit_type, label in [
        ('patient', 'Patient Visits'),
        ('extra', 'Visits with Extras'),
        ('siv', 'SIVs'),
        ('monitor', 'Monitor Visits')
    ]:
        actual_col = (visit_type, 'Actual')
        predicted_col = (visit_type, 'Predicted')

        actual_series = pivot[actual_col]
        predicted_series = pivot[predicted_col]
        total_series = actual_series + predicted_series

        result[f'{label} (Actual)'] = actual_series
        result[f'{label} (Predicted)'] = predicted_series
        result[f'{label} (Total)'] = total_series

    result = result.reset_index().rename(columns={'SiteofVisit': 'Site'})
    result = result.sort_values(['Site', 'Study']).reset_index(drop=True)
    return result


def create_activity_summary_workbook(visits_df: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()
    
    prepared_df = _prepare_visits_dataframe(visits_df)

    historical_sheet = _build_historical_actuals_sheet(prepared_df)
    current_split_sheet = _build_current_fy_split_sheet(prepared_df)

    with pd.ExcelWriter(output, engine=XLSX_ENGINE) as writer:
        if historical_sheet.empty:
            pd.DataFrame({"Message": ["No actual visit data available"]}).to_excel(
                writer, sheet_name="Historical Actuals", index=False
            )
        else:
            historical_sheet.to_excel(writer, sheet_name="Historical Actuals", index=False)

        if current_split_sheet.empty:
            pd.DataFrame({"Message": ["No visits in current financial year"]}).to_excel(
                writer, sheet_name="Current FY Actual vs Pred", index=False
            )
        else:
            current_split_sheet.to_excel(writer, sheet_name="Current FY Actual vs Pred", index=False)

    output.seek(0)
    return output

