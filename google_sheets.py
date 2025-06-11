import os
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import streamlit as st
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

class GoogleSheetsConnector:
    """
    Google Sheets connector for loading and processing support ticket data.
    Handles authentication, data loading, client filtering, and Jira ticket extraction.
    """
    
    # Restricted client list for filtering
    ALLOWED_CLIENTS = [
        "AU Bank",
        "Axis", 
        "DBS Bank",
        "Extraordinary Weekends",
        "Fi Money",
        "HDFC Bank", 
        "IDFC FIRST Bank",
        "Jana Bank",
        "Kotak Mahindra Bank",
        "SBI Aurum"
    ]
    
    def __init__(self):
        """Initialize the Google Sheets connector with authentication."""
        self.client = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API using available credentials."""
        try:
            # Try service account first
            creds_json = os.getenv('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')
            
            if creds_json:
                # Parse JSON credentials
                creds_info = json.loads(creds_json)
                
                # Store service account email for user reference
                self.service_account_email = creds_info.get('client_email', 'Unknown')
                
                # Load credentials with proper scopes
                scopes = [
                    'https://www.googleapis.com/auth/spreadsheets.readonly',
                    'https://www.googleapis.com/auth/drive.readonly'
                ]
                credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
                
                # Initialize gspread client
                self.client = gspread.authorize(credentials)
                return
            
            # Alternative: Try with API key (limited functionality)
            api_key = os.getenv('GOOGLE_SHEETS_API_KEY')
            if api_key:
                st.warning("Using API key authentication - this may have limited access to private sheets")
                # Note: gspread doesn't directly support API key auth, would need different approach
                raise ValueError("API key authentication not implemented yet")
            
            raise ValueError("No Google Sheets authentication credentials found")
            
        except Exception as e:
            st.error(f"Failed to authenticate with Google Sheets: {str(e)}")
            raise
    
    def _extract_sheet_id(self, url: str) -> str:
        """Extract sheet ID from Google Sheets URL."""
        patterns = [
            r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'key=([a-zA-Z0-9-_]+)',
            r'#gid=([0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # If no pattern matches, assume the URL is already a sheet ID
        if len(url) > 20 and '/' not in url:
            return url
        
        raise ValueError("Could not extract sheet ID from URL")
    
    def load_data(self, sheets_url: str, worksheet_name: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Load data from Google Sheets URL.
        
        Args:
            sheets_url: Google Sheets URL or ID
            worksheet_name: Specific worksheet name (optional, defaults to first sheet)
            
        Returns:
            DataFrame with loaded data or None if error
        """
        try:
            if not self.client:
                raise ValueError("Google Sheets client not authenticated")
            
            # Extract sheet ID
            sheet_id = self._extract_sheet_id(sheets_url)
            st.info(f"Attempting to access sheet ID: {sheet_id}")
            
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(sheet_id)
            
            # Get worksheet
            if worksheet_name:
                worksheet = spreadsheet.worksheet(worksheet_name)
            else:
                worksheet = spreadsheet.get_worksheet(0)  # First worksheet
            
            # Get all records
            records = worksheet.get_all_records()
            
            if not records:
                st.warning("No data found in the spreadsheet")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(records)
            
            # Clean and process data
            df = self._clean_data(df)
            
            return df
            
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                st.error("❌ Permission denied accessing the Google Sheets document.")
                st.warning(f"🔑 Please share your Google Sheets document with this service account email:")
                st.code(getattr(self, 'service_account_email', 'Service account email not available'))
                st.info("Steps: Open your Google Sheets → Click 'Share' → Add the email above → Give 'Viewer' permission → Click 'Send'")
            else:
                st.error(f"Error loading Google Sheets data: {error_msg}")
            return None
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and process the loaded data with LoyaltyPro filtering."""
        try:
            # Remove completely empty rows
            df = df.dropna(how='all')
            
            # Apply LoyaltyPro product filter (case-insensitive)
            if 'Product name' in df.columns:
                df = df[df['Product name'].str.lower() == 'loyaltypro']
                st.info(f"Filtered to LoyaltyPro tickets: {len(df)} records")
            
            # Apply escalation filter - only rows with Jira ticket numbers
            jira_columns = ['Jira ticket number if escalated to PSE', 'Jira Ticket', 'jira_ticket']
            for col in jira_columns:
                if col in df.columns:
                    df = df[df[col].notna() & (df[col] != '') & (df[col] != 'nan')]
                    st.info(f"Filtered to escalated tickets: {len(df)} records")
                    break
            
            # Convert date columns if they exist
            date_columns = ['Date', 'Created Date', 'Resolved Date', 'date', 'created_date']
            for col in date_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                    except:
                        pass
            
            # Clean string columns
            string_columns = df.select_dtypes(include=['object']).columns
            for col in string_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    # Replace empty strings with NaN
                    df[col] = df[col].replace('', None)
            
            return df
            
        except Exception as e:
            st.warning(f"Error cleaning data: {str(e)}")
            return df
    
    def get_available_clients(self, df: pd.DataFrame) -> List[str]:
        """
        Get list of available clients from the data, filtered by allowed clients.
        
        Args:
            df: DataFrame with client data
            
        Returns:
            List of available client names
        """
        try:
            # Try to find client column - expanded list for LoyaltyPro data
            client_columns = ['Client', 'client', 'Client Name', 'client_name', 'Customer', 'customer', 
                            'Account name', 'Account Name', 'account_name', 'Company', 'Organization']
            client_col = None
            
            for col in client_columns:
                if col in df.columns:
                    client_col = col
                    break
            
            if not client_col:
                st.warning(f"No client column found in data. Available columns: {list(df.columns)}")
                return []
            
            # Get unique clients
            unique_clients = df[client_col].dropna().unique().tolist()
            
            # Filter by allowed clients
            available_clients = [
                client for client in unique_clients 
                if client in self.ALLOWED_CLIENTS
            ]
            
            return sorted(available_clients)
            
        except Exception as e:
            st.error(f"Error extracting clients: {str(e)}")
            return []
    
    def filter_by_clients(self, df: pd.DataFrame, selected_clients: List[str]) -> pd.DataFrame:
        """
        Filter DataFrame by selected clients.
        
        Args:
            df: Source DataFrame
            selected_clients: List of client names to filter by
            
        Returns:
            Filtered DataFrame
        """
        try:
            # Find client column
            client_columns = ['Client', 'client', 'Client Name', 'client_name', 'Customer', 'customer']
            client_col = None
            
            for col in client_columns:
                if col in df.columns:
                    client_col = col
                    break
            
            if not client_col:
                return df
            
            # Filter by selected clients
            filtered_df = df[df[client_col].isin(selected_clients)].copy()
            
            return filtered_df
            
        except Exception as e:
            st.error(f"Error filtering by clients: {str(e)}")
            return df
    
    def filter_by_date_range(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Filter DataFrame by date range.
        
        Args:
            df: Source DataFrame
            start_date: Start date for filtering
            end_date: End date for filtering
            
        Returns:
            Filtered DataFrame
        """
        try:
            # Find date column
            date_columns = ['Date', 'Created Date', 'Resolved Date', 'date', 'created_date']
            date_col = None
            
            for col in date_columns:
                if col in df.columns:
                    date_col = col
                    break
            
            if not date_col:
                return df
            
            # Ensure date column is datetime
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            
            # Filter by date range
            start_date = pd.to_datetime(start_date)
            end_date = pd.to_datetime(end_date)
            
            filtered_df = df[
                (df[date_col] >= start_date) & 
                (df[date_col] <= end_date)
            ].copy()
            
            return filtered_df
            
        except Exception as e:
            st.error(f"Error filtering by date range: {str(e)}")
            return df
    
    def extract_jira_tickets(self, df: pd.DataFrame) -> List[str]:
        """
        Extract Jira ticket IDs from the 'Jira ticket number if escalated to PSE' column.
        
        Args:
            df: DataFrame containing Jira ticket information
            
        Returns:
            List of unique Jira ticket IDs
        """
        try:
            # Possible column names for Jira tickets
            jira_columns = [
                'Jira ticket number if escalated to PSE',
                'Jira Ticket',
                'jira_ticket',
                'Jira ID',
                'jira_id',
                'Ticket ID',
                'ticket_id'
            ]
            
            jira_col = None
            for col in jira_columns:
                if col in df.columns:
                    jira_col = col
                    break
            
            if not jira_col:
                st.warning("No Jira ticket column found in data")
                return []
            
            # Extract ticket IDs
            ticket_ids = []
            
            for value in df[jira_col].dropna():
                if pd.isna(value) or str(value).strip() == '':
                    continue
                
                # Convert to string and extract ticket patterns
                ticket_str = str(value).strip()
                
                # Common Jira ticket patterns
                patterns = [
                    r'[A-Z]+-\d+',  # Standard Jira format (e.g., PROJ-123)
                    r'[A-Z]{2,10}-\d{1,6}',  # More specific Jira format
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, ticket_str, re.IGNORECASE)
                    ticket_ids.extend(matches)
                
                # If no pattern matches but looks like a ticket ID
                if not any(re.search(pattern, ticket_str) for pattern in patterns):
                    if len(ticket_str) > 3 and '-' in ticket_str:
                        ticket_ids.append(ticket_str)
            
            # Remove duplicates and return
            unique_tickets = list(set(ticket_ids))
            
            return unique_tickets
            
        except Exception as e:
            st.error(f"Error extracting Jira tickets: {str(e)}")
            return []
    
    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate summary statistics for the loaded data.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dictionary with summary statistics
        """
        try:
            summary = {
                'total_records': len(df),
                'columns': list(df.columns),
                'date_range': None,
                'clients': self.get_available_clients(df),
                'jira_tickets': len(self.extract_jira_tickets(df))
            }
            
            # Get date range if date column exists
            date_columns = ['Date', 'Created Date', 'date', 'created_date']
            for col in date_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                        date_series = df[col].dropna()
                        if not date_series.empty:
                            summary['date_range'] = {
                                'start': date_series.min(),
                                'end': date_series.max()
                            }
                        break
                    except:
                        continue
            
            return summary
            
        except Exception as e:
            st.error(f"Error generating data summary: {str(e)}")
            return {}
