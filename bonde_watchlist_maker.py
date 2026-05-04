import sys
import os
import json
import logging
import pandas as pd
from datetime import datetime

# 프로젝트 경로 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY_DIR = os.path.join(BASE_DIR, "strategy_builder")
STOCKS_INFO_DIR = os.path.join(BASE_DIR, "stocks_info")

if STRATEGY_DIR not in sys.path:
    sys.path.append(STRATEGY_DIR)
if STOCKS_INFO_DIR not in sys.path:
    sys.path.append(STOCKS_INFO_DIR)

import kis_auth as ka
from core import data_fetcher
import kis_kospi_code_mst as kospi
import kis_kosdaq_code_mst as kosdaq

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_full_watchlist():
    """
    KOSPI, KOSDAQ 전 종목을 가져와서 bonde_watchlist.json 생성
    """
    logger.info("START: Generating Full KOSPI/KOSDAQ Watchlist...")
    
    watchlist = []
    
    try:
        # 1. KOSPI 마스터 다운로드 및 파싱
        logger.info("Downloading KOSPI master...")
        kospi.kospi_master_download(STOCKS_INFO_DIR)
        df_kospi = kospi.get_kospi_master_dataframe(STOCKS_INFO_DIR)
        for _, row in df_kospi.iterrows():
            watchlist.append({
                "code": str(row['단축코드']).zfill(6),
                "name": row['한글명'],
                "market": "KOSPI",
                "roe": float(row.get('ROE', 0))
            })
            
        # 2. KOSDAQ 마스터 다운로드 및 파싱
        logger.info("Downloading KOSDAQ master...")
        kosdaq.kosdaq_master_download(STOCKS_INFO_DIR)
        df_kosdaq = kosdaq.get_kosdaq_master_dataframe(STOCKS_INFO_DIR)
        for _, row in df_kosdaq.iterrows():
            watchlist.append({
                "code": str(row['단축코드']).zfill(6),
                "name": row['한글종목명'],
                "market": "KOSDAQ",
                "roe": float(row.get('ROE(자기자본이익률)', 0))
            })
            
    except Exception as e:
        logger.error(f"Failed to get full master list: {e}")
        # Fallback to a smaller list if needed
        return

    # 파일 저장
    output_path = os.path.join(BASE_DIR, "bonde_watchlist.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)
        
    logger.info(f"SUCCESS: Full Watchlist created with {len(watchlist)} stocks.")

if __name__ == "__main__":
    generate_full_watchlist()
