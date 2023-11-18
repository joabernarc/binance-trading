from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import talib
import pandas as pd
import pandas_ta as ta
import config
import numpy as np
from binance.client import Client
from binance.enums import HistoricalKlinesType

# Constants
API_KEY = config.API_KEY
API_SECRET = config.API_SECRET

# Fetch historical data
client = Client(API_KEY, API_SECRET)
klines = client.get_historical_klines("snxusdt", Client.KLINE_INTERVAL_1DAY, "1 March, 2023", klines_type=HistoricalKlinesType.FUTURES)
df = pd.DataFrame(klines, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
df = df.astype({'OpenTime': 'float', 'Open': 'float', 'High': 'float', 'Low': 'float', 'Close': 'float', 'Volume': 'float'})
df = df.iloc[:, :6]
df = df.join(pd.DataFrame(ta.kc(df.High, df.Low, df.Close).dropna().round(2)))
df.set_index("OpenTime", inplace=True)
df.index = pd.to_datetime(df.index, unit='ms')
df = df[df.High != df.Low]

# Define indicatior functions
def fetch_indicator_kc(data, kc_period, kc_mult):
    kc = np.array(ta.kc(high=data.High, low=data.Low, close=data.Close, length=kc_period, scalar=kc_mult / 20))
    return kc

def fetch_indicator_stoch(data, stoch_k, stoch_d, stoch_smooth):
    stoch = np.array(ta.stoch(high=data.High, low=data.Low, close=data.Close, k=stoch_k, d=stoch_d, smooth_k=stoch_smooth))
    return stoch

# Define strategy class
class KeltnerStrategy(Strategy):
    kc_period = 6
    kc_mult = 18
    max_retry_count = 2
    sl_mult = 25
    tp_mult = 50
    stoch_k = 14
    stoch_d = 3
    stoch_high = 72
    stoch_low = 26
    stoch_smooth = 3
    sizing = 27777
    daily_target = 120

    def init(self):
        # Add EMA, Stochastic indicator
        self.ema8 = self.I(talib.EMA, self.data.Close, 8)
        self.ema80 = self.I(talib.EMA, self.data.Close, 80)
        self.slowk, self.slowd = self.I(talib.STOCH, self.data.High, self.data.Low, self.data.Close, self.stoch_k, self.stoch_d, 0, self.stoch_smooth)
        self.lowest_price = None
        self.highest_price = None
        self.retry_count = 0
        self.daily_counter = 0
        self.daily_base_equity = 100

    def next(self):
        self.lowest_price = self.data.Low[-1]
        self.highest_price = self.data.High[-1]

        if self.position.is_long and crossover(self.slowk, 80):
            self.position.close()

        if self.position.is_short and crossover(20, self.slowk):
            self.position.close()

        if not self.position and crossover(self.slowk, self.slowd) and self.slowk[-2] < self.stoch_low:
            self.retry_count = 0
            self.buy(sl=(self.data.Close[-1]) * (1 - (self.sl_mult * 0.001)), tp=(self.data.Close[-1]) * (1 + (self.tp_mult * 0.001)))

        if not self.position and crossover(self.slowd, self.slowk) and self.slowk[-2] > self.stoch_high:
            self.retry_count = 0
            self.sell(sl=(self.data.Close[-1]) * (1 + (self.sl_mult * 0.001)), tp=(self.data.Close[-1]) * (1 - (self.tp_mult * 0.001)))

# Run backtest
bt = Backtest(df, KeltnerStrategy, cash=100, margin=0.25)
# Run optimization
stats = bt.optimize(sl_mult=range(20, 30, 5), tp_mult=range(37, 50, 10), stoch_low=range(16, 28, 2), stoch_high=range(72, 84, 2), maximize='Return [%]')

# Display results
print(stats._strategy)
bt.plot()
