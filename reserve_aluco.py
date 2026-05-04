import os
import sys
import logging
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 프로젝트 경로 설정
TRADING_BOT_DIR = r"c:\1.auto bonde bot\trading_bot"
STRATEGY_DIR = r"c:\1.auto bonde bot\strategy_builder"

sys.path.append(TRADING_BOT_DIR)
sys.path.append(STRATEGY_DIR)

import kis_auth as ka
from core import data_fetcher, order_executor
from core.signal import Signal, Action
from telegram_notifier import send_telegram_message

def reserve_aluco():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 [RESERVE] 알루코 지정가 매수 주문 실행")
    
    # 1. KIS 인증
    ka.auth(svr="prod", product="01")
    
    # 2. 정보 설정
    code = "001780"
    name = "알루코"
    target_price = 2900
    qty = 30
    
    # 3. 주문 실행
    executor = order_executor.OrderExecutor(env_dv="prod")
    # strength=0.7 (일반 시그널)로 설정하여 지정가 주문을 유도함
    sig = Signal(code, name, Action.BUY, strength=0.7, 
                 reason=f"사용자 지정가({target_price}원) 예약 매수", 
                 quantity=qty, target_price=target_price)
    
    res = executor.execute_signal(sig)
    
    if not res.empty:
        success_msg = f"✅ [지정가 주문 완료] {name}({code})\n- 가격: {target_price:,.0f}원\n- 수량: {qty}주"
        logger.info(success_msg)
        send_telegram_message(success_msg)
    else:
        logger.error("지정가 주문 실행에 실패했습니다.")
        send_telegram_message(f"❌ [지정가 주문 실패] {name}({code}) 주문 처리 중 오류 발생")

if __name__ == "__main__":
    reserve_aluco()
