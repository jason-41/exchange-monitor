import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import plotly.graph_objects as go

# Page Config
st.set_page_config(
    page_title="Exchange Rate Monitor",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Core Logic (Reused from your main.py) ---
class BankRateFetcher:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.currency_map = {
            'EUR': '欧元',
            'USD': '美元',
            'HKD': '港币',
            'GBP': '英镑',
            'JPY': '日元'
        }

    def get_boc_rates(self, currency_code):
        try:
            url = "https://www.boc.cn/sourcedb/whpj/"
            response = requests.get(url, headers=self.headers, timeout=5)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            target_name = self.currency_map.get(currency_code)
            if not target_name: return None
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) > 0 and target_name in cols[0].text.strip():
                        return {'spot_sell': cols[3].text.strip(), 'cash_sell': cols[4].text.strip()}
            return None
        except: return None

    def get_cmb_rates(self, currency_code):
        try:
            url = "https://fx.cmbchina.com/api/v1/fx/rate"
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://fx.cmbchina.com/hq/',
                'Origin': 'https://fx.cmbchina.com'
            }
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200: return None
            data = response.json()
            target_name = self.currency_map.get(currency_code)
            if 'body' in data:
                for item in data['body']:
                    if target_name in item.get('ccyNbr', ''):
                        return {'spot_sell': item.get('rthOfr', 'N/A'), 'cash_sell': item.get('rtcOfr', 'N/A')}
            return None
        except: return None

# --- Streamlit UI ---

# Sidebar Controls
st.sidebar.title("Settings")

currencies = {
    'EUR': {'yf': 'EURCNY=X', 'name': 'Euro'},
    'USD': {'yf': 'CNY=X', 'name': 'US Dollar'},
    'HKD': {'yf': 'HKDCNY=X', 'name': 'Hong Kong Dollar'},
    'GBP': {'yf': 'GBPCNY=X', 'name': 'British Pound'},
    'JPY': {'yf': 'JPYCNY=X', 'name': 'Japanese Yen'}
}

selected_currency = st.sidebar.radio("Currency", list(currencies.keys()))
currency_info = currencies[selected_currency]

time_ranges = {
    '1h':  {'period': '1d',  'interval': '1m'},
    '24h': {'period': '5d',  'interval': '1m'},
    '48h': {'period': '5d',  'interval': '2m'},
    '7d':  {'period': '1mo', 'interval': '15m'},
    '1m':  {'period': '3mo', 'interval': '60m'}
}
selected_range = st.sidebar.radio("Time Range", list(time_ranges.keys()), index=2)

# Auto-refresh logic
if st.sidebar.checkbox("Auto Refresh (10s)", value=True):
    time.sleep(10)
    st.rerun()

# Main Content
st.title(f"{currency_info['name']} ({selected_currency}) to CNY")

# Fetch Data
@st.cache_data(ttl=60) # Cache YFinance data for 60 seconds to prevent spamming
def get_history(ticker, period, interval):
    data = yf.Ticker(ticker).history(period=period, interval=interval)
    return data

# Get Live Data
ticker_symbol = currency_info['yf']
hist_data = get_history(ticker_symbol, time_ranges[selected_range]['period'], time_ranges[selected_range]['interval'])

# Get Bank Rates
fetcher = BankRateFetcher()
boc_rate = fetcher.get_boc_rates(selected_currency)
cmb_rate = fetcher.get_cmb_rates(selected_currency)

# Display Metrics
col1, col2, col3 = st.columns(3)

current_price = hist_data['Close'].iloc[-1] if not hist_data.empty else 0
prev_price = hist_data['Close'].iloc[0] if not hist_data.empty else 0
delta = current_price - prev_price
delta_percent = (delta / prev_price) * 100 if prev_price != 0 else 0

with col1:
    st.metric("Live Rate (Yahoo)", f"{current_price:.4f}", f"{delta_percent:.2f}%")

with col2:
    boc_val = f"{boc_rate['spot_sell']} / {boc_rate['cash_sell']}" if boc_rate else "N/A"
    st.metric("Bank of China (现汇/现钞)", boc_val)

with col3:
    cmb_val = f"{cmb_rate['spot_sell']} / {cmb_rate['cash_sell']}" if cmb_rate else "N/A"
    st.metric("China Merchants Bank (现汇/现钞)", cmb_val)

# Plotting with Plotly (Interactive)
if not hist_data.empty:
    # Filter data based on range roughly (YFinance returns more than needed sometimes)
    # For simplicity we use what YF returns, but you can filter by datetime here if needed
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist_data.index, 
        y=hist_data['Close'],
        mode='lines',
        name='Rate',
        line=dict(color='#ff3333' if delta >= 0 else '#00ff00', width=2),
        fill='tozeroy',
        fillcolor='rgba(255, 50, 50, 0.1)' if delta >= 0 else 'rgba(0, 255, 0, 0.1)'
    ))
    
    fig.update_layout(
        title=f"Exchange Rate Trend ({selected_range})",
        xaxis_title="Time",
        yaxis_title="CNY",
        height=500,
        template="plotly_dark", # Matches your dark theme preference
        margin=dict(l=0, r=0, t=30, b=0)
    )
    
    st.plotly_chart(fig, use_container_width=True)

st.caption("Source: Yahoo Finance API & Bank Official Websites. © 2025 Jason Cao.")
