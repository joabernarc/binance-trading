from backtesting import Backtest, Strategy
from backtesting.lib import crossover, cross, barssince
import talib
from backtesting.test import SMA, GOOG
import pandas as pd
import pandas_ta as ta
import config
import numpy as np
from binance.client import Client
from binance.enums import *

# Fetch historical data
client = Client(config.API_KEY, config.API_SECRET)
klines = client.get_historical_klines("agixusdt", Client.KLINE_INTERVAL_1DAY, "14 September, 2023", klines_type=HistoricalKlinesType.FUTURES)
df = pd.DataFrame(klines, columns = ['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
df = df.astype({'OpenTime':'float', 'Open':'float', 'High':'float', 'Low':'float', 'Close':'float', 'Volume':'float'})
df = df.iloc[:,:6]
df.set_index("OpenTime", inplace=True)
df.index = pd.to_datetime(df.index, unit='ms')
df=df[df.High!=df.Low]

# Display the length of the DataFrame
print('len:', len(df))

def indicator(data, kc_period, kc_mult):
    kc = ta.kc(high=df.High, low=df.Low, close=df.Close, length=kc_period, scalar=kc_mult/20)
    #print('kc:', kc)
    kc = np.array(kc)
    return kc

# Define strategy class
class IFR2Strategy(Strategy):
    #kc_period = 21
    #kc_mult = 7.6
    rsi_period = 8
    rsi_overbough = 80
    rsi_middle = 50
    rsi_oversold = 20
    take_profit = 16
    sizing = 27777
    
    def init(self):
        
        self.rsi = self.I(talib.RSI, self.data.Close, self.rsi_period)
        #self.kc = self.I(indicator, self.data, self.kc_period, self.kc_mult)
        self.ema8 = self.I(talib.EMA, self.data.Close, 8)
        self.ema20 = self.I(talib.EMA, self.data.Close, 20)
        self.lowest_price = None
        self.highest_price = None
        self.retry_count = 0
        self.stop_loss_long = 0
        self.stop_loss_short = 0
        self.tops = []
        self.top_happened = False
        self.bottoms = []
        self.slope = 0
        self.intercept = 0
    def next(self):
        # Calculate stop prices and take profits
        self.lowest_price = min(self.data.Low[-1], self.data.Low[-2], self.data.Low[-3], self.data.Low[-4]) 
        self.highest_price = max(self.data.High[-1], self.data.High[-2], self.data.High[-3], self.data.High[-4])
        self.stop_loss_long = (self.lowest_price - (self.data.Close[-1] - self.lowest_price)) * 0.9999
        self.stop_loss_short = (self.highest_price + (self.highest_price - self.data.Close[-1])) * 1.0001

        # Find last Top
        if len(self.orders) > 0:
            self.orders[-1].cancel()
        if self.data.High[-2] > self.data.High[-1] and self.data.High[-2] > self.data.High[-3]:
            self.tops.append(self.data.High[-2])
            self.top_happened = True
        else:
            self.top_happened = False
        if len(self.tops) > 0 and self.top_happened:
            self.slope = self.tops[-1] - self.data.High[-1]
            self.intercept = self.data.High[-1] - self.slope
        else:
            self.intercept = 0
        # Open new positions based on conditions
        if not self.position and self.data.Close is not None and self.ema8[-1] > self.ema20[-1] and self.rsi > self.rsi_middle and self.intercept != 0:
            self.buy(sl=self.intercept * 0.995, limit=self.intercept*1.00002, tp=self.intercept*1.005)
            self.retry_count = 0

        # Short position -> cancelled because of start of bullrun
        # if not self.position and self.data.Close is not None and self.ema8[-1] < self.ema20[-1] and self.rsi < self.rsi_middle:
        #     self.sell(sl=self.stop_loss_short, tp=(self.data.Close-((self.highest_price - self.data.Close[-1])*self.take_profit/10))* 0.9999)
        #     self.retry_count = 0

# Run backtest
bt = Backtest(df, IFR2Strategy, cash=100, margin=0.1)
stats = bt.run()
# stats = bt.optimize(
#         kc_period = range(4, 20, 1),
#         kc_mult = range(1, 20, 1),
#         #rsi_period = range(2, 8, 1),
#         #take_profit = range(15, 25, 1),
#         maximize='Return [%]')

# Display results
print(stats)
bt.plot()