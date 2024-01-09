import time
import pyupbit
import datetime
import numpy as np

access = "your-access"  # 본인의 엑세스 키 입력
secret = "your-secret"  # 본인의 시크릿 키 입력

def get_target_price(ticker, k):
    """변동성 돌파 전략으로 매수 목표가 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
    target_price = df.iloc[0]['close'] + (df.iloc[0]['high'] - df.iloc[0]['low']) * k
    return target_price

def get_start_time(ticker):
    """시작 시간 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
    start_time = df.index[0]
    return start_time


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

def get_ror(k=0.5):
    """수익률(Return on Rate) 계산"""
    df = pyupbit.get_ohlcv("KRW-BTC", count=7)
    df['range'] = (df['high'] - df['low']) * k
    df['target'] = df['open'] + df['range'].shift(1)
    df['ror'] = np.where(df['high'] > df['target'],
                         df['close'] / df['target'],
                         1)
    ror = df['ror'].cumprod().iloc[-2]
    return ror


def get_optimal_k():
    """최적의 k 값 탐색"""
    max_ror = 0
    optimal_k = 0.5
    for k in np.arange(0.1, 1.0, 0.1):
        ror = get_ror(k)
        if ror > max_ror:
            max_ror = ror
            optimal_k = k
    return optimal_k

# 로그인
upbit = pyupbit.Upbit(access, secret)
print("autotrade start")

optimal_k = get_optimal_k()
last_update_time = datetime.datetime.now()

# 자동매매 시작
while True:
    try:
        now = datetime.datetime.now()
        start_time = get_start_time("KRW-BTC")
        end_time = start_time + datetime.timedelta(days=1)

        # 매일 오전 9시에 optimal_k 업데이트
        if now.hour == 9 and (now - last_update_time).seconds > 3600:
            optimal_k = get_optimal_k()
            last_update_time = now
            print(f"Updated optimal k to {optimal_k}")

        if start_time < now < end_time - datetime.timedelta(minutes=50):
            target_price = get_target_price("KRW-BTC", optimal_k)
            current_price = get_current_price("KRW-BTC")

            if target_price < current_price:
                krw = get_balance("KRW")
                if krw > 5000:
                    upbit.buy_market_order("KRW-BTC", krw*0.9995)
        else:
            btc = get_balance("BTC")
            if btc > 0.00008:
                upbit.sell_market_order("KRW-BTC", btc*0.9995)

        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
