"""
Configuration settings for Clinical Trial Calendar Generator
Working version with no syntax errors
"""

import streamlit as st
import os
from typing import Dict, List

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

APP_TITLE = "Clinical Trial Calendar Generator"
APP_VERSION = "v2.5.0"
APP_SUBTITLE = "Enhanced Error Handling Version"

APP_CONFIG = {
    'title': APP_TITLE,
    'version': APP_VERSION,
    'description': 'Generate comprehensive visit calendars for clinical trials',
    'max_file_size_mb': 50,
    'supported_file_types': ['csv', 'xlsx', 'xls']
}

# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def initialize_session_state():
    """Initialize all session state variables"""
    if 'show_patient_form' not in st.session_state:
        st.session_state.show_patient_form = False
    if 'show_visit_form' not in st.session_state:
        st.session_state.show_visit_form = False
    if 'patient_added' not in st.session_state:
        st.session_state.patient_added = False
    if 'visit_added' not in st.session_state:
        st.session_state.visit_added = False
    if 'list_weight' not in st.session_state:
        st.session_state.list_weight = 35
    if 'work_weight' not in st.session_state:
        st.session_state.work_weight = 35
    if 'recruitment_weight' not in st.session_state:
        st.session_state.recruitment_weight = 30
    if 'show_weights_form' not in st.session_state:
        st.session_state.show_weights_form = False

# =============================================================================
# LEGACY CONSTANTS (Backward Compatibility)
# =============================================================================

DEFAULT_LIST_WEIGHT = 35
DEFAULT_WORK_WEIGHT = 35  
DEFAULT_RECRUITMENT_WEIGHT = 30
ASHFIELDS_LIST_SIZE = 28500
KILTEARN_LIST_SIZE = 12500

# =============================================================================
# FILE STRUCTURE REQUIREMENTS
# =============================================================================

REQUIRED_COLUMNS = {
    'patients': {
        'required': ['PatientID', 'Study', 'StartDate'],
        'optional': ['Site', 'PatientPractice', 'Randomization', 'Notes'],
        'description': 'Patient enrollment data with study start dates'
    },
    'trials': {
        'required': ['Study', 'Day', 'VisitName'],
        'optional': ['SiteforVisit', 'Income', 'Payment', 'ToleranceBefore', 'ToleranceAfter'],
        'description': 'Trial visit schedule templates'
    },
    'actual_visits': {
        'required': ['PatientID', 'Study', 'VisitName', 'ActualDate'],
        'optional': ['ActualPayment', 'Notes', 'Status', 'Site'],
        'description': 'Actual completed visit records (optional file)'
    }
}

# Legacy column lists
PATIENTS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['patients']['required']
TRIALS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['trials']['required']
ACTUAL_VISITS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['actual_visits']['required']

# =============================================================================
# VALIDATION RULES
# =============================================================================

VALIDATION_RULES = {
    'patient_id': {
        'max_length': 50,
        'allow_empty': False,
        'description': 'Alphanumeric with hyphens and underscores only'
    },
    'study_name': {
        'max_length': 100,
        'allow_empty': False,
        'description': 'Study protocol identifier'
    },
    'visit_name': {
        'max_length': 100,
        'allow_empty': False,
        'description': 'Visit identifier'
    },
    'date_range': {
        'min_year': 2020,
        'max_years_future': 5,
        'description': 'Reasonable date range for clinical trials'
    }
}

# =============================================================================
# UI CONFIGURATION
# =============================================================================

UI_CONFIG = {
    'date_formats': {
        'display': '%d/%m/%Y',
        'input': ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y']
    }
}

UK_DATE_FORMATS = UI_CONFIG['date_formats']['input']
DISPLAY_DATE_FORMAT = UI_CONFIG['date_formats']['display']

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_structure_info() -> str:
    """Return file structure information as markdown"""
    info = []
    
    for file_type, config in REQUIRED_COLUMNS.items():
        section = f"**{file_type.replace('_', ' ').title()} File:**\n"
        section += f"{config['description']}\n\n"
        section += "Required columns:\n"
        for col in config['required']:
            section += f"- {col}\n"
        
        if config['optional']:
            section += "\nOptional columns:\n"
            for col in config['optional']:
                section += f"- {col}\n"
        
        info.append(section)
    
    return "\n".join(info)

def get_validation_summary() -> Dict[str, str]:
    """Get validation rules summary"""
    summary = {}
    for rule_type, rules in VALIDATION_RULES.items():
        summary[rule_type] = rules.get('description', 'No description')
    return summary
