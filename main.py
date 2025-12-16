import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates
from matplotlib.widgets import RadioButtons
import yfinance as yf
import pandas as pd
import seaborn as sns
from datetime import datetime, timedelta
import warnings
import mplcursors
import numpy as np
import requests
from bs4 import BeautifulSoup
import threading
import time

# Suppress pandas warnings
warnings.filterwarnings('ignore')

# Configure font to support Chinese characters
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

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
        """Fetches rates from Bank of China."""
        try:
            url = "https://www.boc.cn/sourcedb/whpj/"
            response = requests.get(url, headers=self.headers, timeout=5)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            target_name = self.currency_map.get(currency_code)
            if not target_name:
                return None

            # Find the table
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) > 0 and target_name in cols[0].text.strip():
                        # BOC Columns: Name(0), Spot Buy(1), Cash Buy(2), Spot Sell(3), Cash Sell(4)
                        return {
                            'spot_sell': cols[3].text.strip(),
                            'cash_sell': cols[4].text.strip()
                        }
            return None
        except Exception as e:
            print(f"BOC Fetch Error: {e}")
            return None

    def get_cmb_rates(self, currency_code):
        """Fetches rates from China Merchants Bank using their API."""
        try:
            url = "https://fx.cmbchina.com/api/v1/fx/rate"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://fx.cmbchina.com/hq/',
                'Origin': 'https://fx.cmbchina.com'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return None
                
            data = response.json()
            target_name = self.currency_map.get(currency_code)
            if not target_name:
                return None

            # The API returns a list in data['body']
            if 'body' in data:
                for item in data['body']:
                    # Match by Chinese name (e.g., "美元")
                    if target_name in item.get('ccyNbr', ''):
                        return {
                            'spot_sell': item.get('rthOfr', 'N/A'),
                            'cash_sell': item.get('rtcOfr', 'N/A')
                        }
            
            return None
        except Exception as e:
            print(f"CMB Fetch Error: {e}")
            return None
            return None
            
        except Exception as e:
            print(f"CMB Fetch Error: {e}")
            return None

class ExchangeRateMonitor:
    def __init__(self, update_interval=2):
        self.update_interval = update_interval
        
        # Theme Configuration
        self.themes = {
            'Dark': {
                'bg': 'black',
                'fg': '#e0e0e0',
                'grid': '#404040',
                'widget_bg': '#2b2b2b',
                'widget_fg': 'white',
                'history_line': '#888888',
                'live_line_base': '#ffffff',
                'hover_bg': '#2b2b2b',
                'hover_fg': 'white'
            },
            'Light': {
                'bg': '#f0f0f0',
                'fg': 'black',
                'grid': '#d0d0d0',
                'widget_bg': '#e0e0e0',
                'widget_fg': 'black',
                'history_line': '#999999',
                'live_line_base': '#333333',
                'hover_bg': '#ffffff',
                'hover_fg': 'black'
            }
        }
        self.current_theme = 'Dark'
        
        # Configuration State
        self.currencies = {
            'EUR': {'yf': 'EURCNY=X', 'name': 'Euro'},
            'USD': {'yf': 'CNY=X', 'name': 'US Dollar'},
            'HKD': {'yf': 'HKDCNY=X', 'name': 'Hong Kong Dollar'},
            'GBP': {'yf': 'GBPCNY=X', 'name': 'British Pound'},
            'JPY': {'yf': 'JPYCNY=X', 'name': 'Japanese Yen'}
        }
        self.current_currency = 'EUR'
        
        # High Resolution History Settings
        self.time_ranges = {
            '1h':  {'hours': 1,   'yf_period': '1d',  'yf_interval': '1m'},  # 1 minute resolution
            '24h': {'hours': 24,  'yf_period': '5d',  'yf_interval': '1m'},  # 1 minute resolution
            '48h': {'hours': 48,  'yf_period': '5d',  'yf_interval': '1m'},  # 1 minute resolution
            '7d':  {'hours': 168, 'yf_period': '1mo', 'yf_interval': '5m'}, # 15 minute resolution
            '1m':  {'hours': 720, 'yf_period': '3mo', 'yf_interval': '60m'}, # 60 minute resolution
            '6m':  {'hours': 4320, 'yf_period': '6mo', 'yf_interval': '1d'}, # Daily resolution
            '1y':  {'hours': 8760, 'yf_period': '1y',  'yf_interval': '1d'}  # Daily resolution
        }
        self.current_range = '48h'
        
        # Data storage
        self.history_data = pd.DataFrame()
        self.live_times = []
        self.live_rates = []
        self.fill_collection = None
        
        # Bank Rates
        self.bank_fetcher = BankRateFetcher()
        self.bank_rates = {'BOC': None, 'CMB': None}
        
        # Setup Figure and Layout
        self.fig = plt.figure(figsize=(14, 8))
        self.fig.canvas.manager.set_window_title('Professional Exchange Rate Monitor (API Mode)')
        
        # Create Grid Layout (Main plot + Sidebar)
        # [Left: Plot (0.05, 0.1, 0.85, 0.85)] [Right: Controls (0.91, ..., 0.08, ...)]
        self.ax = self.fig.add_axes([0.06, 0.09, 0.85, 0.85])
        
        # Setup Widgets
        self.setup_widgets()
        
        # Initial Setup
        self.apply_theme()
        self.setup_plot_elements()
        self.refresh_data()
        self.start_bank_monitoring()
        
        # Setup Hover Cursor
        self.cursor = mplcursors.cursor([self.history_line, self.live_line], hover=True)
        self.cursor.connect("add", self.on_hover)

    def setup_widgets(self):
        """Initialize control widgets."""
        # Currency Selection
        self.ax_currency = self.fig.add_axes([0.925, 0.75, 0.05, 0.20])
        self.ax_currency.set_title("Currency", fontsize=10)
        self.radio_currency = RadioButtons(self.ax_currency, list(self.currencies.keys()), active=0,
                                           activecolor='#ff00ff', radio_props={'s': [50]*5})
        self.radio_currency.on_clicked(self.change_currency)

        # Time Range Selection
        self.ax_range = self.fig.add_axes([0.925, 0.45, 0.05, 0.25])
        self.ax_range.set_title("Time Range", fontsize=10)
        self.radio_range = RadioButtons(self.ax_range, list(self.time_ranges.keys()), active=2, # Default 48h
                                        activecolor='#00ff9d', radio_props={'s': [50]*5})
        self.radio_range.on_clicked(self.change_range)
        
        # Theme Selection
        self.ax_theme = self.fig.add_axes([0.925, 0.32, 0.05, 0.10])
        self.ax_theme.set_title("Theme", fontsize=10)
        self.radio_theme = RadioButtons(self.ax_theme, list(self.themes.keys()), active=0,
                                        activecolor='#00aaff', radio_props={'s': [50]*2})
        self.radio_theme.on_clicked(self.change_theme)      
        
        # Bank Rates Display
        self.ax_bank = self.fig.add_axes([0.92, 0.05, 0.08, 0.25]) # Increased height and moved up
        self.ax_bank.axis('off')
        self.bank_text = self.ax_bank.text(0, 0.6, "Loading\nBank Rates...", 
                                           fontsize=9, va='center', ha='left')
        self.bank_source_text = self.ax_bank.text(0, 0.2, "Source: Bank Websites", 
                                           fontsize=8, va='bottom', ha='left', 
                                           color='#888888', style='italic', fontfamily='Arial')
        
        # Copyright Text
        self.fig.text(0.5, 0.005, "© 2025 Jason Cao. Personal Use Only.", 
                      ha='center', va='bottom', fontsize=8, color='#888888', style='italic')
        
    def apply_theme(self):
        """Applies the current theme colors to all elements."""
        theme = self.themes[self.current_theme]
        
        # Figure and Axes Background
        self.fig.patch.set_facecolor(theme['bg'])
        self.ax.set_facecolor(theme['bg'])
        
        # Axis Labels and Ticks
        self.ax.set_xlabel('Time', fontsize=12, fontweight='bold', color=theme['fg'], labelpad=10)
        self.ax.set_ylabel('Exchange Rate (CNY)', fontsize=12, fontweight='bold', color=theme['fg'], labelpad=10)
        self.ax.tick_params(axis='both', colors=theme['fg'])
        
        # Grid and Spines
        self.ax.grid(True, linestyle='--', alpha=0.3, color=theme['grid'])
        for spine in self.ax.spines.values():
            spine.set_color(theme['grid'])
            
        # Widget Styling
        for ax_widget in [self.ax_currency, self.ax_range, self.ax_theme]:
            ax_widget.set_facecolor(theme['widget_bg'])
            ax_widget.title.set_color(theme['widget_fg'])
            
        # Bank Text
        if hasattr(self, 'bank_text'):
            self.bank_text.set_color(theme['fg'])
            
        # Radio Button Labels
        for radio in [self.radio_currency, self.radio_range, self.radio_theme]:
            for label in radio.labels:
                label.set_color(theme['widget_fg'])
                label.set_fontsize(9)
                
        # Update existing lines if they exist
        if hasattr(self, 'history_line'):
            # Only reset history line color if it's not currently colored by trend (which we handle in update_visuals)
            # But update_visuals is called frequently, so we can just let it handle it.
            pass

        self.fig.canvas.draw_idle()

    def setup_plot_elements(self):
        """Initialize plot lines and legend."""
        theme = self.themes[self.current_theme]
        
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        
        # Initialize Lines
        self.history_line, = self.ax.plot([], [], '-', color=theme['history_line'], alpha=0.5, 
                                          label='History', linewidth=1.5)
        self.live_line, = self.ax.plot([], [], '-', color=theme['live_line_base'], 
                                       label='Live', linewidth=1.5)
        
        self.legend = None
            
        self.source_text = self.ax.text(0.99, 0.01, 'Source: Yahoo Finance API', 
            transform=self.ax.transAxes, ha='right', va='bottom', 
            fontsize=8, color='#888888', style='italic', fontfamily='Arial')

    def change_currency(self, label):
        """Callback for currency change."""
        self.current_currency = label
        print(f"Switched to {label}")
        self.live_times = []
        self.live_rates = []
        self.refresh_data()
        # Bank updates are handled by background loops monitoring self.current_currency

    def change_range(self, label):
        """Callback for time range change."""
        self.current_range = label
        print(f"Switched to {label} range")
        self.refresh_data()
        
    def change_theme(self, label):
        """Callback for theme change."""
        self.current_theme = label
        print(f"Switched to {label} theme")
        self.apply_theme()
        # Re-trigger visual update to ensure line colors match theme if neutral, 
        # or just let the next update loop handle it.
        
    def refresh_data(self):
        """Refreshes history and resets plot."""
        self.fetch_history()
        self.update_visuals(0, 0) # Reset visuals
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.canvas.draw_idle()

    def start_bank_monitoring(self):
        """Starts background threads for periodic bank rate updates."""
        def run_boc_loop():
            last_currency = None
            while True:
                current = self.current_currency
                # If currency changed, reset display immediately
                if current != last_currency:
                    self.bank_rates['BOC'] = None
                    self.update_bank_text()
                    last_currency = current
                
                try:
                    rate = self.bank_fetcher.get_boc_rates(current)
                    if self.current_currency == current:
                        self.bank_rates['BOC'] = rate
                        self.update_bank_text()
                except Exception as e:
                    print(f"BOC loop error: {e}")
                
                # Sleep 30s, check for change every 0.5s
                for _ in range(60):
                    if self.current_currency != current:
                        break
                    time.sleep(0.5)

        def run_cmb_loop():
            last_currency = None
            while True:
                current = self.current_currency
                if current != last_currency:
                    self.bank_rates['CMB'] = None
                    self.update_bank_text()
                    last_currency = current
                
                try:
                    rate = self.bank_fetcher.get_cmb_rates(current)
                    if self.current_currency == current:
                        self.bank_rates['CMB'] = rate
                        self.update_bank_text()
                except Exception as e:
                    print(f"CMB loop error: {e}")
                
                # Sleep 20s, check for change every 0.5s
                for _ in range(40):
                    if self.current_currency != current:
                        break
                    time.sleep(0.5)

        threading.Thread(target=run_boc_loop, daemon=True).start()
        threading.Thread(target=run_cmb_loop, daemon=True).start()

    def update_bank_text(self):
        """Updates the bank rate text widget."""
        text = "银行外汇牌价\n(卖出价)\n\n"
        
        # BOC
        text += "中国银行:\n"
        if self.bank_rates['BOC']:
            text += f"{self.bank_rates['BOC']['spot_sell']}\n"
        else:
            text += "N/A\n"
            
        text += "\n"
        
        # CMB
        text += "招商银行:\n"
        if self.bank_rates['CMB']:
            text += f"{self.bank_rates['CMB']['spot_sell']}"
        else:
            text += "N/A"
            
        self.bank_text.set_text(text)
        self.fig.canvas.draw_idle()

    def fetch_history(self):
        """Fetches historical data based on current settings."""
        cfg = self.time_ranges[self.current_range]
        ticker_symbol = self.currencies[self.current_currency]['yf']
        
        print(f"Fetching {self.current_range} history for {ticker_symbol}...")
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period=cfg['yf_period'], interval=cfg['yf_interval'])
            
            if not hist.empty:
                # Timezone conversion
                local_tz = datetime.now().astimezone().tzinfo
                hist.index = hist.index.tz_convert(local_tz).tz_localize(None)
                
                # Filter by hours
                cutoff_time = datetime.now() - timedelta(hours=cfg['hours'])
                self.history_data = hist[hist.index >= cutoff_time]
                
                # Update Line
                self.history_line.set_data(self.history_data.index, self.history_data['Close'])
            else:
                self.history_data = pd.DataFrame()
                self.history_line.set_data([], [])
                
        except Exception as e:
            print(f"Error fetching history: {e}")
            self.history_data = pd.DataFrame()

    def get_live_rate(self):
        """Fetches current rate using yfinance API."""
        ticker_symbol = self.currencies[self.current_currency]['yf']
        try:
            ticker = yf.Ticker(ticker_symbol)
            # Try fast_info first (faster, less data overhead)
            price = ticker.fast_info.last_price
            
            # Fallback if fast_info fails
            if price is None or np.isnan(price):
                 hist = ticker.history(period='1d', interval='1m')
                 if not hist.empty:
                     price = hist['Close'].iloc[-1]
            
            if price is not None and not np.isnan(price):
                return float(price)
            return None
        except Exception as e:
            print(f"Error fetching live rate: {e}")
            return None

    def on_hover(self, sel):
        """Tooltip callback."""
        theme = self.themes[self.current_theme]
        x, y = sel.target
        # Convert float date to datetime
        date = mdates.num2date(x).strftime('%Y-%m-%d %H:%M:%S')
        sel.annotation.set_text(f"Time: {date}\nRate: {y:.4f}")
        sel.annotation.get_bbox_patch().set(fc=theme['hover_bg'], alpha=0.9, edgecolor=theme['hover_fg'])
        sel.annotation.set_color(theme['hover_fg'])

    def update_visuals(self, change, pct_change):
        """Updates colors and fills."""
        if change >= 0:
            color = '#ff3333' # Red
            symbol = '▲'
        else:
            color = '#00ff00' # Green
            symbol = '▼'
            
        self.live_line.set_color(color)
        self.history_line.set_color(color)
        self.history_line.set_alpha(0.5)
        
        # Fill
        if self.fill_collection:
            self.fill_collection.remove()
            
        # Combine data
        all_times = []
        all_rates = []
        if not self.history_data.empty:
            all_times.extend(self.history_data.index)
            all_rates.extend(self.history_data['Close'].values)
            
        all_times.extend(self.live_times)
        all_rates.extend(self.live_rates)
        
        if all_times:
            self.fill_collection = self.ax.fill_between(
                all_times, all_rates, min(all_rates)*0.999, color=color, alpha=0.15
            )
            
        return symbol, color

    def update(self, frame):
        """Animation loop."""
        current_rate = self.get_live_rate()
        current_time = datetime.now()
        
        if current_rate is not None:
            self.live_times.append(current_time)
            self.live_rates.append(current_rate)
            
            # Keep live buffer reasonable
            if len(self.live_times) > 3600: # Store up to 1 hour of live data (at 1s interval)
                self.live_times.pop(0)
                self.live_rates.pop(0)
            
            self.live_line.set_data(self.live_times, self.live_rates)
            
            # Connect history line to the start of live data
            if not self.history_data.empty and self.live_times:
                times = self.history_data.index.tolist() + [self.live_times[0]]
                rates = self.history_data['Close'].tolist() + [self.live_rates[0]]
                self.history_line.set_data(times, rates)
            
            # Calculate change based on visible history
            change = 0
            pct_change = 0
            if not self.history_data.empty:
                start_rate = self.history_data['Close'].iloc[0]
                change = current_rate - start_rate
                pct_change = (change / start_rate) * 100
            
            symbol, color = self.update_visuals(change, pct_change)
            
            # Update Title
            currency_name = self.currencies[self.current_currency]['name']
            title = (f"{currency_name} ({self.current_currency}) to CNY | Current: {current_rate:.4f} | "
                     f"Change ({self.current_range}): {symbol} {abs(pct_change):.2f}%")
            
            self.ax.set_title(title, fontsize=12, fontweight='bold', color=color)
            
            self.ax.relim()
            self.ax.autoscale_view()

        return self.live_line, self.history_line

    def start(self):
        print("Starting monitor...")
        ani = animation.FuncAnimation(self.fig, self.update, interval=self.update_interval*1000, cache_frame_data=False)
        plt.show()

if __name__ == "__main__":
    monitor = ExchangeRateMonitor(update_interval=1)
    monitor.start()
