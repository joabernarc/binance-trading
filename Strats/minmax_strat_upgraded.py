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
    kc_mult = 1
    max_retry_count = 2
    sl_mult = 2
    sizing = 27777
    rsi_period = 8
    over_bought = 50
    over_sold = 45
    daily_target = 110
    def init(self):
        # Calculate rsi oscillator and Keltner Channels
        self.rsi = self.I(talib.RSI, self.data.Close, self.rsi_period)
        self.kc = self.I(KeltnerChannels, self.data, self.kc_period, self.kc_mult)
        self.lowest_price = None
        self.highest_price = None
        self.upperKC = None
        self.lowerKC = None
        self.retry_count = 0
        self.daily_counter = 0
        self.can_trade = True
        self.daily_base_equity = 100
    def next(self):
        # Stop trading based on daily loss/profit
        if self.equity >= (self.daily_base_equity*(self.daily_target/100)):
            self.position.close()
            self.can_trade = False
        self.daily_counter = self.daily_counter + 1
        if self.daily_counter%288 == 0:
            self.can_trade = True
            self.daily_base_equity = self.equity

        # Calculate stop prices and take profits
        self.lowest_price = min(self.data.Low[-1], self.data.Low[-2])
        self.highest_price = max(self.data.High[-1], self.data.High[-2])
        self.upperKC = round(self.kc[2][-1], 5)
        self.lowerKC = round(self.kc[0][-1], 5)
        #print('self.data.Close:', self.data.Close)
        #print('self.kc inside loop:', self.upperKC)
        #print('self.kcSend:', self.upperKCTESTE[-1])

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
        if not self.position and self.data.Close is not None and self.data.Close[-1] >= self.upperKC and self.rsi[-1] >= self.over_sold and self.can_trade:
            self.retry_count = 0
            self.buy(sl=(self.lowest_price*1.0002)*(1 - (self.sl_mult*0.001)), limit=self.lowest_price*1.00002, tp=self.data.High[-1])
        if not self.position and self.data.Close is not None and self.data.Close[-1] <= self.lowerKC and self.rsi[-1] <= self.over_bought and self.can_trade:
            self.retry_count = 0
            self.sell(sl=(self.highest_price*0.9998)*(1 + (self.sl_mult*0.001)), limit=self.highest_price*0.99998, tp=self.data.Low[-1])

# Extra optimization function
# def optim_func(series):
#     return series['Return [%]'] / series['Max. Drawdown [%]']

# Run backtest
bt = Backtest(df, KeltnerStrategy, cash=100, margin=0.1)
stats = bt.run()
# stats = bt.optimize(
#         #kc_period = range(6, 10, 1),
#         #kc_mult = range(1, 6, 1),
#         #max_retry_count = range(1, 4, 1),
#         #sl_mult = range(1, 10, 1),
#         #rsi_period = range(7, 13, 1),
#         #over_bought = range(50, 70, 5),
#         #over_sold = range(30, 50, 5),
#         daily_target = range(106, 112, 1),
#         maximize='Max. Drawdown [%]')
#         #maximize=optim_func)

# Display results
print(stats)
bt.plot()