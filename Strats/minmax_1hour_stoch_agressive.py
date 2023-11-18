from backtesting import Backtest, Strategy
from backtesting.lib import crossover, barssince
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
klines = client.get_historical_klines("agixusdt", Client.KLINE_INTERVAL_1HOUR, "17 March, 2023", klines_type=HistoricalKlinesType.FUTURES)
df = pd.DataFrame(klines, columns = ['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
df = df.astype({'OpenTime':'float', 'Open':'float', 'High':'float', 'Low':'float', 'Close':'float', 'Volume':'float'})
df = df.iloc[:,:6]

# Add Keltner Channels to the DataFrame
KC=pd.DataFrame(ta.kc(df.High, df.Low, df.Close).dropna().round(2))
df = df.join(KC)
df.set_index("OpenTime", inplace=True)
df.index = pd.to_datetime(df.index, unit='ms')
df=df[df.High!=df.Low]
print('len:', len(df))

# Define indicator function
def KeltnerChannels(data, kc_period, kc_mult):
    kc = ta.kc(high=df.High, low=df.Low, close=df.Close, length=kc_period, scalar=kc_mult/20)
    #print('kc:', kc)
    kc = np.array(kc)
    return kc

# Define strategy class
class KeltnerStrategy(Strategy):
    kc_period = 8
    kc_mult = 3
    max_retry_count = 2
    bb_period = 12
    bb_std = 18
    sl_mult = 4
    sizing = 27777
    daily_target = 120
    
    def init(self):
        # Calculate stochastic oscillator and Keltner Channels
        self.slowk, self.slowd = self.I(talib.STOCH, self.data.High, self.data.Low, self.data.Close, 8, 3, 0, 3)
        self.kc = self.I(KeltnerChannels, self.data, self.kc_period, self.kc_mult)
        self.ema8 = self.I(talib.EMA, self.data.Close, self.kc_period)
        self.ema80 = self.I(talib.EMA, self.data.Close, 80)
        self.lowest_price = None
        self.highest_price = None
        self.upperKC = None
        self.lowerKC = None
        self.retry_count = 0
        self.daily_counter = 0
        self.can_trade = False
        self.daily_base_equity = 100
        self.tp_long = 0
        self.tp_short = 0
        self.sl_long = 0
        self.sl_short = 0
    def next(self):
        # Stop trading based on daily loss/profit

        # if self.equity >= (self.daily_base_equity*(self.daily_target/100)):
        #     self.position.close()
        #     self.can_trade = False
        # self.daily_counter = self.daily_counter + 1
        # if self.daily_counter%288 == 0:
        #     self.can_trade = True
        #     self.daily_base_equity = self.equity

        # Calculate stop prices and take profits
        self.tp_long = max(self.data.High[-1], self.data.High[-2])
        self.tp_short = min(self.data.Low[-1], self.data.Low[-2])
        self.lowest_price = self.data.Low[-1] #+ ((self.data.High - self.data.Low)*(self.test/10)) #min(self.data.Low[-1], self.data.Low[-2])
        self.highest_price = self.data.High[-1] #- ((self.data.High - self.data.Low)*(self.test/10))#max(self.data.High[-1], self.data.High[-1])
        if self.ema8 > self.ema80:
            self.sl_long = None
            self.sl_short = (self.highest_price*0.9998)*(1 + (self.sl_mult*0.001))
        if self.ema8 < self.ema80:
            self.sl_long = (self.lowest_price*1.0002)*(1 - (self.sl_mult*0.001))
            self.sl_short = None
        
        self.upperKC = round(self.kc[2][-1], 5)
        self.lowerKC = round(self.kc[0][-1], 5)

        # Close positions based on conditions
        if len(self.orders) > 0:
            self.orders[-1].cancel()
        if self.position.is_long:
            self.retry_count = self.retry_count + 1
            if self.retry_count > self.max_retry_count:
                self.position.close()
            else:
                self.trades[-1].tp = self.highest_price
        if self.position.is_short:
            self.retry_count = self.retry_count + 1
            if self.retry_count > self.max_retry_count:
                self.position.close()
            else:
                self.trades[-1].tp = self.lowest_price
       
        # Open new positions based on conditions
        if not self.position and self.data.Close is not None and self.data.Close[-1] >= self.upperKC:# and self.data.Close[-1] > self.data.Close[-2]: #and self.data.Close[-1] < self.bbupper[-1]:
            self.retry_count = 0
            self.buy(sl=self.sl_long, limit=self.lowest_price*1.00002, tp=self.highest_price)
        if not self.position and self.data.Close is not None and self.data.Close[-1] <= self.lowerKC: #and self.data.Close[-1] < self.data.Close[-2]: #and self.data.Close[-1] > self.bblower[-1]:
            self.retry_count = 0
            self.sell(sl=self.sl_short, limit=self.highest_price*0.99998, tp=self.lowest_price)

# Extra optimization function
# def optim_func(series):
#     return series['Return [%]'] * series['Win Rate [%]']

# Run backtest
bt = Backtest(df, KeltnerStrategy, cash=100, margin=0.1)
stats = bt.run()
# stats = bt.optimize(
#         kc_period = range(6, 13, 1),
#         kc_mult = range(1, 15, 2),
#         #max_retry_count = range(2, 6, 1),
#         #bb_period = range(10, 20, 2),
#         #bb_std = range(2, 20, 2),
#         #sl_mult = range(4, 13, 1),
#         #daily_target = range(110, 150, 5),
#         maximize='Return [%]')
#         #maximize=optim_func) 

# Display results
print(stats)
bt.plot()