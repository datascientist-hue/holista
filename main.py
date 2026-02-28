import streamlit as st

st.set_page_config(page_title="Holista Dashboards", layout="wide")

pages = [
    st.Page("pages/holistafile.py", title="Holista Dashboard", icon="📊", default=True),
    st.Page("pages/overduepaymentholista.py", title="Overdue Payment", icon="💰"),
    st.Page("pages/overduecreditorholista.py", title="Overdue Creditor", icon="💳"),
    st.Page("pages/purchaseorderholista.py", title="Purchase Order", icon="📦"),
    st.Page("pages/salesorderholista.py", title="Sales Order", icon="📈"),
]

navigator = st.navigation(pages)
navigator.run()
