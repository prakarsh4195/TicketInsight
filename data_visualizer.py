import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime, timedelta

class DataVisualizer:
    """
    Data visualization module using Plotly for interactive charts and graphs.
    Handles various chart types for support analytics and executive dashboards.
    """
    
    # Color palette for consistent theming
    RAZORPAY_COLORS = {
        'primary': '#528FF0',
        'secondary': '#7B68EE',
        'success': '#28a745',
        'warning': '#ffc107',
        'danger': '#dc3545',
        'info': '#17a2b8'
    }
    
    # Client-specific color mapping
    CLIENT_COLORS = {
        'AU Bank': '#FF6B6B',
        'Axis': '#4ECDC4',
        'DBS Bank': '#45B7D1',
        'Extraordinary Weekends': '#96CEB4',
        'Fi Money': '#FECA57',
        'HDFC Bank': '#FF9FF3',
        'IDFC FIRST Bank': '#54A0FF',
        'Jana Bank': '#5F27CD',
        'Kotak Mahindra Bank': '#00D2D3',
        'SBI Aurum': '#FF6348'
    }
    
    def __init__(self):
        """Initialize the data visualizer."""
        pass
    
    def create_client_distribution(self, df: pd.DataFrame) -> go.Figure:
        """
        Create client distribution chart.
        
        Args:
            df: DataFrame with client data
            
        Returns:
            Plotly figure object
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
                return self._create_empty_chart("No client data found")
            
            # Count clients
            client_counts = df[client_col].value_counts()
            
            # Create colors for clients
            colors = [self.CLIENT_COLORS.get(client, self.RAZORPAY_COLORS['primary']) 
                     for client in client_counts.index]
            
            # Create bar chart
            fig = go.Figure(data=[
                go.Bar(
                    x=client_counts.index,
                    y=client_counts.values,
                    marker_color=colors,
                    text=client_counts.values,
                    textposition='auto',
                )
            ])
            
            fig.update_layout(
                title='Support Tickets by Client',
                xaxis_title='Client',
                yaxis_title='Number of Tickets',
                showlegend=False,
                height=400
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating client distribution chart: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_time_series_analysis(self, df: pd.DataFrame, grouping: str = 'weekly') -> go.Figure:
        """
        Create time series analysis chart.
        
        Args:
            df: DataFrame with time data
            grouping: Time grouping ('daily', 'weekly', 'monthly')
            
        Returns:
            Plotly figure object
        """
        try:
            # Find date column
            date_columns = ['Date', 'Created Date', 'date', 'created_date', 'Resolved Date']
            date_col = None
            
            for col in date_columns:
                if col in df.columns:
                    date_col = col
                    break
            
            if not date_col:
                return self._create_empty_chart("No date data found")
            
            # Convert to datetime
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df_clean = df.dropna(subset=[date_col])
            
            if df_clean.empty:
                return self._create_empty_chart("No valid date data")
            
            # Group by time period
            if grouping == 'daily':
                df_clean['period'] = df_clean[date_col].dt.date
                title_suffix = 'Daily'
            elif grouping == 'weekly':
                df_clean['period'] = df_clean[date_col].dt.to_period('W').dt.start_time
                title_suffix = 'Weekly'
            else:  # monthly
                df_clean['period'] = df_clean[date_col].dt.to_period('M').dt.start_time
                title_suffix = 'Monthly'
            
            # Count tickets by period
            time_counts = df_clean.groupby('period').size().reset_index(name='count')
            
            # Create line chart
            fig = go.Figure(data=[
                go.Scatter(
                    x=time_counts['period'],
                    y=time_counts['count'],
                    mode='lines+markers',
                    marker_color=self.RAZORPAY_COLORS['primary'],
                    line=dict(width=3),
                    marker=dict(size=8)
                )
            ])
            
            fig.update_layout(
                title=f'Support Tickets Trend ({title_suffix})',
                xaxis_title='Time Period',
                yaxis_title='Number of Tickets',
                showlegend=False,
                height=400
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating time series chart: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_status_distribution(self, df: pd.DataFrame) -> go.Figure:
        """
        Create status distribution pie chart.
        
        Args:
            df: DataFrame with status data
            
        Returns:
            Plotly figure object
        """
        try:
            if 'status' not in df.columns:
                return self._create_empty_chart("No status data found")
            
            status_counts = df['status'].value_counts()
            
            # Create pie chart
            fig = go.Figure(data=[
                go.Pie(
                    labels=status_counts.index,
                    values=status_counts.values,
                    hole=0.3,
                    marker_colors=[
                        self.RAZORPAY_COLORS['success'] if 'Done' in status else
                        self.RAZORPAY_COLORS['warning'] if 'Progress' in status else
                        self.RAZORPAY_COLORS['info'] if 'Open' in status else
                        self.RAZORPAY_COLORS['danger']
                        for status in status_counts.index
                    ]
                )
            ])
            
            fig.update_layout(
                title='Ticket Status Distribution',
                height=400,
                showlegend=True
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating status distribution chart: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_priority_analysis(self, df: pd.DataFrame) -> go.Figure:
        """
        Create priority analysis chart.
        
        Args:
            df: DataFrame with priority data
            
        Returns:
            Plotly figure object
        """
        try:
            if 'priority' not in df.columns:
                return self._create_empty_chart("No priority data found")
            
            priority_counts = df['priority'].value_counts()
            
            # Define priority colors
            priority_colors = {
                'Highest': self.RAZORPAY_COLORS['danger'],
                'High': '#FF6B6B',
                'Medium': self.RAZORPAY_COLORS['warning'],
                'Low': self.RAZORPAY_COLORS['success'],
                'Lowest': '#95E1D3'
            }
            
            colors = [priority_colors.get(priority, self.RAZORPAY_COLORS['primary']) 
                     for priority in priority_counts.index]
            
            # Create horizontal bar chart
            fig = go.Figure(data=[
                go.Bar(
                    x=priority_counts.values,
                    y=priority_counts.index,
                    orientation='h',
                    marker_color=colors,
                    text=priority_counts.values,
                    textposition='auto'
                )
            ])
            
            fig.update_layout(
                title='Ticket Priority Distribution',
                xaxis_title='Number of Tickets',
                yaxis_title='Priority Level',
                showlegend=False,
                height=400
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating priority analysis chart: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_root_cause_distribution(self, root_causes: Dict[str, int]) -> go.Figure:
        """
        Create root cause distribution chart.
        
        Args:
            root_causes: Dictionary with root cause counts
            
        Returns:
            Plotly figure object
        """
        try:
            if not root_causes:
                return self._create_empty_chart("No root cause data available")
            
            # Sort by count
            sorted_causes = dict(sorted(root_causes.items(), key=lambda x: x[1], reverse=True))
            
            # Create bar chart
            fig = go.Figure(data=[
                go.Bar(
                    x=list(sorted_causes.keys()),
                    y=list(sorted_causes.values()),
                    marker_color=self.RAZORPAY_COLORS['secondary'],
                    text=list(sorted_causes.values()),
                    textposition='auto'
                )
            ])
            
            fig.update_layout(
                title='Root Cause Categories Distribution',
                xaxis_title='Category',
                yaxis_title='Number of Issues',
                showlegend=False,
                height=400,
                xaxis={'tickangle': 45}
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating root cause distribution chart: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_client_category_matrix(self, df: pd.DataFrame) -> go.Figure:
        """
        Create client × category matrix heatmap.
        
        Args:
            df: DataFrame with client and category data
            
        Returns:
            Plotly figure object
        """
        try:
            # Find client and category columns
            client_col = None
            category_col = None
            
            client_columns = ['Client', 'client', 'Client Name', 'client_name']
            for col in client_columns:
                if col in df.columns:
                    client_col = col
                    break
            
            category_columns = ['Category', 'category', 'Issue Type', 'issue_type', 'Type']
            for col in category_columns:
                if col in df.columns:
                    category_col = col
                    break
            
            if not client_col or not category_col:
                return self._create_empty_chart("Client or category data not found")
            
            # Create pivot table
            pivot_data = pd.crosstab(df[client_col], df[category_col])
            
            # Create heatmap
            fig = go.Figure(data=go.Heatmap(
                z=pivot_data.values,
                x=pivot_data.columns,
                y=pivot_data.index,
                colorscale='Blues',
                text=pivot_data.values,
                texttemplate="%{text}",
                textfont={"size": 10},
                hoverongaps=False
            ))
            
            fig.update_layout(
                title='Client × Category Matrix',
                xaxis_title='Category',
                yaxis_title='Client',
                height=500
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating client category matrix: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def create_executive_trends(self, df: pd.DataFrame, grouping: str = 'weekly') -> go.Figure:
        """
        Create executive-level trend analysis with multiple metrics.
        
        Args:
            df: DataFrame with data
            grouping: Time grouping
            
        Returns:
            Plotly figure object
        """
        try:
            # Find date column
            date_columns = ['Date', 'Created Date', 'date', 'created_date']
            date_col = None
            
            for col in date_columns:
                if col in df.columns:
                    date_col = col
                    break
            
            if not date_col:
                return self._create_empty_chart("No date data for trends")
            
            # Convert to datetime
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df_clean = df.dropna(subset=[date_col])
            
            if df_clean.empty:
                return self._create_empty_chart("No valid date data")
            
            # Group by time period
            if grouping == 'daily':
                df_clean['period'] = df_clean[date_col].dt.date
            elif grouping == 'weekly':
                df_clean['period'] = df_clean[date_col].dt.to_period('W').dt.start_time
            else:  # monthly
                df_clean['period'] = df_clean[date_col].dt.to_period('M').dt.start_time
            
            # Calculate metrics by period
            metrics = df_clean.groupby('period').agg({
                date_col: 'count',  # Total tickets
            }).rename(columns={date_col: 'total_tickets'})
            
            # Add escalation rate if Jira data available
            if any('jira' in col.lower() for col in df_clean.columns):
                # Find Jira column
                jira_col = None
                for col in df_clean.columns:
                    if 'jira' in col.lower():
                        jira_col = col
                        break
                
                if jira_col:
                    escalated = df_clean.groupby('period')[jira_col].apply(
                        lambda x: x.notna().sum()
                    )
                    metrics['escalated_tickets'] = escalated
                    metrics['escalation_rate'] = (metrics['escalated_tickets'] / metrics['total_tickets'] * 100).fillna(0)
            
            # Create subplot
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Ticket Volume Trend', 'Escalation Rate Trend'),
                vertical_spacing=0.1
            )
            
            # Add ticket volume
            fig.add_trace(
                go.Scatter(
                    x=metrics.index,
                    y=metrics['total_tickets'],
                    mode='lines+markers',
                    name='Total Tickets',
                    line=dict(color=self.RAZORPAY_COLORS['primary'], width=3),
                    marker=dict(size=8)
                ),
                row=1, col=1
            )
            
            # Add escalation rate if available
            if 'escalation_rate' in metrics.columns:
                fig.add_trace(
                    go.Scatter(
                        x=metrics.index,
                        y=metrics['escalation_rate'],
                        mode='lines+markers',
                        name='Escalation Rate (%)',
                        line=dict(color=self.RAZORPAY_COLORS['warning'], width=3),
                        marker=dict(size=8)
                    ),
                    row=2, col=1
                )
            
            fig.update_layout(
                title='Executive Dashboard - Key Trends',
                height=600,
                showlegend=True
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating executive trends: {str(e)}")
            return self._create_empty_chart("Error creating chart")
    
    def generate_executive_insights(self, df: pd.DataFrame) -> List[str]:
        """
        Generate executive insights from data analysis.
        
        Args:
            df: DataFrame with support data
            
        Returns:
            List of insight strings
        """
        insights = []
        
        try:
            total_tickets = len(df)
            
            # Client insights
            client_col = None
            client_columns = ['Client', 'client', 'Client Name', 'client_name']
            for col in client_columns:
                if col in df.columns:
                    client_col = col
                    break
            
            if client_col:
                client_counts = df[client_col].value_counts()
                top_client = client_counts.index[0]
                top_client_pct = (client_counts.iloc[0] / total_tickets) * 100
                insights.append(f"{top_client} generates {top_client_pct:.1f}% of all support tickets")
                
                if len(client_counts) > 1:
                    active_clients = len(client_counts)
                    insights.append(f"Support activity across {active_clients} active clients")
            
            # Time-based insights
            date_columns = ['Date', 'Created Date', 'date', 'created_date']
            for col in date_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                        date_range = df[col].max() - df[col].min()
                        insights.append(f"Data spans {date_range.days} days of support operations")
                        break
                    except:
                        continue
            
            # Escalation insights
            jira_columns = [col for col in df.columns if 'jira' in col.lower()]
            if jira_columns:
                jira_col = jira_columns[0]
                escalated_count = df[jira_col].notna().sum()
                escalation_rate = (escalated_count / total_tickets) * 100
                insights.append(f"Escalation rate: {escalation_rate:.1f}% ({escalated_count} out of {total_tickets} tickets)")
                
                if escalation_rate > 20:
                    insights.append("High escalation rate indicates potential process improvement opportunities")
                elif escalation_rate < 5:
                    insights.append("Low escalation rate suggests effective first-line support")
            
            # Volume insights
            if total_tickets > 1000:
                insights.append("High ticket volume indicates active user base but may require process optimization")
            elif total_tickets < 100:
                insights.append("Low ticket volume suggests effective self-service or stable product")
            
            return insights
            
        except Exception as e:
            st.error(f"Error generating insights: {str(e)}")
            return ["Unable to generate insights from current data"]
    
    def _create_empty_chart(self, message: str) -> go.Figure:
        """
        Create empty chart with message.
        
        Args:
            message: Message to display
            
        Returns:
            Empty Plotly figure
        """
        fig = go.Figure()
        
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            xanchor='center', yanchor='middle',
            showarrow=False,
            font=dict(size=16, color="gray")
        )
        
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            height=400
        )
        
        return fig
    
    def create_resolution_time_analysis(self, df: pd.DataFrame) -> go.Figure:
        """
        Create resolution time analysis chart.
        
        Args:
            df: DataFrame with resolution time data
            
        Returns:
            Plotly figure object
        """
        try:
            if 'resolution_time_hours' not in df.columns:
                return self._create_empty_chart("No resolution time data available")
            
            # Filter valid resolution times
            resolution_data = df[df['resolution_time_hours'].notna() & (df['resolution_time_hours'] > 0)]
            
            if resolution_data.empty:
                return self._create_empty_chart("No valid resolution time data")
            
            # Convert hours to days for better readability
            resolution_data = resolution_data.copy()
            resolution_data['resolution_time_days'] = resolution_data['resolution_time_hours'] / 24
            
            # Create histogram
            fig = go.Figure(data=[
                go.Histogram(
                    x=resolution_data['resolution_time_days'],
                    nbinsx=20,
                    marker_color=self.RAZORPAY_COLORS['info'],
                    opacity=0.7
                )
            ])
            
            # Add average line
            avg_resolution = resolution_data['resolution_time_days'].mean()
            fig.add_vline(
                x=avg_resolution,
                line_dash="dash",
                line_color=self.RAZORPAY_COLORS['danger'],
                annotation_text=f"Avg: {avg_resolution:.1f} days"
            )
            
            fig.update_layout(
                title='Resolution Time Distribution',
                xaxis_title='Resolution Time (Days)',
                yaxis_title='Number of Tickets',
                height=400
            )
            
            return fig
            
        except Exception as e:
            st.error(f"Error creating resolution time analysis: {str(e)}")
            return self._create_empty_chart("Error creating chart")
