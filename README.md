# LoyaltyPro Analytics Dashboard

A comprehensive Streamlit-based data analytics dashboard for support operations intelligence, featuring automated cross-sectional ticket analysis, Google Sheets/CSV integration, Jira ticket analysis, and AI-powered root cause analysis.

## Features

- **Data Integration**: Support for both CSV uploads and Google Sheets integration
- **LoyaltyPro Filtering**: Automatic filtering for LoyaltyPro product tickets
- **Cross-Sectional Analysis**: Automatic analysis without requiring client selection
- **Jira Integration**: Deep analysis of escalated tickets via Jira API
- **AI-Powered Insights**: Root cause analysis using Google Gemini
- **Interactive Visualizations**: Dynamic charts and graphs using Plotly
- **Executive Dashboard**: High-level metrics and trends for management

## Quick Start

### Prerequisites

- Python 3.11+
- Required API credentials (stored in environment variables):
  - `GOOGLE_API_KEY`: Google Gemini API key
  - `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`: Google Sheets service account credentials
  - `JIRA_SERVER_URL`: Your Jira server URL
  - `JIRA_EMAIL`: Jira account email
  - `JIRA_API_TOKEN`: Jira API token

### Installation

1. Clone the repository:
```bash
git clone https://github.com/prakarsh4195/loyaltypro-analytics-dashboard.git
cd loyaltypro-analytics-dashboard
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export GOOGLE_API_KEY="your-google-api-key"
export GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON="your-service-account-json"
export JIRA_SERVER_URL="your-jira-url"
export JIRA_EMAIL="your-jira-email"
export JIRA_API_TOKEN="your-jira-token"
```

4. Run the application:
```bash
streamlit run app.py --server.port 5000
```

## Usage

1. **Data Upload**: Choose between CSV file upload or Google Sheets URL
2. **Automatic Analysis**: The dashboard automatically filters LoyaltyPro tickets and displays cross-sectional analysis
3. **Time Period Selection**: Filter data by date range and time grouping
4. **Jira Deep Analysis**: Analyze escalated tickets with AI-powered insights
5. **Executive Summary**: View high-level trends and patterns

## Project Structure

```
├── app.py                 # Main Streamlit application
├── modules/
│   ├── __init__.py
│   ├── google_sheets.py   # Google Sheets integration
│   ├── jira_integration.py # Jira API integration
│   ├── ai_analyzer.py     # AI-powered analysis
│   └── data_visualizer.py # Data visualization
├── utils/
│   └── config.py          # Configuration utilities
├── .streamlit/
│   └── config.toml        # Streamlit configuration
└── requirements.txt       # Python dependencies
```

## Configuration

### Streamlit Configuration

The application is configured to run on `0.0.0.0:5000` for deployment compatibility. Configuration is stored in `.streamlit/config.toml`.

### Data Filtering

The system automatically applies these filters:
- **Product Filter**: Only "loyaltypro" tickets (case-insensitive)
- **Escalation Filter**: Only tickets with Jira ticket numbers
- **Client Filter**: Optional filtering by allowed clients

## API Integrations

### Google Sheets
- Service account authentication
- Automatic data loading and cleaning
- Support for multiple worksheet formats

### Jira
- REST API integration
- Ticket detail retrieval
- Status history tracking

### Google Gemini AI
- Root cause analysis
- Pattern identification
- Executive summary generation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License.