import os
import json
import streamlit as st
from typing import Dict, Any, Optional

class ConfigManager:
    """
    Configuration manager for handling Replit Vault integration and environment variables.
    Manages secure credential loading and validation for all external services.
    """
    
    def __init__(self):
        """Initialize configuration manager."""
        self.required_configs = {
            'Google Sheets': 'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON',
            'Jira': ['JIRA_SERVER_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN'],
            'AI Service': 'GOOGLE_API_KEY'
        }
        
        self.optional_configs = {
            'OpenAI': 'OPENAI_API_KEY',
            'Anthropic': 'ANTHROPIC_API_KEY'
        }
    
    def get_configuration_status(self) -> Dict[str, bool]:
        """
        Check configuration status for all services.
        
        Returns:
            Dictionary with service status (True if configured, False otherwise)
        """
        status = {}
        
        for service, config_keys in self.required_configs.items():
            if isinstance(config_keys, list):
                # Multiple keys required (e.g., Jira)
                status[service] = all(self._check_env_var(key) for key in config_keys)
            else:
                # Single key required
                status[service] = self._check_env_var(config_keys)
        
        return status
    
    def _check_env_var(self, key: str) -> bool:
        """
        Check if environment variable exists and is not empty.
        
        Args:
            key: Environment variable key
            
        Returns:
            True if variable exists and has value, False otherwise
        """
        try:
            value = os.getenv(key)
            return value is not None and value.strip() != ""
        except Exception:
            return False
    
    def get_google_sheets_config(self) -> Optional[Dict[str, Any]]:
        """
        Get Google Sheets configuration.
        
        Returns:
            Google Sheets service account configuration or None
        """
        try:
            creds_json = os.getenv('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')
            
            if not creds_json:
                return None
            
            # Parse and validate JSON
            creds_dict = json.loads(creds_json)
            
            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            if not all(field in creds_dict for field in required_fields):
                st.error("Invalid Google Sheets service account JSON format")
                return None
            
            return creds_dict
            
        except json.JSONDecodeError:
            st.error("Invalid JSON format in Google Sheets service account configuration")
            return None
        except Exception as e:
            st.error(f"Error loading Google Sheets configuration: {str(e)}")
            return None
    
    def get_jira_config(self) -> Optional[Dict[str, str]]:
        """
        Get Jira configuration.
        
        Returns:
            Jira configuration dictionary or None
        """
        try:
            config = {}
            
            # Required Jira configuration
            required_keys = ['JIRA_SERVER_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN']
            
            for key in required_keys:
                value = os.getenv(key)
                if not value:
                    return None
                config[key.lower().replace('jira_', '')] = value
            
            # Validate server URL format
            server_url = config['server_url']
            if not server_url.startswith(('http://', 'https://')):
                st.error("Invalid Jira server URL format")
                return None
            
            return config
            
        except Exception as e:
            st.error(f"Error loading Jira configuration: {str(e)}")
            return None
    
    def get_ai_config(self) -> Optional[Dict[str, str]]:
        """
        Get AI service configuration.
        
        Returns:
            AI configuration dictionary or None
        """
        try:
            config = {}
            
            # Primary AI service (Google Gemini)
            google_api_key = os.getenv('GOOGLE_API_KEY')
            if google_api_key:
                config['google_api_key'] = google_api_key
                config['primary_provider'] = 'google'
            
            # Fallback AI services
            openai_key = os.getenv('OPENAI_API_KEY')
            if openai_key:
                config['openai_api_key'] = openai_key
                if 'primary_provider' not in config:
                    config['primary_provider'] = 'openai'
            
            anthropic_key = os.getenv('ANTHROPIC_API_KEY')
            if anthropic_key:
                config['anthropic_api_key'] = anthropic_key
                if 'primary_provider' not in config:
                    config['primary_provider'] = 'anthropic'
            
            return config if config else None
            
        except Exception as e:
            st.error(f"Error loading AI configuration: {str(e)}")
            return None
    
    def validate_all_configurations(self) -> Dict[str, Any]:
        """
        Validate all configurations and return detailed status.
        
        Returns:
            Dictionary with detailed configuration validation results
        """
        validation_results = {
            'overall_status': True,
            'services': {},
            'warnings': [],
            'errors': []
        }
        
        try:
            # Check Google Sheets
            sheets_config = self.get_google_sheets_config()
            validation_results['services']['google_sheets'] = {
                'configured': sheets_config is not None,
                'details': 'Service account JSON loaded' if sheets_config else 'Missing service account JSON'
            }
            
            if not sheets_config:
                validation_results['overall_status'] = False
                validation_results['errors'].append('Google Sheets configuration missing')
            
            # Check Jira
            jira_config = self.get_jira_config()
            validation_results['services']['jira'] = {
                'configured': jira_config is not None,
                'details': 'Credentials loaded' if jira_config else 'Missing credentials'
            }
            
            if not jira_config:
                validation_results['warnings'].append('Jira configuration missing - ticket analysis will be limited')
            
            # Check AI services
            ai_config = self.get_ai_config()
            validation_results['services']['ai'] = {
                'configured': ai_config is not None,
                'details': f"Primary provider: {ai_config.get('primary_provider', 'none')}" if ai_config else 'No AI service configured'
            }
            
            if not ai_config:
                validation_results['warnings'].append('AI service configuration missing - root cause analysis will be unavailable')
            
            return validation_results
            
        except Exception as e:
            validation_results['overall_status'] = False
            validation_results['errors'].append(f"Configuration validation error: {str(e)}")
            return validation_results
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get environment information for debugging.
        
        Returns:
            Dictionary with environment information
        """
        try:
            env_info = {
                'platform': 'Replit',
                'python_version': os.sys.version,
                'environment_variables': {},
                'vault_status': 'Connected' if self._check_vault_connection() else 'Disconnected'
            }
            
            # Check which environment variables are set (without exposing values)
            all_config_keys = []
            
            for config_list in self.required_configs.values():
                if isinstance(config_list, list):
                    all_config_keys.extend(config_list)
                else:
                    all_config_keys.append(config_list)
            
            for key in list(self.optional_configs.values()) + all_config_keys:
                env_info['environment_variables'][key] = 'Set' if self._check_env_var(key) else 'Not Set'
            
            return env_info
            
        except Exception as e:
            return {'error': f"Could not gather environment info: {str(e)}"}
    
    def _check_vault_connection(self) -> bool:
        """
        Check if Replit Vault is accessible.
        
        Returns:
            True if vault is accessible, False otherwise
        """
        try:
            # Try to access any environment variable to test vault connection
            test_var = os.getenv('PATH')  # PATH should always exist
            return test_var is not None
        except Exception:
            return False
    
    def display_configuration_help(self):
        """Display configuration help in Streamlit sidebar."""
        with st.sidebar:
            st.markdown("### 📋 Configuration Guide")
            
            with st.expander("Required Environment Variables"):
                st.markdown("""
                **Google Sheets Integration:**
                - `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`: Complete service account JSON
                
                **Jira Integration:**
                - `JIRA_SERVER_URL`: https://razorpay.atlassian.net
                - `JIRA_EMAIL`: Your Jira email address
                - `JIRA_API_TOKEN`: Your Jira API token
                
                **AI Analysis:**
                - `GOOGLE_API_KEY`: Google Gemini API key
                """)
            
            with st.expander("Setup Instructions"):
                st.markdown("""
                1. Go to your Replit project's "Secrets" tab
                2. Add each environment variable with its value
                3. Ensure JSON is properly formatted for Google Sheets
                4. Restart the application after adding secrets
                """)
            
            # Display current status
            status = self.get_configuration_status()
            st.markdown("### 🔍 Current Status")
            for service, is_configured in status.items():
                icon = "✅" if is_configured else "❌"
                st.write(f"{icon} {service}")
    
    def export_configuration_template(self) -> str:
        """
        Export configuration template for setup guidance.
        
        Returns:
            Configuration template as string
        """
        template = """
# Razorpay Support Analytics Dashboard - Configuration Template

## Required Environment Variables (Replit Vault)

# Google Sheets Integration
GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "your-project", ...}

# Jira Integration  
JIRA_SERVER_URL=https://razorpay.atlassian.net
JIRA_EMAIL=your-email@razorpay.com
JIRA_API_TOKEN=your-jira-api-token

# AI Analysis (Google Gemini)
GOOGLE_API_KEY=your-google-gemini-api-key

## Optional Environment Variables

# Fallback AI Services
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key

## Setup Instructions

1. Obtain Google Sheets service account JSON from Google Cloud Console
2. Generate Jira API token from Atlassian account settings
3. Get Google Gemini API key from Google AI Studio
4. Add all variables to Replit Vault (Secrets tab)
5. Restart the application

## Client Filtering

The application restricts analysis to these clients only:
- AU Bank
- Axis
- DBS Bank
- Extraordinary Weekends
- Fi Money
- HDFC Bank
- IDFC FIRST Bank
- Jana Bank
- Kotak Mahindra Bank
- SBI Aurum
"""
        return template
