"""
Database service for Supabase integration
Handles all database operations for the clinical trial calendar app
"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Any
from supabase import create_client, Client

class DatabaseService:
    def __init__(self):
        self.client: Optional[Client] = None
        self.connected = False
        self.organization_id = None
        self.user_id = None
        
    def connect(self, url: str, key: str, email: str = None) -> bool:
        """Connect to Supabase and authenticate user"""
        try:
            self.client = create_client(url, key)
            
            # For now, we'll use a simple approach - get the first organization
            # In a real app, you'd have proper authentication
            if email:
                # Try to get user by email
                users_response = self.client.table('users').select('*').eq('email', email).execute()
                if users_response.data:
                    user = users_response.data[0]
                    self.user_id = user['id']
                    self.organization_id = user['organization_id']
                else:
                    # Create a default user if none exists
                    orgs_response = self.client.table('organizations').select('*').limit(1).execute()
                    if orgs_response.data:
                        self.organization_id = orgs_response.data[0]['id']
                    else:
                        # Create default organization
                        org_response = self.client.table('organizations').insert({
                            'name': 'Default Organization'
                        }).execute()
                        self.organization_id = org_response.data[0]['id']
                    
                    # Create user
                    user_response = self.client.table('users').insert({
                        'email': email,
                        'organization_id': self.organization_id,
                        'role': 'admin'
                    }).execute()
                    self.user_id = user_response.data[0]['id']
            else:
                # Get first organization and user
                orgs_response = self.client.table('organizations').select('*').limit(1).execute()
                if orgs_response.data:
                    self.organization_id = orgs_response.data[0]['id']
                    users_response = self.client.table('users').select('*').eq('organization_id', self.organization_id).limit(1).execute()
                    if users_response.data:
                        self.user_id = users_response.data[0]['id']
            
            self.connected = True
            return True
            
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False
    
    def load_patients(self) -> pd.DataFrame:
        """Load patients from database"""
        if not self.connected:
            return pd.DataFrame()
        
        try:
            # Get patients with study information
            response = self.client.table('patients').select(
                'id, patient_id, start_date, patient_site, created_at, '
                'studies(id, name)'
            ).eq('organization_id', self.organization_id).execute()
            
            if not response.data:
                return pd.DataFrame()
            
            # Transform to match CSV structure
            data = []
            for patient in response.data:
                study = patient['studies']
                data.append({
                    'PatientID': patient['patient_id'],
                    'Study': study['name'] if study else 'Unknown',
                    'StartDate': patient['start_date'],
                    'PatientPractice': patient.get('patient_site', ''),
                    'id': patient['id']  # Keep for updates
                })
            
            return pd.DataFrame(data)
            
        except Exception as e:
            print(f"Error loading patients: {e}")
            return pd.DataFrame()
    
    def load_trials(self) -> pd.DataFrame:
        """Load trial visits from database"""
        if not self.connected:
            return pd.DataFrame()
        
        try:
            # Get trial visits with study information
            response = self.client.table('trial_visits').select(
                'id, visit_name, day_number, payment, tolerance_before, tolerance_after, site_for_visit, '
                'studies(id, name)'
            ).eq('studies.organization_id', self.organization_id).execute()
            
            if not response.data:
                return pd.DataFrame()
            
            # Transform to match CSV structure
            data = []
            for trial in response.data:
                study = trial['studies']
                data.append({
                    'Study': study['name'] if study else 'Unknown',
                    'Day': trial['day_number'],
                    'VisitName': trial['visit_name'],
                    'SiteforVisit': trial['site_for_visit'],
                    'Payment': trial.get('payment', 0),
                    'ToleranceBefore': trial.get('tolerance_before', 0),
                    'ToleranceAfter': trial.get('tolerance_after', 0),
                    'id': trial['id']  # Keep for updates
                })
            
            return pd.DataFrame(data)
            
        except Exception as e:
            print(f"Error loading trials: {e}")
            return pd.DataFrame()
    
    def load_actual_visits(self) -> pd.DataFrame:
        """Load actual visits from database"""
        if not self.connected:
            return pd.DataFrame()
        
        try:
            # Get actual visits with patient and study information
            response = self.client.table('actual_visits').select(
                'id, visit_name, actual_date, actual_payment, notes, created_at, '
                'patients(id, patient_id, studies(id, name))'
            ).eq('patients.organization_id', self.organization_id).execute()
            
            if not response.data:
                return pd.DataFrame()
            
            # Transform to match CSV structure
            data = []
            for visit in response.data:
                patient = visit['patients']
                study = patient['studies'] if patient else None
                data.append({
                    'PatientID': patient['patient_id'] if patient else 'Unknown',
                    'Study': study['name'] if study else 'Unknown',
                    'VisitName': visit['visit_name'],
                    'ActualDate': visit['actual_date'],
                    'Notes': visit.get('notes', ''),
                    'VisitType': 'patient',  # Default for now
                    'Status': 'completed',   # Default for now
                    'id': visit['id']  # Keep for updates
                })
            
            return pd.DataFrame(data)
            
        except Exception as e:
            print(f"Error loading actual visits: {e}")
            return pd.DataFrame()
    
    def add_patient(self, patient_data: Dict[str, Any]) -> bool:
        """Add a new patient to the database"""
        if not self.connected:
            return False
        
        try:
            # Get or create study
            study_id = self._get_or_create_study(patient_data['Study'])
            if not study_id:
                return False
            
            # Insert patient
            response = self.client.table('patients').insert({
                'organization_id': self.organization_id,
                'patient_id': patient_data['PatientID'],
                'study_id': study_id,
                'start_date': patient_data['StartDate'],
                'patient_site': patient_data.get('PatientPractice', '')
            }).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            print(f"Error adding patient: {e}")
            return False
    
    def add_visit(self, visit_data: Dict[str, Any]) -> bool:
        """Add a new actual visit to the database"""
        if not self.connected:
            return False
        
        try:
            # Find patient by patient_id and study
            patient_id = self._get_patient_id(visit_data['PatientID'], visit_data['Study'])
            if not patient_id:
                print(f"Patient not found: {visit_data['PatientID']} in study {visit_data['Study']}")
                return False
            
            # Insert visit
            response = self.client.table('actual_visits').insert({
                'patient_id': patient_id,
                'visit_name': visit_data['VisitName'],
                'actual_date': visit_data['ActualDate'],
                'actual_payment': visit_data.get('ActualPayment', 0),
                'notes': visit_data.get('Notes', '')
            }).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            print(f"Error adding visit: {e}")
            return False
    
    def add_study_event(self, event_data: Dict[str, Any]) -> bool:
        """Add a study event (SIV/Monitor) to the database"""
        if not self.connected:
            return False
        
        try:
            # Create a special patient ID for study events
            patient_id = f"{event_data['VisitType'].upper()}_{event_data['Study']}"
            study_id = self._get_or_create_study(event_data['Study'])
            
            if not study_id:
                return False
            
            # Create or get patient for study event
            event_patient_id = self._get_or_create_event_patient(patient_id, study_id, event_data.get('PatientPractice', ''))
            
            if not event_patient_id:
                return False
            
            # Insert visit
            response = self.client.table('actual_visits').insert({
                'patient_id': event_patient_id,
                'visit_name': event_data['VisitName'],
                'actual_date': event_data['ActualDate'],
                'notes': event_data.get('Notes', ''),
                'actual_payment': event_data.get('ActualPayment', 0)
            }).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            print(f"Error adding study event: {e}")
            return False
    
    def _get_or_create_study(self, study_name: str) -> Optional[str]:
        """Get existing study or create new one"""
        try:
            # Try to find existing study
            response = self.client.table('studies').select('id').eq('name', study_name).eq('organization_id', self.organization_id).execute()
            
            if response.data:
                return response.data[0]['id']
            
            # Create new study
            response = self.client.table('studies').insert({
                'organization_id': self.organization_id,
                'name': study_name
            }).execute()
            
            return response.data[0]['id'] if response.data else None
            
        except Exception as e:
            print(f"Error with study {study_name}: {e}")
            return None
    
    def _get_patient_id(self, patient_id: str, study_name: str) -> Optional[str]:
        """Get patient UUID by patient_id and study"""
        try:
            study_id = self._get_or_create_study(study_name)
            if not study_id:
                return None
            
            response = self.client.table('patients').select('id').eq('patient_id', patient_id).eq('study_id', study_id).eq('organization_id', self.organization_id).execute()
            
            return response.data[0]['id'] if response.data else None
            
        except Exception as e:
            print(f"Error finding patient: {e}")
            return None
    
    def _get_or_create_event_patient(self, patient_id: str, study_id: str, patient_site: str = '') -> Optional[str]:
        """Get or create patient for study events"""
        try:
            # Try to find existing event patient
            response = self.client.table('patients').select('id').eq('patient_id', patient_id).eq('study_id', study_id).eq('organization_id', self.organization_id).execute()
            
            if response.data:
                return response.data[0]['id']
            
            # Create new event patient
            response = self.client.table('patients').insert({
                'organization_id': self.organization_id,
                'patient_id': patient_id,
                'study_id': study_id,
                'start_date': datetime.now().date(),
                'patient_site': patient_site
            }).execute()
            
            return response.data[0]['id'] if response.data else None
            
        except Exception as e:
            print(f"Error with event patient: {e}")
            return None

# Global database service instance
db_service = DatabaseService()
