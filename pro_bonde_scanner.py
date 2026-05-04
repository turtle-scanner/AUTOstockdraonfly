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
BASE_DIR = r"c:\1.auto bonde bot"
TRADING_BOT_DIR = os.path.join(BASE_DIR, "trading_bot")
STOCKS_INFO_DIR = os.path.join(BASE_DIR, "stocks_info")
STRATEGY_DIR = os.path.join(BASE_DIR, "strategy_builder")

sys.path.append(TRADING_BOT_DIR)
sys.path.append(STOCKS_INFO_DIR)
sys.path.append(STRATEGY_DIR)

from strategy.strategy_11_bonde import BondeStrategy
import kis_kospi_code_mst as kospi
import kis_kosdaq_code_mst as kosdaq

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_rs_score(df):
    """
    미너비니/본데 스타일의 RS 점수 계산 (yfinance 데이터용)
    """
    if len(df) < 150:
        return 0
    
    curr = df['Close'].iloc[-1]
    p3m = df['Close'].iloc[-63] if len(df) >= 63 else df['Close'].iloc[0]
    p6m = df['Close'].iloc[-126] if len(df) >= 126 else df['Close'].iloc[0]
    p9m = df['Close'].iloc[-189] if len(df) >= 189 else df['Close'].iloc[0]
    p12m = df['Close'].iloc[-252] if len(df) >= 252 else df['Close'].iloc[0]
    
    # RS Score formula (weighted momentum)
    rs = (curr/p3m * 0.4) + (curr/p6m * 0.2) + (curr/p9m * 0.2) + (curr/p12m * 0.2)
    return rs * 100

def check_vcp_pattern(df):
    """
    변동성 수축 패턴(VCP) 및 Tightness 체크
    """
    if len(df) < 150:
        return False, ""

    c = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    sma150 = df['Close'].rolling(150).mean().iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    
    # 1. Trend Template (Stage 2)
    if not (c > sma50 > sma150 > sma200):
        return False, "Not in Stage 2"

    # 2. Tightness (변동성 수축) - Bollinger Band Width로 정밀 측정
    recent_df = df.tail(20)
    std_20 = recent_df['Close'].std()
    ma_20 = recent_df['Close'].mean()
    bb_width = (std_20 * 4) / ma_20 * 100 # 대략적인 볼린저 밴드 폭 (%)
    
    high_15 = df.tail(15)['High'].max()
    low_15 = df.tail(15)['Low'].min()
    volatility = (high_15 - low_15) / low_15 * 100
    
    # 3. Volume Dry up (거래량 메마름)
    avg_vol_50 = df['Volume'].rolling(50).mean().iloc[-1]
    recent_vol_avg = df['Volume'].tail(3).mean() # 최근 3일 거래량
    vol_dry = recent_vol_avg < avg_vol_50 * 0.6 # 기존 0.8보다 더 엄격하게 0.6 적용
    
    if (volatility < 12.0 or bb_width < 10.0) and vol_dry:
        return True, f"High Tightness (Vol: {volatility:.1f}%, BBW: {bb_width:.1f}%, VolDry: {recent_vol_avg/avg_vol_50*100:.1f}%)"
    
    return False, ""

def scan_pro():
    logger.info("[PRO SCAN] yfinance 기반 본데 x 미너비니 스캔 시작")
    
    # 1. 마스터 데이터 로드
    df_kospi = kospi.get_kospi_master_dataframe(STOCKS_INFO_DIR)
    df_kosdaq = kosdaq.get_kosdaq_master_dataframe(STOCKS_INFO_DIR)
    
    df_kospi = df_kospi.rename(columns={'한글명': 'name', 'ROE': 'roe', '시가총액': 'mcap'})
    df_kosdaq = df_kosdaq.rename(columns={'한글종목명': 'name', 'ROE(자기자본이익률)': 'roe', '전일기준 시가총액 (억)': 'mcap'})
    
    for df in [df_kospi, df_kosdaq]:
        df['roe'] = pd.to_numeric(df['roe'], errors='coerce').fillna(0)
        df['mcap'] = pd.to_numeric(df['mcap'], errors='coerce').fillna(0)

    # 필터: ROE 10 이상, 시총 상위 300개씩
    df_kospi = df_kospi[df_kospi['roe'] >= 10].sort_values('mcap', ascending=False).head(300)
    df_kosdaq = df_kosdaq[df_kosdaq['roe'] >= 10].sort_values('mcap', ascending=False).head(300)
    
    candidates = []
    for _, row in df_kospi.iterrows():
        candidates.append({"code": str(row['단축코드']).zfill(6) + ".KS", "name": row['name'], "roe": row['roe']})
    for _, row in df_kosdaq.iterrows():
        candidates.append({"code": str(row['단축코드']).zfill(6) + ".KQ", "name": row['name'], "roe": row['roe']})
    
    logger.info(f"Scanning {len(candidates)} candidates via yfinance...")
    
    strategy = BondeStrategy()
    results = []
    top_rs_stocks = []
    
    # 벌크 다운로드를 위해 티커 리스트 생성
    tickers = [c['code'] for c in candidates]
    
    # yfinance 벌크 다운로드 (속도 향상)
    data = yf.download(tickers, period="1y", interval="1d", group_by='ticker', progress=True)
    
    for stock in candidates:
        code = stock['code']
        name = stock['name']
        
        try:
            df = data[code].dropna()
            if df.empty or len(df) < 100:
                continue
            
            # RS 점수
            rs_score = calculate_rs_score(df)
            top_rs_stocks.append({
                "name": name, "code": code, "rs": rs_score, "roe": stock['roe'], "price": df['Close'].iloc[-1]
            })

            if rs_score < 110: # RS 110 (상대적 수치) 이상만 상세 분석
                continue
                
            is_vcp, vcp_reason = check_vcp_pattern(df)
            
            # Bonde Strategy 신호용 데이터 변환 (소문자 컬럼 기대)
            df_bonde = df.copy()
            df_bonde.columns = [c.lower() for c in df_bonde.columns]
            signal = strategy.check_signal(code, name, df_bonde)
            
            if is_vcp or signal.action.value == "buy":
                status = "BUY NOW" if signal.action.value == "buy" else "WATCHING (VCP)"
                results.append({
                    "name": name, "code": code, "rs": rs_score, "roe": stock['roe'], 
                    "status": status, "reason": signal.reason if signal.action.value == "buy" else vcp_reason,
                    "price": df['Close'].iloc[-1]
                })
        except:
            continue

    # 결과 리포트
    # 결과 정렬 및 상위 퍼센틸 계산
    results = sorted(results, key=lambda x: x['rs'], reverse=True)
    top_rs_stocks = sorted(top_rs_stocks, key=lambda x: x['rs'], reverse=True)
    
    total_scanned = len(top_rs_stocks)
    for i, res in enumerate(results):
        rank = next((idx for idx, s in enumerate(top_rs_stocks) if s['code'] == res['code']), total_scanned)
        res['rs_percentile'] = (1 - (rank / total_scanned)) * 100 if total_scanned > 0 else 0
        if res['rs_percentile'] >= 95:
            res['sector_momentum'] = "시장 주도주 (Top 5% RS)"
        elif res['rs_percentile'] >= 85:
            res['sector_momentum'] = "강세 섹터 (Top 15% RS)"
        else:
            res['sector_momentum'] = "일반"

    top_rs_stocks = top_rs_stocks[:30] 
        
    print("\n" + "="*80)
    print(f"[BONDE MARKET DASHBOARD] {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*80)
    
    for s in top_rs_stocks:
        print(f"[{s['rs']:.1f}] {s['name']}({s['code']}) | ROE: {s['roe']:.1f} | Price: {s['price']:,}원")
    
    print("\n" + "="*80)
    print("Buy Timing & VCP Setups")
    print("="*80)
    
    if not results:
        print("현재 즉시 매수 또는 VCP 돌파 임박 종목이 없습니다.")
    else:
        # 워치리스트 업데이트용 데이터 준비
        watchlist_data = []
        for res in results:
            print(f"[{res['status']}] {res['name']}({res['code']})")
            print(f"   - RS: {res['rs']:.1f} | ROE: {res['roe']:.1f}")
            print(f"   - Reason: {res['reason']}")
            print(f"   - Price: {res['price']:,}원")
            print("-" * 40)
            
            # 워치리스트 형식에 맞춰 추가 (Gemini Context 확장)
            watchlist_data.append({
                "code": res['code'].split('.')[0],
                "name": res['name'],
                "rs_score": round(res['rs'], 1),
                "rs_percentile": round(res.get('rs_percentile', 0), 1),
                "roe": round(res['roe'], 1),
                "sector_momentum": res.get('sector_momentum', '일반'),
                "reason": res['reason'],
                "status": res['status']
            })
        
        # bonde_watchlist.json 저장
        import json
        watchlist_path = os.path.join(TRADING_BOT_DIR, "bonde_watchlist.json")
        try:
            with open(watchlist_path, "w", encoding="utf-8") as f:
                json.dump(watchlist_data, f, ensure_ascii=False, indent=4)
            logger.info(f"✅ [WATCHLIST] {len(watchlist_data)}개 종목이 워치리스트에 업데이트되었습니다.")
        except Exception as e:
            logger.error(f"워치리스트 저장 중 에러: {e}")

    print("="*80)

if __name__ == "__main__":
    scan_pro()
