import os
import sys
import pandas as pd
from datetime import datetime
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
from core import data_fetcher
from telegram_notifier import send_telegram_message

def send_balance_report():
    print("🚀 [REPORT] 잔고 및 보유 종목 리포트 생성 중...")
    
    # 1. KIS 인증
    ka.auth(svr="prod", product="01")
    
    # 2. 예수금 및 총 자산 조회
    acc = data_fetcher.get_deposit(env_dv="prod")
    if not acc:
        print("❌ 예수금 조회 실패")
        return
        
    total_eval = acc.get('total_eval', 0)
    deposit = acc.get('deposit', 0)
    pnl = acc.get('pnl', 0)
    pnl_rate = acc.get('pnl_rate', 0)
    
    # 3. 보유 종목 조회
    holdings = data_fetcher.get_holdings(env_dv="prod")
    
    # 4. 메시지 포맷팅
    msg = f"📊 *[투자 계좌 리포트]* ({datetime.now().strftime('%m/%d %H:%M')})\n"
    msg += f"──────────────────\n"
    msg += f"💰 *총 자산*: {total_eval:,.0f}원\n"
    msg += f"💵 *예수금*: {deposit:,.0f}원\n"
    msg += f"📈 *총 손익*: {pnl:,.0f}원 ({pnl_rate:.2f}%)\n"
    msg += f"──────────────────\n"
    
    if holdings.empty:
        msg += "현재 보유 중인 종목이 없습니다.\n"
    else:
        msg += "*보유 종목 현황*:\n"
        for _, row in holdings.iterrows():
            name = row['stock_name']
            qty = int(float(row['quantity']))
            profit_rate = float(row['profit_rate'])
            current_price = float(row['current_price'])
            
            # 수익률에 따른 이모지
            emoji = "🔴" if profit_rate > 0 else "🔵" if profit_rate < 0 else "⚪"
            
            msg += f"{emoji} *{name}*: {qty}주\n"
            msg += f"   - 현재가: {current_price:,.0f}원\n"
            msg += f"   - 수익률: {profit_rate:.2f}%\n"
            
    msg += f"──────────────────\n"
    msg += "본데(Bonde) 자동매매 시스템 가동 중 🤖"
    
    # 5. 텔레그램 전송
    success = send_telegram_message(msg)
    if success:
        print("✅ 텔레그램 리포트 전송 완료!")
    else:
        print("❌ 텔레그램 전송 실패")

if __name__ == "__main__":
    send_balance_report()
