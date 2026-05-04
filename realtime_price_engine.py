import asyncio
import json
import logging
import os
import sys
import websockets
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 경로 설정
BASE_DIR = r"c:\1.auto bonde bot"
TRADING_BOT_DIR = os.path.join(BASE_DIR, "trading_bot")
sys.path.append(TRADING_BOT_DIR)

import kis_auth
from telegram_notifier import send_telegram_message

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KISRealtimeEngine:
    def __init__(self):
        self.approval_key = None
        self.ws_url = None
        self.monitored_stocks = set()
        self.active_positions = {}
        self.price_triggers = []
        self.is_running = True

    async def connect(self):
        """
        KIS 웹소켓 연결 및 인증
        """
        kis_auth.changeTREnv(None, svr="prod") # 실전투자 환경 로드
        self.approval_key = kis_auth._TRENV.my_app_key
        self.ws_url = kis_auth._TRENV.my_url_ws
        
        if not self.approval_key:
            logger.error("❌ Approval Key 발급 실패")
            return False
            
        logger.info(f"🚀 웹소켓 연결 시작: {self.ws_url}")
        return True

    def load_targets(self):
        """
        감시 대상 로드 (포지션 + 가격 트리거)
        """
        # 1. 활성 포지션 로드 (손절 감시)
        pos_path = os.path.join(TRADING_BOT_DIR, "bonde_active_positions.json")
        if os.path.exists(pos_path):
            try:
                with open(pos_path, "r", encoding="utf-8") as f:
                    self.active_positions = json.load(f).get("positions", {})
            except:
                self.active_positions = {}

        # 2. 가격 트리거 로드 (매수 감시)
        trig_path = os.path.join(TRADING_BOT_DIR, "bonde_price_triggers.json")
        if os.path.exists(trig_path):
            try:
                with open(trig_path, "r", encoding="utf-8") as f:
                    self.price_triggers = json.load(f).get("triggers", [])
            except:
                self.price_triggers = []

        # 3. 티커 리스트 업데이트
        new_stocks = set()
        for code in self.active_positions.keys():
            new_stocks.add(code)
        for trig in self.price_triggers:
            new_stocks.add(trig['code'])
            
        if new_stocks != self.monitored_stocks:
            self.monitored_stocks = new_stocks
            logger.info(f"📡 감시 종목 업데이트: {len(self.monitored_stocks)}개")
            return True # 변경됨
        return False

    async def subscribe(self, websocket):
        """
        종목 구독 신청
        """
        for code in self.monitored_stocks:
            # 국내주식 실시간 체결가 (H0STCNT0)
            msg = {
                "header": {
                    "approval_key": self.approval_key,
                    "custtype": "P",
                    "tr_type": "1", # 1: 등록, 2: 해제
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",
                        "tr_key": code
                    }
                }
            }
            await websocket.send(json.dumps(msg))
            logger.info(f"✅ {code} 구독 신청 완료")
            await asyncio.sleep(0.1)

    async def monitor_loop(self):
        while self.is_running:
            try:
                if not await self.connect():
                    await asyncio.sleep(60)
                    continue

                async with websockets.connect(self.ws_url, ping_interval=30, ping_timeout=10) as websocket:
                    self.load_targets()
                    await self.subscribe(websocket)
                    
                    send_telegram_message("🛰️ [REALTIME] 실시간 시세 감시 엔진 가동 시작")

                    while self.is_running:
                        try:
                            # 1분마다 타겟 재로드 체크
                            # (실제로는 더 세밀한 로직 필요하지만 단순화)
                            data = await asyncio.wait_for(websocket.recv(), timeout=60)
                            
                            if data.startswith('0') or data.startswith('1'): # 데이터 수신
                                parts = data.split('|')
                                if len(parts) >= 4:
                                    tr_id = parts[1]
                                    content = parts[3]
                                    
                                    # 체결 데이터 파싱 (포맷에 따라 다름, 여기서는 첫번째 종목 데이터만 예시)
                                    # KIS 체결 데이터는 탭이나 특정 구분자로 되어 있음
                                    # H0STCNT0: 종목코드|체결시간|전일대비부호|전일대비|전일대비율|현재가|...
                                    # 실제 데이터는 암호화되지 않은 경우 구분자로 파싱 가능
                                    stock_data = content.split('^')
                                    code = stock_data[0]
                                    price = float(stock_data[2]) # 현재가
                                    
                                    await self.handle_price_update(code, price)
                                    
                        except asyncio.TimeoutError:
                            # 타임아웃 발생 시 타겟 변경 확인
                            if self.load_targets():
                                await self.subscribe(websocket)
                            # 하트비트
                            logger.info("💓 WebSocket Alive...")
                        except Exception as e:
                            logger.error(f"WS Recv Error: {e}")
                            break # 재연결

            except Exception as e:
                logger.error(f"WS Connect Error: {e}")
                await asyncio.sleep(10)

    async def handle_price_update(self, code, price):
        """
        가격 변동에 따른 실시간 대응
        """
        # 1. 손절/익절 체크
        if code in self.active_positions:
            pos = self.active_positions[code]
            stop_loss = pos.get('stop_loss', 0)
            if stop_loss > 0 and price <= stop_loss:
                logger.warning(f"🚨 [STOP LOSS] {pos['name']}({code}) 현재가 {price} <= 손절가 {stop_loss}")
                send_telegram_message(f"🚨 [REALTIME STOP] {pos['name']}({code}) 손절가 도달 ({price}원). 즉시 매도 작전을 검토하세요!")
                # 여기서 자동 매도 실행 가능

        # 2. 매수 트리거 체크
        for trig in self.price_triggers:
            if trig['code'] == code:
                target = trig['target_price']
                if price >= target:
                    logger.info(f"🎯 [TRIGGER] {trig['name']}({code}) 돌파: {price} >= {target}")
                    send_telegram_message(f"🎯 [REALTIME TRIGGER] {trig['name']}({code}) 목표가 {target}원 돌파! ({price}원)")
                    # 여기서 자동 매수 실행 가능

if __name__ == "__main__":
    engine = KISRealtimeEngine()
    try:
        asyncio.run(engine.monitor_loop())
    except KeyboardInterrupt:
        logger.info("Terminated by user")
