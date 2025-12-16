import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import plotly.graph_objects as go
import numpy as np

# Page Config
st.set_page_config(
    page_title="Exchange Rate Monitor",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Core Logic ---
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
    '1m':  {'period': '3mo', 'interval': '60m'},
    '6m':  {'period': '6mo', 'interval': '1d'},
    '1y':  {'period': '1y',  'interval': '1d'}
}
selected_range = st.sidebar.radio("Time Range", list(time_ranges.keys()), index=2)

# Theme Selection
theme_map = {'Dark': 'plotly_dark', 'Light': 'plotly_white'}
selected_theme = st.sidebar.radio("Theme", list(theme_map.keys()), index=0)

# Apply Theme Colors (CSS & Chart)
if selected_theme == 'Dark':
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #000000;
            color: #e0e0e0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    chart_bg = '#000000'
    chart_grid = '#404040'
    chart_font_color = '#e0e0e0'
else:
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #f0f0f0;
            color: #000000;
        }
        /* Force black text for common elements in Light Mode */
        .stMarkdown, .stText, .stMetricLabel, .stMetricValue, .stDataFrame, .stTable, .stRadio label, .stSelectbox label, p, span, div {
            color: #000000 !important;
        }
        /* Sidebar background */
        [data-testid="stSidebar"] {
            background-color: #e0e0e0;
        }
        [data-testid="stSidebar"] * {
            color: #000000 !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    chart_bg = '#f0f0f0'
    chart_grid = '#d0d0d0'
    chart_font_color = '#000000'

# Initialize Session State
if 'live_data' not in st.session_state:
    st.session_state.live_data = {'times': [], 'rates': []}
if 'bank_rates' not in st.session_state:
    st.session_state.bank_rates = {'BOC': None, 'CMB': None}
if 'last_bank_update' not in st.session_state:
    st.session_state.last_bank_update = {'BOC': 0, 'CMB': 0}
if 'last_currency' not in st.session_state:
    st.session_state.last_currency = selected_currency

# Reset live data if currency changes
if st.session_state.last_currency != selected_currency:
    st.session_state.live_data = {'times': [], 'rates': []}
    st.session_state.bank_rates = {'BOC': None, 'CMB': None}
    st.session_state.last_bank_update = {'BOC': 0, 'CMB': 0}
    st.session_state.last_currency = selected_currency

# Fetch History (Cached)
@st.cache_data(ttl=60)
def get_history(ticker, period, interval):
    try:
        data = yf.Ticker(ticker).history(period=period, interval=interval)
        return data
    except:
        return pd.DataFrame()

ticker_symbol = currency_info['yf']
hist_data = get_history(ticker_symbol, time_ranges[selected_range]['period'], time_ranges[selected_range]['interval'])

# Placeholders
title_placeholder = st.empty()
metrics_placeholder = st.empty()
chart_placeholder = st.empty()
footer_placeholder = st.empty()

fetcher = BankRateFetcher()

# Live Loop
while True:
    current_time = time.time()
    
    # 1. Fetch Live Rate (Yahoo)
    try:
        ticker = yf.Ticker(ticker_symbol)
        price = ticker.fast_info.last_price
        if price is None or np.isnan(price):
             # Fallback
             hist = ticker.history(period='1d', interval='1m')
             if not hist.empty:
                 price = hist['Close'].iloc[-1]
    except:
        price = None

    if price:
        st.session_state.live_data['times'].append(datetime.now())
        st.session_state.live_data['rates'].append(price)
        # Keep buffer size reasonable (e.g., 1 hour of seconds)
        if len(st.session_state.live_data['times']) > 3600:
            st.session_state.live_data['times'].pop(0)
            st.session_state.live_data['rates'].pop(0)

    # 2. Fetch Bank Rates (Throttled)
    # BOC (30s)
    if current_time - st.session_state.last_bank_update['BOC'] > 30:
        rate = fetcher.get_boc_rates(selected_currency)
        if rate:
            st.session_state.bank_rates['BOC'] = rate
        st.session_state.last_bank_update['BOC'] = current_time
    
    # CMB (10s)
    if current_time - st.session_state.last_bank_update['CMB'] > 10:
        rate = fetcher.get_cmb_rates(selected_currency)
        if rate:
            st.session_state.bank_rates['CMB'] = rate
        st.session_state.last_bank_update['CMB'] = current_time

    # 3. Update UI
    
    # Title
    title_placeholder.title(f"{selected_currency} ({currency_info['name']}) to CNY")

    # Metrics
    current_val = price if price else (hist_data['Close'].iloc[-1] if not hist_data.empty else 0)
    start_val = hist_data['Close'].iloc[0] if not hist_data.empty else current_val
    delta = current_val - start_val
    delta_percent = (delta / start_val) * 100 if start_val != 0 else 0
    
    boc = st.session_state.bank_rates['BOC']
    cmb = st.session_state.bank_rates['CMB']
    
    with metrics_placeholder.container():
        c1, c2, c3 = st.columns(3)
        # delta_color="inverse" makes positive delta Red (Up) and negative delta Green (Down)
        c1.metric("实时汇率 (Yahoo)", f"{current_val:.4f}", f"{delta_percent:.2f}%", delta_color="inverse")
        c2.metric("中国银行 (卖出价)", f"{boc['spot_sell']}" if boc else "Loading...")
        c3.metric("招商银行 (卖出价)", f"{cmb['spot_sell']}" if cmb else "Loading...")

    # Chart
    fig = go.Figure()
    
    # Determine Colors based on Theme
    if selected_theme == 'Dark':
        c_up, c_down = '#ff3333', '#00ff00'
        f_up, f_down = 'rgba(255, 50, 50, 0.2)', 'rgba(0, 255, 0, 0.2)'
    elif selected_theme == 'Light':
        c_up, c_down = '#d62728', '#2ca02c' # Plotly standard red/green
        f_up, f_down = 'rgba(214, 39, 40, 0.2)', 'rgba(44, 160, 44, 0.2)'
        
    line_col = c_up if delta >= 0 else c_down
    fill_col = f_up if delta >= 0 else f_down
    
    # History Line
    if not hist_data.empty:
        fig.add_trace(go.Scatter(
            x=hist_data.index, 
            y=hist_data['Close'],
            mode='lines',
            name='History',
            line=dict(color=line_col, width=2, dash='solid'),
            opacity=0.5,
            fill='tozeroy',
            fillcolor=fill_col
        ))
        
        # Connect History to Live
        if st.session_state.live_data['times']:
            fig.add_trace(go.Scatter(
                x=[hist_data.index[-1], st.session_state.live_data['times'][0]],
                y=[hist_data['Close'].iloc[-1], st.session_state.live_data['rates'][0]],
                mode='lines',
                showlegend=False,
                line=dict(color=line_col, width=2, dash='solid'),
                opacity=0.5,
                fill='tozeroy',
                fillcolor=fill_col
            ))

    # Live Line
    if st.session_state.live_data['times']:
        fig.add_trace(go.Scatter(
            x=st.session_state.live_data['times'], 
            y=st.session_state.live_data['rates'],
            mode='lines',
            name='Live',
            line=dict(color=line_col, width=2),
            fill='tozeroy',
            fillcolor=fill_col
        ))

    # Calculate dynamic Y-axis range
    all_rates = []
    if not hist_data.empty:
        all_rates.extend(hist_data['Close'].tolist())
    if st.session_state.live_data['rates']:
        all_rates.extend(st.session_state.live_data['rates'])
    
    y_range = None
    if all_rates:
        min_val = min(all_rates)
        max_val = max(all_rates)
        y_range = [min_val * 0.999, max_val * 1.001]

    fig.update_layout(
        title=dict(text=f"Exchange Rate Trend ({selected_range})", font=dict(color=chart_font_color)),
        xaxis=dict(title="Time", title_font=dict(color=chart_font_color), tickfont=dict(color=chart_font_color), gridcolor=chart_grid),
        yaxis=dict(title="CNY", title_font=dict(color=chart_font_color), tickfont=dict(color=chart_font_color), range=y_range, tickformat=".4f", gridcolor=chart_grid),
        showlegend=False,
        height=500,
        template=theme_map[selected_theme],
        paper_bgcolor=chart_bg,
        plot_bgcolor=chart_bg,
        font=dict(color=chart_font_color),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    chart_placeholder.plotly_chart(fig, width='stretch')
    
    footer_placeholder.caption("Source: Yahoo Finance API & Bank Official Websites/API. © 2025 Jason Cao. Personal Use Only.")

    time.sleep(3)
