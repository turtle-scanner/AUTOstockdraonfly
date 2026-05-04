import json
import os
import sys
import time
import logging
from datetime import datetime

# 프로젝트 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY_DIR = os.path.join(BASE_DIR, "strategy_builder")
if STRATEGY_DIR not in sys.path:
    sys.path.append(STRATEGY_DIR)

import kis_auth as ka
from strategy.strategy_11_bonde import BondeStrategy
from telegram_notifier import send_telegram_message

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scan_all():
    print("="*60)
    print("START: Bonde Strategy Full Market Scanner")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 1. KIS 인증 (모의투자 우선)
    try:
        ka.auth(svr="vps", product="01")
        logger.info("KIS API Auth Success (Paper Trading)")
    except Exception as e:
        logger.error(f"Auth Failed: {e}")
        return

    # 2. 전략 초기화
    strategy = BondeStrategy(min_change_mb=4.0)
    
    # 3. 관심종목 로드
    watchlist_path = os.path.join(BASE_DIR, "bonde_watchlist.json")
    signals_path = os.path.join(BASE_DIR, "bonde_signals.json")
    
    # 신호 파일 초기화
    with open(signals_path, "w", encoding="utf-8") as f:
        json.dump({"last_update": "", "progress": 0, "total": 0, "signals": []}, f)

    if not os.path.exists(watchlist_path):
        logger.error("Watchlist file not found! Please run bonde_watchlist_maker.py first.")
        return
        
    with open(watchlist_path, "r", encoding="utf-8") as f:
        watchlist = json.load(f)
    
    # 한국 주식 + 미국 주요 종목 (엔비디아, 마이크론 등)
    kr_watchlist = [s for s in watchlist if s['market'] in ['KOSPI', 'KOSDAQ']]
    us_watchlist = [
        {"code": "NVDA", "name": "NVIDIA", "market": "NAS"},
        {"code": "MU", "name": "Micron", "market": "NAS"},
        {"code": "TSLA", "name": "Tesla", "market": "NAS"},
        {"code": "AAPL", "name": "Apple", "market": "NAS"},
        {"code": "MSFT", "name": "Microsoft", "market": "NAS"},
        {"code": "AMZN", "name": "Amazon", "market": "NAS"},
        {"code": "META", "name": "Meta", "market": "NAS"}
    ]
    
    combined_watchlist = kr_watchlist + us_watchlist
    total = len(combined_watchlist)
    logger.info(f"Scanning {total} stocks (KR: {len(kr_watchlist)}, US: {len(us_watchlist)})")

    # 4. 루프 시작
    found_count = 0
    signals_list = []
    for i, stock in enumerate(combined_watchlist):
        code = stock['code']
        name = stock['name']
        
        # 진행률 표시 및 파일 업데이트 (10종목마다)
        if i % 10 == 0:
            progress_data = {
                "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "progress": i,
                "total": total,
                "signals": signals_list # 이전에 찾은 신호들 유지
            }
            with open(signals_path, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=4)
            print(f"Progress: {i}/{total} ({i/total*100:.1f}%) ...")

        try:
            # 전략 신호 생성
            signal = strategy.generate_signal(code, name)
            
            if signal.action.value == "buy":
                found_count += 1
                new_signal = {
                    "code": code,
                    "name": name,
                    "market": stock['market'], # 시장 정보 추가
                    "reason": signal.reason,
                    "stop_loss": signal.stop_loss,
                    "time": datetime.now().strftime('%H:%M:%S')
                }
                signals_list.append(new_signal)
                
                msg = f"🚀 [Bonde Signal] {name}({code})\n- Setup: {signal.reason}\n- StopLoss: {signal.stop_loss}"
                print("\n" + "!"*30)
                print(msg)
                print("!"*30 + "\n")
                
                # 텔레그램 전송
                send_telegram_message(msg)
            
            # API 제한 방지 (0.1초 대기 - 모의투자는 초당 2건 제한이므로 조금 더 길게 잡음)
            time.sleep(0.5) 
            
        except Exception as e:
            # 에러 발생 시 로그만 남기고 다음 종목으로 진행
            if "Over rate limit" in str(e):
                logger.warning("API Rate Limit hit. Waiting 5 seconds...")
                time.sleep(5)
            continue

    print("\n" + "="*60)
    print(f"Scan Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Scanned: {total}")
    print(f"Buy Signals Found: {found_count}")
    print("="*60)

if __name__ == "__main__":
    scan_all()
