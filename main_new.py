import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import io
import zipfile
from datetime import datetime
import os
import requests
import json
import google.generativeai as genai

# Page configuration
st.set_page_config(
    page_title="LoyaltyPro Support Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# App title and description
st.title("LoyaltyPro Support Analytics Dashboard")
st.markdown("Advanced ticket analysis with Jira integration and AI-powered insights")

# Initialize session state for storing data
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'filtered_data' not in st.session_state:
    st.session_state['filtered_data'] = None
if 'columns' not in st.session_state:
    st.session_state['columns'] = []
if 'jira_tickets' not in st.session_state:
    st.session_state['jira_tickets'] = []
if 'ai_analysis' not in st.session_state:
    st.session_state['ai_analysis'] = {}

# Helper functions for data cleaning
def clean_data_types(df):
    """Convert data types appropriately and handle mixed types"""
    df_clean = df.copy()
    
    # First pass: Convert obvious numeric columns
    for col in df_clean.columns:
        # Skip columns that are clearly categorical
        if col in ['Account name', 'Product name', 'Issue Category', 'Issue Sub-category', 
                  'FD Ticket Status', 'Agent', 'Source']:
            continue
            
        # Try to convert to numeric, but preserve string values if they exist
        try:
            numeric_series = pd.to_numeric(df_clean[col], errors='coerce')
            
            # Only convert if we don't lose too many values (80% can be converted)
            if numeric_series.notna().mean() > 0.8:
                df_clean[col] = numeric_series
        except:
            pass
    
    # Convert date columns
    date_columns = ['Date created', 'Date Completed', 'Created', 'Resolved', 'Updated']
    for col in date_columns:
        if col in df_clean.columns:
            try:
                df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
            except:
                pass
    
    return df_clean

def filter_loyaltypro_data(df):
    """Filter data for LoyaltyPro product only (case-insensitive)"""
    if 'Product name' in df.columns:
        df = df[df['Product name'].str.lower() == 'loyaltypro']
        st.info(f"Filtered to LoyaltyPro tickets: {len(df)} records")
    return df

def extract_jira_ticket_ids(df):
    """Extract Jira ticket IDs from the dataset"""
    jira_columns = ['Jira ticket number if escalated to PSE', 'Jira Ticket', 'jira_ticket']
    ticket_ids = []
    
    for col in jira_columns:
        if col in df.columns:
            # Extract non-null, non-empty ticket IDs
            tickets = df[col].dropna()
            tickets = tickets[tickets.str.strip() != '']
            ticket_ids.extend(tickets.tolist())
    
    # Remove duplicates and return unique ticket IDs
    return list(set(ticket_ids))

# Jira Integration Functions
def get_jira_ticket_data(ticket_id):
    """Fetch Jira ticket data using API"""
    try:
        jira_url = os.getenv('JIRA_SERVER_URL', 'https://razorpay.atlassian.net')
        jira_email = os.getenv('JIRA_EMAIL')
        jira_token = os.getenv('JIRA_API_TOKEN')
        
        if not all([jira_email, jira_token]):
            return None
            
        auth = (jira_email, jira_token)
        headers = {'Accept': 'application/json'}
        
        url = f"{jira_url}/rest/api/3/issue/{ticket_id}"
        response = requests.get(url, headers=headers, auth=auth)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
            
    except Exception as e:
        st.error(f"Error fetching Jira ticket {ticket_id}: {str(e)}")
        return None

def analyze_ticket_with_gemini(ticket_data):
    """Analyze Jira ticket using Gemini AI"""
    try:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return None
            
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prepare ticket context
        ticket_context = f"""
        Ticket ID: {ticket_data.get('key', 'N/A')}
        Summary: {ticket_data.get('fields', {}).get('summary', 'N/A')}
        Description: {ticket_data.get('fields', {}).get('description', 'N/A')}
        Priority: {ticket_data.get('fields', {}).get('priority', {}).get('name', 'N/A') if ticket_data.get('fields', {}).get('priority') else 'N/A'}
        Status: {ticket_data.get('fields', {}).get('status', {}).get('name', 'N/A') if ticket_data.get('fields', {}).get('status') else 'N/A'}
        Created: {ticket_data.get('fields', {}).get('created', 'N/A')}
        Resolution: {ticket_data.get('fields', {}).get('resolution', {}).get('name', 'N/A') if ticket_data.get('fields', {}).get('resolution') else 'N/A'}
        """
        
        # Analysis prompt from your specification
        prompt = f"""
        You are an expert support operations analyst with deep expertise in technical troubleshooting, pattern recognition, and business impact assessment. I'm providing you with detailed data from a Jira support ticket. Analyze this data thoroughly and provide cutting-edge insights that would be impossible for a human analyst to derive manually.

        [TICKET CONTENT]
        {ticket_context}
        [/TICKET CONTENT]

        Please provide a comprehensive analysis with the following sections:

        1. **Executive Summary (3-4 sentences)**
           - Distill the core issue, business impact, and resolution approach

        2. **Root Cause Analysis**
           - Identify the fundamental technical cause (not just symptoms)
           - Classify whether it's a code bug, configuration issue, third-party integration problem, or user error
           - Provide confidence level for your analysis (e.g., 85% confident)

        3. **Resolution Pathway Assessment**
           - Evaluate the efficiency of the resolution approach
           - Identify any unnecessary steps or delays
           - Suggest optimal resolution path that could have saved time

        4. **Pattern Recognition**
           - Identify similarities to other common issues
           - Flag if this appears to be a recurring issue that needs systemic fixes
           - Connect to potential product or infrastructure weaknesses

        5. **Technical Complexity Scoring**
           - Rate the issue on a scale of 1-10 for technical complexity
           - Break down complexity factors (e.g., 3/10 for debugging difficulty, 7/10 for domain knowledge required)
           - Estimate appropriate expertise level needed to resolve (junior/mid/senior)

        6. **Business Impact Assessment**
           - Quantify potential revenue impact if possible
           - Identify affected user journeys or customer experiences
           - Assess reputational risk

        7. **Preventative Recommendations**
           - Suggest 2-3 concrete actions to prevent similar issues
           - Recommend monitoring or alerting that could catch this earlier
           - Propose documentation or training that would help prevent recurrence

        Format your analysis with clear section headers and concise bullet points. Where appropriate, use rating scales or confidence percentages to quantify your assessments. Highlight particularly important insights or urgent recommendations.

        For visualization purposes, include a one-line JSON schema at the end with these fields:
        {{"category": "", "subcategory": "", "complexity": 0, "recurrence_risk": 0, "business_impact": 0, "resolution_efficiency": 0, "prevention_difficulty": 0}}
        """
        
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        st.error(f"Error analyzing ticket with Gemini: {str(e)}")
        return None

# Data Source Selection
st.sidebar.header("Data Source")
st.sidebar.markdown("📊 Upload your support ticket CSV file to begin analysis")

# CSV Upload Section
st.sidebar.subheader("CSV Upload")
uploaded_file = st.sidebar.file_uploader("Upload CSV file", type=['csv'])

if uploaded_file is not None:
    try:
        # Read CSV file
        df = pd.read_csv(uploaded_file, encoding='utf-8', low_memory=False)
        
        # Clean and process the dataframe
        df = clean_data_types(df)
        
        # Filter for LoyaltyPro
        df = filter_loyaltypro_data(df)
        
        # Store data in session state
        st.session_state['data'] = df
        st.session_state['columns'] = df.columns.tolist()
        
        # Extract Jira ticket IDs
        jira_ticket_ids = extract_jira_ticket_ids(df)
        st.session_state['jira_tickets'] = jira_ticket_ids
        
        st.sidebar.success(f"✅ Loaded {len(df)} LoyaltyPro records")
        if jira_ticket_ids:
            st.sidebar.info(f"🎫 Found {len(jira_ticket_ids)} Jira tickets")
        
    except Exception as e:
        st.sidebar.error(f"Error loading CSV: {str(e)}")

# Main Dashboard Content
if st.session_state['data'] is not None:
    df = st.session_state['data']
    
    # Jira Analysis Section
    st.header("🔍 Jira Ticket Deep Analysis")
    
    # Check for Jira credentials
    jira_configured = all([
        os.getenv('JIRA_EMAIL'),
        os.getenv('JIRA_API_TOKEN'),
        os.getenv('GOOGLE_API_KEY')
    ])
    
    if not jira_configured:
        st.warning("⚠️ Jira integration requires configuration. Please add these secrets to your Replit Vault:")
        st.code("""
        JIRA_EMAIL - Your Jira email address
        JIRA_API_TOKEN - Your Jira API token
        GOOGLE_API_KEY - Your Google Gemini API key
        """)
    else:
        if st.session_state['jira_tickets']:
            selected_ticket = st.selectbox(
                "Select Jira ticket for AI analysis:",
                st.session_state['jira_tickets']
            )
            
            if st.button("🤖 Analyze with Gemini AI"):
                with st.spinner("Fetching ticket data and analyzing with AI..."):
                    ticket_data = get_jira_ticket_data(selected_ticket)
                    if ticket_data:
                        analysis = analyze_ticket_with_gemini(ticket_data)
                        if analysis:
                            st.session_state['ai_analysis'][selected_ticket] = analysis
                            st.success("✅ Analysis complete!")
                        else:
                            st.error("Failed to analyze ticket with AI")
                    else:
                        st.error("Failed to fetch ticket data from Jira")
            
            # Display analysis if available
            if selected_ticket in st.session_state['ai_analysis']:
                st.subheader(f"AI Analysis for {selected_ticket}")
                st.markdown(st.session_state['ai_analysis'][selected_ticket])
                
                # Add direct link to Jira ticket
                jira_url = f"https://razorpay.atlassian.net/browse/{selected_ticket}"
                st.markdown(f"🔗 [View original ticket in Jira]({jira_url})")
        else:
            st.info("No Jira tickets found in the uploaded data.")
    
    # Data Overview
    st.header("📊 Data Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tickets", len(df))
    with col2:
        escalated_count = len([tid for tid in st.session_state['jira_tickets'] if tid])
        st.metric("Escalated Tickets", escalated_count)
    with col3:
        if len(df) > 0:
            escalation_rate = (escalated_count / len(df)) * 100
            st.metric("Escalation Rate", f"{escalation_rate:.1f}%")
    with col4:
        if 'Account name' in df.columns:
            unique_clients = df['Account name'].nunique()
            st.metric("Unique Clients", unique_clients)
    
    # Date filtering
    st.sidebar.subheader("Date Filters")
    date_columns = [col for col in df.columns if 'date' in col.lower() or 'created' in col.lower()]
    
    if date_columns:
        date_col = st.sidebar.selectbox("Select date column:", date_columns)
        if date_col in df.columns and not df[date_col].isna().all():
            min_date = df[date_col].min()
            max_date = df[date_col].max()
            
            if pd.notna(min_date) and pd.notna(max_date):
                start_date = st.sidebar.date_input("Start date", min_date.date())
                end_date = st.sidebar.date_input("End date", max_date.date())
                
                # Filter data by date range
                mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
                df = df[mask]
                st.session_state['filtered_data'] = df
    
    # Client filtering
    if 'Account name' in df.columns:
        st.sidebar.subheader("Client Filters")
        available_clients = sorted(df['Account name'].dropna().unique())
        selected_clients = st.sidebar.multiselect(
            "Select clients:",
            available_clients,
            default=available_clients
        )
        
        if selected_clients:
            df = df[df['Account name'].isin(selected_clients)]
            st.session_state['filtered_data'] = df
    
    # Visualizations
    if len(df) > 0:
        st.header("📈 Analytics & Visualizations")
        
        # Client distribution
        if 'Account name' in df.columns:
            st.subheader("Client Distribution")
            client_counts = df['Account name'].value_counts()
            fig = px.bar(
                x=client_counts.index,
                y=client_counts.values,
                title="Tickets by Client",
                labels={'x': 'Client', 'y': 'Number of Tickets'}
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        # Time series analysis
        if date_columns and date_col in df.columns:
            st.subheader("Time Series Analysis")
            df_time = df.set_index(date_col).resample('W').size().reset_index()
            df_time.columns = ['Date', 'Ticket Count']
            
            fig = px.line(
                df_time,
                x='Date',
                y='Ticket Count',
                title="Tickets Over Time (Weekly)"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Issue category analysis
        if 'Issue Category' in df.columns:
            st.subheader("Issue Category Analysis")
            category_counts = df['Issue Category'].value_counts()
            fig = px.pie(
                values=category_counts.values,
                names=category_counts.index,
                title="Distribution by Issue Category"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Cross-sectional analysis
        st.subheader("Cross-sectional Analysis")
        if 'Account name' in df.columns and 'Issue Category' in df.columns:
            crosstab = pd.crosstab(df['Account name'], df['Issue Category'])
            
            fig = px.imshow(
                crosstab.values,
                x=crosstab.columns,
                y=crosstab.index,
                aspect="auto",
                title="Client vs Issue Category Heatmap"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        # Export functionality
        st.subheader("📥 Export Data")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Download Filtered Data as CSV"):
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"loyaltypro_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("Download AI Analysis Report"):
                if st.session_state['ai_analysis']:
                    report = "\n\n".join([
                        f"=== Analysis for {ticket_id} ===\n{analysis}"
                        for ticket_id, analysis in st.session_state['ai_analysis'].items()
                    ])
                    st.download_button(
                        label="Download Report",
                        data=report,
                        file_name=f"ai_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain"
                    )
                else:
                    st.info("No AI analysis available for download")
    
    else:
        st.warning("No data available after filtering. Please adjust your filters.")

else:
    # Show instructions when no data is loaded
    st.info("👆 Please upload a CSV file to begin analysis")
    
    st.markdown("""
    ### Features included:
    - **LoyaltyPro Ticket Filtering**: Automatically filters for LoyaltyPro product tickets
    - **Jira Integration**: Direct API access to fetch complete ticket details
    - **AI-Powered Analysis**: Gemini AI provides deep insights on ticket patterns and root causes
    - **Interactive Visualizations**: Time series, cross-sectional analysis, and client distributions
    - **Advanced Filtering**: Date ranges, client selection, and real-time filtering
    - **Export Capabilities**: Download filtered data and AI analysis reports
    """)