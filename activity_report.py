import io
import pandas as pd

from helpers import get_financial_year_for_series, log_activity


def _sanitize_visits(visits_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize visits for activity reporting."""
    if visits_df is None or visits_df.empty:
        return pd.DataFrame()
    df = visits_df.copy()
    # Ensure required columns exist
    for col in ['Date', 'Study', 'SiteofVisit', 'Visit', 'IsActual', 'IsProposed']:
        if col not in df.columns:
            df[col] = None
    # Drop tolerance markers
    df = df[~df['Visit'].isin(['-', '+'])]
    # Normalize date
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    # Add FinancialYear column
    df['FinancialYear'] = get_financial_year_for_series(df['Date'])
    return df


def create_activity_summary_workbook(visits_df: pd.DataFrame) -> io.BytesIO:
    """
    Build activity summary workbook (actual vs predicted) by FY, site, and study.
    Returns BytesIO for download.
    """
    output = io.BytesIO()
    try:
        df = _sanitize_visits(visits_df)
        if df.empty:
            # Return an empty workbook with headers to avoid errors
            empty_summary = pd.DataFrame(
                columns=['FinancialYear', 'Site', 'Study', 'ActualVisits', 'PredictedVisits', 'TotalVisits']
            )
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                empty_summary.to_excel(writer, sheet_name='Summary', index=False)
            output.seek(0)
            return output

        # Determine actual vs predicted
        is_actual = df.get('IsActual', False) == True
        is_proposed = df.get('IsProposed', False) == True if 'IsProposed' in df.columns else pd.Series([False] * len(df))

        actual_df = df[is_actual & ~is_proposed]
        predicted_df = df[~is_actual]

        # Group counts
        group_cols = ['FinancialYear', 'SiteofVisit', 'Study']
        actual_counts = (
            actual_df.groupby(group_cols)['Visit']
            .count()
            .rename('ActualVisits')
            .reset_index()
        )
        predicted_counts = (
            predicted_df.groupby(group_cols)['Visit']
            .count()
            .rename('PredictedVisits')
            .reset_index()
        )

        summary = pd.merge(
            actual_counts,
            predicted_counts,
            on=group_cols,
            how='outer'
        ).fillna(0)

        summary['TotalVisits'] = summary['ActualVisits'] + summary['PredictedVisits']
        summary = summary.rename(columns={'SiteofVisit': 'Site'})

        # Ensure ints for counts
        for col in ['ActualVisits', 'PredictedVisits', 'TotalVisits']:
            summary[col] = summary[col].astype(int)

        # Sort for readability
        summary = summary.sort_values(['FinancialYear', 'Site', 'Study'])

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary.to_excel(writer, sheet_name='Summary', index=False)

        output.seek(0)
        return output
    except Exception as e:
        log_activity(f"Activity report generation failed: {e}", level='error')
        raise
