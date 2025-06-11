import streamlit as st

# Configure Streamlit page - MUST be first command
st.set_page_config(
    page_title="LoyaltyPro Analytics Dashboard", 
    page_icon="📊", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import requests
import os
import json
import re
import warnings
import google.generativeai as genai
import base64

# Try to import tabulate, use fallback if not available
try:
    import tabulate
    TABULATE_AVAILABLE = True
except ImportError:
    TABULATE_AVAILABLE = False

def df_to_markdown(df):
    """Convert DataFrame to markdown table with or without tabulate"""
    if TABULATE_AVAILABLE:
        return df.to_markdown()
    else:
        # Manual markdown table creation
        if df.empty:
            return "| No data available |\n|---|\n"
        
        # Create header
        header = "| " + " | ".join(str(col) for col in df.columns) + " |"
        separator = "|" + "|".join(["---"] * len(df.columns)) + "|"
        
        # Add rows
        rows = []
        for idx, row in df.iterrows():
            row_str = "| " + str(idx) + " | " + " | ".join(str(val) for val in row) + " |"
            rows.append(row_str)
        
        return header + "\n" + separator + "\n" + "\n".join(rows)

# Page configuration is already set at the top of the file

# Data processing functions
@st.cache_data
def process_csv(uploaded_file):
    """Process uploaded CSV with robust error handling and type conversion"""
    try:
        # Load CSV as string dtype first to avoid type issues
        df = pd.read_csv(uploaded_file, dtype=str)
        
        # Basic cleaning
        df = df.dropna(how='all')  # Remove completely empty rows
        df.columns = df.columns.str.strip()  # Remove whitespace from column names
        
        # Convert date columns with multiple possible names (suppress warnings)
        date_columns = ["Date", "First response sent time", "JIRA created time", "Created date", 
                       "Date created", "Creation date", "Created", "Timestamp"]
        for col in date_columns:
            if col in df.columns:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df[col] = pd.to_datetime(df[col], errors='coerce')
        
        return df, None
    except Exception as e:
        return None, str(e)

def apply_default_filters(df):
    """Apply all default filters in sequence as per technical requirements"""
    original_count = len(df)
    filter_log = []
    
    # 1. Last 30 days filter
    primary_date_col = None
    date_priority = ["Date", "First response sent time", "JIRA created time", "Created date", "Date created"]
    
    for col in date_priority:
        if col in df.columns:
            primary_date_col = col
            break
    
    if primary_date_col:
        try:
            # Get the most recent date in the dataset
            latest_date = df[primary_date_col].max()
            thirty_days_ago = latest_date - timedelta(days=30)
            df = df[df[primary_date_col] >= thirty_days_ago]
            filter_log.append(f"30-day filter: {len(df)} records from {thirty_days_ago.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')} (using {primary_date_col})")
        except Exception as e:
            filter_log.append(f"Date filter error: {str(e)}")
    else:
        filter_log.append("No date column found - showing all data")
    
    # 2. LoyaltyPro product filter (check multiple possible formats)
    if "Product name" in df.columns:
        loyalty_variations = ["LoyaltyPro", "Loyalty_Pro", "Loyalty Pro", "loyaltypro"]
        df = df[df["Product name"].str.lower().isin([v.lower() for v in loyalty_variations])]
        filter_log.append(f"LoyaltyPro filter: {len(df)} records")
    else:
        filter_log.append("No Product name column found")
    
    # 3. Specific target clients
    if "Account name" in df.columns:
        target_clients = ["AU Bank", "Axis", "DBS Bank", "Extraordinary Weekends", 
                         "Fi Money", "HDFC Bank", "IDFC FIRST Bank", "Jana Bank", 
                         "Kotak Mahindra Bank", "SBI Aurum"]
        df = df[df["Account name"].isin(target_clients)]
        filter_log.append(f"Client filter: {len(df)} records")
    else:
        filter_log.append("No Account name column found")
    
    # 4. Add Jira URL column if Jira ticket numbers exist
    jira_col = None
    for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "]:
        if col in df.columns:
            jira_col = col
            break
    
    if jira_col:
        # Create full Jira URL
        df["Jira URL"] = df[jira_col].apply(
            lambda x: f"https://razorpay.atlassian.net/browse/{x}" if pd.notna(x) and x != "" else ""
        )
        filter_log.append(f"Added Jira URLs for {jira_col}")
    
    return df, filter_log

def create_ticket_links(ticket_ids):
    """Create comma-separated hyperlinked ticket IDs"""
    if not ticket_ids:
        return ""
    
    # Convert to list if it's not already
    if isinstance(ticket_ids, str):
        ticket_ids = [ticket_ids]
    
    # Create hyperlinks for each ticket ID
    links = []
    for ticket_id in ticket_ids:
        # Clean the ticket ID
        ticket_id = str(ticket_id).strip()
        if ticket_id and ticket_id != 'nan':
            link = f"[{ticket_id}](https://razorpay.atlassian.net/browse/{ticket_id})"
            links.append(link)
    
    # Join with commas
    return ", ".join(links)

def extract_jira_tickets(df):
    """Extract Jira ticket IDs"""
    jira_columns = [
        'Jira ticket number if escalated to PSE',
        'Jira ticket number if escalated to PSE ',
        'JIRA ticket',
        'Jira Ticket',
        'Ticket ID'
    ]
    
    tickets = []
    for col in jira_columns:
        if col in df.columns:
            valid_tickets = df[col].dropna()
            valid_tickets = valid_tickets[valid_tickets.str.strip() != '']
            tickets.extend(valid_tickets.tolist())
    
    return list(set(tickets))  # Remove duplicates

def get_jira_ticket_data(ticket_id):
    """Fetch Jira ticket data"""
    jira_server = os.getenv('JIRA_SERVER_URL')
    jira_email = os.getenv('JIRA_EMAIL')
    jira_token = os.getenv('JIRA_API_TOKEN')
    
    if not all([jira_server, jira_email, jira_token]):
        return None
    
    try:
        url = f"{jira_server}/rest/api/3/issue/{ticket_id}"
        response = requests.get(url, auth=(jira_email, jira_token))
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception:
        return None

def extract_devrev_tickets(df):
    """Extract DevRev ticket IDs"""
    devrev_columns = [
        'DevRev ticket number',
        'DevRev Ticket',
        'DevRev ID',
        'Work ID',
        'Ticket ID'
    ]
    
    tickets = []
    # Look for DevRev-specific patterns in text columns
    for col in df.columns:
        if df[col].dtype == 'object':
            for value in df[col].astype(str):
                # Match DevRev patterns like DON-123, PLT-456, etc.
                matches = re.findall(r'(DON|PLT|ISS|DEV|REV|TKT|WORK)-\d+', str(value))
                tickets.extend(matches)
    
    # Also check specific DevRev columns
    for col in devrev_columns:
        if col in df.columns:
            valid_tickets = df[col].dropna()
            valid_tickets = valid_tickets[valid_tickets.str.strip() != '']
            tickets.extend(valid_tickets.tolist())
    
    return list(set(tickets))  # Remove duplicates

def get_devrev_ticket_data(ticket_id):
    """Fetch DevRev ticket data"""
    devrev_token = os.getenv('DEVREV_ACCESS_TOKEN')
    
    if not devrev_token:
        return None
    
    try:
        # DevRev API endpoint for getting work items
        url = "https://api.devrev.ai/works.get"
        headers = {
            'Authorization': f'Bearer {devrev_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'id': ticket_id
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception:
        return None

def extract_all_tickets(df):
    """Extract both Jira and DevRev ticket IDs"""
    jira_tickets = extract_jira_tickets(df)
    devrev_tickets = extract_devrev_tickets(df)
    
    return {
        'jira': jira_tickets,
        'devrev': devrev_tickets,
        'total': len(jira_tickets) + len(devrev_tickets)
    }

def get_ticket_data(ticket_id, ticket_type='auto'):
    """Unified function to get ticket data from either Jira or DevRev"""
    if ticket_type == 'auto':
        # Auto-detect based on ticket pattern
        if re.match(r'(DON|PLT|ISS|DEV|REV|TKT|WORK)-\d+', ticket_id):
            data = get_devrev_ticket_data(ticket_id)
            return data, 'devrev' if data else None
        else:
            data = get_jira_ticket_data(ticket_id)
            return data, 'jira' if data else None
    elif ticket_type == 'jira':
        data = get_jira_ticket_data(ticket_id)
        return data, 'jira' if data else None
    elif ticket_type == 'devrev':
        data = get_devrev_ticket_data(ticket_id)
        return data, 'devrev' if data else None
    
    return None, None



# Visualization functions
def create_trend_chart(df, date_col):
    """Create 30-day trend visualization"""
    if date_col not in df.columns:
        return None
    
    # Group by date
    daily_counts = df.groupby(df[date_col].dt.date).size().reset_index()
    daily_counts.columns = ['Date', 'Tickets']
    
    fig = px.line(daily_counts, x='Date', y='Tickets', 
                  title='30-Day Ticket Volume Trend',
                  line_shape='spline')
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Number of Tickets",
        hovermode='x unified'
    )
    return fig

def create_client_breakdown(df):
    """Create client breakdown chart"""
    if 'Account name' not in df.columns:
        return None
    
    client_counts = df['Account name'].value_counts()
    
    fig = px.bar(x=client_counts.index, y=client_counts.values,
                 title='Tickets by Client',
                 labels={'x': 'Client', 'y': 'Number of Tickets'})
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_priority_distribution(df):
    """Create priority distribution chart"""
    priority_cols = [col for col in df.columns if 'priority' in col.lower()]
    
    if not priority_cols:
        return None
    
    priority_col = priority_cols[0]
    priority_counts = df[priority_col].value_counts()
    
    fig = px.pie(values=priority_counts.values, names=priority_counts.index,
                 title='Tickets by Priority')
    return fig

# Main application logic
def apply_razorpay_styling():
    """Apply Razorpay-inspired styling"""
    st.markdown("""
    <style>
    /* Main styling */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    
    /* Header styling */
    .header-container {
        background: linear-gradient(90deg, #528BFF 0%, #3B82F6 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 12px rgba(82, 139, 255, 0.15);
    }
    
    .header-content {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
    }
    
    .header-title {
        color: white;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
    }
    
    .header-subtitle {
        color: rgba(255, 255, 255, 0.9);
        font-size: 1.1rem;
        font-weight: 400;
        margin: 0.5rem 0 0 0;
    }
    
    /* Logo styling */
    .logo-container {
        display: flex;
        align-items: center;
    }
    
    /* Card styling */
    .upload-zone {
        background: white;
        padding: 3rem 2rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border: 2px dashed #528BFF;
        margin: 2rem 0;
    }
    
    .success-box {
        background: #F0FDF4;
        border: 1px solid #BBF7D0;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 4px;
        margin-bottom: 1rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        padding: 12px 24px;
        background-color: transparent;
        border-radius: 6px;
        color: #64748B;
        font-weight: 500;
        border: none;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #528BFF !important;
        color: white !important;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(90deg, #528BFF 0%, #3B82F6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(82, 139, 255, 0.3);
    }
    
    /* Info boxes */
    .stInfo {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 8px;
    }
    
    /* Success boxes */
    .stSuccess {
        background-color: #F0FDF4;
        border: 1px solid #BBF7D0;
        border-radius: 8px;
    }
    
    /* Warning boxes */
    .stWarning {
        background-color: #FFFBEB;
        border: 1px solid #FED7AA;
        border-radius: 8px;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #F8FAFC;
    }
    
    /* Download button styling */
    .stDownloadButton > button {
        background-color: #10B981;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    
    /* File uploader styling */
    .stFileUploader {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

def create_razorpay_logo():
    """Create Razorpay logo SVG"""
    return """
    <svg width="120" height="40" viewBox="0 0 120 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 8H32C34.2091 8 36 9.79086 36 12V28C36 30.2091 34.2091 32 32 32H8C5.79086 32 4 30.2091 4 28V12C4 9.79086 5.79086 8 8 8Z" fill="#528BFF"/>
        <path d="M12 12H16L20 20L24 12H28L21 25H19L12 12Z" fill="white"/>
        <text x="40" y="25" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#1F2937">Razorpay</text>
    </svg>
    """

def main():
    # Apply custom styling
    apply_razorpay_styling()
    
    # Header with clean styling
    st.markdown("""
    <div style="background: linear-gradient(90deg, #528BFF 0%, #3B82F6 100%); padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 2rem; box-shadow: 0 4px 12px rgba(82, 139, 255, 0.15); text-align: center;">
        <h1 style="color: white; font-size: 2.2rem; font-weight: 700; margin: 0;">📊 LoyaltyPro Analytics Dashboard</h1>
        <p style="color: rgba(255, 255, 255, 0.9); font-size: 1.1rem; font-weight: 400; margin: 0.5rem 0 0 0;">Support Operations Intelligence & AI-Driven Insights</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar for file upload
    with st.sidebar:
        st.header("📂 Data Upload")
        uploaded_file = st.file_uploader("Upload CSV file", type=['csv'])
        
        if uploaded_file:
            st.success(f"File uploaded: {uploaded_file.name}")
    
    # Main content area
    if uploaded_file is None:
        # Landing page
        st.markdown("""
        <div class="upload-zone">
            <h3>Welcome to LoyaltyPro Support Analytics</h3>
            <p>Upload your CSV file to begin comprehensive ticket analysis</p>
            <p><strong>Features:</strong></p>
            <ul style="text-align: left; display: inline-block;">
                <li>30-day trend analysis with interactive visualizations</li>
                <li>AI-powered insights with real Jira integration</li>
                <li>Monthly comparison with technical root cause analysis</li>
                <li>Individual ticket explorer with deep dive capabilities</li>
                <li>Advanced search and filtering across all historical data</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Process uploaded file
    with st.spinner("Processing CSV file..."):
        df, error = process_csv(uploaded_file)
    
    if error:
        st.error(f"Error loading file: {error}")
        return
    
    if df is None or df.empty:
        st.error("No data found in uploaded file")
        return
    
    # Display upload confirmation
    st.markdown(f"""
    <div class="success-box">
        <strong>✅ File processed successfully!</strong><br>
        Loaded {len(df)} rows and {len(df.columns)} columns
    </div>
    """, unsafe_allow_html=True)
    
    # Apply default filters as per technical requirements
    st.subheader("🔍 Data Filtering")
    
    with st.expander("View filtering details", expanded=False):
        df_filtered, filter_log = apply_default_filters(df)
        
        st.info(f"**Original dataset:** {len(df)} records")
        for log_entry in filter_log:
            st.info(f"**{log_entry}**")
        
        st.success(f"**Final dataset:** {len(df_filtered)} records ready for analysis")
    
    if df_filtered.empty:
        st.warning("No data remaining after filtering. Please check your data format.")
        return
    
    # Prepare unfiltered data for AI Insights (apply product and client filters only, no date restrictions)
    df_ai_insights = df.copy()
    ai_filter_log = []
    
    # Apply only non-date filters for AI insights
    if "Product name" in df_ai_insights.columns:
        loyalty_variations = ["LoyaltyPro", "Loyalty_Pro", "Loyalty Pro", "loyaltypro"]
        df_ai_insights = df_ai_insights[df_ai_insights["Product name"].str.lower().isin([v.lower() for v in loyalty_variations])]
        ai_filter_log.append(f"LoyaltyPro filter: {len(df_ai_insights)} records")
    
    if "Account name" in df_ai_insights.columns:
        target_clients = ["AU Bank", "Axis", "DBS Bank", "Extraordinary Weekends", 
                         "Fi Money", "HDFC Bank", "IDFC FIRST Bank", "Jana Bank", 
                         "Kotak Mahindra Bank", "SBI Aurum"]
        df_ai_insights = df_ai_insights[df_ai_insights["Account name"].isin(target_clients)]
        ai_filter_log.append(f"Client filter: {len(df_ai_insights)} records")
    
    # Add Jira URL column for AI insights data
    jira_col = None
    for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "]:
        if col in df_ai_insights.columns:
            jira_col = col
            break
    
    if jira_col:
        df_ai_insights["Jira URL"] = df_ai_insights[jira_col].apply(
            lambda x: f"https://razorpay.atlassian.net/browse/{x}" if pd.notna(x) and x != "" else ""
        )
    
    # Store filtered data in session state
    st.session_state['filtered_data'] = df_filtered
    st.session_state['ai_insights_data'] = df_ai_insights
    st.session_state['jira_tickets'] = extract_jira_tickets(df_filtered)
    
    # Create tabs with updated order
    tab1, tab2, tab3, tab4 = st.tabs(["30-Day Trends", "AI powered insights", "Monthly comparison", "Ticket Explorer"])
    
    with tab1:
        show_trends_tab(df_filtered)
    
    with tab2:
        show_search_tab(df_ai_insights)
    
    with tab3:
        # Use unfiltered data (no date restrictions) for AI insights to access all months
        show_ai_insights_tab(df_ai_insights)
    
    with tab4:
        show_ticket_explorer_tab(df_filtered)

def show_trends_tab(df):
    """Display 30-day trend analysis visualizations"""
    st.header("30-Day Ticket Trends")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Tickets", len(df))
    
    # Calculate escalation rate if Jira column exists
    jira_col = next((col for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "] 
                     if col in df.columns), None)
    if jira_col:
        escalated = df[df[jira_col].notna() & (df[jira_col] != "")].shape[0]
        escalation_rate = f"{round((escalated / len(df)) * 100, 1)}%" if len(df) > 0 else "0%"
        col2.metric("Escalated Tickets", escalated)
        col3.metric("Escalation Rate", escalation_rate)
    
    col4.metric("Unique Clients", df["Account name"].nunique() if "Account name" in df.columns else 0)
    
    # Time series visualization
    if "Date" in df.columns:
        st.subheader("Daily Ticket Volume")
        daily_tickets = df.groupby(df["Date"].dt.date).size().reset_index(name="Count")
        fig = px.line(
            daily_tickets, 
            x="Date", 
            y="Count",
            markers=True,
            line_shape="linear",
            height=400
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Number of Tickets",
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Client breakdown
        if "Account name" in df.columns:
            st.subheader("Tickets by Client")
            client_counts = df["Account name"].value_counts().reset_index()
            client_counts.columns = ["Client", "Count"]
            fig = px.bar(
                client_counts,
                x="Client",
                y="Count",
                color="Client",
                height=400
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        # Category breakdown
        if "Issue Category" in df.columns:
            st.subheader("Tickets by Issue Category")
            category_counts = df["Issue Category"].value_counts().reset_index()
            category_counts.columns = ["Category", "Count"]
            fig = px.pie(
                category_counts,
                values="Count",
                names="Category",
                hole=0.4,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            # Alternative breakdown by priority if available
            priority_cols = [col for col in df.columns if 'priority' in col.lower()]
            if priority_cols:
                st.subheader(f"Tickets by {priority_cols[0]}")
                priority_counts = df[priority_cols[0]].value_counts().reset_index()
                priority_counts.columns = ["Priority", "Count"]
                fig = px.pie(
                    priority_counts,
                    values="Count",
                    names="Priority",
                    hole=0.4,
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No 'Date' column found. Unable to create time-based visualizations.")

def analyze_with_gemini(df, api_key):
    """Process ticket data with Gemini 1.5 Flash for insights"""
    # Configure Gemini API
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Prepare data for analysis
    tickets_summary = []
    
    jira_col = next((col for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "] 
                     if col in df.columns), None)
    
    # Get all tickets with Jira numbers
    if jira_col:
        jira_tickets = df[df[jira_col].notna() & (df[jira_col] != "")]
        
        # Format ticket data
        for _, ticket in jira_tickets.iterrows():
            ticket_data = {
                "ticket_id": ticket[jira_col] if jira_col in ticket else "",
                "date": ticket["Date"].strftime("%Y-%m-%d") if "Date" in ticket and pd.notna(ticket["Date"]) else "",
                "client": ticket["Account name"] if "Account name" in ticket else "",
                "category": ticket["Issue Category"] if "Issue Category" in ticket else "",
                "subcategory": ticket["Issue Sub-category"] if "Issue Sub-category" in ticket else "",
                "status": ticket["FD Ticket Status"] if "FD Ticket Status" in ticket else "",
                "description": "Not available in CSV"  # Would come from Jira API
            }
            tickets_summary.append(ticket_data)
    
    # Enhanced 30-day trend analysis prompt for Gemini 2.5 Pro
    prompt = f"""
    You are a data science expert specializing in support operations analytics for fintech platforms. Analyze this 30-day dataset of LoyaltyPro support tickets to extract strategic insights and identify actionable patterns.

    [TICKET_SUMMARY]
    {json.dumps(tickets_summary)}
    [/TICKET_SUMMARY]

    Conduct a comprehensive multi-dimensional analysis and provide the following:

    1. **EXECUTIVE INTELLIGENCE BRIEF**
       - 3-5 sentence executive summary highlighting critical patterns and actionable intelligence
       - Key performance metrics with percentage changes compared to previous periods
       - Overall health assessment with confidence score

    2. **CLIENT ECOSYSTEM ANALYSIS**
       - Client segmentation by ticket volume, issue types, and resolution complexity
       - Client-specific trend patterns with statistical significance scores
       - Cross-client issue correlation matrix identifying shared underlying causes
       - Identification of outlier clients requiring special attention

    3. **TECHNICAL ROOT CAUSE MAPPING**
       - Hierarchical clustering of issues by underlying technical causes
       - Identification of common failure points across the LoyaltyPro architecture
       - Correlation between issue categories and specific system components
       - Technical debt indicators revealed by support patterns

    4. **TEMPORAL PATTERN RECOGNITION**
       - Day-of-week and time-of-day distribution with statistical significance
       - Time-series decomposition of ticket volume trends
       - Detection of anomalous spikes or patterns with p-values
       - Forecasting of expected ticket volumes for next 7-14 days

    5. **BUSINESS IMPACT ASSESSMENT**
       - Estimated revenue impact by issue category and client
       - Client satisfaction risk assessment based on ticket patterns
       - Opportunity cost analysis of engineering resources
       - Comparison to industry benchmarks where available

    6. **STRATEGIC RECOMMENDATIONS**
       - 3-5 high-impact, actionable recommendations with expected outcomes
       - Prioritized engineering initiatives to reduce ticket volume
       - Client-specific intervention strategies
       - Enhanced monitoring and alerting recommendations with implementation details

    Format your analysis as a structured report with clear section headers. Use bullet points for clarity but provide detailed technical explanations where needed. Include specific metrics, percentages, and statistical significance where possible.

    Your analysis should bridge technical and business perspectives, focusing on actionable insights that could drive meaningful improvements to the LoyaltyPro platform and support operations.
    """
    
    try:
        # Call Gemini API
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating AI analysis: {str(e)}"

def prepare_trend_analysis_data(df, current_df, previous_df, dimensions):
    """Prepare structured data for trend analysis"""
    analysis_data = {
        "overview": {
            "total_tickets": {
                "current": len(current_df),
                "previous": len(previous_df),
                "change_pct": round(((len(current_df) - len(previous_df)) / max(len(previous_df), 1)) * 100, 1)
            },
            "unique_clients": {
                "current": current_df["Account name"].nunique() if "Account name" in current_df.columns else 0,
                "previous": previous_df["Account name"].nunique() if "Account name" in previous_df.columns else 0
            }
        },
        "dimensions": {}
    }
    
    # Add pivot table data for each dimension
    for dimension in dimensions:
        if dimension in df.columns:
            # Current period breakdown
            current_counts = current_df[dimension].value_counts().to_dict()
            
            # Previous period breakdown
            previous_counts = previous_df[dimension].value_counts().to_dict()
            
            # Calculate changes
            all_values = set(list(current_counts.keys()) + list(previous_counts.keys()))
            comparison = {}
            
            for value in all_values:
                current_count = current_counts.get(value, 0)
                previous_count = previous_counts.get(value, 0)
                change = current_count - previous_count
                change_pct = round((change / max(previous_count, 1)) * 100, 1)
                
                comparison[value] = {
                    "current": current_count,
                    "previous": previous_count,
                    "change": change,
                    "change_pct": change_pct
                }
            
            analysis_data["dimensions"][dimension] = comparison
    
    # Create cross-tab data if both Issue Category and Account name are selected
    if "Issue Category" in dimensions and "Account name" in dimensions:
        # Current period cross-tab
        current_crosstab = pd.crosstab(
            current_df["Account name"] if "Account name" in current_df.columns else pd.Series(["Unknown"]), 
            current_df["Issue Category"] if "Issue Category" in current_df.columns else pd.Series(["Unknown"])
        ).fillna(0).astype(int)
        
        # Previous period cross-tab
        previous_crosstab = pd.crosstab(
            previous_df["Account name"] if "Account name" in previous_df.columns else pd.Series(["Unknown"]), 
            previous_df["Issue Category"] if "Issue Category" in previous_df.columns else pd.Series(["Unknown"])
        ).fillna(0).astype(int)
        
        # Convert crosstabs to dict for JSON serialization
        analysis_data["crosstabs"] = {
            "current": current_crosstab.to_dict(),
            "previous": previous_crosstab.to_dict()
        }
    
    return analysis_data

def prepare_overall_analysis_data(df, dimensions):
    """Prepare data for overall analysis without month comparison"""
    analysis_data = {
        "overview": {
            "total_tickets": len(df),
            "unique_clients": df["Account name"].nunique() if "Account name" in df.columns else 0
        },
        "dimensions": {}
    }
    
    # Add breakdown for each dimension
    for dimension in dimensions:
        if dimension in df.columns:
            counts = df[dimension].value_counts().to_dict()
            analysis_data["dimensions"][dimension] = counts
    
    # Create cross-tab data if both Issue Category and Account name are selected
    if "Issue Category" in dimensions and "Account name" in dimensions:
        crosstab = pd.crosstab(
            df["Account name"] if "Account name" in df.columns else pd.Series(["Unknown"]), 
            df["Issue Category"] if "Issue Category" in df.columns else pd.Series(["Unknown"])
        ).fillna(0).astype(int)
        
        # Convert crosstab to dict for JSON serialization
        analysis_data["crosstabs"] = crosstab.to_dict()
    
    return analysis_data

def generate_category_client_prompt(current_df, previous_df):
    """Generate prompt for Issue Category × Client analysis"""
    # Calculate counts for current period
    current_crosstab = pd.crosstab(
        current_df["Account name"] if "Account name" in current_df.columns else pd.Series(["Unknown"]),
        current_df["Issue Category"] if "Issue Category" in current_df.columns else pd.Series(["Unknown"]),
        margins=True
    ).fillna(0).astype(int)
    
    # Calculate counts for previous period
    previous_crosstab = pd.crosstab(
        previous_df["Account name"] if "Account name" in previous_df.columns else pd.Series(["Unknown"]),
        previous_df["Issue Category"] if "Issue Category" in previous_df.columns else pd.Series(["Unknown"]),
        margins=True
    ).fillna(0).astype(int)
    
    # Current and previous month names
    current_month = current_df["Month-Year"].iloc[0] if not current_df.empty else "Current"
    previous_month = previous_df["Month-Year"].iloc[0] if not previous_df.empty else "Previous"
    
    # Convert to markdown tables for the prompt
    current_table = df_to_markdown(current_crosstab)
    previous_table = df_to_markdown(previous_crosstab)
    
    prompt = f"""
    You are a data analyst specializing in support operations for fintech companies. I'm providing you with ticket count data comparing {previous_month} to {current_month}. Format your analysis EXACTLY like the reference format below.

    [CURRENT MONTH DATA: {current_month}]
    {current_table}
    [/CURRENT MONTH DATA]

    [PREVIOUS MONTH DATA: {previous_month}]
    {previous_table}
    [/PREVIOUS MONTH DATA]

    Create a concise, tabulated analysis with EXACTLY this format:

    ## {current_month} Ticket Count
    
    [CREATE EXACT MARKDOWN TABLE showing Account name × Issue Category]
    
    ## {current_month} ticket counts
    [1-2 sentences about total ticket volume and main trends]
    
    [CREATE TABLE with Issue Category, {previous_month}, {current_month}, and Delta columns]
    
    ## Category Deep-Dive: [Select the most significant category]
    [1-2 sentences about this category]
    
    [CREATE TABLE with Account name, {previous_month}, {current_month}, Delta columns for this category]
    
    ### Top Client Issue: [Select client+category with biggest change]
    
    [CREATE TABLE showing specific breakdown with Remarks column]
    
    [1-2 sentences of insights about root causes]

    CRITICAL FORMATTING REQUIREMENTS:
    1. Use ONLY markdown tables, NOT HTML tables
    2. Keep all analysis EXTREMELY concise - no more than 1-2 sentences per section
    3. Tables must be formatted exactly as shown in the instructions
    4. Focus ONLY on the most significant changes and patterns
    5. Do not include any introduction, conclusion, or additional sections
    """
    
    return prompt

def generate_mom_comparison_prompt(current_df, previous_df):
    """Generate prompt for Month-over-Month comparison"""
    # Current and previous month names
    current_month = current_df["Month-Year"].iloc[0] if not current_df.empty else "Current"
    previous_month = previous_df["Month-Year"].iloc[0] if not previous_df.empty else "Previous"
    
    # Prepare category data
    categories = pd.concat([
        previous_df["Issue Category"].value_counts(),
        current_df["Issue Category"].value_counts()
    ], axis=1, sort=True).fillna(0).astype(int)
    categories.columns = [previous_month, current_month]
    categories['Delta'] = categories[current_month] - categories[previous_month]
    
    # Prepare client data
    clients = pd.concat([
        previous_df["Account name"].value_counts(),
        current_df["Account name"].value_counts()
    ], axis=1, sort=True).fillna(0).astype(int)
    clients.columns = [previous_month, current_month]
    clients['Delta'] = clients[current_month] - clients[previous_month]
    
    # Convert to markdown tables
    categories_table = df_to_markdown(categories)
    clients_table = df_to_markdown(clients)
    
    prompt = f"""
    You are a data analyst specializing in support operations for fintech companies. I'm providing you with ticket count data comparing {previous_month} to {current_month}. Format your analysis EXACTLY like the reference format.

    [CATEGORY COMPARISON]
    {categories_table}
    [/CATEGORY COMPARISON]

    [CLIENT COMPARISON]
    {clients_table}
    [/CLIENT COMPARISON]

    Create a concise, tabulated analysis with EXACTLY this format:

    ## Month-over-Month Comparison: {previous_month} vs {current_month}
    
    [1 sentence summary of overall change]
    
    ## Issue Category Changes
    
    [CREATE TABLE with Issue Category, {previous_month}, {current_month}, Delta columns, sorted by Delta descending]
    
    [1 sentence explanation of the biggest category change]
    
    ## Client Changes
    
    [CREATE TABLE with Account name, {previous_month}, {current_month}, Delta columns, sorted by Delta descending]
    
    [1 sentence explanation of the biggest client change]
    
    ## Top Focus Areas
    
    [CREATE TABLE with 3-5 rows showing Client, Category, Delta, Root Cause (1-2 words), Action (1-2 words)]
    
    CRITICAL FORMATTING REQUIREMENTS:
    1. Use ONLY markdown tables, NOT HTML tables
    2. Keep all analysis EXTREMELY concise - no more than 1-2 sentences per section
    3. Tables must be formatted exactly as shown in the instructions
    4. Only show the most significant items in each table (limit to top 5-7 entries)
    5. Do not include any introduction or conclusion
    """
    
    return prompt

def generate_action_plan_prompt(current_df, previous_df):
    """Generate prompt for Root Cause & Action Plan analysis"""
    # Current and previous month names
    current_month = current_df["Month-Year"].iloc[0] if not current_df.empty else "Current"
    
    # Create cross-tab for client × category
    crosstab = pd.crosstab(
        current_df["Account name"] if "Account name" in current_df.columns else pd.Series(["Unknown"]),
        current_df["Issue Category"] if "Issue Category" in current_df.columns else pd.Series(["Unknown"]),
        margins=True
    ).fillna(0).astype(int)
    
    # Convert to markdown
    crosstab_table = df_to_markdown(crosstab)
    
    prompt = f"""
    You are a support operations analyst for a fintech company. Based on this ticket data for {current_month}, create a root cause analysis and action plan in the EXACT format shown below.

    [TICKET DISTRIBUTION]
    {crosstab_table}
    [/TICKET DISTRIBUTION]

    Create a concise, tabulated action plan with EXACTLY this format:

    ## Path to 60/month tickets
    
    Going through all the tickets raised, we can reduce approximately 65% of these tickets through specific actions.
    
    [CREATE TABLE with columns: Bank, Issue Category, #Tickets that can be reduced, Reason, Actionables]
    - Format exactly like this example:
    | Bank | Issue Category | #Tickets that can be reduced | Reason | Actionables |
    |------|---------------|----------------------------|--------|------------|
    | Bank1 | Category1 | 25 | Brief reason | Brief action |
    
    ## Potential Impact
    
    [CREATE TABLE showing: Current baseline, Reduction potential, New potential baseline]
    
    CRITICAL FORMATTING REQUIREMENTS:
    1. Use ONLY markdown tables, NOT HTML tables
    2. Make tables EXACTLY match the format shown
    3. Be extremely brief in the "Reason" and "Actionables" columns - no more than 10 words each
    4. Focus on the highest-impact items (those that can reduce the most tickets)
    5. Group similar issues that have the same resolution
    6. Format the final calculation as simple math: "189-124 = 65"
    7. No introduction, conclusion, or additional sections
    """
    
    return prompt

def generate_overall_analysis_prompt(df, analysis_type):
    """Generate prompt for overall analysis without month comparison"""
    # Create cross-tab
    crosstab = pd.crosstab(
        df["Account name"] if "Account name" in df.columns else pd.Series(["Unknown"]),
        df["Issue Category"] if "Issue Category" in df.columns else pd.Series(["Unknown"]),
        margins=True
    ).fillna(0).astype(int)
    
    crosstab_table = df_to_markdown(crosstab)
    
    if analysis_type == "Root Cause & Action Plan":
        prompt = f"""
        You are a support operations analyst for a fintech company. Based on this overall ticket data, create a root cause analysis and action plan.

        [TICKET DISTRIBUTION]
        {crosstab_table}
        [/TICKET DISTRIBUTION]

        Create a concise, tabulated action plan with EXACTLY this format:

        ## Path to Ticket Reduction
        
        Going through all the tickets raised, we can reduce approximately 65% of these tickets through specific actions.
        
        [CREATE TABLE with columns: Bank, Issue Category, #Tickets that can be reduced, Reason, Actionables]
        
        ## Potential Impact
        
        [CREATE TABLE showing: Current baseline, Reduction potential, New potential baseline]
        
        CRITICAL FORMATTING REQUIREMENTS:
        1. Use ONLY markdown tables, NOT HTML tables
        2. Be extremely brief in the "Reason" and "Actionables" columns
        3. Focus on the highest-impact items
        4. No introduction or conclusion
        """
    else:
        prompt = f"""
        You are a data analyst specializing in support operations. Analyze this ticket distribution data.

        [TICKET DISTRIBUTION]
        {crosstab_table}
        [/TICKET DISTRIBUTION]

        Create a concise analysis with markdown tables showing:
        1. Top issue categories by volume
        2. Top clients by ticket count
        3. Key patterns and insights

        Keep analysis extremely brief with proper markdown table formatting.
        """
    
    return prompt

def generate_jira_insights_section(df, api_key):
    """Generate detailed Jira ticket insights for section 3"""
    # Initialize Gemini
    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-pro')
        except Exception as e:
            return f"Error initializing Gemini model: {str(e)}"
    
    # Extract Jira ticket information
    jira_col = next((col for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "] 
                     if col in df.columns), None)
    
    if not jira_col or jira_col not in df.columns:
        return "No Jira ticket column found in data"
    
    # Filter for rows with Jira tickets
    jira_tickets = df[df[jira_col].notna() & (df[jira_col] != "")]
    
    if jira_tickets.empty:
        return "No Jira tickets found in the filtered data"
    
    # Create cross-tabulation for category × client
    if "Account name" in jira_tickets.columns and "Issue Category" in jira_tickets.columns:
        crosstab = pd.crosstab(
            jira_tickets["Account name"],
            jira_tickets["Issue Category"],
            margins=True
        ).fillna(0).astype(int)
        
        # Get top combinations
        combinations = []
        for client in crosstab.index:
            if client == "All":
                continue
            for category in crosstab.columns:
                if category == "All":
                    continue
                if crosstab.loc[client, category] > 0:
                    combinations.append({
                        "client": client,
                        "category": category,
                        "count": int(crosstab.loc[client, category]),
                        "ticket_ids": jira_tickets[
                            (jira_tickets["Account name"] == client) & 
                            (jira_tickets["Issue Category"] == category)
                        ][jira_col].tolist()
                    })
        
        # Sort by count descending
        combinations = sorted(combinations, key=lambda x: x["count"], reverse=True)
        
        # Keep only top 10 combinations to limit prompt size
        top_combinations = combinations[:10]
        
        # Prepare additional ticket details for top combinations
        for combo in top_combinations:
            # Get sample tickets for this combination
            combo_tickets = jira_tickets[
                (jira_tickets["Account name"] == combo["client"]) & 
                (jira_tickets["Issue Category"] == combo["category"])
            ]
            
            # Extract additional info
            sample_tickets = []
            for _, ticket in combo_tickets.head(3).iterrows():  # Limit to 3 sample tickets
                ticket_info = {
                    "id": ticket[jira_col],
                    "url": f"https://razorpay.atlassian.net/browse/{ticket[jira_col]}",
                    "client": ticket["Account name"] if "Account name" in ticket else "",
                    "category": ticket["Issue Category"] if "Issue Category" in ticket else "",
                    "subcategory": ticket["Issue Sub-category"] if "Issue Sub-category" in ticket else "",
                    "status": ticket["FD Ticket Status"] if "FD Ticket Status" in ticket else "",
                    "priority": ticket["Priority"] if "Priority" in ticket else ""
                }
                sample_tickets.append(ticket_info)
            
            combo["sample_tickets"] = sample_tickets
    else:
        return "Missing required Account name or Issue Category columns"
    
    # Generate the prompt for Jira analysis
    prompt = f"""
    You are a support operations analyst for a fintech company specializing in the LoyaltyPro product. Based on Jira ticket data, provide a detailed pattern analysis for each client-category combination below.

    [TICKET_COMBINATIONS]
    {json.dumps(top_combinations, indent=2)}
    [/TICKET_COMBINATIONS]

    Create a detailed analysis section titled "3. Key Patterns & Insights from Jira Tickets" with the following structure:

    First, provide a summary table of the top issues:

    | Client-Category | Count | Primary Root Cause | Typical Resolution | Est. Resolution Time |
    |----------------|-------|-------------------|-------------------|---------------------|
    | Client1-Category1 | XX | Brief technical root cause | Brief resolution approach | X days/hours |
    | Client2-Category2 | XX | Brief technical root cause | Brief resolution approach | X days/hours |
    
    Then, for EACH of the top 5 client-category combinations, provide a detailed breakdown with:
    
    ### [Client] - [Category] ([Count] tickets)
    
    **Root Cause Analysis:**
    * Primary technical cause: [specific technical issue, not generic description]
    * System components involved: [specific components/services]
    * Triggering conditions: [what specific conditions cause this issue]
    
    **Resolution Pattern:**
    * Standard resolution process: [step-by-step technical resolution]
    * Teams involved: [specific teams needed]
    * Average resolution time: [estimate based on complexity]
    
    **Action Items:**
    * [3-5 specific, technical recommendations to prevent recurrence]
    * [Include both immediate fixes and long-term prevention measures]
    * [Specify which team should implement each action]
    
    For refund issues, explain exactly what causes payment failures or refund delays in the specific system integration. For campaign issues, identify the exact campaign mechanism failing. Be technically precise rather than generic.

    Each analysis must include:
    1. The specific technical component failing
    2. The exact integration point or data flow causing issues
    3. Whether it's a code-level bug, configuration issue, or system limitation
    4. Precise resolution steps that would be taken by support/engineering teams

    Format all of this as clean markdown, with proper headers, bullet points, and tables. Focus on being specific and technical in your analysis - avoid generic statements.
    """
    
    try:
        # Call Gemini API
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating Jira insights: {str(e)}"

def fetch_jira_ticket_content(ticket_ids, jira_credentials):
    """Fetch actual content from Jira tickets"""
    jira_url = jira_credentials.get("url", "https://razorpay.atlassian.net")
    jira_email = jira_credentials.get("email")
    jira_api_token = jira_credentials.get("api_token")
    
    if not jira_email or not jira_api_token:
        return {"error": "Missing Jira credentials"}
    
    headers = {"Accept": "application/json"}
    auth = (jira_email, jira_api_token)
    
    ticket_data = []
    success_count = 0
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticket_id in enumerate(ticket_ids[:15]):  # Limit to 15 tickets
        status_text.text(f"Processing ticket {i+1}/{min(15, len(ticket_ids))}: {ticket_id}")
        
        try:
            # Clean ticket ID
            clean_ticket_id = str(ticket_id).strip()
            api_url = f"{jira_url}/rest/api/3/issue/{clean_ticket_id}"
            
            response = requests.get(api_url, headers=headers, auth=auth, timeout=15)
            
            if response.status_code == 200:
                issue_data = response.json()
                fields = issue_data.get("fields", {})
                
                # Extract description content
                description_content = ""
                description = fields.get("description", {})
                if isinstance(description, dict) and "content" in description:
                    # Handle Atlassian Document Format
                    for content_block in description.get("content", []):
                        if content_block.get("type") == "paragraph":
                            for text_block in content_block.get("content", []):
                                if text_block.get("type") == "text":
                                    description_content += text_block.get("text", "") + " "
                elif isinstance(description, str):
                    description_content = description
                
                ticket_info = {
                    "id": clean_ticket_id,
                    "summary": fields.get("summary", ""),
                    "description": description_content.strip(),
                    "status": fields.get("status", {}).get("name", ""),
                    "priority": fields.get("priority", {}).get("name", ""),
                    "issue_type": fields.get("issuetype", {}).get("name", ""),
                    "created": fields.get("created", ""),
                    "updated": fields.get("updated", ""),
                    "comments": []
                }
                
                # Extract comments
                if "comment" in fields:
                    comments = fields.get("comment", {}).get("comments", [])
                    for comment in comments[:5]:  # Get more comments for better analysis
                        comment_text = ""
                        body = comment.get("body", {})
                        if isinstance(body, dict) and "content" in body:
                            # Handle Atlassian Document Format for comments
                            for content_block in body.get("content", []):
                                if content_block.get("type") == "paragraph":
                                    for text_block in content_block.get("content", []):
                                        if text_block.get("type") == "text":
                                            comment_text += text_block.get("text", "") + " "
                        elif isinstance(body, str):
                            comment_text = body
                        
                        if comment_text.strip():
                            ticket_info["comments"].append({
                                "text": comment_text.strip(),
                                "author": comment.get("author", {}).get("displayName", ""),
                                "created": comment.get("created", "")
                            })
                
                ticket_data.append(ticket_info)
                success_count += 1
                
            elif response.status_code == 401:
                ticket_data.append({"id": clean_ticket_id, "error": "Authentication failed - check credentials"})
            elif response.status_code == 404:
                ticket_data.append({"id": clean_ticket_id, "error": "Ticket not found"})
            else:
                ticket_data.append({"id": clean_ticket_id, "error": f"HTTP {response.status_code}: {response.text[:100]}"})
                
        except requests.exceptions.Timeout:
            ticket_data.append({"id": ticket_id, "error": "Request timeout"})
        except Exception as e:
            ticket_data.append({"id": ticket_id, "error": f"Exception: {str(e)}"})
        
        # Update progress
        progress_bar.progress((i + 1) / min(15, len(ticket_ids)))
    
    # Clear progress indicators
    progress_bar.empty()
    status_text.empty()
    
    return {
        "ticket_data": ticket_data, 
        "success_count": success_count,
        "total_processed": min(15, len(ticket_ids))
    }

def show_ai_insights_tab(df):
    """Monthly Comparison - Enhanced Analysis with Optional Jira Content"""
    st.header("Monthly Comparison Analysis")
    st.info("📊 Issue Category × Client Analysis - Uses ALL historical data (no 30-day restrictions)")
    
    # Month selection
    months = []
    try:
        df["Month-Year"] = pd.to_datetime(df["Date"]).dt.strftime("%b-%Y")
        months = sorted(df["Month-Year"].unique().tolist())
    except:
        st.error("Could not extract months from data")
        return
    
    if len(months) < 2:
        st.warning("Need at least 2 months of data for comparison analysis")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        current_month = st.selectbox("Current period:", months, index=len(months)-1, key="current_select")
    with col2:
        prev_options = [m for m in months if m != current_month]
        previous_month = st.selectbox("Comparison period:", prev_options, index=len(prev_options)-1, key="prev_select")
    
    # Check if Jira credentials are available in environment
    jira_email = os.environ.get("JIRA_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN")
    
    if jira_email and jira_token:
        st.info("🔧 Enhanced Analysis with Jira Content - Using configured credentials")
    else:
        with st.expander("🔧 Enhanced Analysis with Jira Content (Optional)", expanded=False):
            st.info("Provide Jira credentials to analyze actual ticket content for more specific insights")
            col1, col2 = st.columns(2)
            with col1:
                jira_email = st.text_input("Jira Email:", key="jira_email")
            with col2:
                jira_token = st.text_input("Jira API Token:", type="password", key="jira_token")
    
    # Analysis button
    if st.button("Generate Monthly Comparison Analysis", key="gen_button"):
        with st.spinner("Generating analysis..."):
            try:
                api_key = os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    st.error("⚠️ Gemini API key not found. Please add GOOGLE_API_KEY to Replit Secrets.")
                    return
                
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                
                # Filter data for selected periods
                current_data = df[df["Month-Year"] == current_month].copy()
                previous_data = df[df["Month-Year"] == previous_month].copy()
                
                st.info(f"Analyzing: {previous_month} ({len(previous_data)} tickets) vs {current_month} ({len(current_data)} tickets)")
                
                # Check if Jira credentials provided
                use_jira_content = bool(jira_email and jira_token)
                jira_content = None
                
                if use_jira_content:
                    # Extract Jira ticket IDs from current month data
                    jira_col = next((col for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "] 
                                    if col in current_data.columns), None)
                    
                    if jira_col:
                        jira_tickets = current_data[current_data[jira_col].notna() & (current_data[jira_col] != "")]
                        if not jira_tickets.empty:
                            ticket_ids = jira_tickets[jira_col].unique().tolist()
                            st.info(f"🔍 Fetching content from {len(ticket_ids)} Jira tickets...")
                            
                            jira_credentials = {
                                "url": "https://razorpay.atlassian.net",
                                "email": jira_email,
                                "api_token": jira_token
                            }
                            
                            jira_result = fetch_jira_ticket_content(ticket_ids, jira_credentials)
                            
                            if "error" not in jira_result and jira_result.get("success_count", 0) > 0:
                                jira_content = jira_result["ticket_data"]
                                success_count = jira_result.get("success_count", 0)
                                total_processed = jira_result.get("total_processed", 0)
                                st.success(f"✅ Retrieved content from {success_count}/{total_processed} tickets")
                                
                                # Filter out tickets with errors for analysis
                                valid_tickets = [t for t in jira_content if "error" not in t and (t.get("summary") or t.get("description"))]
                                if valid_tickets:
                                    jira_content = valid_tickets
                                    st.info(f"📋 Analyzing {len(valid_tickets)} tickets with content")
                                else:
                                    st.warning("⚠️ No valid ticket content found. Using statistical analysis only.")
                                    use_jira_content = False
                            else:
                                error_msg = jira_result.get('error', 'Unknown error')
                                st.warning(f"⚠️ Jira API error: {error_msg}. Using statistical analysis only.")
                                use_jira_content = False
                
                # Create enhanced analysis prompt
                if use_jira_content and jira_content:
                    # Create a summary of actual ticket content for analysis
                    ticket_summaries = []
                    for ticket in jira_content:
                        summary_text = f"Ticket {ticket['id']}: {ticket.get('summary', '')}"
                        if ticket.get('description'):
                            summary_text += f" | Description: {ticket['description'][:200]}..."
                        if ticket.get('comments'):
                            latest_comment = ticket['comments'][0] if ticket['comments'] else {}
                            comment_text = latest_comment.get('text', '')[:100]
                            if comment_text:
                                summary_text += f" | Latest Comment: {comment_text}..."
                        ticket_summaries.append(summary_text)
                    
                    # Enhanced prompt with actual Jira content analysis
                    prompt = f"""
                    You are a Senior Support Operations Analyst at Razorpay with deep technical knowledge of LoyaltyPro systems. Create a detailed analysis of {len(jira_content)} actual Jira tickets from {current_month}.

                    ACTUAL TICKET CONTENT ANALYSIS:
                    {chr(10).join(ticket_summaries)}

                    Based on the ACTUAL CONTENT above, create this analysis:

                    ## {current_month} Technical Root Cause Analysis

                    ### Volume Overview
                    | Metric | {previous_month} | {current_month} | Change |
                    |--------|------------------|-----------------|---------|
                    | Total Tickets | {len(previous_data)} | {len(current_data)} | {len(current_data) - len(previous_data)} |
                    | Analyzed Jira Tickets | N/A | {len(jira_content)} | +{len(jira_content)} |

                    ### Root Causes from Actual Ticket Content
                    | Issue Pattern | Specific Root Cause (from tickets) | Frequency | Technical Details |
                    |---------------|-----------------------------------|-----------|-------------------|

                    For each row above, extract ACTUAL technical issues mentioned in the ticket summaries, descriptions, or comments. Quote specific error messages, system names, or technical problems mentioned.

                    ### Key Technical Findings
                    * Quote specific technical issues found in ticket descriptions
                    * Reference actual error messages or system failures mentioned
                    * Identify patterns in the actual ticket content provided

                    ### Recommendations Based on Ticket Analysis
                    | Technical Issue | Root Cause (from tickets) | Recommendation |
                    |-----------------|---------------------------|----------------|

                    CRITICAL REQUIREMENTS:
                    1. Extract and quote ACTUAL technical details from the ticket content provided
                    2. Reference specific error messages, system names, or technical problems mentioned in tickets
                    3. Do NOT use generic technical knowledge - only use what's in the actual ticket data
                    4. If tickets mention specific systems, APIs, or errors, quote them directly
                    5. Group similar technical issues found in multiple tickets
                    """
                else:
                    # Fallback to enhanced statistical analysis with domain knowledge
                    try:
                        # Create cross-tabulations for enhanced analysis
                        current_cross = pd.crosstab(
                            current_data["Account name"] if "Account name" in current_data.columns else pd.Series(['Unknown']),
                            current_data["Issue Category"] if "Issue Category" in current_data.columns else pd.Series(['Unknown']),
                            margins=True
                        )
                        
                        previous_cross = pd.crosstab(
                            previous_data["Account name"] if "Account name" in previous_data.columns else pd.Series(['Unknown']),
                            previous_data["Issue Category"] if "Issue Category" in previous_data.columns else pd.Series(['Unknown']),
                            margins=True
                        )
                        
                        current_table = current_cross.reset_index().to_string(index=False)
                        previous_table = previous_cross.reset_index().to_string(index=False)
                        
                        # Calculate category changes
                        category_changes = {}
                        if "Issue Category" in current_data.columns and "Issue Category" in previous_data.columns:
                            categories_current = current_data["Issue Category"].value_counts()
                            categories_previous = previous_data["Issue Category"].value_counts()
                            
                            common_categories = set(categories_current.index).intersection(set(categories_previous.index))
                            
                            for cat in common_categories:
                                curr = categories_current.get(cat, 0)
                                prev = categories_previous.get(cat, 0)
                                change = curr - prev
                                category_changes[cat] = {
                                    "current": int(curr),
                                    "previous": int(prev),
                                    "change": int(change),
                                    "pct_change": round((change / max(1, prev)) * 100, 1) if prev > 0 else 0
                                }
                        
                        prompt = f"""
                        You are a Senior Support Operations Analyst at Razorpay with deep technical knowledge of LoyaltyPro systems. Create a month-over-month analysis comparing {previous_month} to {current_month} using statistical patterns and domain expertise.

                        [CURRENT MONTH DATA: {current_month}]
                        {current_table}
                        [/CURRENT MONTH DATA]

                        [PREVIOUS MONTH DATA: {previous_month}]
                        {previous_table}
                        [/PREVIOUS MONTH DATA]

                        [CATEGORY CHANGES]
                        {json.dumps(category_changes, indent=2)}
                        [/CATEGORY CHANGES]

                        # DOMAIN KNOWLEDGE: SPECIFIC ROOT CAUSES

                        ## Refund_Issue Technical Patterns:
                        - Failed Bookings Refund Loop: Payment captured but booking creation failed
                        - Ledger Timeout: Bank ledger systems (DBS Intellect, SBI) timing out during operations
                        - Voucher Code State Mismatch: Voucher marked as used but booking failed
                        - Points Transfer Failure: Failed loyalty points transfers due to reconciliation mismatches
                        - Yatra Integration State Handling: Booking state synchronization issues

                        ## Campaign_Issue Technical Patterns:
                        - SFTP Layer Failures: File transfer failures for bulk benefit distribution
                        - Renewal Date Detection: Credit card renewal information not received on time
                        - Concierge Voucher Retrigger: Manual voucher retriggering requests from bank teams
                        - DBS Vantage Card Renewal: Membership activation issues for Vantage renewals
                        - Voucher Distribution Race Condition: Pre-procured voucher bundles showing as redeemed

                        ## Client-Specific Patterns:
                        - DBS Bank: Intellect ledger timeouts, Vantage card processing pipeline issues
                        - SBI Aurum: Midnight batch processing, custom payment gateway integration issues
                        - HDFC Bank: Dual-ledger synchronization, PayZapp integration inconsistencies
                        - Kotak Mahindra Bank: 30-second API timeouts, weekend reconciliation issues

                        Create a comprehensive analysis:

                        ## {current_month} Ticket Count

                        | Account Name | Issue Category | Count |
                        |--------------|----------------|-------|
                        [Use actual data from cross-tabulation]

                        ## Volume Analysis
                        {current_month} shows {len(current_data)} tickets compared to {len(previous_data)} in {previous_month}, representing a {((len(current_data) - len(previous_data)) / max(1, len(previous_data)) * 100):.1f}% change.

                        ## Category Deep-Dive: [Select most significant category]
                        [Analyze the category with highest volume or change using domain knowledge]

                        | Issue Category | {previous_month} | {current_month} | Delta | % Change |
                        |----------------|------------------|-----------------|-------|----------|
                        [Fill with actual category data]

                        ### Technical Root Cause Analysis

                        | Issue Type | Most Likely Root Cause | Technical System | Recommendation |
                        |------------|------------------------|------------------|----------------|
                        [Use domain knowledge to map issue patterns to specific technical causes]

                        Based on the patterns observed, the primary technical issues likely involve [specific system components and integration points based on the data patterns].

                        REQUIREMENTS:
                        1. Use actual numbers from the data provided
                        2. Apply domain knowledge to infer most likely technical causes
                        3. Reference specific systems and integration points
                        4. Format all tables with markdown pipes (|)
                        """
                        
                    except Exception as e:
                        prompt = f"""
                        Analyze support ticket trends comparing {previous_month} ({len(previous_data)} tickets) to {current_month} ({len(current_data)} tickets).
                        
                        Provide insights about volume changes, potential technical patterns, and recommendations based on the data available.
                        Format analysis with clear sections and markdown tables.
                        """
                
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
                # Add download button
                st.download_button(
                    "Download Analysis Report",
                    response.text,
                    file_name=f"monthly_comparison_{previous_month}_vs_{current_month}.md",
                    mime="text/markdown",
                    key="download_monthly_analysis"
                )
            
            except Exception as e:
                st.error(f"Error generating analysis: {str(e)}")

def show_ticket_explorer_tab(df):
    """Display individual ticket explorer tab with both Jira and DevRev support"""
    st.header("Ticket Explorer")
    
    # Extract both Jira and DevRev tickets
    all_tickets = extract_all_tickets(df)
    jira_tickets = all_tickets['jira']
    devrev_tickets = all_tickets['devrev']
    total_tickets = all_tickets['total']
    
    if total_tickets == 0:
        st.warning("No tickets found in the dataset.")
        return
    
    # Display ticket statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Tickets", total_tickets)
    with col2:
        st.metric("Jira Tickets", len(jira_tickets))
    with col3:
        st.metric("DevRev Tickets", len(devrev_tickets))
    
    # Combine all tickets for selection
    all_ticket_list = jira_tickets + devrev_tickets
    
    # Create ticket options with enhanced display
    ticket_options = []
    for ticket_id in all_ticket_list:
        # Find the row containing this ticket
        ticket_row = None
        for _, row in df.iterrows():
            for col in df.columns:
                if ticket_id in str(row[col]):
                    ticket_row = row
                    break
            if ticket_row is not None:
                break
        
        if ticket_row is not None:
            client = ticket_row["Account name"] if "Account name" in ticket_row and pd.notna(ticket_row["Account name"]) else "Unknown"
            category = ticket_row["Issue Category"] if "Issue Category" in ticket_row and pd.notna(ticket_row["Issue Category"]) else "Unknown"
            ticket_type = "DevRev" if ticket_id in devrev_tickets else "Jira"
            display_text = f"{ticket_id} ({ticket_type}) - {client} - {category}"
            ticket_options.append((display_text, ticket_id))
    
    if not ticket_options:
        st.warning("No valid tickets found in dataset.")
        return
    
    # Search functionality
    st.subheader("Search and Analyze Tickets")
    search_term = st.text_input("Search for specific ticket ID or keywords:", key="explorer_search_input")
    
    if search_term:
        filtered_options = [(display, ticket_id) for display, ticket_id in ticket_options 
                          if search_term.upper() in display.upper()]
        if filtered_options:
            st.success(f"Found {len(filtered_options)} matching tickets")
        else:
            st.warning("No tickets match your search term")
            filtered_options = ticket_options
    else:
        filtered_options = ticket_options
    
    # Select ticket for analysis
    selected_display_text = st.selectbox(
        "Select a ticket to analyze:",
        options=[option[0] for option in filtered_options],
        key="explorer_ticket_selector"
    )
    
    # Get the selected ticket ID
    selected_ticket_id = next((option[1] for option in filtered_options if option[0] == selected_display_text), None)
    
    if selected_ticket_id:
        # Determine ticket type
        is_devrev = selected_ticket_id in devrev_tickets
        ticket_type = 'devrev' if is_devrev else 'jira'
        
        # Find the row with this ticket
        selected_ticket = None
        for _, row in df.iterrows():
            for col in df.columns:
                if selected_ticket_id in str(row[col]):
                    selected_ticket = row
                    break
            if selected_ticket is not None:
                break
        
        if selected_ticket is not None:
            st.subheader(f"Ticket Details: {selected_ticket_id}")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("CSV Ticket Data")
                
                # Display ticket information
                display_fields = [
                    "Account name", "Issue Category", "Issue Sub-category", 
                    "Date", "FD Ticket Status", "Priority"
                ]
                
                for field in display_fields:
                    if field in selected_ticket.index and pd.notna(selected_ticket[field]):
                        st.markdown(f"**{field}:** {selected_ticket[field]}")
                
                # Display ticket type
                st.markdown(f"**Ticket System:** {ticket_type.upper()}")
                
                # Try to fetch ticket data from appropriate system
                with st.spinner(f"Fetching {ticket_type.upper()} ticket details..."):
                    ticket_data, source = get_ticket_data(selected_ticket_id, ticket_type)
                    
                if ticket_data and source:
                    st.subheader(f"Additional {source.upper()} Information")
                    
                    if source == 'jira':
                        # Extract useful information from Jira response
                        fields = ticket_data.get('fields', {})
                        jira_info = {
                            "Summary": fields.get('summary', 'N/A'),
                            "Status": fields.get('status', {}).get('name', 'N/A'),
                            "Priority": fields.get('priority', {}).get('name', 'N/A'),
                            "Assignee": fields.get('assignee', {}).get('displayName', 'Unassigned') if fields.get('assignee') else 'Unassigned',
                            "Reporter": fields.get('reporter', {}).get('displayName', 'N/A') if fields.get('reporter') else 'N/A',
                            "Created": fields.get('created', 'N/A')[:10] if fields.get('created') else 'N/A',
                            "Updated": fields.get('updated', 'N/A')[:10] if fields.get('updated') else 'N/A'
                        }
                        
                        for key, value in jira_info.items():
                            st.markdown(f"**{key}:** {value}")
                        
                        # Add Jira link
                        jira_url = f"https://razorpay.atlassian.net/browse/{selected_ticket_id}"
                        st.markdown(f"[View original Jira ticket ↗]({jira_url})")
                        
                    elif source == 'devrev':
                        # Extract useful information from DevRev response
                        work = ticket_data.get('work', {})
                        devrev_info = {
                            "Title": work.get('title', 'N/A'),
                            "Status": work.get('stage', {}).get('name', 'N/A'),
                            "Priority": work.get('priority', 'N/A'),
                            "Assignee": work.get('owned_by', [{}])[0].get('display_name', 'Unassigned') if work.get('owned_by') else 'Unassigned',
                            "Created": work.get('created_date', 'N/A')[:10] if work.get('created_date') else 'N/A',
                            "Modified": work.get('modified_date', 'N/A')[:10] if work.get('modified_date') else 'N/A'
                        }
                        
                        for key, value in devrev_info.items():
                            st.markdown(f"**{key}:** {value}")
                        
                        # Add DevRev link if available
                        if work.get('id'):
                            st.markdown(f"[View original DevRev ticket ↗](https://app.devrev.ai/work/{work.get('id')})")
                else:
                    st.info(f"Could not fetch additional details from {ticket_type.upper()} API. Using CSV data only.")
            
            with col2:
                st.subheader("AI-Generated Ticket Summary")
                
                if st.button("Analyze This Ticket"):
                    with st.spinner("Generating AI analysis..."):
                        # Configure Gemini API
                        api_key = os.environ.get("GOOGLE_API_KEY")
                        if not api_key:
                            st.error("Gemini API key not found.")
                        else:
                            genai.configure(api_key=api_key)
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            
                            # Create ticket data for analysis
                            analysis_data = {
                                "ticket_id": selected_ticket_id,
                                "ticket_system": ticket_type.upper(),
                                "client": selected_ticket["Account name"] if "Account name" in selected_ticket and pd.notna(selected_ticket["Account name"]) else "Unknown",
                                "category": selected_ticket["Issue Category"] if "Issue Category" in selected_ticket and pd.notna(selected_ticket["Issue Category"]) else "Unknown",
                                "subcategory": selected_ticket["Issue Sub-category"] if "Issue Sub-category" in selected_ticket and pd.notna(selected_ticket["Issue Sub-category"]) else "Unknown",
                                "date": selected_ticket["Date"] if "Date" in selected_ticket and pd.notna(selected_ticket["Date"]) else "Unknown",
                                "status": selected_ticket["FD Ticket Status"] if "FD Ticket Status" in selected_ticket and pd.notna(selected_ticket["FD Ticket Status"]) else "Unknown",
                                "description": "Available from API data" if ticket_data else "Not available in CSV"
                            }
                            
                            # Enhanced individual ticket analysis prompt
                            prompt = f"""
                            You are a senior technical support analyst specializing in fintech systems, particularly payment and loyalty platforms. Analyze this LoyaltyPro support ticket comprehensively and provide expert-level insights.

                            [TICKET_INFO]
                            Ticket ID: {analysis_data['ticket_id']}
                            Ticket System: {analysis_data['ticket_system']}
                            Client: {analysis_data['client']}
                            Category: {analysis_data['category']}
                            Subcategory: {analysis_data['subcategory']}
                            Date: {analysis_data['date']}
                            Status: {analysis_data['status']}
                            Description: {analysis_data['description']}
                            [/TICKET_INFO]

                            Provide a detailed yet concise technical analysis with the following components:

                            1. **ISSUE DIAGNOSIS (3-4 sentences)**
                               - Precise technical description of the problem
                               - Identify the affected components or services in the LoyaltyPro ecosystem
                               - Specify any API endpoints, services, or data flows likely involved

                            2. **ROOT CAUSE DETERMINATION**
                               - Primary technical cause with 85%+ confidence
                               - Secondary contributing factors
                               - Whether this is likely a code-level issue, configuration problem, integration failure, or data inconsistency
                               - Specific technical components that failed or behaved unexpectedly

                            3. **RESOLUTION PATHWAY EVALUATION**
                               - Optimal technical solution approach
                               - Estimated resolution complexity (with justification)
                               - Necessary team involvement (Backend/Frontend/DevOps/Database)
                               - Resolution verification steps to ensure complete fix

                            4. **CLIENT-SPECIFIC CONTEXT**
                               - Whether this issue is unique to {analysis_data['client']} or common across clients
                               - Any specific client implementation details that may have contributed
                               - Historical context if this client has faced similar issues
                               - Business impact assessment specific to this client

                            5. **SYSTEM-WIDE IMPLICATIONS**
                               - Potential impact on other LoyaltyPro clients
                               - Relationship to known system vulnerabilities
                               - Early warning indicators for similar future issues
                               - Systemic changes needed to prevent recurrence

                            6. **TECHNICAL PREVENTATIVE MEASURES**
                               - Code-level improvements (be specific)
                               - Configuration adjustments
                               - Monitoring implementation details
                               - Testing procedures to catch this issue earlier

                            Format your response with clear headings and concise, technically precise bullet points. Include relevant technical terms specific to payment systems and loyalty platforms where appropriate.

                            Add a "TECHNICAL TAGS" section with 5-7 specific technical tags that could be used to categorize this ticket in a knowledge base.
                            """
                            
                            try:
                                response = model.generate_content(prompt)
                                st.markdown(response.text)
                            except Exception as e:
                                st.error(f"Error: {str(e)}")

def show_search_tab(df):
    """Display dedicated search functionality tab with working hyperlinks"""
    st.header("🔎 Advanced Ticket Search")
    
    # Display data scope information
    date_info = ""
    if "Date" in df.columns:
        try:
            min_date = df["Date"].min()
            max_date = df["Date"].max()
            date_info = f" from {min_date.strftime('%b %Y')} to {max_date.strftime('%b %Y')}"
        except:
            date_info = " (date range unavailable)"
    
    st.info(f"📊 Search across ALL historical data ({len(df)} tickets){date_info} - no date restrictions applied.")
    
    # Identify Jira ticket column
    jira_col = next((col for col in ["Jira ticket number if escalated to PSE", "Jira ticket number if escalated to PSE "] 
                     if col in df.columns), None)
    
    # Search input fields
    search_term = st.text_input("Search for specific ticket ID or keywords:", key="search_tab_main_input")
    
    # Search across all fields by default
    search_field = "All Fields"
    
    # Advanced Filters section
    with st.expander("Advanced Filters", expanded=True):
        filter_col1, filter_col2 = st.columns(2)
        
        with filter_col1:
            # Client filter if available
            selected_clients = []
            if "Account name" in df.columns:
                selected_clients = st.multiselect(
                    "Filter by Client:",
                    options=sorted(df["Account name"].unique().tolist()),
                    default=[],
                    key="search_tab_client_filter"
                )
            
            # Category filter if available
            selected_categories = []
            if "Issue Category" in df.columns:
                selected_categories = st.multiselect(
                    "Filter by Category:",
                    options=sorted(df["Issue Category"].unique().tolist()),
                    default=[],
                    key="search_tab_category_filter"
                )
        
        with filter_col2:
            # Date range if available
            date_range = None
            if "Date" in df.columns:
                try:
                    df["Date"] = pd.to_datetime(df["Date"])
                    min_date = df["Date"].min().date()
                    max_date = df["Date"].max().date()
                    
                    date_range = st.date_input(
                        "Filter by Date Range:",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key="search_tab_date_range"
                    )
                except Exception as e:
                    st.warning(f"Could not parse Date column: {str(e)}")
    
    # Apply search and filters
    filtered_df = df.copy()
    
    # Apply client filter
    if "Account name" in df.columns and selected_clients:
        filtered_df = filtered_df[filtered_df["Account name"].isin(selected_clients)]
    
    # Apply category filter
    if "Issue Category" in df.columns and selected_categories:
        filtered_df = filtered_df[filtered_df["Issue Category"].isin(selected_categories)]
    
    # Apply date filter
    if "Date" in filtered_df.columns and date_range and len(date_range) == 2:
        try:
            filtered_df = filtered_df[
                (filtered_df["Date"].dt.date >= date_range[0]) & 
                (filtered_df["Date"].dt.date <= date_range[1])
            ]
        except Exception as e:
            st.warning(f"Error applying date filter: {str(e)}")
    
    # Apply search term
    if search_term:
        if search_field == "All Fields":
            # Search across all columns
            filtered_df = filtered_df[
                filtered_df.astype(str).apply(
                    lambda row: row.str.contains(search_term, case=False).any(), 
                    axis=1
                )
            ]
        else:
            # Search in specific column
            filtered_df = filtered_df[
                filtered_df[search_field].astype(str).str.contains(search_term, case=False)
            ]
    
    # Display search results
    if filtered_df.empty:
        st.warning("No tickets match your search criteria")
    else:
        st.success(f"Found {len(filtered_df)} matching tickets")
        
        # Create a display dataframe with formatted hyperlinks
        display_df = filtered_df.copy()
        
        # Select columns to display
        display_cols = ["Date", "Account name", "Issue Category", "Issue Sub-category"]
        
        # Add Jira link column with properly formatted links
        if jira_col and jira_col in display_df.columns:
            # Create a new column with HTML hyperlinks
            display_df["Jira Link"] = display_df[jira_col].apply(
                lambda x: f'<a href="https://razorpay.atlassian.net/browse/{x}" target="_blank">{x}</a>' 
                if pd.notna(x) and x != "" else ""
            )
            display_cols.append("Jira Link")
        
        # Only include columns that actually exist
        display_cols = [col for col in display_cols if col in display_df.columns]
        
        # Sort by date if available
        if "Date" in display_cols:
            display_df = display_df.sort_values(by="Date", ascending=False)
        
        # Display as HTML with clickable links
        st.markdown("""
        <style>
        .dataframe-container th {
            text-align: left;
            background-color: #f0f2f6;
            padding: 8px;
        }
        .dataframe-container td {
            text-align: left;
            padding: 8px;
        }
        .dataframe-container tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Convert to HTML and display
        html_table = display_df[display_cols].to_html(
            escape=False, 
            index=False,
            classes='dataframe-container'
        )
        st.markdown(html_table, unsafe_allow_html=True)
        
        # Add download button for search results
        import io
        csv_buffer = io.StringIO()
        filtered_df.to_csv(csv_buffer, index=False)
        csv_str = csv_buffer.getvalue()
        
        st.download_button(
            label="Download Search Results as CSV",
            data=csv_str,
            file_name="ticket_search_results.csv",
            mime="text/csv"
        )
        
        # Add button to analyze filtered tickets
        if st.button("Generate AI Summary of Filtered Tickets", key="search_tab_ai_analysis"):
            analyze_filtered_tickets(filtered_df, jira_col)

def analyze_filtered_tickets(filtered_df, jira_col):
    """Generate AI summary for the filtered list of tickets"""
    with st.spinner("Analyzing filtered tickets with Gemini AI..."):
        try:
            # Get API key
            api_key = os.environ.get("GOOGLE_API_KEY") or st.secrets.get("GOOGLE_API_KEY", None)
            
            if not api_key:
                st.error("Gemini API key not found. Please add it to your Replit Secrets.")
                return
                
            # Configure Gemini
            genai.configure(api_key=api_key)
            
            # Try to use best available model
            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
            except:
                try:
                    model = genai.GenerativeModel('gemini-pro')
                except Exception as e:
                    st.error(f"Could not initialize Gemini model: {str(e)}")
                    return
            
            # Prepare ticket data for analysis
            ticket_data = []
            for _, ticket in filtered_df.iterrows():
                ticket_info = {
                    "ticket_id": ticket[jira_col] if jira_col in ticket and pd.notna(ticket[jira_col]) else "N/A",
                    "date": ticket["Date"].strftime("%Y-%m-%d") if "Date" in ticket and pd.notna(ticket["Date"]) else "N/A",
                    "client": ticket["Account name"] if "Account name" in ticket and pd.notna(ticket["Account name"]) else "N/A",
                    "category": ticket["Issue Category"] if "Issue Category" in ticket and pd.notna(ticket["Issue Category"]) else "N/A",
                    "subcategory": ticket["Issue Sub-category"] if "Issue Sub-category" in ticket and pd.notna(ticket["Issue Sub-category"]) else "N/A",
                    "status": ticket["FD Ticket Status"] if "FD Ticket Status" in ticket and pd.notna(ticket["FD Ticket Status"]) else "N/A",
                    "priority": ticket["Priority"] if "Priority" in ticket and pd.notna(ticket["Priority"]) else "N/A",
                    "jira_url": f"https://razorpay.atlassian.net/browse/{ticket[jira_col]}" if jira_col in ticket and pd.notna(ticket[jira_col]) else "N/A"
                }
                ticket_data.append(ticket_info)
            
            # Enhanced technical analysis prompt
            prompt = f"""
            You are a Senior Technical Support Analyst at Razorpay specializing in LoyaltyPro product. You're analyzing {len(ticket_data)} support tickets for a detailed technical report.

            I'm providing you with:
            1. Statistical data showing ticket counts by client and category
            2. A list of actual Jira tickets with their IDs that you can see in the data

            Your task is to analyze the tickets and provide SPECIFIC, DETAILED insights based on your technical expertise with payment systems, loyalty platforms, and banking integrations.

            [TICKET_DATA]
            {json.dumps(ticket_data, indent=2)}
            [/TICKET_DATA]

            Based on this data, create a detailed technical analysis with the following EXACT structure:

            ## Filtered Tickets Technical Analysis

            [CREATE MARKDOWN TABLE showing Account name × Issue Category counts]

            ## Root Cause Analysis

            [CREATE TABLE with columns: Issue Type, Root Cause, Frequency, Average Resolution Time]

            In the Root Cause column, provide SPECIFIC technical reasons like:
            - "Timeout in DBS Intellect ledger system during points transfer API calls"
            - "SFTP file transfer failure due to certificate expiration for AU Bank integration"
            - "Race condition in voucher allocation during high-volume campaign launch for HDFC"
            - "Payment gateway state mismatch with Yatra booking system for SBI transactions"

            NEVER use generic phrases like "requires further investigation" or "unknown cause" - you must provide specific technical root causes based on your expertise with these systems.

            ## Technical Details

            * [SPECIFIC technical insight about the most common issue pattern]
            * [SPECIFIC technical insight about client-specific integration problems]
            * [SPECIFIC technical insight about system bottlenecks or failure points]

            ## Recommended Solutions

            * [SPECIFIC technical recommendation with implementation details]
            * [SPECIFIC technical recommendation addressing the highest-volume issue]
            * [SPECIFIC technical recommendation for preventing recurring issues]

            ## Ticket References

            [CREATE TABLE with columns: Client, Category, Ticket IDs]
            - Display Ticket IDs as markdown links: [ID](https://razorpay.atlassian.net/browse/ID)
            - Combine multiple tickets for the same client+category on a single row
            - Use comma-separated ticket IDs when multiple tickets exist

            CRITICAL REQUIREMENTS:
            1. Use ONLY markdown tables with pipes (|)
            2. Provide SPECIFIC technical details for every issue - no generic placeholders
            3. Leverage your knowledge of payment systems, loyalty platforms, and banking integrations
            4. When identifying root causes, be precise about exact technical components that are failing
            5. Reference specific clients and categories from the data provided

            Your analysis should be so specific and technically precise that engineers could immediately understand and address the issues without needing additional investigation.
            """
            
            # Generate the analysis
            try:
                response = model.generate_content(prompt)
                
                # Display the results
                st.subheader("AI Analysis of Filtered Tickets")
                st.markdown(response.text)
                
                # Add option to download the analysis
                st.download_button(
                    label="Download Analysis as Markdown",
                    data=response.text,
                    file_name="filtered_tickets_analysis.md",
                    mime="text/markdown"
                )
            except Exception as e:
                st.error(f"Error generating analysis: {str(e)}")
        
        except Exception as e:
            st.error(f"Error processing tickets: {str(e)}")

if __name__ == "__main__":
    main()