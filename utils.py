import pandas as pd
import plotly.express as px

def detect_date_format(df, date_column):
    """Detect and convert date format."""
    try:
        df[date_column] = pd.to_datetime(df[date_column])
        return df
    except Exception:
        try:
            # Try with dayfirst for DD/MM/YYYY format
            df[date_column] = pd.to_datetime(df[date_column], dayfirst=True)
            return df
        except Exception:
            # Return original dataframe if conversion fails
            return df

def clean_column_names(df):
    """Clean column names by trimming whitespace."""
    df.columns = df.columns.str.strip()
    return df

def format_large_number(num):
    """Format large numbers with commas."""
    return f"{num:,}"

def get_jira_ticket_column(df):
    """Find the Jira ticket column in the dataframe."""
    possible_columns = [
        "Jira ticket number if escalated to PSE", 
        "Jira ticket number if escalated to PSE ",
        "Jira Ticket Number",
        "JIRA Ticket Number"
    ]
    
    for col in possible_columns:
        if col in df.columns:
            return col
    
    return None

def preprocess_dataframe(df):
    """Perform initial preprocessing on the dataframe."""
    # Clean column names
    df = clean_column_names(df)
    
    # Convert date columns if they exist
    date_columns = ["Date", "First response sent time", "JIRA created time"]
    for col in date_columns:
        if col in df.columns:
            df = detect_date_format(df, col)
    
    return df