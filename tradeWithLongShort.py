import time
import pyupbit
import datetime
import logging

# 로깅 설정
logging.basicConfig(filename='trading_log.log', level=logging.INFO, 
                    format='%(asctime)s %(message)s', encoding='utf-8')

class AutoTrader:
    def __init__(self, access, secret):
        self.upbit = pyupbit.Upbit(access, secret)
        self.long_target = None
        self.short_target = None
        self.start_time = None
        self.buy_price = None
        self.interval = 'minute60'  # 'day', 'minute240', 'minute60', 'minute30', 'minute1'
        self.ticker = "KRW-BTC"
        self.MIN_TRADE_VALUE = 5000

    def get_target_price(self):
        df = pyupbit.get_ohlcv(self.ticker, interval=self.interval, count=2)
        volatility = df.iloc[0]['high'] - df.iloc[0]['low']
        self.long_target = df.iloc[0]['close'] + volatility * 0.5
        self.short_target = df.iloc[0]['close'] - volatility * 0.5

    def get_balance(self, ticker):
        balances = self.upbit.get_balances()
        for b in balances:
            if b['currency'] == ticker:
                if b['balance'] is not None:
                    return float(b['balance'])
                else:
                    return 0
        return 0
    def get_current_price(self):
        return pyupbit.get_orderbook(ticker=self.ticker)["orderbook_units"][0]["ask_price"]

    def check_stop_loss(self, current_price):
        if self.buy_price is None:
            return False
        return current_price < self.buy_price * 0.95

    def get_start_time(self):
        df = pyupbit.get_ohlcv(self.ticker, interval=self.interval, count=1)
        self.start_time = df.index[0]

    def get_interval_minutes(self):
        intervals = {'day': 1440, 'minute240': 240, 'minute60': 60, 'minute30': 30, 'minute1': 1}
        return intervals.get(self.interval, 0)

    def trade_logic(self):
        now = datetime.datetime.now()    

        if self.start_time is None or self.long_target is None or self.short_target is None or now >= self.start_time + datetime.timedelta(minutes=self.get_interval_minutes()):
            self.get_start_time()
            self.get_target_price()
        
        # logging.info(f"long_target: {self.long_target}")
        # logging.info(f"short_target: {self.short_target}")

        current_price = self.get_current_price()
        
        if self.long_target is not None and self.short_target is not None:
            if current_price > self.long_target:                
                logging.info(f"매수: {current_price}")                
                krw = self.get_balance("KRW")
                fee_rate = 0.0005
                buy_amount = krw / (1 + fee_rate)
                if buy_amount > self.MIN_TRADE_VALUE:
                    self.upbit.buy_market_order(self.ticker, buy_amount)
                    self.buy_price = current_price
                    

            elif current_price < self.short_target or self.check_stop_loss(current_price):                
                logging.info(f"매도: {current_price}")                
                btc = self.get_balance("BTC")
                btc_value = btc * current_price
                if btc_value > self.MIN_TRADE_VALUE:
                    self.upbit.sell_market_order(self.ticker, btc)
                    self.buy_price = None

if __name__ == "__main__":
    access = ""  # 사용자의 엑세스 키
    secret = ""  # 사용자의 시크릿 키

    auto_trader = AutoTrader(access, secret)
    logging.info("autotrade start")

    while True:
        try:
            auto_trader.trade_logic()    
            time.sleep(2)
        except Exception as e:
            logging.error(f"API 요청 중 오류 발생: {e}")
            time.sleep(60)
