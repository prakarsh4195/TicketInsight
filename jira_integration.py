import os
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

class JiraIntegration:
    """
    Jira integration module for accessing ticket data via REST API.
    Handles authentication, ticket retrieval, and data processing.
    """
    
    def __init__(self):
        """Initialize Jira integration with authentication."""
        self.server_url = os.getenv('JIRA_SERVER_URL', 'https://razorpay.atlassian.net')
        self.email = os.getenv('JIRA_EMAIL')
        self.api_token = os.getenv('JIRA_API_TOKEN')
        
        if not all([self.email, self.api_token]):
            st.warning("Jira credentials not fully configured")
            return
        
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self) -> bool:
        """Test connection to Jira API."""
        try:
            url = f"{self.server_url}/rest/api/3/myself"
            response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                st.warning(f"Jira connection test failed: {response.status_code}")
                return False
                
        except Exception as e:
            st.warning(f"Jira connection error: {str(e)}")
            return False
    
    def get_ticket_details(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed information for a specific Jira ticket.
        
        Args:
            ticket_id: Jira ticket ID (e.g., 'PROJ-123')
            
        Returns:
            Dictionary with ticket details or None if error
        """
        try:
            url = f"{self.server_url}/rest/api/3/issue/{ticket_id}"
            
            # Expand fields for comprehensive data
            params = {
                'expand': 'changelog,comments,worklog,attachments,transitions'
            }
            
            response = requests.get(
                url, 
                auth=self.auth, 
                headers=self.headers, 
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                ticket_data = response.json()
                return self._process_ticket_data(ticket_data)
            
            elif response.status_code == 404:
                st.warning(f"Ticket {ticket_id} not found")
                return None
            
            else:
                st.error(f"Error fetching ticket {ticket_id}: {response.status_code}")
                return None
                
        except Exception as e:
            st.error(f"Error retrieving ticket {ticket_id}: {str(e)}")
            return None
    
    def _process_ticket_data(self, ticket_data: Dict) -> Dict[str, Any]:
        """
        Process raw Jira ticket data into structured format.
        
        Args:
            ticket_data: Raw ticket data from Jira API
            
        Returns:
            Processed ticket information
        """
        try:
            fields = ticket_data.get('fields', {})
            
            # Extract basic information
            processed = {
                'ticket_id': ticket_data.get('key'),
                'summary': fields.get('summary', ''),
                'description': fields.get('description', ''),
                'status': fields.get('status', {}).get('name', 'Unknown'),
                'priority': fields.get('priority', {}).get('name', 'Unknown'),
                'issue_type': fields.get('issuetype', {}).get('name', 'Unknown'),
                'created': fields.get('created'),
                'updated': fields.get('updated'),
                'resolved': fields.get('resolutiondate'),
                'assignee': None,
                'reporter': None,
                'project': fields.get('project', {}).get('key', 'Unknown'),
                'resolution': fields.get('resolution', {}).get('name') if fields.get('resolution') else None,
                'labels': fields.get('labels', []),
                'components': [comp.get('name') for comp in fields.get('components', [])],
                'comments_count': 0,
                'worklog_hours': 0,
                'attachments_count': 0,
                'status_history': []
            }
            
            # Extract assignee information
            if fields.get('assignee'):
                processed['assignee'] = fields['assignee'].get('displayName', 'Unknown')
            
            # Extract reporter information
            if fields.get('reporter'):
                processed['reporter'] = fields['reporter'].get('displayName', 'Unknown')
            
            # Process comments
            comments = ticket_data.get('fields', {}).get('comment', {}).get('comments', [])
            processed['comments_count'] = len(comments)
            processed['comments'] = [
                {
                    'author': comment.get('author', {}).get('displayName', 'Unknown'),
                    'body': comment.get('body', ''),
                    'created': comment.get('created')
                }
                for comment in comments
            ]
            
            # Process worklog
            worklog = ticket_data.get('fields', {}).get('worklog', {}).get('worklogs', [])
            total_seconds = sum(log.get('timeSpentSeconds', 0) for log in worklog)
            processed['worklog_hours'] = total_seconds / 3600 if total_seconds > 0 else 0
            
            # Process attachments
            attachments = fields.get('attachment', [])
            processed['attachments_count'] = len(attachments)
            
            # Process status history from changelog
            changelog = ticket_data.get('changelog', {}).get('histories', [])
            status_changes = []
            
            for history in changelog:
                for item in history.get('items', []):
                    if item.get('field') == 'status':
                        status_changes.append({
                            'from_status': item.get('fromString'),
                            'to_status': item.get('toString'),
                            'changed_date': history.get('created'),
                            'author': history.get('author', {}).get('displayName', 'System')
                        })
            
            processed['status_history'] = status_changes
            
            # Calculate resolution time
            if processed['created'] and processed['resolved']:
                try:
                    created_dt = pd.to_datetime(processed['created'])
                    resolved_dt = pd.to_datetime(processed['resolved'])
                    resolution_time = (resolved_dt - created_dt).total_seconds() / 3600  # hours
                    processed['resolution_time_hours'] = resolution_time
                except:
                    processed['resolution_time_hours'] = None
            else:
                processed['resolution_time_hours'] = None
            
            return processed
            
        except Exception as e:
            st.error(f"Error processing ticket data: {str(e)}")
            return {}
    
    def get_tickets_by_date_range(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        project_key: Optional[str] = None,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve tickets within a specific date range.
        
        Args:
            start_date: Start date for search
            end_date: End date for search
            project_key: Optional project key filter
            max_results: Maximum number of results to return
            
        Returns:
            List of ticket dictionaries
        """
        try:
            # Format dates for JQL
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # Build JQL query
            jql_parts = [f"created >= '{start_str}' AND created <= '{end_str}'"]
            
            if project_key:
                jql_parts.append(f"project = '{project_key}'")
            
            jql = " AND ".join(jql_parts)
            
            url = f"{self.server_url}/rest/api/3/search"
            
            payload = {
                'jql': jql,
                'maxResults': max_results,
                'expand': ['changelog'],
                'fields': [
                    'summary', 'status', 'priority', 'issuetype', 'created', 
                    'updated', 'resolutiondate', 'assignee', 'reporter', 
                    'project', 'resolution', 'labels', 'components'
                ]
            }
            
            response = requests.post(
                url,
                auth=self.auth,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                tickets = []
                
                for issue in data.get('issues', []):
                    processed_ticket = self._process_ticket_data(issue)
                    tickets.append(processed_ticket)
                
                return tickets
            
            else:
                st.error(f"Error searching tickets: {response.status_code}")
                return []
                
        except Exception as e:
            st.error(f"Error retrieving tickets by date range: {str(e)}")
            return []
    
    def calculate_average_resolution_time(self, tickets_df: pd.DataFrame) -> float:
        """
        Calculate average resolution time for resolved tickets.
        
        Args:
            tickets_df: DataFrame with ticket data
            
        Returns:
            Average resolution time in days
        """
        try:
            if 'resolution_time_hours' not in tickets_df.columns:
                return 0.0
            
            # Filter resolved tickets with resolution time
            resolved_tickets = tickets_df[
                (tickets_df['resolution_time_hours'].notna()) &
                (tickets_df['resolution_time_hours'] > 0)
            ]
            
            if resolved_tickets.empty:
                return 0.0
            
            # Convert hours to days and calculate average
            avg_hours = resolved_tickets['resolution_time_hours'].mean()
            avg_days = avg_hours / 24
            
            return avg_days
            
        except Exception as e:
            st.error(f"Error calculating average resolution time: {str(e)}")
            return 0.0
    
    def get_ticket_journey(self, ticket_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete journey of a ticket through different statuses.
        
        Args:
            ticket_id: Jira ticket ID
            
        Returns:
            List of status changes with timestamps
        """
        try:
            ticket_data = self.get_ticket_details(ticket_id)
            
            if not ticket_data or 'status_history' not in ticket_data:
                return []
            
            journey = ticket_data['status_history']
            
            # Add current status if not in history
            if journey and ticket_data.get('status'):
                last_status = journey[-1].get('to_status')
                if last_status != ticket_data['status']:
                    journey.append({
                        'from_status': last_status,
                        'to_status': ticket_data['status'],
                        'changed_date': ticket_data.get('updated'),
                        'author': 'System'
                    })
            
            return journey
            
        except Exception as e:
            st.error(f"Error getting ticket journey for {ticket_id}: {str(e)}")
            return []
    
    def analyze_ticket_patterns(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze patterns across multiple tickets.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            Analysis results with patterns and statistics
        """
        try:
            if not tickets:
                return {}
            
            df = pd.DataFrame(tickets)
            
            analysis = {
                'total_tickets': len(df),
                'status_distribution': df['status'].value_counts().to_dict(),
                'priority_distribution': df['priority'].value_counts().to_dict(),
                'issue_type_distribution': df['issue_type'].value_counts().to_dict(),
                'average_resolution_hours': 0,
                'tickets_with_comments': 0,
                'most_active_assignee': None,
                'common_components': [],
                'resolution_rate': 0
            }
            
            # Calculate resolution metrics
            resolved_tickets = df[df['resolution_time_hours'].notna()]
            if not resolved_tickets.empty:
                analysis['average_resolution_hours'] = resolved_tickets['resolution_time_hours'].mean()
                analysis['resolution_rate'] = len(resolved_tickets) / len(df) * 100
            
            # Comment analysis
            analysis['tickets_with_comments'] = len(df[df['comments_count'] > 0])
            
            # Assignee analysis
            assignee_counts = df['assignee'].value_counts()
            if not assignee_counts.empty:
                analysis['most_active_assignee'] = assignee_counts.index[0]
            
            # Component analysis
            all_components = []
            for components in df['components']:
                if isinstance(components, list):
                    all_components.extend(components)
            
            if all_components:
                component_counts = pd.Series(all_components).value_counts()
                analysis['common_components'] = component_counts.head(5).to_dict()
            
            return analysis
            
        except Exception as e:
            st.error(f"Error analyzing ticket patterns: {str(e)}")
            return {}
