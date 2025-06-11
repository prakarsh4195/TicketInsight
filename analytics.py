import pandas as pd
import plotly.express as px

def generate_crosstab(df, dim1, dim2):
    """Generate a crosstab between two dimensions."""
    try:
        crosstab = pd.crosstab(
            df[dim1], 
            df[dim2],
            margins=True, 
            margins_name="Total"
        )
        return crosstab
    except Exception as e:
        print(f"Error generating crosstab: {str(e)}")
        return None

def create_heatmap(crosstab_df, dim1, dim2):
    """Create a heatmap visualization from a crosstab."""
    # Remove the "Total" row and column for visualization
    plot_df = crosstab_df.drop('Total', axis=0).drop('Total', axis=1) if 'Total' in crosstab_df.index and 'Total' in crosstab_df.columns else crosstab_df
    
    fig = px.imshow(
        plot_df, 
        labels=dict(x=dim2, y=dim1, color="Count"),
        text_auto=True,
        aspect="auto",
        color_continuous_scale="Viridis"
    )
    
    fig.update_layout(
        height=600,
        margin=dict(l=50, r=50, t=30, b=50),
    )
    
    return fig

def create_bar_chart(df, dim1, dim2):
    """Create a stacked bar chart from two dimensions."""
    plot_data = df.groupby([dim1, dim2]).size().reset_index(name='Count')
    
    fig = px.bar(
        plot_data,
        x=dim1,
        y="Count",
        color=dim2,
        barmode="stack",
        height=500
    )
    
    return fig

def create_time_series(df, time_col, dimension, count_col='Count'):
    """Create a time series analysis."""
    fig = px.line(
        df,
        x=time_col,
        y=count_col,
        color=dimension,
        markers=True,
        height=500
    )
    
    return fig