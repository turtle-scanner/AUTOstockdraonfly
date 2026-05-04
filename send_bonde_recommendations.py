import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 프로젝트 경로 설정
TRADING_BOT_DIR = r"c:\1.auto bonde bot\trading_bot"
STRATEGY_DIR = r"c:\1.auto bonde bot\strategy_builder"
STOCKS_INFO_DIR = r"c:\1.auto bonde bot\stocks_info"

sys.path.append(TRADING_BOT_DIR)
sys.path.append(STRATEGY_DIR)
sys.path.append(STOCKS_INFO_DIR)

import kis_kospi_code_mst as kospi
import kis_kosdaq_code_mst as kosdaq
from telegram_notifier import send_telegram_message

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_bonde_rules(df, name, code):
    """
    사용자의 5가지 본데 핵심 규칙에 따라 종목 분석
    """
    if len(df) < 200: return None
    
    c = df['Close'].iloc[-1]
    v = df['Volume'].iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    sma150 = df['Close'].rolling(150).mean().iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    avg_vol_50 = df['Volume'].rolling(50).mean().iloc[-1]
    
    res = {"name": name, "code": code, "price": c, "category": "", "reason": ""}
    
    # 규칙 5: EP (Earnings/Event Pivot) - 오늘 대량 거래 + 급등
    if v > avg_vol_50 * 5 and (c - df['Close'].iloc[-2]) / df['Close'].iloc[-2] > 0.05:
        res["category"] = "🔥 규칙 5: EP (초강력 돌파)"
        res["reason"] = f"오늘 거래량이 평균 대비 {v/avg_vol_50:.1f}배 폭증하며 장대양봉 발생."
        return res

    # 규칙 2: VCP Tightness (깨알 같은 캔들)
    recent_10 = df.tail(10)
    volatility = (recent_10['High'].max() - recent_10['Low'].min()) / recent_10['Low'].min() * 100
    if volatility < 5.0 and c > sma50 > sma150:
        res["category"] = "⏳ 규칙 2: VCP Tightness (에너지 응축)"
        res["reason"] = f"최근 10일간 변동폭이 {volatility:.1f}%로 극도로 제한됨. 돌파 임박."
        return res

    # 규칙 3: 거래량 드라이업 (Dry-up)
    recent_vol_3 = df['Volume'].tail(3).mean()
    if recent_vol_3 < avg_vol_50 * 0.4 and c > sma50:
        res["category"] = "💧 규칙 3: 거래량 드라이업 (매도세 소멸)"
        res["reason"] = f"최근 3일 거래량이 평균의 {recent_vol_3/avg_vol_50*100:.1f}% 수준으로 마름."
        return res

    # 규칙 4: 2단계 상승 추세 초기 돌파
    if c > sma50 > sma150 > sma200:
        # 최근 20일 고점 돌파 여부
        high_20 = df['High'].iloc[-21:-1].max()
        if c > high_20 and df['Close'].iloc[-2] <= high_20:
            res["category"] = "🚀 규칙 4: 2단계 상승 초기 돌파"
            res["reason"] = f"정배열 상태에서 최근 20일 박스권 상단을 오늘 돌파함."
            return res

    # 규칙 1: 지연 반응 (Delayed Reaction) - 2~5일 전 EP 후 횡보
    for i in range(2, 6):
        prev_v = df['Volume'].iloc[-i]
        prev_c_change = (df['Close'].iloc[-i] - df['Close'].iloc[-i-1]) / df['Close'].iloc[-i-1]
        if prev_v > avg_vol_50 * 3 and prev_c_change > 0.07:
            # 그 이후로 횡보 중인지 확인
            after_ep = df.iloc[-i+1:]
            max_after = after_ep['High'].max()
            if c >= df['High'].iloc[-i] * 0.98: # 전고점 근처
                res["category"] = "⚡ 규칙 1: 지연 반응 돌파"
                res["reason"] = f"{i}일 전 강력한 EP 발생 후 에너지를 소화하고 다시 전고점 탈환 시도."
                return res

    return None

def send_recommendations():
    logger.info("Starting Bonde Recommendation Scan...")
    
    # 1. 대상 종목 선정 (ROE 10 이상, 시총 상위)
    df_kospi = kospi.get_kospi_master_dataframe(STOCKS_INFO_DIR)
    df_kosdaq = kosdaq.get_kosdaq_master_dataframe(STOCKS_INFO_DIR)
    
    # 컬럼 처리
    df_kospi = df_kospi.rename(columns={'한글명': 'name', 'ROE': 'roe', '시가총액': 'mcap'})
    df_kosdaq = df_kosdaq.rename(columns={'한글종목명': 'name', 'ROE(자기자본이익률)': 'roe', '전일기준 시가총액 (억)': 'mcap'})
    
    for df in [df_kospi, df_kosdaq]:
        df['roe'] = pd.to_numeric(df['roe'], errors='coerce').fillna(0)
        df['mcap'] = pd.to_numeric(df['mcap'], errors='coerce').fillna(0)

    # 필터링
    df_kospi = df_kospi[df_kospi['roe'] >= 10].sort_values('mcap', ascending=False).head(300)
    df_kosdaq = df_kosdaq[df_kosdaq['roe'] >= 10].sort_values('mcap', ascending=False).head(300)
    
    candidates = []
    for _, row in df_kospi.iterrows():
        candidates.append({"code": str(row['단축코드']).zfill(6) + ".KS", "name": row['name']})
    for _, row in df_kosdaq.iterrows():
        candidates.append({"code": str(row['단축코드']).zfill(6) + ".KQ", "name": row['name']})
    
    # 2. 데이터 다운로드
    tickers = [c['code'] for c in candidates]
    data = yf.download(tickers, period="1y", interval="1d", group_by='ticker', progress=True)
    
    results = []
    for stock in candidates:
        try:
            df = data[stock['code']].dropna()
            analysis = analyze_bonde_rules(df, stock['name'], stock['code'])
            if analysis:
                results.append(analysis)
        except: continue

    # 3. 텔레그램 리포트 생성
    if not results:
        send_telegram_message("🔍 현재 본데의 5가지 핵심 규칙에 부합하는 종목이 없습니다.")
        return

    msg = f"🌟 *[본데 전략 핵심 추천 종목]* ({datetime.now().strftime('%m/%d %H:%M')})\n"
    msg += "사용자 정의 5대 매수 타이밍 기준 분석 결과입니다.\n"
    msg += "──────────────────\n"
    
    # 카테고리별 정렬
    for res in results[:15]: # 상위 15개만
        msg += f"*{res['category']}*\n"
        msg += f"📌 *{res['name']}* ({res['code']})\n"
        msg += f"   - 현재가: {res['price']:,.0f}원\n"
        msg += f"   - 분석: {res['reason']}\n"
        msg += "──────────────────\n"
    
    msg += "💡 *매수 팁*: 돌파 시점에 거래량이 실리는지 반드시 확인하세요!"
    
    send_telegram_message(msg)
    logger.info("Recommendation Report Sent to Telegram.")

if __name__ == "__main__":
    send_recommendations()
