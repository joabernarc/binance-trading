from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import talib
import pandas as pd
import pandas_ta as ta
import config
import numpy as np
from binance.client import Client
from binance.enums import HistoricalKlinesType

# Fetch historical data
client = Client(config.API_KEY, config.API_SECRET)
klines = client.get_historical_klines("agixusdt", Client.KLINE_INTERVAL_1DAY, "14 September, 2023", klines_type=HistoricalKlinesType.FUTURES)
df = pd.DataFrame(klines, columns = ['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
df = df.astype({'OpenTime':'float', 'Open':'float', 'High':'float', 'Low':'float', 'Close':'float', 'Volume':'float'})
df = df.iloc[:,:6]

# Add Bollinger Bands to the DataFrame
BB = pd.DataFrame(ta.bbands(df.Close, length=20, std=2).fillna(sum(df.Close)/len(df)))
df = df.join(BB)
df.set_index("OpenTime", inplace=True)
df.index = pd.to_datetime(df.index, unit='ms')
df=df[df.High!=df.Low]

# Display the length of the DataFrame
print('len:', len(df))

# Define indicatior function

def BollingerBands(data, bb_period, bb_std):
    bb = ta.bbands(close=df.Close, length=bb_period, std=bb_std/10)
    bb = bb.iloc[:,:3]
    bb = np.array(bb)
    return bb

# Define strategy class
class BollingerStrategy(Strategy):
    bb_period = 20
    bb_std = 20
    ema = 80
    sl_mult = 10
    tp_mult = 20
    sizing = 1
    
    def init(self):
        # Add Bollinger Bands, EMA indicator
        self.bbands = self.I(BollingerBands, self.data, self.bb_period, self.bb_std)
        self.ema8 = self.I(talib.EMA, self.data.Close, 8)
        self.ema80 = self.I(talib.EMA, self.data.Close, 80)
        self.lowest_price = None
        self.highest_price = None
        self.stop_price_short = 0
        self.stop_price_long = 0
        self.retry_count = 0
    def next(self):
       # Get upper and lower Bollinger Bands
        self.upperBB = round(self.bbands[2][-1], 5)
        self.lowerBB = round(self.bbands[0][-1], 5)
        # Calculate stop prices and take profits
        self.stop_price_long = self.data.Close[-1] * (1-(self.sl_mult*0.0001))
        self.stop_price_short = self.data.Close[-1] * (1+(self.sl_mult*0.0001))
        self.take_profit_long = self.data.Close[-1] * (1+(self.tp_mult*0.0001))
        self.take_profit_short = self.data.Close[-1] * (1-(self.tp_mult*0.0001))
        # Close positions based on conditions
        if self.position.is_long:
            if self.ema8[-1] <= self.upperBB or self.position.pl_pct > self.tp_mult/1000:
                self.position.close()
                self.retry_count = 0
        if self.position.is_short:
            if self.ema8[-1] >= self.lowerBB or self.position.pl_pct > self.tp_mult/1000:
                self.position.close()
                self.retry_count = 0
        # Open new positions based on conditions
        if not self.position and self.data.Close is not None and self.data.Close[-1] < self.lowerBB:
            self.buy(sl=self.stop_price_long)
            self.retry_count = 0
        if not self.position and self.data.Close is not None and self.data.Close[-1] > self.upperBB:
            self.sell(sl=self.stop_price_short)
            self.retry_count = 0

# Run backtest
bt = Backtest(df, BollingerStrategy, cash=100, margin=0.1)
stats = bt.run()
# stats = bt.optimize(
#         #bb_period = range(10, 30, 2),
#         #bb_std = range(10, 30, 2),
#         #atr_divisor = range(10, 20, 1),
#         #ema = range(60, 210, 10),
#         sl_mult = range(10, 30, 2),
#         tp_mult = range(10, 30, 5),
#         maximize='Return [%]')
#         #maximize='Avg. Drawdown [%]')

# Display results
print(stats)
bt.plot()