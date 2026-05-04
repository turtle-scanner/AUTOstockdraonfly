import argparse
import json
import logging
import math
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 경로 추가 (상위 디렉토리의 strategy_builder 참조)
TRADING_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TRADING_BOT_DIR)
STRATEGY_DIR = os.path.join(BASE_DIR, "strategy_builder")
if STRATEGY_DIR not in sys.path:
    sys.path.append(STRATEGY_DIR)
if TRADING_BOT_DIR not in sys.path:
    sys.path.append(TRADING_BOT_DIR)

import kis_auth as ka
from core import data_fetcher, order_executor, indicators
from core.signal import Signal, Action
from strategy.strategy_11_bonde import AdvancedBondeStrategy
from telegram_notifier import send_telegram_message
from gemini_analyzer import GeminiStockAnalyzer

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(TRADING_BOT_DIR, "bonde_bot_v5.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BondeProceduralBotV3:
    def __init__(self, env_dv="prod"):
        self.env_dv = env_dv
        self.strategy = AdvancedBondeStrategy()
        self.executor = order_executor.OrderExecutor(env_dv=env_dv)
        self.watchlist_path = os.path.join(TRADING_BOT_DIR, "bonde_watchlist.json")
        self.positions_path = os.path.join(TRADING_BOT_DIR, "bonde_active_positions.json")
        self.pending_path = os.path.join(TRADING_BOT_DIR, "bonde_pending_orders.json")
        self.history_path = os.path.join(TRADING_BOT_DIR, "bonde_trade_history.json")
        self.scan_results_path = os.path.join(TRADING_BOT_DIR, "bonde_scan_results.json")
        self.triggers_path = os.path.join(TRADING_BOT_DIR, "bonde_price_triggers.json")
        
        self.active_positions = self._load_positions()
        self.trade_history = self._load_history()
        
        # 매도 제외 종목 (장기 보유용)
        self.exclude_sell_list = ["NVDA"]
        
        # 설정값 (본데 v5.0)
        self.max_positions = 10
        self.last_heartbeat = 0
        self.market_status = "OK"
        self.market_volatility_factor = 1.0 # 동적 리스크 관리를 위한 변동성 지수
        self.analyzer = GeminiStockAnalyzer()
        
    def _load_positions(self):
        if os.path.exists(self.positions_path):
            try:
                with open(self.positions_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: return {}
        return {}

    def _load_history(self):
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: return []
        return []

    def _save_positions(self):
        with open(self.positions_path, "w", encoding="utf-8") as f:
            json.dump(self.active_positions, f, ensure_ascii=False, indent=4)

    def _calculate_exposure(self):
        """본데의 Progressive Exposure: 연승 시 비중 확대, 연패 및 시장 변동성 시 비중 축소"""
        base_risk = 0.01 # 기본 1%
        
        if self.trade_history:
            recent_trades = self.trade_history[-5:] # 최근 5회 매매
            wins = sum(1 for t in recent_trades if t.get('profit_rate', 0) > 0)
            
            if wins >= 4: base_risk = 0.02 # 연승 중이면 2% 공격적 투자
            elif wins <= 1: base_risk = 0.005 # 연패 중이면 0.5% 보수적 투자

        # [DYNAMIC RISK] 시장 변동성이 높으면 비중을 축소
        if self.market_volatility_factor > 1.5:
            base_risk *= 0.5 # 절반으로 축소
            logger.info(f"⚠️ [DYNAMIC RISK] 시장 고변동성 감지 (VolFactor: {self.market_volatility_factor:.2f}). 리스크 비중을 축소합니다: {base_risk*100}%")

        return base_risk

    def _fetch_with_backoff(self, func, *args, max_retries=5, **kwargs):
        for i in range(max_retries):
            try:
                res = func(*args, **kwargs)
                if res is not None:
                    if isinstance(res, pd.DataFrame) and res.empty:
                        time.sleep(1)
                        continue
                    return res
            except Exception as e:
                time.sleep(2 ** i)
        return None

    def check_market_health(self):
        """마켓 브레스 필터: 코스피/코스닥이 50일 이평선 위에 있는지 확인"""
        try:
            # 코스피(0001) 및 코스닥(1001) 조회
            kospi_df = data_fetcher.get_index_daily_price("0001", days=100)
            kosdaq_df = data_fetcher.get_index_daily_price("1001", days=100)
            
            if kospi_df.empty or kosdaq_df.empty:
                return True # 데이터 없으면 일단 진행
                
            kp_ma50 = kospi_df['close'].rolling(50).mean().iloc[-1]
            kq_ma50 = kosdaq_df['close'].rolling(50).mean().iloc[-1]
            
            kp_curr = kospi_df['close'].iloc[-1]
            kq_curr = kosdaq_df['close'].iloc[-1]
            
            is_bull = (kp_curr > kp_ma50) and (kq_curr > kq_ma50)
            
            # 변동성 측정 (최근 10일 ATR / 종가)
            kp_atr = indicators.calc_atr(kospi_df).iloc[-1]
            vol_pct = (kp_atr / kp_curr) * 100
            
            # 보통 KOSPI의 하루 변동성이 1.5%를 넘어가면 변동성이 큰 장세로 판단
            self.market_volatility_factor = vol_pct / 1.0 
            
            if not is_bull:
                logger.warning(f"⚠️ [MARKET] 지수 하강 추세 (KOSPI: {kp_curr:.1f} < MA50: {kp_ma50:.1f}) | 변동성: {vol_pct:.2f}%")
                self.market_status = "BEAR"
            else:
                self.market_status = "BULL"
            
            return is_bull
        except Exception as e:
            logger.error(f"Market health check error: {e}")
            return True

    def scan_task(self, item):
        code = item['code']
        name = item['name']
        try:
            df = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=150)
            if df is None or len(df) < 100: return None
            
            signal = self.strategy.check_signal(code, name, df)
            if signal and signal.action == Action.BUY:
                atr = indicators.calc_atr(df).iloc[-1]
                return {"item": item, "signal": signal, "atr": atr}
        except: return None
        return None

    def scan_and_buy(self):
        # [UPGRADE] 마켓 필터 체크
        if not self.check_market_health():
            logger.info("🛡️ [MARKET] 하락 추세로 인해 리스크 관리를 위해 신규 매수를 일시 중단합니다.")
            return

        if not os.path.exists(self.watchlist_path): return
        with open(self.watchlist_path, "r", encoding="utf-8") as f:
            watchlist = json.load(f)

        # 1. 공격성(Exposure) 계산
        risk_pct = self._calculate_exposure()
        logger.info(f"[EXPOSURE] 현재 리스크 비중: {risk_pct*100}%")

        # 2. 병렬 스캔
        signals = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(self.scan_task, item) for item in watchlist]
            for future in as_completed(futures):
                res = future.result()
                if res: signals.append(res)

        # [NEW] 스캔 결과 저장 (UI 연동용)
        scan_output = []
        for s in signals:
            scan_output.append({
                "code": s['item']['code'],
                "name": s['item']['name'],
                "reason": s['signal'].reason,
                "strength": s['signal'].strength,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        with open(self.scan_results_path, "w", encoding="utf-8") as f:
            json.dump(scan_output, f, ensure_ascii=False, indent=4)

        if not signals: return
        
        acc = self._fetch_with_backoff(data_fetcher.get_deposit, self.env_dv)
        if not acc: return
        total_asset = acc.get('total_eval', 0)
        risk_money = total_asset * risk_pct
        
        for sig in signals:
            if len(self.active_positions) >= self.max_positions: break
            code = sig['item']['code']
            if code in self.active_positions: continue
            
            price_info = self._fetch_with_backoff(data_fetcher.get_current_price, code)
            entry_price = float(price_info.get('price', 0))
            if entry_price == 0: continue
            
            atr = sig['atr']
            stop_loss = entry_price - (atr * 2)
            
            # 수량 계산
            unit_risk = entry_price - stop_loss
            if unit_risk <= 0: unit_risk = entry_price * 0.03
            qty = int(risk_money / unit_risk)
            
            if qty <= 0: continue

            # [UPGRADE] Gemini를 통한 EP 모멘텀 정밀 분석 (컨텍스트 주입)
            logger.info(f"🤖 [SMART AI] {sig['item']['name']} Catalyst 심층 분석 중...")
            
            ctx_data = {
                "RS_Score": sig['item'].get('rs_score', 'N/A'),
                "시장주도주 여부": sig['item'].get('sector_momentum', '일반'),
                "ROE": sig['item'].get('roe', 'N/A'),
                "기술적 패턴": sig['signal'].reason
            }
            
            ai_score, ai_reason = self.analyzer.analyze_catalyst(sig['item']['name'], code, context_data=ctx_data)
            
            # 주도주이거나 RS가 매우 높으면 AI 통과 기준 완화 (70점 -> 주도주는 60점도 통과)
            pass_score = 65 if "주도주" in str(ctx_data['시장주도주 여부']) else 75
            
            if ai_score < pass_score:
                logger.info(f"🚫 [SKIP] {sig['item']['name']} AI 분석 점수 미달 ({ai_score}/{pass_score}): {ai_reason}")
                continue
                
            logger.info(f"✅ [SMART AI PASS] {sig['item']['name']} 점수: {ai_score}. 사유: {ai_reason}")

            res_order = self.executor.execute_signal(sig['signal'], risk_amount=risk_money)
            if not res_order.empty:
                self.active_positions[code] = {
                    "name": sig['item']['name'],
                    "entry_price": entry_price,
                    "stop_price": stop_loss,
                    "atr": atr,
                    "qty": qty,
                    "entry_date": datetime.now().strftime("%Y-%m-%d"),
                    "reason": sig['signal'].reason,
                    "ai_score": ai_score,
                    "ai_reason": ai_reason,
                    "status": "active"
                }
                self._save_positions()
                send_telegram_message(f"🚀 [Advanced Bonde BUY]\n종목: {sig['item']['name']}\n진입가: {entry_price:,}원\nAI 점수: {ai_score}\n이유: {ai_reason}")

    def sync_positions(self):
        """실제 계좌 잔고(국내/해외)와 봇의 관리 종목을 동기화합니다."""
        try:
            # 1. 국내/해외 잔고 통합 조회
            kr_holdings = data_fetcher.get_holdings(self.env_dv)
            us_holdings = data_fetcher.get_foreign_holdings(self.env_dv)
            
            # API 에러 발생 시 동기화 중단 (포지션 보호)
            if kr_holdings is None or us_holdings is None:
                logger.error("[SYNC] 잔고 조회 API 에러가 발생하여 동기화를 중단합니다. (포지션 보호)")
                return
            
            # DataFrame 통합
            all_holdings = []
            if not kr_holdings.empty: all_holdings.append(kr_holdings)
            if not us_holdings.empty: all_holdings.append(us_holdings)
            
            if not all_holdings:
                # 모든 잔고 조회가 성공했으나 결과가 실제로 비어있는 경우
                if self.active_positions:
                    logger.warning("[SYNC] 현재 계좌에 보유 종목이 없습니다. API 오류가 아닌 실제 상황인지 확인이 필요할 수 있습니다.")
                return

            holdings_df = pd.concat(all_holdings, ignore_index=True)
            real_codes = set(holdings_df['stock_code'].tolist())
            managed_codes = set(self.active_positions.keys())

            # 2. 제거된 종목 처리 (매도 완료)
            for code in managed_codes - real_codes:
                logger.info(f"[SYNC] {self.active_positions[code]['name']} ({code}) 종목이 계좌에 없어 관리 목록에서 제거합니다.")
                del self.active_positions[code]

            # 3. 추가/업데이트 처리
            for _, row in holdings_df.iterrows():
                code = row['stock_code']
                qty = int(float(row['quantity']))
                avg_price = float(row['avg_price'])
                name = row['stock_name']

                if code in self.active_positions:
                    # [UPDATE] 수량 동기화 및 0인 매수가 복구
                    if self.active_positions[code]['qty'] != qty:
                        logger.info(f"[SYNC] {name} ({code}) 수량 변경: {self.active_positions[code]['qty']} -> {qty}")
                        self.active_positions[code]['qty'] = qty
                    
                    if self.active_positions[code].get('entry_price', 0) == 0:
                        logger.info(f"[SYNC] {name} ({code}) 매수가 복구: {avg_price}")
                        self.active_positions[code]['entry_price'] = avg_price
                else:
                    logger.info(f"[SYNC] 새로운 보유 종목 발견: {name} ({code}). 관리 목록에 추가합니다.")
                    
                    # ATR 기반 손절가 자동 설정 (국내/해외 자동 판별)
                    df = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=30)
                    atr = indicators.calc_atr(df).iloc[-1] if df is not None and not df.empty else avg_price * 0.05
                    stop_loss = avg_price - (atr * 2)

                    self.active_positions[code] = {
                        "name": name,
                        "entry_price": avg_price,
                        "stop_price": stop_loss,
                        "atr": atr,
                        "qty": qty,
                        "entry_date": datetime.now().strftime("%Y-%m-%d"),
                        "reason": "Account Sync (Manual Buy or Prior Session)",
                        "status": "active"
                    }
            
            self._save_positions()
        except Exception as e:
            logger.error(f"[SYNC] 계좌 동기화 중 오류 발생: {e}")

    def monitor_and_sell(self):
        # 0. 계좌와 동기화
        self.sync_positions()
        
        if not self.active_positions: return
        codes_to_remove = []
        for code, pos in self.active_positions.items():
            try:
                price_info = self._fetch_with_backoff(data_fetcher.get_current_price, code)
                curr = float(price_info.get('price', 0))
                if curr == 0: continue
                
                # [NEW] 실시간 데이터 업데이트 (UI 연동용)
                self.active_positions[code]['current_price'] = curr
                
                # SMA7 계산 및 저장
                df = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=20)
                if df is not None and len(df) >= 7:
                    sma7 = indicators.calc_ma(df, 7).iloc[-1]
                    self.active_positions[code]['sma7'] = sma7
                    self.active_positions[code]['trend_status'] = "BULL" if curr > sma7 else "BEAR"

                # 0. 엔비디아(NVDA) 예외 처리: 사용자 요청에 따라 강제 보유
                if code == "NVDA":
                    logger.info(f"[SKIP] {pos['name']} ({code}) 종목은 사용자 요청에 따라 매도 대상에서 제외합니다.")
                    continue

                # 1. 고정 -3% 손절 로직 (사용자 요청 사항)
                entry_price = pos.get('entry_price', 0)
                if entry_price > 0:
                    profit_rate = (curr - entry_price) / entry_price
                    if profit_rate <= -0.03:
                        self.executor.execute_signal(Signal(code, pos['name'], Action.SELL, reason=f"고정 손절 (-3% 도달: {profit_rate*100:.1f}%)"))
                        send_telegram_message(f"🔴 [STOP] {pos['name']} 고정 손절가(-3%) 터치: 현재 {profit_rate*100:.1f}%")
                        codes_to_remove.append(code)
                        continue

                # 2. ATR 기반 손절 (보조)
                if pos['stop_price'] > 0 and curr <= pos['stop_price']:
                    self.executor.execute_signal(Signal(code, pos['name'], Action.SELL, reason="ATR 손절"))
                    send_telegram_message(f"🔴 [STOP] {pos['name']} ATR 손절가 터치")
                    codes_to_remove.append(code)
                    continue

                # 3. 지능형 트레일링 스톱 (시장 변동성에 따라 이평선 조절)
                if entry_price > 0:
                    profit_rate = (curr - entry_price) / entry_price
                    if profit_rate >= 0.05:
                        df_recent = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=20)
                        
                        # 고변동성 장세면 짧은 호흡(5일선), 안정적인 장세면 긴 호흡(10일선) 적용
                        trail_days = 5 if self.market_volatility_factor > 1.5 else 10
                        ma_trail = indicators.calc_ma(df_recent, trail_days).iloc[-1] if df_recent is not None else 0
                        
                        if ma_trail > 0 and curr < ma_trail:
                            self.executor.execute_signal(Signal(code, pos['name'], Action.SELL, reason=f"스마트 트레일링 스톱 ({trail_days}일선 이탈, 수익률: {profit_rate*100:.1f}%)"))
                            send_telegram_message(f"💰 [SMART TAKE PROFIT] {pos['name']} 트레일링 스톱 ({trail_days}일선 이탈): 현재 수익 {profit_rate*100:.1f}%")
                            codes_to_remove.append(code)
                            continue
                            
                # 4. 본데 방식 SMA7 추세 이탈
                df = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=150)
                sig = self.strategy.check_signal(code, pos['name'], df)
                if sig.action == Action.SELL:
                    self.executor.execute_signal(sig)
                    send_telegram_message(f"🔵 [EXIT] {pos['name']} 추세 종료 매도: {sig.reason}")
                    codes_to_remove.append(code)
            except: continue

        for c in codes_to_remove: del self.active_positions[c]
        if codes_to_remove: self._save_positions()

    def _check_price_triggers(self):
        if not os.path.exists(self.triggers_path): return
        try:
            with open(self.triggers_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            triggers = data.get("triggers", [])
            if not triggers: return

            remaining_triggers = []
            risk_pct = self._calculate_exposure()
            acc = self._fetch_with_backoff(data_fetcher.get_deposit, self.env_dv)
            total_asset = acc.get('total_eval', 0) if acc else 0
            risk_money = total_asset * risk_pct

            for trigger in triggers:
                code = trigger['code']
                name = trigger['name']
                target = trigger['target_price']
                condition = trigger.get('condition', 'above')
                
                price_info = self._fetch_with_backoff(data_fetcher.get_current_price, code)
                curr = float(price_info.get('price', 0))
                if curr == 0:
                    remaining_triggers.append(trigger)
                    continue

                triggered = False
                if condition == "above" and curr >= target: triggered = True
                elif condition == "below" and curr <= target: triggered = True

                if triggered:
                    logger.info(f"🎯 [TRIGGER] {name}({code}) 가격 도달: {curr} (목표: {target})")
                    sig = Signal(code, name, Action.BUY, strength=1.0, reason=trigger['reason'])
                    
                    # 수량 계산 (ATR 기반)
                    df = self._fetch_with_backoff(data_fetcher.get_daily_prices, code, days=30)
                    atr = indicators.calc_atr(df).iloc[-1] if df is not None and not df.empty else curr * 0.05
                    stop_loss = curr - (atr * 2)
                    
                    res_order = self.executor.execute_signal(sig, risk_amount=risk_money)
                    if not res_order.empty:
                        send_telegram_message(f"✅ [TRIGGER BUY] {name}({code}) {target}원 돌파 매수 완료")
                        # 포지션 관리 추가 (이미 sync_positions에서 처리되겠지만 명시적으로 추가 가능)
                    else:
                        remaining_triggers.append(trigger) # 실패 시 유지
                else:
                    remaining_triggers.append(trigger)

            # 남은 트리거 저장
            if len(remaining_triggers) != len(triggers):
                with open(self.triggers_path, "w", encoding="utf-8") as f:
                    json.dump({"triggers": remaining_triggers}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"[TRIGGER] 에러 발생: {e}")

    def _process_pending_orders(self):
        if not os.path.exists(self.pending_path): return
        try:
            with open(self.pending_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pending = data.get("pending_orders", [])
            for order in pending:
                sig = Signal(order['code'], order['name'], Action.BUY, strength=1.0, reason=order['reason'], quantity=order['qty'])
                self.executor.execute_signal(sig)
            os.remove(self.pending_path)
        except: pass

    def send_heartbeat(self):
        """1시간마다 텔레그램으로 상태 보고"""
        try:
            kst = datetime.now(timezone(timedelta(hours=9)))
            msg = f"🛰️ [BOT HEARTBEAT] {kst.strftime('%Y-%m-%d %H:%M')}\n"
            msg += f"상태: 정상 작동 중 (KST)\n"
            
            # 포지션 요약
            if os.path.exists(self.positions_path):
                with open(self.positions_path, "r", encoding="utf-8") as f:
                    pos = json.load(f).get("positions", {})
                    msg += f"보유 종목: {len(pos)}개\n"
                    for p in pos.values():
                        msg += f" - {p['name']}: {p.get('profit_pct', 0):.1f}%\n"
            
            send_telegram_message(msg)
        except Exception as e:
            logger.error(f"Heartbeat 에러: {e}")

    def run_forever(self):
        logger.info("🚀 Bonde Bot V5.0 Smart & Precise Started")
        ka.auth(svr=self.env_dv)
        self._process_pending_orders()
        
        last_scan_time = 0
        last_monitor_time = 0
        last_heartbeat_time = 0
        
        while True:
            now = time.time()
            kst = datetime.now(timezone(timedelta(hours=9)))
            is_market_open = (kst.weekday() < 5) and (
                (9,0) <= (kst.hour, kst.minute) <= (15,40) or 
                (22,30) <= (kst.hour, kst.minute) or (kst.hour < 5) # 미국장 포함
            )
            
            if is_market_open:
                # 1. 가격 트리거 (10초마다 - 초정밀)
                self._check_price_triggers()
                
                # 2. 보유 종목 모니터링 (1분마다)
                if now - last_monitor_time > 60:
                    self.monitor_and_sell()
                    last_monitor_time = now
                    
                # 3. 신규 종목 스캔 (15분마다)
                if now - last_scan_time > 900:
                    self.scan_and_buy()
                    last_scan_time = now

                # 4. 하트비트 (1시간마다)
                if now - last_heartbeat_time > 3600:
                    self.send_heartbeat()
                    last_heartbeat_time = now
            
            time.sleep(10) # 루프 주기 10초

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="prod")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    bot = BondeProceduralBotV3(env_dv=args.env)
    if args.once:
        ka.auth(svr=bot.env_dv)
        bot.scan_and_buy()
        bot.monitor_and_sell()
    else: bot.run_forever()
