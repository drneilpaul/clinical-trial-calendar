"""
Configuration settings for Clinical Trial Calendar Generator
Enhanced for Supabase integration preparation
"""

import streamlit as st
from typing import Dict, List
import os

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

APP_CONFIG = {
    'title': 'Clinical Trial Calendar Generator',
    'version': '2.0.0',
    'description': 'Generate comprehensive visit calendars for clinical trials',
    'author': 'Clinical Research Team',
    'max_file_size_mb': 50,
    'supported_file_types': ['csv', 'xlsx', 'xls'],
    'date_tolerance_days': 7,
    'session_timeout_minutes': 30
}

# =============================================================================
# SESSION STATE INITIALIZATION (Backward compatibility)
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

# Legacy constants for backward compatibility
APP_TITLE = "Clinical Trial Calendar Generator"
APP_VERSION = "v2.4.0"
APP_SUBTITLE = "Enhanced Version - Three-Level Calendar Display"
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
        'optional': ['SiteforVisit', 'Income', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'Window', 'VisitType', 'Mandatory'],
        'description': 'Trial visit schedule templates'
    },
    'actual_visits': {
        'required': ['PatientID', 'Study', 'VisitName', 'ActualDate'],
        'optional': ['ActualPayment', 'Notes', 'Status', 'Site'],
        'description': 'Actual completed visit records (optional file)'
    }
}

# =============================================================================
# VALIDATION RULES
# =============================================================================

VALIDATION_RULES = {
    'patient_id': {
        'max_length': 50,
        'allow_empty': False,
        'pattern': r'^[A-Za-z0-9\-_]+

# =============================================================================
# DATABASE CONFIGURATION (SUPABASE PREPARATION)
# =============================================================================

DATABASE_CONFIG = {
    'connection_timeout': 30,
    'max_retries': 3,
    'batch_size': 1000,
    'tables': {
        'patients': 'clinical_patients',
        'trials': 'trial_schedules', 
        'visits': 'visit_calendar',
        'actual_visits': 'actual_visits'
    },
    'indexes': [
        'idx_patients_study',
        'idx_visits_patient_date',
        'idx_visits_status'
    ]
}

# Environment variable keys for Supabase
SUPABASE_ENV_VARS = {
    'url': 'SUPABASE_URL',
    'key': 'SUPABASE_ANON_KEY',
    'service_key': 'SUPABASE_SERVICE_KEY'
}

# =============================================================================
# VALIDATION RULES
# =============================================================================

VALIDATION_RULES = {
    'patient_id': {
        'max_length': 50,
        'allow_empty': False,
        'pattern': r'^[A-Za-z0-9\-_]+$',
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
        'description': 'Visit identifier (e.g., Screening, Week 4)'
    },
    'date_range': {
        'min_year': 2020,
        'max_years_future': 5,
        'description': 'Reasonable date range for clinical trials'
    },
    'day_values': {
        'min_day': -30,  # Allow some pre-randomization visits
        'max_day': 3650,  # 10 years maximum
        'description': 'Visit day relative to start date'
    }
}

# =============================================================================
# UI CONFIGURATION
# =============================================================================

UI_CONFIG = {
    'sidebar_width': 300,
    'max_display_rows': 1000,
    'pagination_size': 50,
    'chart_height': 400,
    'colors': {
        'primary': '#1f77b4',
        'success': '#2ca02c', 
        'warning': '#ff7f0e',
        'error': '#d62728',
        'info': '#17becf'
    },
    'date_formats': {
        'display': '%d/%m/%Y',
        'input': ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'],
        'default_locale': 'en_GB'
    }
}

# =============================================================================
# ERROR HANDLING CONFIGURATION
# =============================================================================

ERROR_CONFIG = {
    'max_errors_display': 20,
    'auto_clear_after_minutes': 30,
    'log_level': 'INFO',
    'critical_error_types': [
        'FileProcessingError',
        'DataValidationError', 
        'DatabaseConnectionError'
    ],
    'retry_attempts': {
        'file_upload': 3,
        'database_operation': 3,
        'api_call': 5
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_structure_info() -> str:
    """Generate formatted file structure requirements"""
    info_sections = []
    
    for file_type, config in REQUIRED_COLUMNS.items():
        section = f"## {file_type.replace('_', ' ').title()} File\n"
        section += f"**Description:** {config['description']}\n\n"
        
        section += "**Required Columns:**\n"
        for col in config['required']:
            section += f"- `{col}`\n"
        
        if config['optional']:
            section += "\n**Optional Columns:**\n"
            for col in config['optional']:
                section += f"- `{col}`\n"
        
        section += "\n"
        info_sections.append(section)
    
    return "\n".join(info_sections)

def get_validation_summary() -> Dict[str, str]:
    """Get validation rules summary"""
    summary = {}
    for rule_type, rules in VALIDATION_RULES.items():
        summary[rule_type] = rules.get('description', 'No description available')
    return summary

def is_development_mode() -> bool:
    """Check if running in development mode"""
    return os.getenv('STREAMLIT_ENV', 'production').lower() == 'development'

def get_supabase_config() -> Dict[str, str]:
    """Get Supabase configuration from environment variables"""
    config = {}
    for key, env_var in SUPABASE_ENV_VARS.items():
        config[key] = os.getenv(env_var, '')
    return config

def validate_environment() -> List[str]:
    """Validate required environment variables"""
    missing_vars = []
    
    # Check for Supabase configuration in production
    if not is_development_mode():
        supabase_config = get_supabase_config()
        for key, value in supabase_config.items():
            if not value and key in ['url', 'key']:  # service_key optional
                missing_vars.append(f"Missing {SUPABASE_ENV_VARS[key]}")
    
    return missing_vars

# =============================================================================
# STREAMLIT CONFIGURATION HELPERS
# =============================================================================

def configure_streamlit_page():
    """Configure Streamlit page with consistent settings"""
    st.set_page_config(
        page_title=APP_CONFIG['title'],
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': None,
            'Report a bug': None,
            'About': f"{APP_CONFIG['title']} v{APP_CONFIG['version']}"
        }
    )

def apply_custom_css():
    """Apply custom CSS styling"""
    st.markdown("""
    <style>
    .metric-container {
        background-color: #f0f2f6;
        border: 1px solid #e1e5eb;
        border-radius: 4px;
        padding: 10px;
        margin: 5px 0;
    }
    
    .error-message {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 10px;
        margin: 5px 0;
    }
    
    .warning-message {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 10px;
        margin: 5px 0;
    }
    
    .info-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
        padding: 10px;
        margin: 5px 0;
    }
    
    .success-message {
        background-color: #e8f5e8;
        border-left: 4px solid #4caf50;
        padding: 10px;
        margin: 5px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# CONSTANTS FOR BACKWARD COMPATIBILITY
# =============================================================================

# Legacy constants that might be referenced in existing code
PATIENTS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['patients']['required']
TRIALS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['trials']['required']
ACTUAL_VISITS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['actual_visits']['required']

# Date format constants
UK_DATE_FORMATS = UI_CONFIG['date_formats']['input']
DISPLAY_DATE_FORMAT = UI_CONFIG['date_formats']['display']

# File size limit
MAX_FILE_SIZE_MB = APP_CONFIG['max_file_size_mb']
,
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
        'description': 'Visit identifier (e.g., Screening, Week 4)'
    },
    'date_range': {
        'min_year': 2020,
        'max_years_future': 5,
        'description': 'Reasonable date range for clinical trials'
    },
    'day_values': {
        'min_day': -30,  # Allow some pre-randomization visits
        'max_day': 3650,  # 10 years maximum
        'description': 'Visit day relative to start date'
    }
}

# =============================================================================
# DATABASE CONFIGURATION (SUPABASE PREPARATION)
# =============================================================================

DATABASE_CONFIG = {
    'connection_timeout': 30,
    'max_retries': 3,
    'batch_size': 1000,
    'tables': {
        'patients': 'clinical_patients',
        'trials': 'trial_schedules', 
        'visits': 'visit_calendar',
        'actual_visits': 'actual_visits'
    },
    'indexes': [
        'idx_patients_study',
        'idx_visits_patient_date',
        'idx_visits_status'
    ]
}

# Environment variable keys for Supabase
SUPABASE_ENV_VARS = {
    'url': 'SUPABASE_URL',
    'key': 'SUPABASE_ANON_KEY',
    'service_key': 'SUPABASE_SERVICE_KEY'
}

# =============================================================================
# UI CONFIGURATION
# =============================================================================

UI_CONFIG = {
    'sidebar_width': 300,
    'max_display_rows': 1000,
    'pagination_size': 50,
    'chart_height': 400,
    'colors': {
        'primary': '#1f77b4',
        'success': '#2ca02c', 
        'warning': '#ff7f0e',
        'error': '#d62728',
        'info': '#17becf'
    },
    'date_formats': {
        'display': '%d/%m/%Y',
        'input': ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'],
        'default_locale': 'en_GB'
    }
}

# =============================================================================
# ERROR HANDLING CONFIGURATION
# =============================================================================

ERROR_CONFIG = {
    'max_errors_display': 20,
    'auto_clear_after_minutes': 30,
    'log_level': 'INFO',
    'critical_error_types': [
        'FileProcessingError',
        'DataValidationError', 
        'DatabaseConnectionError'
    ],
    'retry_attempts': {
        'file_upload': 3,
        'database_operation': 3,
        'api_call': 5
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_structure_info() -> str:
    """Generate formatted file structure requirements"""
    info_sections = []
    
    for file_type, config in REQUIRED_COLUMNS.items():
        section = f"## {file_type.replace('_', ' ').title()} File\n"
        section += f"**Description:** {config['description']}\n\n"
        
        section += "**Required Columns:**\n"
        for col in config['required']:
            section += f"- `{col}`\n"
        
        if config['optional']:
            section += "\n**Optional Columns:**\n"
            for col in config['optional']:
                section += f"- `{col}`\n"
        
        section += "\n"
        info_sections.append(section)
    
    return "\n".join(info_sections)

def get_validation_summary() -> Dict[str, str]:
    """Get validation rules summary"""
    summary = {}
    for rule_type, rules in VALIDATION_RULES.items():
        summary[rule_type] = rules.get('description', 'No description available')
    return summary

def is_development_mode() -> bool:
    """Check if running in development mode"""
    return os.getenv('STREAMLIT_ENV', 'production').lower() == 'development'

def get_supabase_config() -> Dict[str, str]:
    """Get Supabase configuration from environment variables"""
    config = {}
    for key, env_var in SUPABASE_ENV_VARS.items():
        config[key] = os.getenv(env_var, '')
    return config

def validate_environment() -> List[str]:
    """Validate required environment variables"""
    missing_vars = []
    
    # Check for Supabase configuration in production
    if not is_development_mode():
        supabase_config = get_supabase_config()
        for key, value in supabase_config.items():
            if not value and key in ['url', 'key']:  # service_key optional
                missing_vars.append(f"Missing {SUPABASE_ENV_VARS[key]}")
    
    return missing_vars

# =============================================================================
# CONSTANTS FOR BACKWARD COMPATIBILITY
# =============================================================================

# Legacy constants that might be referenced in existing code
PATIENTS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['patients']['required']
TRIALS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['trials']['required']
ACTUAL_VISITS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['actual_visits']['required']

# Date format constants
UK_DATE_FORMATS = UI_CONFIG['date_formats']['input']
DISPLAY_DATE_FORMAT = UI_CONFIG['date_formats']['display']

# File size limit
MAX_FILE_SIZE_MB = APP_CONFIG['max_file_size_mb']

# =============================================================================
# DATABASE CONFIGURATION (SUPABASE PREPARATION)
# =============================================================================

DATABASE_CONFIG = {
    'connection_timeout': 30,
    'max_retries': 3,
    'batch_size': 1000,
    'tables': {
        'patients': 'clinical_patients',
        'trials': 'trial_schedules', 
        'visits': 'visit_calendar',
        'actual_visits': 'actual_visits'
    },
    'indexes': [
        'idx_patients_study',
        'idx_visits_patient_date',
        'idx_visits_status'
    ]
}

# Environment variable keys for Supabase
SUPABASE_ENV_VARS = {
    'url': 'SUPABASE_URL',
    'key': 'SUPABASE_ANON_KEY',
    'service_key': 'SUPABASE_SERVICE_KEY'
}

# =============================================================================
# VALIDATION RULES
# =============================================================================

VALIDATION_RULES = {
    'patient_id': {
        'max_length': 50,
        'allow_empty': False,
        'pattern': r'^[A-Za-z0-9\-_]+$',
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
        'description': 'Visit identifier (e.g., Screening, Week 4)'
    },
    'date_range': {
        'min_year': 2020,
        'max_years_future': 5,
        'description': 'Reasonable date range for clinical trials'
    },
    'day_values': {
        'min_day': -30,  # Allow some pre-randomization visits
        'max_day': 3650,  # 10 years maximum
        'description': 'Visit day relative to start date'
    }
}

# =============================================================================
# UI CONFIGURATION
# =============================================================================

UI_CONFIG = {
    'sidebar_width': 300,
    'max_display_rows': 1000,
    'pagination_size': 50,
    'chart_height': 400,
    'colors': {
        'primary': '#1f77b4',
        'success': '#2ca02c', 
        'warning': '#ff7f0e',
        'error': '#d62728',
        'info': '#17becf'
    },
    'date_formats': {
        'display': '%d/%m/%Y',
        'input': ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'],
        'default_locale': 'en_GB'
    }
}

# =============================================================================
# ERROR HANDLING CONFIGURATION
# =============================================================================

ERROR_CONFIG = {
    'max_errors_display': 20,
    'auto_clear_after_minutes': 30,
    'log_level': 'INFO',
    'critical_error_types': [
        'FileProcessingError',
        'DataValidationError', 
        'DatabaseConnectionError'
    ],
    'retry_attempts': {
        'file_upload': 3,
        'database_operation': 3,
        'api_call': 5
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_structure_info() -> str:
    """Generate formatted file structure requirements"""
    info_sections = []
    
    for file_type, config in REQUIRED_COLUMNS.items():
        section = f"## {file_type.replace('_', ' ').title()} File\n"
        section += f"**Description:** {config['description']}\n\n"
        
        section += "**Required Columns:**\n"
        for col in config['required']:
            section += f"- `{col}`\n"
        
        if config['optional']:
            section += "\n**Optional Columns:**\n"
            for col in config['optional']:
                section += f"- `{col}`\n"
        
        section += "\n"
        info_sections.append(section)
    
    return "\n".join(info_sections)

def get_validation_summary() -> Dict[str, str]:
    """Get validation rules summary"""
    summary = {}
    for rule_type, rules in VALIDATION_RULES.items():
        summary[rule_type] = rules.get('description', 'No description available')
    return summary

def is_development_mode() -> bool:
    """Check if running in development mode"""
    return os.getenv('STREAMLIT_ENV', 'production').lower() == 'development'

def get_supabase_config() -> Dict[str, str]:
    """Get Supabase configuration from environment variables"""
    config = {}
    for key, env_var in SUPABASE_ENV_VARS.items():
        config[key] = os.getenv(env_var, '')
    return config

def validate_environment() -> List[str]:
    """Validate required environment variables"""
    missing_vars = []
    
    # Check for Supabase configuration in production
    if not is_development_mode():
        supabase_config = get_supabase_config()
        for key, value in supabase_config.items():
            if not value and key in ['url', 'key']:  # service_key optional
                missing_vars.append(f"Missing {SUPABASE_ENV_VARS[key]}")
    
    return missing_vars

# =============================================================================
# STREAMLIT CONFIGURATION HELPERS
# =============================================================================

def configure_streamlit_page():
    """Configure Streamlit page with consistent settings"""
    st.set_page_config(
        page_title=APP_CONFIG['title'],
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': None,
            'Report a bug': None,
            'About': f"{APP_CONFIG['title']} v{APP_CONFIG['version']}"
        }
    )

def apply_custom_css():
    """Apply custom CSS styling"""
    st.markdown("""
    <style>
    .metric-container {
        background-color: #f0f2f6;
        border: 1px solid #e1e5eb;
        border-radius: 4px;
        padding: 10px;
        margin: 5px 0;
    }
    
    .error-message {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 10px;
        margin: 5px 0;
    }
    
    .warning-message {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 10px;
        margin: 5px 0;
    }
    
    .info-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
        padding: 10px;
        margin: 5px 0;
    }
    
    .success-message {
        background-color: #e8f5e8;
        border-left: 4px solid #4caf50;
        padding: 10px;
        margin: 5px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# CONSTANTS FOR BACKWARD COMPATIBILITY
# =============================================================================

# Legacy constants that might be referenced in existing code
PATIENTS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['patients']['required']
TRIALS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['trials']['required']
ACTUAL_VISITS_REQUIRED_COLUMNS = REQUIRED_COLUMNS['actual_visits']['required']

# Date format constants
UK_DATE_FORMATS = UI_CONFIG['date_formats']['input']
DISPLAY_DATE_FORMAT = UI_CONFIG['date_formats']['display']

# File size limit
MAX_FILE_SIZE_MB = APP_CONFIG['max_file_size_mb']
