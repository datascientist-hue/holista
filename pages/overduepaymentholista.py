"""
Overdue Payment Dashboard Module
Displays aged receivables analysis
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from ftp_data_loader import get_ftp_path, read_excel_from_ftp

def format_indian(num: float) -> str:
    """Format a number using Indian numbering system with commas."""
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
    """Universal formatter for numbers with K/L/Cr abbreviation."""
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


@st.cache_data
def load_overdue_payment_data():
    """Load overdue payment data from FTP."""
    remote_path = get_ftp_path("overdue")
    df = read_excel_from_ftp(remote_path)
    return df


def display_overdue_payment_dashboard():
    """Main dashboard for Overdue Payments."""
    st.title("💰 Overdue Payment Analysis")
    
    df = load_overdue_payment_data()
    
    if df.empty:
        st.warning("No data available in Overdue Payment file.")
        return
    
    # Ensure numeric columns
    aging_cols = ['0 To 10 Days', '11 To 25 Days', '26 To 45 Days', 
                  '46 To 60 Days', '61 To 90 Days', '91 To 120 Days', '121 Days and above']
    
    # Find actual column names by stripping whitespace (Excel often has trailing spaces)
    df.columns = df.columns.str.strip()
    actual_aging_cols = []
    for col_name in aging_cols:
        if col_name in df.columns:
            actual_aging_cols.append(col_name)
        elif col_name.strip() in df.columns:
            actual_aging_cols.append(col_name.strip())
    
    aging_cols = actual_aging_cols if actual_aging_cols else aging_cols
    
    for col in aging_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    if 'Balance/G.Total' in df.columns:
        df['Balance/G.Total'] = pd.to_numeric(df['Balance/G.Total'], errors='coerce').fillna(0)
    
    # KPI Calculations
    total_outstanding = df['Balance/G.Total'].sum() if 'Balance/G.Total' in df.columns else 0
    # build base customer set with positive balance
    if 'Balance/G.Total' in df.columns:
        cust_df = df[df['Balance/G.Total'] > 0][['BP Code', 'BP Name']].drop_duplicates()
        total_customers = len(cust_df)
    else:
        cust_df = pd.DataFrame(columns=['BP Code','BP Name'])
        total_customers = 0
    days_90_plus = (df['91 To 120 Days'].sum() + df['121 Days and above'].sum()) if all(col in df.columns for col in ['91 To 120 Days', '121 Days and above']) else 0
    avg_outstanding = total_outstanding / total_customers if total_customers > 0 else 0
    
    # Display KPI Cards
    st.markdown("---")
    st.subheader("📊 Overview Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Outstanding", format_number(total_outstanding, currency=True, short=True))
    c2.metric("Total Customers", f"{total_customers}")
    c3.metric("90+ Days Outstanding", format_number(days_90_plus, currency=True, short=True))
    c4.metric("Avg Outstanding/Customer", format_number(avg_outstanding, currency=True, short=True))
    
    # Aging Distribution Chart
    if aging_cols and all(col in df.columns for col in aging_cols):
        st.markdown("---")
        st.subheader("📈 Aging Distribution")
        st.caption("Outstanding amounts distributed across aging buckets")
        
        # Prepare data for bar chart - aggregate each aging bucket
        aging_data = []
        for col in aging_cols:
            bucket_amount = df[col].sum()
            aging_data.append({
                'Bucket': col,
                'Amount': bucket_amount
            })
        
        aging_melted = pd.DataFrame(aging_data)
        
        # Create custom format for text labels
        aging_melted['Formatted'] = aging_melted['Amount'].apply(lambda x: format_number(x, currency=True, short=True))
        
        fig_aging = px.bar(
            aging_melted,
            x='Bucket',
            y='Amount',
            title='Outstanding Amount by Aging Bucket',
            labels={'Amount': 'Outstanding Amount', 'Bucket': 'Aging Bucket'},
            color_discrete_sequence=['#636EFA']  # uniform blue color
        )
        
        # Update traces with formatted text
        fig_aging.update_traces(
            text=aging_melted['Formatted'],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Amount: %{customdata}<extra></extra>',
            customdata=aging_melted['Formatted']
        )
        
        fig_aging.update_layout(
            xaxis_title="Aging Bucket",
            yaxis_title="Outstanding Amount",
            height=400,
            hovermode='x unified',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig_aging, use_container_width=True)
    else:
        st.warning("⚠️ Aging bucket columns not found in data. Check Excel sheet column names.")
    
    # Top Overdue Customers
    st.markdown("---")
    st.subheader(" Top Overdue Customers")
    st.caption("Customers with highest outstanding amounts")
    
    if 'Balance/G.Total' in df.columns and 'BP Name' in df.columns:
        top_customers = df.nlargest(10, 'Balance/G.Total')[['BP Name', 'Balance/G.Total']].reset_index(drop=True)
        
        fig_top = px.bar(
            top_customers,
            y='BP Name',
            x='Balance/G.Total',
            orientation='h',
            title='Top 10 Customers by Outstanding',
            text='Balance/G.Total',
            labels={'Balance/G.Total': 'Outstanding Amount'},
            color='Balance/G.Total',
            color_continuous_scale='Reds'
        )
        fig_top.update_traces(
            textposition='auto',
            texttemplate='%{customdata}',
            customdata=top_customers['Balance/G.Total'].apply(lambda x: format_number(x, currency=True, short=True))
        )
        fig_top.update_layout(
            xaxis_title="Outstanding Amount",
            yaxis_title="Customer",
            height=400,
            margin=dict(l=200, r=20, t=40, b=60),
            coloraxis_showscale=False,
            hovermode='y unified'
        )
        st.plotly_chart(fig_top, use_container_width=True)
    
    # High-Risk Customers (61+ days)
    st.markdown("---")
    st.subheader("⚠️ High-Risk Customers (61+ Days Outstanding)")
    st.caption("Customers with amounts in 61-90, 91-120, or 121+ days buckets")
    
    if all(col in df.columns for col in ['BP Code', 'BP Name', '61 To 90 Days', '91 To 120 Days', '121 Days and above', 'Balance/G.Total']):
        df['High_Risk_Amount'] = df['61 To 90 Days'] + df['91 To 120 Days'] + df['121 Days and above']
        high_risk = df[df['High_Risk_Amount'] > 0][['BP Code', 'BP Name', '61 To 90 Days', '91 To 120 Days', '121 Days and above', 'Balance/G.Total', 'High_Risk_Amount']].copy()
        # intersect with active customer base
        if not cust_df.empty:
            high_risk = high_risk.merge(cust_df, on=['BP Code', 'BP Name'])
        high_risk = high_risk.sort_values('High_Risk_Amount', ascending=False)
        
        # Count high-risk customers (after intersection)
        high_risk_count = len(high_risk)
        st.metric("High-Risk Customers", f"{high_risk_count}", f"Total at-risk outstanding: {format_number(high_risk['Balance/G.Total'].sum(), currency=True, short=True)}")
        
        if not high_risk.empty:
            # Format display columns
            df_display = high_risk[['BP Code', 'BP Name', '61 To 90 Days', '91 To 120 Days', '121 Days and above', 'Balance/G.Total']].copy()
            
            # Apply formatting
            for col in ['61 To 90 Days', '91 To 120 Days', '121 Days and above', 'Balance/G.Total']:
                df_display[col] = df_display[col].apply(lambda x: format_number(x, currency=True, short=True))
            
            # Rename columns for display
            df_display = df_display.rename(columns={
                'BP Code': 'Code',
                'BP Name': 'Customer',
                '61 To 90 Days': '61-90 Days',
                '91 To 120 Days': '91-120 Days',
                '121 Days and above': '121+ Days',
                'Balance/G.Total': 'Total Outstanding'
            })
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No customers with 61+ days outstanding!")
    
    # Collection Priority List - 121+ Days
    st.markdown("---")
    st.subheader("🚨 Collection Priority List (121+ Days Outstanding)")
    st.caption("Immediate action required - oldest outstanding dues")
    
    if all(col in df.columns for col in ['BP Code', 'BP Name', '121 Days and above', 'Balance/G.Total']):
        # Filter: 121+ Days > 0 AND Balance/G.Total > 0
        priority_customers = df[(df['121 Days and above'] > 0) & (df['Balance/G.Total'] > 0)][['BP Code', 'BP Name', '121 Days and above', 'Balance/G.Total']].copy()
        priority_customers = priority_customers.sort_values('Balance/G.Total', ascending=False)
        
        # Count and total
        priority_count = len(priority_customers)
        priority_total = priority_customers['121 Days and above'].sum()
        
        col1, col2 = st.columns(2)
        col1.metric("Customers with 121+ Days", f"{priority_count}")
        col2.metric("Total 121+ Days Amount", format_number(priority_total, currency=True, short=True))
        
        if not priority_customers.empty:
            # Format display columns
            df_priority = priority_customers[['BP Code', 'BP Name', '121 Days and above', 'Balance/G.Total']].copy()
            
            # Add a priority index
            df_priority.insert(0, 'Priority', range(1, len(df_priority) + 1))
            
            # Apply formatting
            for col in ['121 Days and above', 'Balance/G.Total']:
                df_priority[col] = df_priority[col].apply(lambda x: format_number(x, currency=True, short=True))
            
            # Rename columns for display
            df_priority = df_priority.rename(columns={
                'BP Code': 'Code',
                'BP Name': 'Customer',
                '121 Days and above': 'Days 121+ Amount',
                'Balance/G.Total': 'Total Outstanding'
            })
            
            st.dataframe(df_priority, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No customers with 121+ days outstanding!")
    
    # Full Aging Details
    st.markdown("---")
    st.subheader("📋 Complete Aging Summary")
    st.caption("Full breakdown of all customers across all aging buckets")
    
    display_cols = ['BP Code', 'BP Name'] + aging_cols + ['Balance/G.Total']
    if all(col in df.columns for col in display_cols):
        df_summary = df[display_cols].copy()
        
        # Format all amount columns
        for col in aging_cols + ['Balance/G.Total']:
            df_summary[col] = df_summary[col].apply(lambda x: format_number(x, currency=True, short=True))
        
        # Rename for display
        display_rename = {
            'BP Code': 'Code',
            'BP Name': 'Customer',
            'Balance/G.Total': 'Total'
        }
        df_summary = df_summary.rename(columns=display_rename)
        
        st.dataframe(df_summary, use_container_width=True, hide_index=True)
