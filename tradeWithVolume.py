import time
import pyupbit
import pandas as pd
import logging

# 로깅 설정
logging.basicConfig(filename='trading_log.log', level=logging.INFO, format='%(asctime)s %(message)s')

access = ""
secret = ""
upbit = pyupbit.Upbit(access, secret)
logging.info("autotrade start")

# 매수 가격 추적을 위한 전역 변수
buy_price = None
last_data_update_time = None
minute_df_cache = None
day_df_cache = None
# RSI 추적을 위한 전역 변수
past_rsi = []

def get_balance(ticker):
    """잔고 조회"""
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가 조회"""
    return pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]

def get_rsi(dataframe, period=14):
    delta = dataframe['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def is_upward_trend(dataframe, short_window=5, long_window=20):
    """상승 추세 여부 판단"""
    short_ma = dataframe['close'].rolling(window=short_window).mean()
    long_ma = dataframe['close'].rolling(window=long_window).mean()
    return short_ma.iloc[-1] > long_ma.iloc[-1]

def is_bullish_candlestick(dataframe):
    """현재 캔들이 양봉인지 판단 (시가보다 종가가 높은 경우)"""
    latest_candle = dataframe.iloc[-1]
    return latest_candle['open'] < latest_candle['close']

def is_high_volume(dataframe, hours=6, multiplier=2):
    """지난 일정 시간 동안 평균 거래량의 특정 배수를 초과하는지 판단"""
    # 최근 hours 시간 동안의 데이터 추출
    recent_data = dataframe.tail(hours)
    # 평균 거래량 계산
    avg_volume = recent_data['volume'].mean()
    # 현재 거래량
    current_volume = dataframe.iloc[-1]['volume']

    return current_volume > avg_volume * multiplier

def track_rsi_highs_lows(rsi_series, lookback=14):
    """RSI의 고점과 저점을 추적"""
    highs = []
    lows = []
    for i in range(lookback, len(rsi_series) - 1):
        if rsi_series.iloc[i] > rsi_series.iloc[i-1] and rsi_series.iloc[i] > rsi_series.iloc[i+1]:
            highs.append((i, rsi_series.iloc[i]))
        elif rsi_series.iloc[i] < rsi_series.iloc[i-1] and rsi_series.iloc[i] < rsi_series.iloc[i+1]:
            lows.append((i, rsi_series.iloc[i]))
    return highs, lows



def get_failure_swing_signals(rsi_series, overbought=70, oversold=30, lookback=14):
    """Failure Swing 신호를 파악"""
    highs, lows = track_rsi_highs_lows(rsi_series, lookback)

    top_failure_swing = False
    bottom_failure_swing = False

    if highs and lows and len(highs) > 1 and len(lows) > 1:
        latest_high = highs[-1]
        previous_low = lows[-2]

        latest_low = lows[-1]
        previous_high = highs[-2]

        # Top Failure Swing
        if latest_high[1] > overbought and latest_low[1] < previous_low[1]:
            top_failure_swing = True

        # Bottom Failure Swing
        if latest_low[1] < oversold and latest_high[1] > previous_high[1]:
            bottom_failure_swing = True

    return top_failure_swing, bottom_failure_swing

def get_buy_sell_signals(minute_df, day_df):
    rsi = get_rsi(minute_df)
    top_failure_swing, bottom_failure_swing = get_failure_swing_signals(rsi)

    # 양봉 및 고거래량 조건 확인
    bullish_candle = is_bullish_candlestick(minute_df)
    high_volume = is_high_volume(minute_df)
    candle_and_volume = bullish_candle and high_volume

    # 최종 매수 신호
    buy_signal = (bottom_failure_swing or candle_and_volume) and is_upward_trend(day_df)

    # 최종 매도 신호
    sell_signal = top_failure_swing
    return buy_signal, sell_signal



def check_stop_loss(current_price):
    """손절매 조건 체크"""
    global buy_price
    if buy_price is None:
        return False
    return current_price < buy_price * 0.95

def update_data():
    """데이터 업데이트 및 캐싱"""
    global last_data_update_time, minute_df_cache, day_df_cache
    current_time = time.time()

    if last_data_update_time is None or (current_time - last_data_update_time) > 5:  # 예: 5초마다 데이터 업데이트
        minute_df_cache = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=200)  # 1시간봉 데이터로 변경
        day_df_cache = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=20)
        last_data_update_time = current_time


def trade_logic():
    global buy_price
    update_data()  # 데이터 업데이트

    buy_signal, sell_signal = get_buy_sell_signals(minute_df_cache, day_df_cache)
    current_price = get_current_price("KRW-BTC")

    if buy_signal and not buy_price:
        # 매수 로직
        krw = get_balance("KRW")
        fee_rate = 0.0005  # 거래 수수료율 0.05%
        buy_amount = krw / (1 + fee_rate)  # 실제 매수에 사용할 금액
        if buy_amount > 5000:
            upbit.buy_market_order("KRW-BTC", buy_amount)
            buy_price = current_price  # 매수 가격 저장
            logging.info(f"Bought at {current_price}, amount: {buy_amount}")


    if sell_signal or check_stop_loss(current_price):
        # 매도 로직
        btc = get_balance("BTC")
        btc_value = btc * current_price  # BTC 잔고의 현재 원화 가치 계산
        if btc_value > 5000:  # 잔고 가치가 5,000원 이상일 때 매도
            upbit.sell_market_order("KRW-BTC", btc)
            buy_price = None  # 매수 가격 초기화
            logging.info(f"Sold at {current_price}, amount: {btc}")

while True:
    try:
        trade_logic()    
        time.sleep(1)  # API 호출 빈도 조절
    except Exception as e:
        logging.error(f"Error: {e}")
        time.sleep(60)  # 오류 발생 시 재시도 대기 시간 증가