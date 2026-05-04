import os
import sys
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging
import urllib3
import ssl
import requests
from concurrent.futures import ThreadPoolExecutor

# SSL 보안 인증서 검증 우회 설정
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# yfinance용 세션 강제 설정 (인증서 검증 안함)
old_merge_environment_settings = requests.Session.merge_environment_settings
def new_merge_environment_settings(self, url, proxies, stream, verify, cert):
    settings = old_merge_environment_settings(self, url, proxies, stream, verify, cert)
    settings['verify'] = False
    return settings
requests.Session.merge_environment_settings = new_merge_environment_settings

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def calculate_rs_score(ticker_symbol):
    """6개월(40%) 및 3개월(60%) 가중치 RS 점수 계산"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=200)
        
        # 데이터 다운로드 (최대한 가볍게)
        df = yf.download(ticker_symbol, start=start_date, end=end_date, progress=False)
        if df.empty or len(df) < 120: return 0
        
        curr_price = float(df['Close'].iloc[-1])
        price_3m = float(df['Close'].iloc[-60]) if len(df) >= 60 else float(df['Close'].iloc[0])
        price_6m = float(df['Close'].iloc[0])
        
        rs_3m = (curr_price / price_3m - 1) * 100
        rs_6m = (curr_price / price_6m - 1) * 100
        
        # 3개월 가중치 60%, 6개월 가중치 40%
        rs_score = (rs_3m * 0.6) + (rs_6m * 0.4)
        return round(rs_score, 2)
    except:
        return 0

def update_watchlist():
    logger.info("START: Generating Optimized RS Watchlist (Top 300 KR / 300 US)...")
    
    # 1. 한국 시장 (KOSDAQ 중심)
    import FinanceDataReader as fdr
    df_krx = fdr.StockListing('KRX')
    # 코스닥 종목 우선 필터링 (사용자 요청)
    df_kosdaq = df_krx[df_krx['Market'] == 'KOSDAQ'].copy()
    
    # RS 계산 (병렬 처리로 속도 향상)
    logger.info(f"Calculating RS for {len(df_kosdaq)} KOSDAQ stocks...")
    tickers = [f"{row['Code']}.KQ" for _, row in df_kosdaq.iterrows()]
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        rs_scores = list(executor.map(calculate_rs_score, tickers))
    
    df_kosdaq['rs_score'] = rs_scores
    top_kr = df_kosdaq.sort_values(by='rs_score', ascending=False).head(300)
    
    # 2. 미국 시장 (NASDAQ 중심)
    logger.info("Fetching US NASDAQ stocks...")
    # 나스닥 상위 종목 리스트 (가져오기 어려울 경우 QQQ 구성 종목 등 주요 종목 사용)
    # 여기서는 상위 500개 중 RS 300개 추출
    df_nasdaq = fdr.StockListing('NASDAQ').head(500)
    logger.info(f"Calculating RS for {len(df_nasdaq)} NASDAQ stocks...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        us_rs_scores = list(executor.map(calculate_rs_score, df_nasdaq['Symbol'].tolist()))
        
    df_nasdaq['rs_score'] = us_rs_scores
    top_us = df_nasdaq.sort_values(by='rs_score', ascending=False).head(300)
    
    # 3. 통합 및 저장
    watchlist = []
    for _, row in top_kr.iterrows():
        watchlist.append({
            "code": row['Code'],
            "name": row['Name'],
            "market": "KOSDAQ",
            "rs_score": row['rs_score']
        })
    for _, row in top_us.iterrows():
        watchlist.append({
            "code": row['Symbol'],
            "name": row['Name'],
            "market": "NASDAQ",
            "rs_score": row['rs_score']
        })
        
    output_path = os.path.join(BASE_DIR, "bonde_watchlist.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)
        
    logger.info(f"SUCCESS: Optimized Watchlist saved ({len(watchlist)} stocks).")

if __name__ == "__main__":
    update_watchlist()
