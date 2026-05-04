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

def full_buy_douzone():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 [FULL BUY] 더존비즈온 풀매수 실행")
    
    # 1. KIS 인증
    ka.auth(svr="prod", product="01")
    
    # 2. 정보 조회
    code = "012510"
    name = "더존비즈온"
    
    price_info = data_fetcher.get_current_price(code, env_dv="prod")
    curr_price = float(price_info.get('price', 0))
    
    acc = data_fetcher.get_deposit(env_dv="prod")
    deposit = float(acc.get('deposit', 0))
    
    if curr_price <= 0 or deposit <= 0:
        logger.error(f"주가({curr_price}) 또는 예수금({deposit}) 정보가 부적절합니다.")
        return

    # 3. 매수 가능 수량 조회 (정확한 풀매수를 위해 KIS API 호출)
    buyable = data_fetcher.get_buyable_amount(code, int(curr_price), env_dv="prod")
    qty = buyable.get('quantity', 0)
    
    if qty <= 0:
        logger.error("매수 가능 수량이 0입니다. (잔고 부족 또는 매수 제한)")
        return
        
    logger.info(f"계산된 매수 가능 수량: {qty}주 (현재가: {curr_price:,.0f}원)")

    # 4. 주문 실행
    executor = order_executor.OrderExecutor(env_dv="prod")
    # 강한 매수 시그널 생성 (strength=1.0 -> 시장가 주문 유도)
    sig = Signal(code, name, Action.BUY, strength=1.0, reason="사용자 요청에 따른 즉시 풀매수", quantity=qty)
    
    res = executor.execute_signal(sig)
    
    if not res.empty:
        success_msg = f"✅ [FULL BUY 완료] {name}({code})\n- 수량: {qty}주\n- 현재가: {curr_price:,.0f}원\n- 총액: {qty*curr_price:,.0f}원"
        logger.info(success_msg)
        send_telegram_message(success_msg)
    else:
        logger.error("주문 실행에 실패했습니다.")
        send_telegram_message(f"❌ [FULL BUY 실패] {name}({code}) 주문 처리 중 오류 발생")

if __name__ == "__main__":
    full_buy_douzone()
