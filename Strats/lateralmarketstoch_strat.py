from backtesting import Backtest, Strategy
from backtesting.lib import crossover, barssince, resample_apply
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
klines = client.get_historical_klines("agixusdt", Client.KLINE_INTERVAL_2HOUR, "25 October, 2023", klines_type=HistoricalKlinesType.FUTURES)
df = pd.DataFrame(klines, columns = ['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
df = df.astype({'OpenTime':'float', 'Open':'float', 'High':'float', 'Low':'float', 'Close':'float', 'Volume':'float'})
df = df.iloc[:,:6]

# Add Keltner Channels to the DataFrame
KC=pd.DataFrame(ta.kc(df.High, df.Low, df.Close).dropna().round(2))
df = df.join(KC)
df.set_index("OpenTime", inplace=True)
df.index = pd.to_datetime(df.index, unit='ms')
df=df[df.High!=df.Low]

# Display the length of the DataFrame
print('len:', len(df))

class LateralMarketStochStrategy(Strategy):
    kc_period = 6
    kc_mult = 18
    max_retry_count = 2
    bb_period = 10
    bb_std = 18
    sl_mult = 25
    tp_mult = 50
    stoch_k = 14
    stoch_d = 3
    stoch_high = 72
    stoch_low = 26
    stoch_smooth = 3
    #test = 3
    sizing = 27777
    daily_target = 120
    deep_vs_tp = 16
    
    def init(self):
        # Add Stochastic, EMA indicator
        self.ema8 = self.I(talib.EMA, self.data.Close, 8)
        self.ema80 = self.I(talib.EMA, self.data.Close, 80)
        self.slowk, self.slowd = self.I(talib.STOCH, self.data.High, self.data.Low, self.data.Close, self.stoch_k, self.stoch_d, 0, self.stoch_smooth)
        self.lowest_price = None
        self.highest_price = None
        self.retry_count = 0
        self.daily_counter = 0
        self.daily_base_equity = 100
        self.tendencia_alta = 0
        self.tendencia_baixa = 0
        self.ultimo_fundo = 0
        self.alvo = 0
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
        self.lowest_price = min(self.data.Low[-1], self.data.Low[-2]) #+ ((self.data.High - self.data.Low)*(self.test/10)) #min(self.data.Low[-1], self.data.Low[-2])
        self.highest_price = self.data.High[-1] #- ((self.data.High - self.data.Low)*(self.test/10))#max(self.data.High[-1], self.data.High[-1])

        # Find last Dip
        if self.data.Low[-3] > self.data.Low[-2] and self.data.Low[-2] < self.data.Low[-1]:
            self.ultimo_fundo = self.data.Low[-2]

        # Close positions based on conditions
        if self.position.is_long:
            #self.retry_count = self.retry_count + 1
            if self.retry_count > self.max_retry_count:
                self.position.close()
            # if crossover(self.slowk, 80):
            #     self.position.close()
                
        if self.position.is_short:
            #self.retry_count = self.retry_count + 1
            if self.retry_count > self.max_retry_count:
                self.position.close()
            if crossover(20, self.slowk):
                self.position.close()
       
        # Open new positions based on conditions
        if not self.position and self.data.Close is not None and self.ema8[-1] > self.ema80[-1] and crossover(self.slowk, self.slowd) and self.slowk[-1] > self.stoch_high:
            self.retry_count = 0
            self.alvo = self.data.Close[-1] + self.deep_vs_tp/10*abs(self.data.Close[-1] - self.ultimo_fundo)
            print(self.alvo, self.data.Close[-1], self.ultimo_fundo)
            if self.alvo <= self.data.Close[-1]:
                print("alvo menor q close")
                self.alvo = self.data.Close[-1] * 1+(self.tp_mult*0.001)
            self.buy(sl=(self.ultimo_fundo), tp=(self.alvo))
        # if not self.position and self.data.Close is not None and crossover(self.slowd, self.slowk) and self.slowk[-2] > self.stoch_high:
        #     self.retry_count = 0
        #     self.sell(sl=(self.data.Close[-1])*(1 + (self.sl_mult*0.001)), tp=(self.data.Close[-1])*(1 - (self.tp_mult*0.001)))

# Extra optimization function
# def optim_func(series):
#     return series['Return [%]'] / series['Max. Drawdown [%]']

# Run backtest
bt = Backtest(df, LateralMarketStochStrategy, cash=100, margin=0.25)
#stats = bt.run()
stats = bt.optimize(
        #kc_period = range(6, 20, 2),
        #kc_mult = range(1, 20, 2),
        #max_retry_count = range(2, 6, 1),
        #bb_period = range(10, 20, 2),
        #bb_std = range(10, 20, 2),
        #sl_mult = range(20, 30, 5),
        #tp_mult = range(37, 50, 10),
        #stoch_low = range(16, 28, 2),
        stoch_high = range(50, 80, 5),
        deep_vs_tp = range(10, 20, 1),
        #daily_target = range(110, 150, 5),
        maximize='Return [%]')
        #maximize=optim_func) 

# Display results
print(stats)
bt.plot()