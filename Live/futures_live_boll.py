import config
import pandas as pd
import pandas_ta as ta
from binance.client import Client
from binance.enums import *
from binance.streams import ThreadedWebsocketManager
from binance.exceptions import BinanceAPIException
from talib import *
from talib.abstract import *
import time

# Binance WebSocket endpoint for Kline updates
#TESTNET = "wss://stream.binancefuture.com/ws"
#LIVE = "wss://fstream.binance.com/ws"

# Constants for trading
TRADE_SYMBOL = 'AGIXUSDT'
TRADE_QUANTITY = 0.01
last_trade_quantity = 0
cum_partial_quantity = 0
quote_order_quantity = 800
quantity = 0
isPartial = False
close = 0
lowest = 0
highest = 0
profit = 0.0
take_profit_order = {}
stop_loss_order = {}
last_order = {}
retry_count = 0
open_new_order_asap = False
isLong = False
isShort = False
upperBollinger = 0
lowerBollinger = 0
above_upper_bollinger = False
below_lower_bollinger = False
kc_period = 6
kc_mult = 18/20
bb_period = 20
bb_std = 20/10
max_retry_count = 5

client = Client(config.API_KEY, config.API_SECRET)

# Utility function for placing orders
def order(side, quantity, symbol, price, order_type, reduce_only, timeInForce=TIME_IN_FORCE_GTC):
    global last_order, retry_count, take_profit_order, stop_loss_order
    try:
        # Print order details
        print("sending order, price:", price)
        print('order type:', order_type)

        # Place different types of orders based on order_type
        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            last_order = client.futures_create_order(symbol=symbol, side=side, type=order_type, timeInForce=timeInForce, quantity=quantity, price=price, reduceOnly=reduce_only)
            print('limit order: ', last_order['origType'] + ', ' + last_order['status'])
        if order_type == FUTURE_ORDER_TYPE_MARKET:
            last_order = client.futures_create_order(symbol=symbol, side=side, type=order_type, quantity=quantity, reduceOnly=reduce_only)
            print('market order: ', last_order['origType'] + ', ' + last_order['status'])
            retry_count = 0
        if order_type == FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET:
            take_profit_order = client.futures_create_order(symbol=symbol, side=side, type=order_type, timeInForce=timeInForce, stopPrice=price, closePosition=True)
            print('take profit order: ', take_profit_order['origType'] + ', ' + take_profit_order['status'])
        if order_type == FUTURE_ORDER_TYPE_STOP_MARKET:
            stop_loss_order = client.futures_create_order(symbol=symbol, side=side, type=order_type, timeInForce=timeInForce, stopPrice=price, closePosition=True)
            print('stop market order: ', stop_loss_order['origType'] + ', ' + stop_loss_order['status'])
    except BinanceAPIException as e:
        print("an exception occured - {}".format(e))
        if e.code == -2021:
            print('as would trigger immediately, sending market order, it was:', order_type)
            print('price was:', price)
            market_order_succeeded = order(side, quantity, symbol, price, FUTURE_ORDER_TYPE_MARKET, True)
        return False

    return True

# Calculate Bollinger Bands using historical klines data.
def bollinger_bands(last_close):
    # Args:
    #     last_close (float): Last closing price
    # Returns:
    #     bool: True if calculation was successful, False otherwise
    global isLong, isShort, retry_count, open_new_order_asap, above_upper_bollinger, below_lower_bollinger, bb_period, bb_std, upperBollinger, lowerBollinger
    try:
        # Fetch historical klines data
        klines = client.get_historical_klines("btcusdt", Client.KLINE_INTERVAL_15MINUTE, "1 March, 2023", klines_type=HistoricalKlinesType.FUTURES)
        df = pd.DataFrame(klines, columns = ['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', '6', '7', '8', '9', '10', '11'])
        df = df.astype({'OpenTime':'float', 'Open':'float', 'High':'float', 'Low':'float', 'Close':'float', 'Volume':'float'})
        df = df.iloc[:,:6]
        df.set_index("OpenTime", inplace=True)
        df.index = pd.to_datetime(df.index, unit='ms')
        df=df[df.High!=df.Low]

        # Calculate Bollinger Bands
        BB=pd.DataFrame(ta.bbands(close=df.Close, length=bb_period, std=bb_std))
        BB = BB.iloc[:,:3]
        print('bb:', BB)

        # Determine upper and lower Bollinger Bands based on the last available candle
        timenowminutes = time.gmtime().tm_min
        print('minutes now:', timenowminutes)
        lastindex = df.index[-1].minute
        print('last minute:', lastindex)
        if timenowminutes == lastindex:
            upperBollinger = round(BB[f'BBU_{bb_period}_{bb_std}'][-2], 5)
            lowerBollinger = round(BB[f'BBL_{bb_period}_{bb_std}'][-2], 5)
        else:
            upperBollinger = round(BB[f'BBU_{bb_period}_{bb_std}'][-1], 5)
            lowerBollinger = round(BB[f'BBL_{bb_period}_{bb_std}'][-1], 5)
        print('upperBollinger:', upperBollinger)
        print('lowerBollinger:', lowerBollinger)
        above_upper_bollinger = float(last_close) > upperBollinger
        below_lower_bollinger = float(last_close) < lowerBollinger
    except Exception as e:
        print("an exception occured - {}".format(e))
        return False

#Handle user information update callback
def user_callback(userDataUpdate):
    global open_new_order_asap, isLong, isShort, isPartial, last_trade_quantity, quote_order_quantity, cum_partial_quantity
    print('>>>>>userDataUpdate>>>>>', userDataUpdate['e'])

    #ACCOUNT_UPDATE means a trade was finished and your balance was updated
    if userDataUpdate['e'] == 'ACCOUNT_UPDATE':
        balance = userDataUpdate['a']['B'][0]['wb']
        print('account balance:', balance)
        quote_order_quantity = (float(balance) * 10) * 0.95
    
    #ORDER_TRADE_UPDATE means a trade was updated
    if userDataUpdate['e'] == 'ORDER_TRADE_UPDATE': 
        print(userDataUpdate['o']['ot'] + ', ' + userDataUpdate['o']['X'])
        if userDataUpdate['o']['X'] == ORDER_STATUS_NEW or userDataUpdate['o']['X'] == ORDER_STATUS_CANCELED:
            open_new_order_asap = False
        elif userDataUpdate['o']['ot'] == FUTURE_ORDER_TYPE_LIMIT and (userDataUpdate['o']['X'] == ORDER_STATUS_FILLED or userDataUpdate['o']['X'] == ORDER_STATUS_PARTIALLY_FILLED):
            open_new_order_asap = True
            
            if userDataUpdate['o']['X'] == ORDER_STATUS_PARTIALLY_FILLED and userDataUpdate['o']['R'] == False:
                isPartial = True
                last_trade_quantity = userDataUpdate['o']['l']
                cum_partial_quantity = userDataUpdate['o']['z']
            else: 
                isPartial = False
                last_trade_quantity = userDataUpdate['o']['z']
            if userDataUpdate['o']['S'] == SIDE_BUY and userDataUpdate['o']['R'] == False:
                isLong = True
            if userDataUpdate['o']['S'] == SIDE_SELL and userDataUpdate['o']['R'] == False:
                isShort = True
        elif userDataUpdate['o']['S'] == SIDE_SELL and userDataUpdate['o']['cp'] == True: #and userDataUpdate['o']['ot'] == FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET:
                open_new_order_asap = False
                isLong = False
                cancel_all_orders = client.futures_cancel_all_open_orders(symbol=TRADE_SYMBOL)
                print('canceled orders:', cancel_all_orders)
        elif userDataUpdate['o']['S'] == SIDE_BUY and userDataUpdate['o']['cp'] == True: #and userDataUpdate['o']['ot'] == FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET:
                open_new_order_asap = False
                isShort = False
                cancel_all_orders = client.futures_cancel_all_open_orders(symbol=TRADE_SYMBOL)
                print('canceled orders:', cancel_all_orders)
        elif userDataUpdate['o']['ot'] == FUTURE_ORDER_TYPE_MARKET and userDataUpdate['o']['S'] == SIDE_SELL and userDataUpdate['o']['R'] == True:
                open_new_order_asap = False
                isLong = False
                cancel_all_orders = client.futures_cancel_all_open_orders(symbol=TRADE_SYMBOL)
                print('canceled orders:', cancel_all_orders)
        elif userDataUpdate['o']['ot'] == FUTURE_ORDER_TYPE_MARKET and userDataUpdate['o']['S'] == SIDE_BUY and userDataUpdate['o']['R'] == True:
                open_new_order_asap = False
                isShort = False
                cancel_all_orders = client.futures_cancel_all_open_orders(symbol=TRADE_SYMBOL)
                print('canceled orders:', cancel_all_orders)
        elif userDataUpdate['o']['X'] == ORDER_STATUS_EXPIRED and userDataUpdate['o']['o'] == FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET:
            open_new_order_asap = False
        elif userDataUpdate['o']['X'] == 'LIQUIDATION':
            open_new_order_asap = False
            isLong = False
            isShort = False

    #Change strategy based on profit/loss

    # data = client.futures_position_information(symbol = TRADE_SYMBOL)
    # for n in range(len(data)):  
    #     if data[n]["symbol"] == TRADE_SYMBOL: 
    #         print('position updated:', data[n])
    #pegar o rp que vem numa ORDER_TRADE_UPDATE em 'rp' e somar localmente; assim consigo definir loss maximo diario se precisar.

#Handle kline value update, ordering
def kline_callback(kline):
    global open_new_order_asap, isPartial, quantity, last_order, retry_count, close, lowest, highest, isLong, isShort, max_retry_count, last_trade_quantity, quote_order_quantity, above_upper_bollinger, below_lower_bollinger, cum_partial_quantity, take_profit_order
    print('received kline update')
    
    candle = kline['data']['k']
    is_candle_closed = candle['x']

    #Update indicator values based on closed candle
    if is_candle_closed:
        candle = kline['data']['k']
        
        close = round(float(candle['c']), 4)
        lowest = round(float(candle['l']), 4)
        highest = round(float(candle['h']), 4)
        quantity = round(quote_order_quantity/close)
        print('quantity:', quantity)
        print('candle closed, values:')
        print('close:', close)
        print('lowest:', lowest)
        print('highest:', highest)
        get_open_orders = client.futures_get_open_orders(symbol=TRADE_SYMBOL)
        print('open orders:', get_open_orders)
        if len(get_open_orders) > 0:
            for open_order in get_open_orders:
                if open_order['type'] == ORDER_TYPE_LIMIT:
                    cancel_limit_order = client.futures_cancel_order(symbol=TRADE_SYMBOL, orderId=open_order['orderId'])
                    print('canceled orders:', cancel_limit_order)
                if open_order['type'] == FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET:
                    cancel_tp_order = client.futures_cancel_order(symbol=TRADE_SYMBOL, orderId=open_order['orderId'])
                    print('canceled orders:', cancel_tp_order)
        bollinger_bands(close)
        print('above_upper_bollinger?', above_upper_bollinger)
        print('below_lower_bollinger?', below_lower_bollinger)

        #Start position based on conditions
        if isLong:
            if close >= lowerBollinger:
                if isPartial:
                    order_succeeded = order(SIDE_SELL, cum_partial_quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_MARKET, True)
                else:
                    order_succeeded = order(SIDE_SELL, last_trade_quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_MARKET, True)
        elif isShort:
            if close <= upperBollinger:
                if isPartial:
                    order_succeeded = order(SIDE_BUY, cum_partial_quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_MARKET, True)
                else:
                    order_succeeded = order(SIDE_BUY, last_trade_quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_MARKET, True)

        else:
            if below_lower_bollinger:
                order_succeeded = order(SIDE_BUY, quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_LIMIT, False)
                retry_count = 0
            if above_upper_bollinger:
                order_succeeded = order(SIDE_SELL, quantity, TRADE_SYMBOL, close, FUTURE_ORDER_TYPE_LIMIT, False)
                retry_count = 0
    
    #When a order is completed and we need a new order placement as soon as possible
    if open_new_order_asap:
        if isLong:
            stop_price_long = round((close * 0.999), 4)
            stop_order_succeeded = order(SIDE_SELL, last_trade_quantity, TRADE_SYMBOL, stop_price_long, FUTURE_ORDER_TYPE_STOP_MARKET, True)
        elif isShort:
            stop_price_short = round((close * 1.001), 4)
            stop_order_succeeded = order(SIDE_BUY, last_trade_quantity, TRADE_SYMBOL, stop_price_short, FUTURE_ORDER_TYPE_STOP_MARKET, True)

#Start the threaded websocket to Binance API    
twm = ThreadedWebsocketManager(api_key=config.API_KEY, api_secret=config.API_SECRET)
twm.start()
streams = ['agixusdt@kline_15m']
twm.start_futures_multiplex_socket(callback=kline_callback, streams=streams)
twm.start_futures_user_socket(callback=user_callback) #//WORKS!!!!!!!!!

timeout = 1 # seconds
while True and twm.is_alive():
    twm.join(timeout=timeout) # Give twm a call to process the streaming
twm.stop()