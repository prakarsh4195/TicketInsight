# Deployment Guide

## Replit Deployment (Recommended)

### 1. Repository Setup
1. Fork this repository to your Replit account
2. Open the Repl in your workspace
3. The application will automatically detect dependencies

### 2. Environment Configuration
In Replit Secrets, add the following variables:

```
GOOGLE_API_KEY=your_gemini_api_key
JIRA_EMAIL=your_jira_email
JIRA_API_TOKEN=your_jira_api_token
JIRA_SERVER_URL=https://your-instance.atlassian.net
DEVREV_ACCESS_TOKEN=your_devrev_token
GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
DEFAULT_GOOGLE_SHEETS_URL=https://docs.google.com/spreadsheets/d/your-sheet-id
```

### 3. Run Configuration
The application is configured to run automatically with:
```bash
streamlit run app.py --server.port 5000
```

### 4. Access
Once deployed, access your dashboard at the provided Replit URL.

## Local Development

### 1. Environment Setup
```bash
git clone <repository-url>
cd loyaltypro-analytics-dashboard
pip install streamlit pandas plotly numpy requests google-generativeai google-auth gspread jira tabulate trafilatura
```

### 2. Environment Variables
Create a `.env` file:
```bash
GOOGLE_API_KEY=your_api_key
JIRA_EMAIL=your_email
JIRA_API_TOKEN=your_token
JIRA_SERVER_URL=your_jira_url
```

### 3. Run Application
```bash
streamlit run app.py --server.port 5000
```

## Production Deployment

### Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install streamlit pandas plotly numpy requests google-generativeai google-auth gspread jira tabulate trafilatura

EXPOSE 5000

CMD ["streamlit", "run", "app.py", "--server.port=5000", "--server.address=0.0.0.0"]
```

### Cloud Deployment
- **Heroku**: Use the included Procfile
- **AWS**: Deploy via EC2 or ECS
- **Google Cloud**: Use Cloud Run or App Engine
- **Azure**: Deploy via Container Instances

## Configuration Notes

### Port Configuration
The application is configured to run on port 5000 for compatibility with various hosting platforms.

### Security
- All sensitive data should be stored in environment variables
- Never commit API keys or credentials to the repository
- Use HTTPS in production environments

### Performance
- The application includes caching for improved performance
- Consider increasing memory allocation for large datasets
- Monitor API rate limits for external services

## Troubleshooting

### Common Issues
1. **Port conflicts**: Ensure port 5000 is available
2. **Missing dependencies**: Check all required packages are installed
3. **API authentication**: Verify all environment variables are set correctly
4. **Memory issues**: Increase available memory for large CSV files