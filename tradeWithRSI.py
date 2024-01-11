import time
import pyupbit
import pandas as pd
import logging

# 로깅 설정
logging.basicConfig(filename='trading_log.log', level=logging.INFO, format='%(asctime)s %(message)s')

access = ""  # 본인의 엑세스 키 입력
secret = ""  # 본인의 시크릿 키 입력
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

def get_buy_sell_signals(minute_df, day_df, buy_threshold=30, sell_threshold=70, continuous_count=3):
    rsi = get_rsi(minute_df)
    global past_rsi

    # 현재 RSI 추가 및 과거 데이터 유지
    past_rsi.append(rsi.iloc[-1])
    past_rsi = past_rsi[-continuous_count:]  # 최근 연속된 RSI 값만 유지

    # 리스트가 충분한 길이에 도달했는지 확인
    if len(past_rsi) < continuous_count:
        return False, False  # 충분한 데이터가 없으면 매매 신호를 생성하지 않음

    # 연속된 과매수/과매도 상태 확인
    overbought = all(r > sell_threshold for r in past_rsi[:-1])
    oversold = all(r < buy_threshold for r in past_rsi[:-1])

    # RSI 상단선/하단선 돌파 여부
    buy_signal = oversold and rsi.iloc[-1] >= buy_threshold
    sell_signal = overbought and rsi.iloc[-1] <= sell_threshold

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

    if last_data_update_time is None or (current_time - last_data_update_time) > 1:  # 예: 1초마다 데이터 업데이트
        minute_df_cache = pyupbit.get_ohlcv("KRW-BTC", interval="minute1", count=200)
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

    if sell_signal or check_stop_loss(current_price):
        # 매도 로직
        btc = get_balance("BTC")
        btc_value = btc * current_price  # BTC 잔고의 현재 원화 가치 계산
        if btc_value > 5000:  # 잔고 가치가 5,000원 이상일 때 매도
            upbit.sell_market_order("KRW-BTC", btc)
            buy_price = None  # 매수 가격 초기화


while True:
    try:
        trade_logic()        
        time.sleep(1)  # API 호출 빈도 조절
    except Exception as e:
        logging.error(f"Error: {e}")
        time.sleep(60)  # 오류 발생 시 재시도 대기 시간 증가