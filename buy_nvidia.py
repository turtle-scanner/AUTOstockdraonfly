# ------------------------------------------------------------
# 파일: g:\내 드라이브\AUTO BONDE\buy_nvidia.py
# 엔비디아 1주 매수 전용 스크립트
# ------------------------------------------------------------
import os
import sys
import json
import logging
from datetime import datetime

# 프로젝트 루트 자동 추가
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# 프로젝트 내부 모듈
import kis_auth as ka
from core import data_fetcher, indicators
from core.signal import Action, Signal
from core.order_executor import OrderExecutor
from telegram_notifier import send_telegram_message

# 로깅 설정
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# 기본 파라미터
TARGET_CODE = "NVDA"            # 엔비디아 티커 (미국 주식)
TARGET_QTY  = 1                 # 매수 수량
ENVIRONMENT = os.getenv("BONDE_ENV", "prod")   # 기본은 prod, 필요 시 vps 로 변경

def main():
    # 1️⃣ 인증
    logger.info("🔐 KIS 인증 시작 (env=%s)", ENVIRONMENT)
    ka.auth(svr=ENVIRONMENT, product="01")   # 기존과 동일한 인증 절차

    # 2️⃣ 현재가 조회
    price_info = data_fetcher.get_current_price(TARGET_CODE, ENVIRONMENT)
    cur_price = float(price_info.get("price", 0))
    if cur_price <= 0:
        logger.error("❌ 현재가 조회 실패 – %s", TARGET_CODE)
        return

    # 3️⃣ 주문 정보 구성
    # 리스크 기반이 아닌 고정 수량(1주)으로 매수
    signal = Signal(
        code=TARGET_CODE,
        name="엔비디아(NVDA)",
        action=Action.BUY,
        strength=1.0,
        reason="사용자 요청: 엔비디아 1주 매수",
        stop_loss=cur_price * 0.97,          # 기본 3% 손절선
        target_price=cur_price * 1.25,       # 목표 25% 상승
        quantity=TARGET_QTY
    )

    # 4️⃣ 주문 실행
    executor = OrderExecutor(env_dv=ENVIRONMENT)
    logger.info("🛒 매수 주문 전송 – %s @ %,.2f 원 x %d", TARGET_CODE, cur_price, TARGET_QTY)
    result_df = executor.execute_signal(signal, risk_amount=cur_price * TARGET_QTY)

    # 5️⃣ 결과 처리 & 텔레그램 알림
    if not result_df.empty:
        msg = (
            f"🟢 [Bonde BUY] 엔비디아(NVDA)\n"
            f"- 가격: {cur_price:,.0f} 원\n"
            f"- 수량: {TARGET_QTY} 주\n"
            f"- 손절: {signal.stop_loss:,.0f} 원\n"
            f"- 목표가: {signal.target_price:,.0f} 원\n"
            f"- 사유: {signal.reason}"
        )
        send_telegram_message(msg)
        logger.info("✅ 매수 성공 – 텔레그램 알림 전송 완료")
    else:
        logger.error("❌ 매수 실패 – 응답이 비어 있음")

if __name__ == "__main__":
    main()
# ------------------------------------------------------------
