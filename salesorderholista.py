import streamlit as st
import pandas as pd
import plotly.express as px
from ftp_data_loader import get_ftp_path, read_excel_from_ftp

# ---------------------------------------------------------------------------
# Formatting helpers (Indian format + short abbreviations)
# ---------------------------------------------------------------------------

def format_indian(num: float) -> str:
    if pd.isna(num):
        return "0"
    sign = "" if num >= 0 else "-"
    num = abs(int(num))
    if num == 0:
        return "0"
    s = str(num)
    if len(s) <= 3:
        return sign + s
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + ',' + result
        s = s[:-2]
    return sign + result


def format_number(num: float, currency: bool = False, short: bool = True) -> str:
    if pd.isna(num):
        return "0"
    num = float(num)
    absnum = abs(num)
    if short:
        if absnum >= 1e7:
            val = num / 1e7
            suffix = "Cr"
        elif absnum >= 1e5:
            val = num / 1e5
            suffix = "L"
        elif absnum >= 1e3:
            val = num / 1e3
            suffix = "K"
        else:
            formatted = format_indian(num)
            return f"₹ {formatted}" if currency else formatted
        formatted_val = f"{val:.2f}".rstrip('0').rstrip('.')
        return f"₹ {formatted_val}{suffix}" if currency else f"{formatted_val}{suffix}"
    else:
        formatted = format_indian(num)
        return f"₹ {formatted}" if currency else formatted


def format_quantity(qty: float) -> str:
    if pd.isna(qty):
        return "0"
    return format_number(qty, currency=False, short=True)


def format_cases_display(cases: float) -> str:
    # alias for backward compatibility
    return format_quantity(cases)

# ---------------------------------------------------------------------------


# 1. custom style
st.markdown(
    """
    <style>
    .reportview-container .main .block-container {padding: 1rem 2rem;}
    h1 {color: #4B8BBE; font-weight: 700;}
    .metric-value {font-size:1.8rem !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. Load Data
@st.cache_data
def load_data():
    remote_path = get_ftp_path("open_so")
    df = read_excel_from_ftp(remote_path)
    df['Posting Date'] = pd.to_datetime(df['Posting Date'])
    # State fallback: use Ship-To-State, fallback to Ship-to-city if blank
    df['Display_State'] = df['Ship-To-State'].fillna(df['Ship-to-city'])
    return df

df = load_data()

# 3. Sidebar Filters
st.sidebar.header("Filters")

# Date range filter
min_date = df['Posting Date'].min()
max_date = df['Posting Date'].max()
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# State filter using Display_State (Ship-To-State with fallback to Ship-to-city)
states = sorted(df['Display_State'].dropna().unique())
selected_states = st.sidebar.multiselect("Select Ship To State / City", options=states)

# Apply filters
if len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = df[(df['Posting Date'].dt.date >= start_date) & (df['Posting Date'].dt.date <= end_date)]
else:
    filtered_df = df

if selected_states:
    filtered_df = filtered_df[filtered_df['Display_State'].isin(selected_states)]
else:
    st.sidebar.warning("Please select one or more states/cities to view data")
    filtered_df = df.iloc[0:0]  # empty dataframe

# 4. KPIs
st.title("📊 Sales Analytics Dashboard")
col1, col2 = st.columns(2)
sales_val = filtered_df['LineTotalBeforeTax'].sum()
qty_total_cases = filtered_df['Qty in Cases/Bags'].sum()
col1.metric("Sales", format_number(sales_val, currency=True, short=True))
col2.metric("Total Cases", format_quantity(qty_total_cases))

# 5. Charts
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Sales Trend over Time")
    # Group by date for cleaner chart
    sales_trend = filtered_df.groupby('Posting Date')['LineTotalBeforeTax'].sum().reset_index()
    sales_trend['Formatted'] = sales_trend['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True))
    fig_trend = px.area(
        sales_trend,
        x='Posting Date',
        y='LineTotalBeforeTax',
        markers=True,
        template='plotly_white',
        title='Sales Trend',
        hover_data={'Formatted': True, 'LineTotalBeforeTax': False}
    )
    fig_trend.update_traces(line_color='#1f77b4', fill='tozeroy', hovertemplate='<b>Date:</b> %{x}<br><b>Sales:</b> %{customdata}<extra></extra>')
    fig_trend.update_layout(margin=dict(l=20,r=20,t=40,b=20), yaxis_title="Sales")
    st.plotly_chart(fig_trend, use_container_width=True)

with col_b:
    st.subheader("Top 10 Products by Cases")
    top_products = (
        filtered_df.groupby('ItemName')['Qty in Cases/Bags']
        .sum()
        .nlargest(10)
        .reset_index()
    )
    top_products = top_products.sort_values('Qty in Cases/Bags', ascending=True)
    top_products['Cases_Display'] = top_products['Qty in Cases/Bags'].apply(format_quantity)
    
    fig_prod = px.bar(
        top_products,
        x='Qty in Cases/Bags',
        y='ItemName',
        orientation='h',
        template='plotly_white',
        color_discrete_sequence=['#636EFA'] * len(top_products),
        title='Top 10 Products by Cases',
        hover_data={'Cases_Display': True, 'Qty in Cases/Bags': False}
    )
    # Add value labels on bars
    fig_prod.update_traces(
        marker_line_width=0,
        text=top_products['Cases_Display'],
        textposition='auto',
        hovertemplate='<b>Product:</b> %{y}<br><b>Cases:</b> %{customdata}<extra></extra>'
    )
    fig_prod.update_layout(
        margin=dict(l=20,r=20,t=40,b=20),
        xaxis_title="Cases",
        height=500,
        yaxis={'tickfont': {'size': 11}}
    )
    st.plotly_chart(fig_prod, use_container_width=True)

# 5.1 Top 3 BP Names
st.subheader("Top 3 Business Partners by Sales")
top_bp = (
    filtered_df.groupby('BP Name')['LineTotalBeforeTax']
    .sum()
    .nlargest(3)
    .reset_index()
)
if not top_bp.empty:
    top_bp['Formatted'] = top_bp['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True))
    fig_bp = px.bar(
        top_bp,
        x='LineTotalBeforeTax',
        y='BP Name',
        orientation='h',
        template='plotly_white',
        color='LineTotalBeforeTax',
        color_continuous_scale='Greens',
        title='Top 3 Business Partners',
        hover_data={'Formatted': True, 'LineTotalBeforeTax': False}
    )
    fig_bp.update_traces(marker_line_width=0, hovertemplate='<b>Partner:</b> %{y}<br><b>Sales:</b> %{customdata}<extra></extra>')
    fig_bp.update_layout(margin=dict(l=20,r=20,t=40,b=20), xaxis_title="Sales")
    st.plotly_chart(fig_bp, use_container_width=True)
else:
    st.write("No business partner data available.")

# 6. Data View
st.subheader("Detailed Data View")
# display filtered data with specified columns
if not filtered_df.empty:
    df_display = filtered_df.copy()
    # rename for display
    df_display = df_display.rename(columns={'Qty in Cases/Bags': 'Cases', 'BP Name': 'Distributor / Customer'})
    # Format currency in Lakhs and quantity with conditional K/L format
    df_display['Sales (Lakhs)'] = df_display['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True) if pd.notna(x) else "₹ 0")
    df_display['Cases'] = df_display['Cases'].apply(lambda x: format_quantity(x) if pd.notna(x) else "0")
    display_cols = [
        'Posting Date',
        'Distributor / Customer',
        'Display_State',
        'Cases',
        'Sales (Lakhs)'
    ]
    display_cols = [c for c in display_cols if c in df_display.columns]
    st.dataframe(df_display[display_cols], use_container_width=True)
else:
    st.write("No data to display. Adjust filters above.")