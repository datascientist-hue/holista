import streamlit as st
import pandas as pd
import plotly.express as px
from ftplib import error_perm
from pages.overduepaymentholista import display_overdue_payment_dashboard
from pages.overduecreditorholista import display_overdue_creditor_dashboard
from ftp_data_loader import get_ftp_path, read_excel_from_ftp, read_tabular_from_ftp

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_indian(num: float) -> str:
    """Format a number using the Indian numbering system with commas.

    Examples:
    * 100000 -> '1,00,000'
    * 1250000 -> '12,50,000'

    Returns ``0`` for NaN or zero values.
    """
    if pd.isna(num):
        return "0"

    # keep sign for later
    sign = "" if num >= 0 else "-"
    num = abs(int(num))
    if num == 0:
        return "0"

    s = str(num)
    if len(s) <= 3:
        return sign + s

    # last 3 digits unchanged, then groups of two
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + ',' + result
        s = s[:-2]

    return sign + result


def format_number(num: float, currency: bool = False, short: bool = True) -> str:
    """Universal formatter used across the dashboard.

    * ``currency`` adds the rupee symbol prefix.
    * ``short`` enables K/L/Cr abbreviation for large values.

    Logic choices are driven by the requirements:
    * All numbers use Indian grouping.
    * Values >=1,000 are abbreviated (K for thousands, L for lakhs,
      Cr for crores) with two decimal places (trailing zeros trimmed).
    """
    if pd.isna(num):
        return "0"

    num = float(num)
    absnum = abs(num)

    if short:
        if absnum >= 1e7:  # 1 crore
            val = num / 1e7
            suffix = "Cr"
        elif absnum >= 1e5:  # 1 lakh
            val = num / 1e5
            suffix = "L"
        elif absnum >= 1e3:  # 1 thousand
            val = num / 1e3
            suffix = "K"
        else:
            # fall back to full format
            formatted = format_indian(num)
            return f"₹ {formatted}" if currency else formatted

        # two decimals, trim unnecessary zeros
        formatted_val = f"{val:.2f}".rstrip('0').rstrip('.')
        return f"₹ {formatted_val}{suffix}" if currency else f"{formatted_val}{suffix}"
    else:
        formatted = format_indian(num)
        return f"₹ {formatted}" if currency else formatted


def format_quantity(qty: float) -> str:
    """Quantity-specific display – simply abbreviates using general formatter."""
    if pd.isna(qty):
        return "0"
    return format_number(qty, currency=False, short=True)


def format_cases_display(cases: float) -> str:
    """Compatibility wrapper used by some legacy scripts.

    Behaves exactly like :func:`format_quantity` but kept for backward
    compatibility with earlier code that imported this name.
    """
    return format_quantity(cases)




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

# 1.b Navigation
st.sidebar.title("📱 Navigation")
# updated menu labels per new requirements
page = st.sidebar.radio(
    "Select Dashboard:",
    ["Overdue Sales Orders", "Overdue Payment", "Overdue Creditor", "Purchase Order", "Stock Status", "Stock Ageing"]
)
st.sidebar.markdown("---")

# 2. Load Data - Dynamic based on page selection
# (sales/purchase handled together; stock status handled separately)
@st.cache_data
def load_sales_data():
    remote_path = get_ftp_path("open_so")
    df = read_excel_from_ftp(remote_path)
    df['Posting Date'] = pd.to_datetime(df['Posting Date'])
    # remove any previously calculated overdue days if present
    if 'Overdue Days' in df.columns:
        df = df.drop(columns=['Overdue Days'])
    # Parse Due Date if it exists
    if 'Due Date' in df.columns:
        df['Due Date'] = pd.to_datetime(df['Due Date'], errors='coerce')
    # State fallback: use Ship-To-State, fallback to Ship-to-city if blank
    df['Display_State'] = df['Ship-To-State'].fillna(df['Ship-to-city'])
    return df

@st.cache_data
def load_purchase_data():
    remote_path = get_ftp_path("open_po")
    df = read_excel_from_ftp(remote_path)
    df['Posting Date'] = pd.to_datetime(df['Posting Date'])
    # State fallback: use Ship-To-State, fallback to Ship-to-city if blank
    df['Display_State'] = df['Ship-To-State'].fillna(df['Ship-to-city'])
    return df

@st.cache_data
def load_stock_data():
    """Read stock status workbook and prepare basic columns."""
    remote_path = get_ftp_path("stock_status")
    df = read_excel_from_ftp(remote_path)
    # ensure numeric for metrics
    for col in ['Quantity', 'Inventory Value']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

@st.cache_data
def load_stock_ageing_data():
    """Read stock ageing workbook with age bucket columns."""
    configured_path = get_ftp_path("inventory")
    candidate_paths: list[str] = []

    def add_candidate(path: str):
        if path and path not in candidate_paths:
            candidate_paths.append(path)

    add_candidate(configured_path)
    add_candidate(get_ftp_path("stock_ageing"))
    add_candidate(get_ftp_path("inventory_ageing"))

    if configured_path and "/" in configured_path:
        base_dir = configured_path.rsplit("/", 1)[0]
        add_candidate(f"{base_dir}/Inventory_Ageing_Report.xlsx")
        add_candidate(f"{base_dir}/inventory_ageing_report.csv")
        add_candidate(f"{base_dir}/stock agenging.xlsx")
        add_candidate(f"{base_dir}/stock ageing.xlsx")
        add_candidate(f"{base_dir}/stock_ageing.xlsx")

    last_error = None
    for remote_path in candidate_paths:
        try:
            df = read_tabular_from_ftp(remote_path)
            break
        except (FileNotFoundError, error_perm, OSError, ValueError) as exc:
            last_error = exc
    else:
        tried = "\n".join(f"- {p}" for p in candidate_paths if p)
        raise FileNotFoundError(
            "Stock ageing file was not found on FTP. "
            "Update [ftp].inventory in .streamlit/secrets.toml to the correct path.\n"
            f"Tried paths:\n{tried}\n"
            f"Last error: {last_error}"
        )

    # ensure numeric columns
    numeric_cols = ['0-15Qty', '0-15Value', '16-30Qty', '16-30Value', 
                    '31-60Qty', '31-60Value', '61-90Qty', '61-90Value',
                    '91-180Qty', '91-180Value', '181-360Qty', '181-360Value',
                    '361-720Qty', '361-720Value', '721+Qty', '721+DaysValue',
                    'In Stock', 'Inventory Value']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

# determine which dataset to use
if page == "Overdue Payment":
    display_overdue_payment_dashboard()
    st.stop()
elif page == "Overdue Creditor":
    display_overdue_creditor_dashboard()
    st.stop()
elif page == "Overdue Sales Orders":
    df = load_sales_data()
    dashboard_title = "📈 Daily Overdue Sales Orders"  # focus on overdue analysis
    
    # Filter for open orders (Line Status = "O") and overdue (Due Date < today)
    today = pd.Timestamp.today().normalize()
    overdue_df = df.copy()

    # keep only open lines
    if 'Line Status' in overdue_df.columns:
        overdue_df = overdue_df[overdue_df['Line Status'].astype(str).str.strip().eq('O')]
    # drop any lines with zero open quantity (balanced/completed)
    if 'OpenQty' in overdue_df.columns:
        overdue_df = overdue_df[pd.to_numeric(overdue_df['OpenQty'], errors='coerce').fillna(0) > 0]
    # also ignore lines with no monetary value
    if 'LineTotalBeforeTax' in overdue_df.columns:
        overdue_df = overdue_df[pd.to_numeric(overdue_df['LineTotalBeforeTax'], errors='coerce').fillna(0) > 0]

    # calculate overdue days using posting date instead of due date
    overdue_df = overdue_df.copy()
    if 'Posting Date' in overdue_df.columns:
        overdue_df['Posting Date'] = pd.to_datetime(overdue_df['Posting Date'], errors='coerce')
        overdue_df['Overdue Days'] = (today - overdue_df['Posting Date']).dt.days
    else:
        # if posting date not present, create column with zeros to avoid errors later
        overdue_df['Overdue Days'] = 0
    
    # Display page title
    st.title(dashboard_title)
    
    # Summary metrics and charts
    if not overdue_df.empty:
        # compute key indicators
        total_lines = len(overdue_df)
        # total overdue value using full line amount
        total_value = overdue_df['LineTotalBeforeTax'].sum()
        # compute average delay and count critical orders based on posting date-derived age
        avg_delay = overdue_df['Overdue Days'].mean()
        critical_count = (overdue_df['Overdue Days'] > 7).sum()

        # KPI cards
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overdue Orders", f"{total_lines}")
        c2.metric("Total Overdue Value", format_number(total_value, currency=True, short=True))
        c3.metric("Average Delay (Days)", f"{avg_delay:.1f}")
        c4.metric("Overdue Orders (>7d)", f"{critical_count}")

        # aging buckets for chart
        bins = [0,15,30,60,90,9999]
        labels = ["1-15 Days","16-30 Days","31-60 Days","61-90 Days","90+ Days"]
        overdue_df['Age Bucket'] = pd.cut(overdue_df['Overdue Days'], bins=bins, labels=labels, right=True)
        bucket_sum = overdue_df.groupby('Age Bucket')['LineTotalBeforeTax'].sum().reindex(labels, fill_value=0).reset_index()

        st.markdown("---")
        st.subheader("Overdue Aging")
        fig_age = px.bar(
            bucket_sum,
            x='Age Bucket',
            y='LineTotalBeforeTax',
            title='Overdue Value by Delay Bucket',
            text=bucket_sum['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True)),
            color_discrete_sequence=['#EF553B']
        )
        fig_age.update_layout(margin=dict(l=60,r=20,t=40,b=60))
        st.plotly_chart(fig_age, use_container_width=True)

        # top customers chart
        # sum full line amounts per customer (no change needed)
        cust_sum = overdue_df.groupby('BP Name')['LineTotalBeforeTax'].sum().sort_values(ascending=False).reset_index()
        cust_top = cust_sum.head(10)
        st.subheader("Top Customers with Overdue")
        fig_cust = px.bar(
            cust_top,
            x='LineTotalBeforeTax',
            y='BP Name',
            orientation='h',
            title='Customers by Pending Value',
            text=cust_top['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True)),
            color_discrete_sequence=['#636EFA']
        )
        fig_cust.update_layout(margin=dict(l=150,r=20,t=40,b=60))
        st.plotly_chart(fig_cust, use_container_width=True)

        # Display overdue orders table
        st.markdown("---")
        st.subheader("Detailed Overdue Line Items")

        # Prepare display dataframe with requested columns
        # ensure 'Document Number' is available by copying from common alternatives
        if 'Document Number' not in overdue_df.columns:
            if 'DocNum' in overdue_df.columns:
                overdue_df['Document Number'] = overdue_df['DocNum']
            elif 'Sales Order No' in overdue_df.columns:
                overdue_df['Document Number'] = overdue_df['Sales Order No']
        # focus on open pending sales order lines only
        display_cols = ['Document Number','Posting Date','BP Name','Item Description','Warehouse Code',
                        'OpenQty','LineTotalBeforeTax','Overdue Days']
        alt_cols = {
            'Document Number':'Document Number',
            'Posting Date':'Posting Date',
            'BP Name':'Customer Name',
            'Item Description':'Item',
            'Warehouse Code':'Warehouse',
            'OpenQty':'Open Qty',
            'LineTotalBeforeTax':'Pending Value',
            'Overdue Days':'Days Overdue'
        }
        df_display = overdue_df[[c for c in display_cols if c in overdue_df.columns]].copy()
        df_display = df_display.rename(columns=alt_cols)

        # format numeric columns
        if 'Quantity' in df_display.columns:
            df_display['Quantity'] = df_display['Quantity'].apply(format_quantity)
        if 'Pending Value' in df_display.columns:
            df_display['Pending Value'] = df_display['Pending Value'].apply(lambda x: format_number(x, currency=True, short=True))

        # date formatting
        if 'Posting Date' in df_display.columns:
            df_display['Posting Date'] = pd.to_datetime(df_display['Posting Date']).dt.strftime('%Y-%m-%d')

        st.dataframe(df_display, use_container_width=True, hide_index=True)
        # Since we always calculate 'Overdue Days' from Posting Date, this else branch is no longer needed
    else:
        st.success("✅ No overdue sales orders! All orders are on track.")
    
    st.stop()
elif page == "Purchase Order":
    df = load_purchase_data()
    dashboard_title = "📦 Purchase Order Analytics"
elif page == "Stock Status":
    # Stock Status page doesn't use the sales/purchase filters or charts
    stock_df = load_stock_data()

    # --- warehouse filter in sidebar ------------------------------------------------
    wh_codes = sorted(stock_df['Warehouse Code'].dropna().unique())
    selected_wh = st.sidebar.multiselect("Select Warehouse Code", options=wh_codes, default=wh_codes)
    if selected_wh:
        filtered_stock = stock_df[stock_df['Warehouse Code'].isin(selected_wh)]
    else:
        # if user clears selection show nothing so they have to pick at least one
        filtered_stock = stock_df.iloc[0:0]

    # show overview metrics based on filtered data
    st.title("📦 Stock Status Overview")
    total_value = filtered_stock['Inventory Value'].sum()
    total_qty = filtered_stock['Quantity'].sum()
    # count unique items by item no/description
    if 'Item No.' in filtered_stock.columns and 'Item Description' in filtered_stock.columns:
        total_items = filtered_stock[['Item No.', 'Item Description']].drop_duplicates().shape[0]
    else:
        total_items = len(filtered_stock)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Inventory Value", format_number(total_value, currency=True, short=True))
    col2.metric("Total Quantity", format_number(total_qty, currency=False, short=True))
    col3.metric("Total Items", f"{total_items}")

    # insights section
    st.markdown("---")
    st.subheader("Stock Insights")

    # Top 5 analysis
    if not filtered_stock.empty:
        # Top 5 by Quantity - vertical bar chart
        top_qty = filtered_stock.sort_values('Quantity', ascending=False).head(5)[['Item Description','Quantity']]
        st.markdown("**Top 5 Items by Quantity**")
        fig_qty = px.bar(
            top_qty,
            x='Item Description',
            y='Quantity',
            title='Top 5 Items by Quantity',
            color_discrete_sequence=['#636EFA']
        )
        fig_qty.update_traces(text=top_qty['Quantity'].apply(format_quantity), textposition='outside')
        fig_qty.update_layout(margin=dict(l=80, r=20, t=40, b=60), xaxis_tickangle=-45)
        st.plotly_chart(fig_qty, use_container_width=True)

        # Top 5 by Inventory Value - line/trend chart
        top_val = filtered_stock.sort_values('Inventory Value', ascending=False).head(5)[['Item Description','Inventory Value']]
        st.markdown("**Top 5 Items by Inventory Value**")
        fig_val = px.line(
            top_val,
            x='Item Description',
            y='Inventory Value',
            markers=True,
            title='Top 5 Items by Inventory Value Trend'
        )
        fig_val.update_layout(margin=dict(l=80, r=20, t=40, b=60), xaxis_tickangle=-45)
        st.plotly_chart(fig_val, use_container_width=True)

        # overall stock chart (vertical bars with single color)
        st.markdown("**Overall Stock Chart**")
        overall = filtered_stock.sort_values('Quantity', ascending=False).head(20)
        fig_overall = px.bar(
            overall,
            x='Item Description',
            y='Quantity',
            title='Overall Stock Quantity by Item',
            color_discrete_sequence=['#1f77b4']
        )
        fig_overall.update_traces(text=overall['Quantity'].apply(format_quantity), textposition='outside')
        fig_overall.update_layout(margin=dict(l=80, r=20, t=40, b=60), xaxis_tickangle=-45)
        st.plotly_chart(fig_overall, use_container_width=True)
    else:
        st.write("No data for selected warehouse(s). Pick at least one warehouse to see insights.")

    st.markdown("---")
    st.subheader("Full Stock Table")
    # apply formatting to numeric columns for readability
    stock_display = filtered_stock.copy()
    for col in ['Quantity', 'Inventory Value']:
        if col in stock_display.columns:
            stock_display[col] = stock_display[col].apply(
                lambda x: format_number(x, currency=(col == 'Inventory Value'), short=True)
            )
    st.dataframe(stock_display, use_container_width=True)
    # skip remaining code since not relevant
    st.stop()

elif page == "Stock Ageing":
    # Stock Ageing Analytics
    try:
        ageing_df = load_stock_ageing_data()
    except Exception as exc:
        st.title("📊 Core Stock Ageing Analytics")
        st.error("Unable to load Stock Ageing data from FTP.")
        st.code(str(exc))
        st.info("Fix the FTP path in .streamlit/secrets.toml, key: [ftp].inventory")
        st.stop()
    
    st.title("📊 Core Stock Ageing Analytics")
    
    # Stock age summary (always shown)
    # compute fresh (<30 days) and old (>30 days) totals
    fresh_cols = ["0-15Qty", "0-15Value", "16-30Qty", "16-30Value"]
    fresh_qty = ageing_df[["0-15Qty", "16-30Qty"]].sum().sum()
    fresh_val = ageing_df[["0-15Value", "16-30Value"]].sum().sum()
    old_qty = ageing_df[["31-60Qty","61-90Qty","91-180Qty","181-360Qty","361-720Qty","721+Qty"]].sum().sum()
    old_val = ageing_df[["31-60Value","61-90Value","91-180Value","181-360Value","361-720Value","721+DaysValue"]].sum().sum()

    # cards side by side
    c1, c2 = st.columns(2)
    c1.metric("Fresh Stock (<30 Days) - Value", format_number(fresh_val, currency=True, short=True))
    c1.metric("Fresh Stock (<30 Days) - Cases", format_quantity(fresh_qty))
    c2.metric("Old Stock (>30 Days) - Value", format_number(old_val, currency=True, short=True))
    c2.metric("Old Stock (>30 Days) - Cases", format_quantity(old_qty))

    # percentage insight
    total_cases = fresh_qty + old_qty
    if total_cases > 0:
        perc_fresh = fresh_qty/total_cases*100
        note = f"{perc_fresh:.1f}% of cases are fresh; {100-perc_fresh:.1f}% are ageing."
    else:
        note = "No cases available."
    st.caption(note)

    # Brand Value by Age section
    st.markdown("---")
    st.subheader("Brand Value by Age")
    # fresh by brand
    fresh_brand = ageing_df.groupby('Brand')[['0-15Value','16-30Value','0-15Qty','16-30Qty']].sum()
    fresh_brand['Value'] = fresh_brand[['0-15Value','16-30Value']].sum(axis=1)
    fresh_brand['Qty'] = fresh_brand[['0-15Qty','16-30Qty']].sum(axis=1)
    fresh_brand = fresh_brand.sort_values('Value', ascending=False).reset_index()
    # aged by brand (>30)
    old_brand = ageing_df.groupby('Brand')[['31-60Value','61-90Value','91-180Value','181-360Value','361-720Value','721+DaysValue',
                                          '31-60Qty','61-90Qty','91-180Qty','181-360Qty','361-720Qty','721+Qty']].sum()
    old_brand['Value'] = old_brand[['31-60Value','61-90Value','91-180Value','181-360Value','361-720Value','721+DaysValue']].sum(axis=1)
    old_brand['Qty'] = old_brand[['31-60Qty','61-90Qty','91-180Qty','181-360Qty','361-720Qty','721+Qty']].sum(axis=1)
    old_brand = old_brand.sort_values('Value', ascending=False).reset_index()

    # charts
    fig_fresh_brand = px.bar(
        fresh_brand,
        x='Brand',
        y='Value',
        title='Fresh Stock Value by Brand (<30 Days)',
        color_discrete_sequence=['#636EFA']
    )
    fig_fresh_brand.update_traces(text=fresh_brand['Value'].apply(lambda x: format_number(x, currency=True, short=True)), textposition='outside')
    fig_fresh_brand.update_layout(margin=dict(l=80,r=20,t=40,b=60), xaxis_tickangle=-45)
    st.plotly_chart(fig_fresh_brand, use_container_width=True)

    fig_old_brand = px.bar(
        old_brand,
        x='Brand',
        y='Value',
        title='Old Stock Value by Brand (>30 Days)',
        color_discrete_sequence=['#EF553B']
    )
    fig_old_brand.update_traces(text=old_brand['Value'].apply(lambda x: format_number(x, currency=True, short=True)), textposition='outside')
    fig_old_brand.update_layout(margin=dict(l=80,r=20,t=40,b=60), xaxis_tickangle=-45)
    st.plotly_chart(fig_old_brand, use_container_width=True)

    # --- Ageing Bucket Analysis --------------------------------------------------------
    st.markdown("---")
    st.subheader("Inventory Age Distribution")

    # define buckets explicitly
    buckets = [
        ("0–15 Days", "0-15Qty", "0-15Value"),
        ("16–30 Days", "16-30Qty", "16-30Value"),
        ("31–60 Days", "31-60Qty", "31-60Value"),
        ("61–90 Days", "61-90Qty", "61-90Value"),
        ("91–180 Days", "91-180Qty", "91-180Value"),
        ("181–360 Days", "181-360Qty", "181-360Value"),
        ("361–720 Days", "361-720Qty", "361-720Value"),
        ("721+ Days", "721+Qty", "721+DaysValue")
    ]

    # compute summary per bucket
    dist_rows = []
    for name, qty_col, val_col in buckets:
        qty = ageing_df[qty_col].sum()
        val = ageing_df[val_col].sum()
        dist_rows.append({"Bucket": name, "Quantity": qty, "Inventory Value": val})
    dist_df = pd.DataFrame(dist_rows)

    # KPI cards definitions
    fresh_val = dist_df.loc[dist_df['Bucket'].isin(["0–15 Days","16–30 Days"]), 'Inventory Value'].sum()
    slow_val = dist_df.loc[dist_df['Bucket'].isin(["31–60 Days","61–90 Days"]), 'Inventory Value'].sum()
    risk_val = dist_df.loc[dist_df['Bucket'].isin(["91–180 Days","181–360 Days"]), 'Inventory Value'].sum()
    dead_val = dist_df.loc[dist_df['Bucket'].isin(["361–720 Days","721+ Days"]), 'Inventory Value'].sum()

    colf, cols, colomb, cold = st.columns(4)
    colf.metric("Fresh Stock Value", format_number(fresh_val, currency=True, short=True), delta_color="normal")
    cols.metric("Slow Moving Stock Value", format_number(slow_val, currency=True, short=True), delta_color="normal")
    colomb.metric("Risk Stock Value", format_number(risk_val, currency=True, short=True), delta_color="off")
    cold.metric("Dead Stock Value", format_number(dead_val, currency=True, short=True), delta_color="inverse")
    
    # combined chart: bars inventory value, line quantity
    st.markdown("**Bucket-level Inventory Age Chart**")
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # bar trace
    fig.add_trace(
            go.Bar(
                x=dist_df['Bucket'],
                y=dist_df['Inventory Value'],
                name='Inventory Value',
                marker_color=['green','green','yellow','yellow','orange','orange','red','red'],
                text=dist_df['Inventory Value'].apply(lambda x: format_number(x, currency=True, short=True)),
                textposition='outside'
            ),
            secondary_y=False
        )
    # line trace
    fig.add_trace(
        go.Scatter(
            x=dist_df['Bucket'],
            y=dist_df['Quantity'],
            name='Quantity (Cases)',
            mode='lines+markers+text',
            text=dist_df['Quantity'].apply(format_quantity),
            textposition='top center',
            line=dict(color='blue')
        ),
        secondary_y=True
    )
    fig.update_layout(
        title='Inventory Age Distribution',
        margin=dict(l=80, r=80, t=40, b=60),
        xaxis_tickangle=-45
    )
    fig.update_yaxes(title_text='Inventory Value', secondary_y=False)
    fig.update_yaxes(title_text='Quantity', secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    # final detailed table
    st.markdown("---")
    st.subheader("Detailed Ageing Data")
    display_cols = ['Item Description', 'Warehouse Code', 'In Stock', 'Inventory Value']
    if all(col in ageing_df.columns for col in display_cols):
        df_temp = ageing_df[display_cols].copy()
        # format numeric columns
        for col in ['In Stock', 'Inventory Value']:
            if col in df_temp.columns:
                df_temp[col] = df_temp[col].apply(
                    lambda x: format_number(x, currency=(col == 'Inventory Value'), short=True)
                )
        st.dataframe(df_temp, use_container_width=True)
    else:
        # if structure unexpected, just show as-is but still try to format any numeric
        df_temp = ageing_df.copy()
        for col in df_temp.select_dtypes(include='number').columns:
            df_temp[col] = df_temp[col].apply(lambda x: format_number(x, currency=False, short=True))
        st.dataframe(df_temp, use_container_width=True)
    
    st.stop()

    # always stop after Stock Ageing page so later filters/KPIs don't run
    st.stop()

else:
    # Fallback
    st.error("Unknown page selected")
    st.stop()

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
st.title(dashboard_title)
col1, col2 = st.columns(2)
# total values used for metrics; formatting helper will abbreviate
sales_val = filtered_df['LineTotalBeforeTax'].sum()
qty_total_cases = filtered_df['Qty in Cases/Bags'].sum()
# only purchase orders are shown here
col1.metric("Purchase Value", format_number(sales_val, currency=True, short=True))
col2.metric("Total Cases", format_quantity(qty_total_cases))

# 5. Charts
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Purchase Trend over Time")
    # Group by date for cleaner chart
    sales_trend = filtered_df.groupby('Posting Date')['LineTotalBeforeTax'].sum().reset_index()
    sales_trend['Formatted'] = sales_trend['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True))
    chart_title = "Purchase Trend"
    fig_trend = px.area(
        sales_trend,
        x='Posting Date',
        y='LineTotalBeforeTax',
        markers=True,
        template='plotly_white',
        title=chart_title,
        hover_data={'Formatted': True, 'LineTotalBeforeTax': False}
    )
    fig_trend.update_traces(line_color='#1f77b4', fill='tozeroy', hovertemplate='<b>Date:</b> %{x}<br><b>Sales:</b> %{customdata}<extra></extra>')
    fig_trend.update_layout(margin=dict(l=20,r=20,t=40,b=20), yaxis_title="Value")
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
    
    if not top_products.empty:
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
    else:
        st.info("No product data available to display.")

# 5.1 Top 3 BP Names
bp_title = "Top 3 Business Partners by Purchase Value"
st.subheader(bp_title)
top_bp = (
    filtered_df.groupby('BP Name')['LineTotalBeforeTax']
    .sum()
    .nlargest(3)
    .reset_index()
)
if not top_bp.empty:
    top_bp['Formatted'] = top_bp['LineTotalBeforeTax'].apply(lambda x: format_number(x, currency=True, short=True))
    bp_chart_title = "Top 3 Business Partners"
    bp_hover_label = "Purchase Value"
    bp_xaxis_title = "Purchase Value"
    fig_bp = px.bar(
        top_bp,
        x='LineTotalBeforeTax',
        y='BP Name',
        orientation='h',
        template='plotly_white',
        color='LineTotalBeforeTax',
        color_continuous_scale='Greens',
        title=bp_chart_title,
        hover_data={'Formatted': True, 'LineTotalBeforeTax': False}
    )
    fig_bp.update_traces(marker_line_width=0, hovertemplate=f'<b>Partner:</b> %{{y}}<br><b>{bp_hover_label}:</b> %{{customdata}}<extra></extra>')
    fig_bp.update_layout(margin=dict(l=20,r=20,t=40,b=20), xaxis_title=bp_xaxis_title)
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
    df_display['Cases'] = df_display['Cases'].apply(lambda x: format_cases_display(x) if pd.notna(x) else "0")
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
