import pandas as pd
import io
from datetime import datetime

def create_enhanced_excel_export(calendar_df, patients_df, visits_df, site_column_mapping, unique_sites):
    """Create Excel export with enhanced explanatory headers and documentation"""
    
    try:
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.table import Table, TableStyleInfo
    except ImportError:
        st.error("openpyxl library required for enhanced Excel formatting")
        return None
    
    # Create workbook with multiple sheets
    wb = Workbook()
    
    # === Main Calendar Sheet ===
    ws_calendar = wb.active
    ws_calendar.title = "Clinical Trial Calendar"
    
    # Add title and metadata
    ws_calendar['A1'] = "Clinical Trial Calendar - Patient Visit Schedule"
    ws_calendar['A1'].font = Font(size=16, bold=True, color="1F4E79")
    ws_calendar.merge_cells('A1:H1')
    
    ws_calendar['A2'] = f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws_calendar['A2'].font = Font(size=10, italic=True)
    
    ws_calendar['A3'] = f"Total Patients: {len(patients_df)} | Total Sites: {len(unique_sites)}"
    ws_calendar['A3'].font = Font(size=10, italic=True)
    
    # Column explanations
    explanations = {
        'Date': 'Calendar Date (DD/MM/YYYY)',
        'Day': 'Day of Week',
        'Daily Total': 'Total Daily Revenue (£)',
        'Monthly Total': 'Cumulative Monthly Revenue (£)', 
        'FY Total': 'Cumulative Financial Year Revenue (£)'
    }
    
    # Prepare enhanced dataframe
    enhanced_df = calendar_df.copy()
    
    # Add site grouping headers row
    site_headers_row = [''] * len(enhanced_df.columns)
    column_explanations_row = [''] * len(enhanced_df.columns)
    
    for col_idx, col_name in enumerate(enhanced_df.columns):
        # Add explanations for standard columns
        if col_name in explanations:
            column_explanations_row[col_idx] = explanations[col_name]
        
        # Add site headers for patient columns
        if col_name not in ['Date', 'Day'] and not any(x in col_name for x in ['Income', 'Total']):
            # Find which site this patient belongs to
            for site in unique_sites:
                if col_name in site_column_mapping.get(site, []):
                    site_headers_row[col_idx] = f"Site: {site}"
                    # Enhanced patient column explanation
                    if '_' in col_name:
                        study, patient_id = col_name.split('_', 1)
                        column_explanations_row[col_idx] = f"Study: {study} | Patient: {patient_id}"
                    else:
                        column_explanations_row[col_idx] = f"Patient: {col_name}"
                    break
    
    # Write to Excel starting from row 5
    start_row = 5
    
    # Site headers row
    for col_idx, header in enumerate(site_headers_row, 1):
        if header:
            cell = ws_calendar.cell(row=start_row, column=col_idx, value=header)
            cell.font = Font(bold=True, size=11, color="FFFFFF")
            cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
    
    # Column explanations row
    for col_idx, explanation in enumerate(column_explanations_row, 1):
        if explanation:
            cell = ws_calendar.cell(row=start_row + 1, column=col_idx, value=explanation)
            cell.font = Font(size=9, italic=True, color="595959")
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
    
    # Column names row
    for col_idx, col_name in enumerate(enhanced_df.columns, 1):
        cell = ws_calendar.cell(row=start_row + 2, column=col_idx, value=col_name)
        cell.font = Font(bold=True, size=10)
        cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")
    
    # Data rows
    for row_idx, row in enhanced_df.iterrows():
        for col_idx, value in enumerate(row, 1):
            cell = ws_calendar.cell(row=start_row + 3 + row_idx, column=col_idx, value=value)
            # Format dates
            if col_idx == 1 and isinstance(value, str):  # Date column
                cell.number_format = 'DD/MM/YYYY'
            # Format currency columns
            elif any(x in enhanced_df.columns[col_idx-1] for x in ['Total', 'Income']):
                if isinstance(value, str) and '£' in value:
                    cell.number_format = '"£"#,##0.00'
    
    # Auto-adjust column widths
    for col_idx, col in enumerate(enhanced_df.columns, 1):
        col_letter = get_column_letter(col_idx)
        max_length = max(
            len(str(site_headers_row[col_idx-1])),
            len(str(column_explanations_row[col_idx-1])),
            len(str(col)),
            max([len(str(cell)) for cell in enhanced_df[col].astype(str)])
        )
        ws_calendar.column_dimensions[col_letter].width = min(max(12, max_length + 2), 25)
    
    # Set row heights for header rows
    ws_calendar.row_dimensions[start_row].height = 25
    ws_calendar.row_dimensions[start_row + 1].height = 35
    ws_calendar.row_dimensions[start_row + 2].height = 20
    
    # === Data Dictionary Sheet ===
    ws_dict = wb.create_sheet("Data Dictionary")
    
    dictionary_data = [
        ["Column Name", "Description", "Data Type", "Example"],
        ["Date", "Calendar date for the visit schedule", "Date", "15/09/2025"],
        ["Day", "Day of the week", "Text", "Monday"],
        ["Daily Total", "Total revenue for all visits on this date", "Currency", "£1,250.00"],
        ["Monthly Total", "Cumulative revenue for the month up to this date", "Currency", "£15,750.00"],
        ["FY Total", "Cumulative revenue for financial year up to this date", "Currency", "£125,500.00"],
        ["Study_PatientID", "Visit information for specific patient", "Text", "V1, V2"],
        ["Site Income", "Revenue generated by visits at specific site", "Currency", "£500.00"]
    ]
    
    for row_idx, row_data in enumerate(dictionary_data, 1):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws_dict.cell(row=row_idx, column=col_idx, value=value)
            if row_idx == 1:  # Header row
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="2F5F8F", end_color="2F5F8F", fill_type="solid")
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    
    # Auto-adjust dictionary columns
    for col_idx in range(1, 5):
        col_letter = get_column_letter(col_idx)
        if col_idx == 2:  # Description column
            ws_dict.column_dimensions[col_letter].width = 40
        else:
            ws_dict.column_dimensions[col_letter].width = 15
    
    # === Summary Sheet ===
    ws_summary = wb.create_sheet("Summary")
    
    summary_data = [
        ["Clinical Trial Summary", ""],
        ["", ""],
        ["Total Patients", len(patients_df)],
        ["Total Sites", len(unique_sites)],
        ["Date Range", f"{enhanced_df['Date'].min()} to {enhanced_df['Date'].max()}"],
        ["", ""],
        ["Sites Included:", ""],
    ]
    
    # Add site details
    for site in sorted(unique_sites):
        site_patients = len([col for col in enhanced_df.columns if col in site_column_mapping.get(site, [])])
        summary_data.append([f"  - {site}", f"{site_patients} patients"])
    
    for row_idx, (label, value) in enumerate(summary_data, 1):
        ws_summary.cell(row=row_idx, column=1, value=label).font = Font(bold=True if value == "" else False)
        ws_summary.cell(row=row_idx, column=2, value=value)
    
    ws_summary.column_dimensions['A'].width = 20
    ws_summary.column_dimensions['B'].width = 15
    
    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output

# Usage in your Streamlit app:
def add_enhanced_download_section(calendar_df, patients_df, visits_df, site_column_mapping, unique_sites):
    """Add enhanced download section with explanatory Excel export"""
    
    st.subheader("📊 Enhanced Downloads")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Standard CSV download
        csv_data = calendar_df.to_csv(index=False)
        st.download_button(
            label="📄 Download CSV",
            data=csv_data,
            file_name=f"clinical_calendar_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    with col2:
        # Basic Excel download
        basic_excel = io.BytesIO()
        with pd.ExcelWriter(basic_excel, engine='openpyxl') as writer:
            calendar_df.to_excel(writer, sheet_name='Calendar', index=False)
        basic_excel.seek(0)
        
        st.download_button(
            label="📊 Download Basic Excel",
            data=basic_excel.getvalue(),
            file_name=f"clinical_calendar_basic_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col3:
        # Enhanced Excel download
        enhanced_excel = create_enhanced_excel_export(
            calendar_df, patients_df, visits_df, site_column_mapping, unique_sites
        )
        
        if enhanced_excel:
            st.download_button(
                label="✨ Download Enhanced Excel",
                data=enhanced_excel.getvalue(),
                file_name=f"clinical_calendar_enhanced_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Includes explanatory headers, data dictionary, and summary sheet"
            )
    
    # Information about enhanced features
    with st.expander("ℹ️ What's included in the Enhanced Excel?"):
        st.markdown("""
        **Enhanced Excel Export Features:**
        
        📋 **Main Calendar Sheet:**
        - Site grouping headers above patient columns
        - Column explanations (what each column represents)
        - Professional formatting with colors and borders
        - Auto-sized columns for better readability
        
        📖 **Data Dictionary Sheet:**
        - Detailed explanation of each column type
        - Data types and example values
        - Easy reference for understanding the data
        
        📊 **Summary Sheet:**
        - Overview of total patients and sites
        - Date range covered
        - Breakdown of patients per site
        - Quick statistics
        
        **Perfect for:**
        - Sharing with stakeholders who need context
        - Long-term archival with self-documenting format
        - Compliance and audit requirements
        """)
