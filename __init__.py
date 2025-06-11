"""
Razorpay Support Analytics Dashboard Modules

This package contains the core modules for the analytics dashboard:
- google_sheets: Google Sheets integration and data loading
- jira_integration: Jira API integration for ticket analysis
- ai_analyzer: AI-powered root cause analysis using Google Gemini
- data_visualizer: Interactive data visualizations with Plotly
"""

__version__ = "1.0.0"
__author__ = "Razorpay Support Analytics Team"

# Module imports for easy access
from .google_sheets import GoogleSheetsConnector
from .jira_integration import JiraIntegration
from .ai_analyzer import AIAnalyzer
from .data_visualizer import DataVisualizer

__all__ = [
    'GoogleSheetsConnector',
    'JiraIntegration', 
    'AIAnalyzer',
    'DataVisualizer'
]
