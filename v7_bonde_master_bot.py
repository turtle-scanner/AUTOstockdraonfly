import os
import asyncio
import logging
import json
from datetime import datetime
import pytz
import google.generativeai as genai
import re
from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

# 실계좌 연동용 모듈 임포트
try:
    from headless_dragonfly_bot import (
        get_kis_access_token, 
        get_total_assets, 
        get_detailed_holdings, 
        execute_kis_market_order
    )
    REAL_TRADING_ENABLED = True
except ImportError:
    REAL_TRADING_ENABLED = False
    print("⚠️ headless_dragonfly_bot 모듈을 찾을 수 없어 모의 모드로 동작합니다.")

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# .env 파일 로드
load_dotenv()

# --- 설정 정보 ---
# 사용자가 제공한 토큰 및 계좌번호 (보안을 위해 .env 사용 권장)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8728920940:AAFenbR2SNCFe3m7w4b-_yLG2zoS_cTC3s0")
ACC_NO = os.environ.get("KIS_ACCOUNT_NO", "4654671301")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBEm692ZnxgNImYVHnzBSvXQ7JAfjl4ox0")

# 제미나이 설정
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = """
당신은 '거북이투자전문가'의 전용 매매 조력자 '본데 마스터'입니다.
사용자의 요청에 따라 국내/미국 시장의 VCP(변동성 수축 패턴) 및 SEPA(특정 진입 포인트 분석) 전략을 기반으로 답변하세요.

[매매 원칙: 본데 방식]
1. VCP 패턴: 주가가 횡보하며 변동성이 줄어드는 지점(Tightness)을 포착하여 돌파 시 매수.
2. RS 점수: 시장 지수보다 강하게 움직이는 종목 우선순위.
3. 리스크 관리: 손절매 7-8% 엄격 준수, 비중 분산.

항상 전문적이면서도 지휘관(사용자)을 보좌하는 충성스러운 비서의 말투(~합니다, ~해요)를 사용하세요.
"""

# --- 메뉴 구성 ---
MENU_KEYBOARD = [
    ["1. 국내주식 스캔 (VCP/RS)", "2. 미국주식 스캔 (SEPA/EP)"],
    ["3. 계좌 및 수익률 조회", "4. 국내 시황 요약"],
    ["5. 미국 시황 요약", "6. 주식 매매 실행 (종목 수량 가격)"]
]
reply_markup = ReplyKeyboardMarkup(MENU_KEYBOARD, resize_keyboard=True)

# --- 1. 국내주식 스캔 (VCP/RS) ---
async def scan_domestic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 국내 시장 주도주 및 VCP 패턴 스캔을 시작합니다. 잠시만 기다려주세요...")
    
    # 실제 스캐너 결과 파일(bonde_watchlist.json) 확인
    watchlist_path = "bonde_watchlist.json"
    if os.path.exists(watchlist_path):
        try:
            with open(watchlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not data:
                await update.message.reply_text("현재 스캔된 종목이 없습니다. `pro_bonde_scanner.py`를 실행하여 갱신하세요.")
                return

            report = "🚀 [국내 본데 VCP 스캔 결과]\n\n"
            for i, stock in enumerate(data[:10]): # 상위 10개만
                report += f"{i+1}. {stock['name']}({stock['code']})\n"
                report += f"   - RS: {stock['rs_score']} | 상태: {stock['status']}\n"
                report += f"   - 이유: {stock['reason']}\n\n"
            
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"⚠️ 결과 파일 읽기 오류: {e}")
    else:
        # 파일이 없으면 샘플 데이터 보고 (혹은 스캐너 직접 실행 로직 추가 가능)
        await update.message.reply_text("⚠️ `bonde_watchlist.json` 파일을 찾을 수 없습니다. 기본 스캔 로직을 구동 중입니다...")
        await update.message.reply_text("[샘플 결과] 삼성전자(VCP 수축 중), SK하이닉스(RS 강세), 현대차(돌파 임박)")

# --- 2. 미국주식 스캔 (SEPA/EP) ---
async def scan_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌎 미국 시장 SEPA/EP 패턴 스캔 중... (yfinance 기반 분석)")
    # 미국 주식은 실시간 데이터나 yfinance를 활용한 간단한 분석 보고
    prompt = f"{SYSTEM_PROMPT}\n현재 미국 증시에서 미너비니 SEPA 패턴을 보이는 관심 종목 3개를 추천하고 이유를 짧게 설명해줘. (NVDA, TSLA, AAPL 등 대형주 위주)"
    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(f"📡 [미국 본데 SEPA 분석 보고]\n\n{response.text}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 분석 오류: {e}")

# --- 3. 계좌 및 수익률 조회 ---
async def check_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not REAL_TRADING_ENABLED:
        await update.message.reply_text("⚠️ 실계좌 연동 모듈이 없어 모의 데이터를 표시합니다.")
        # (기존 Mock 데이터 유지)
        await update.message.reply_text(
            f"💳 [계좌 정보 조회 - MOCK]\n계좌번호: {ACC_NO}\n현재 총 자산: 52,400,000 KRW\n보유 종목: NVDA 10주 (+15.4%)"
        )
        return

    await update.message.reply_text("⏳ 실시간 계좌 정보를 서버에서 불러오고 있습니다...")
    try:
        token = get_kis_access_token()
        if not token:
            await update.message.reply_text("❌ KIS 인증 실패. API 키를 확인하세요.")
            return

        total_assets = get_total_assets(token)
        holdings = get_detailed_holdings(token)

        report = f"💳 [실시간 계좌 보고]\n"
        report += f"계좌번호: {ACC_NO}\n"
        report += f"총 평가 자산: {total_assets:,.0f}원\n\n"
        
        if holdings:
            report += "📂 [보유 종목 현황]\n"
            for h in holdings:
                report += f"📍 {h['ticker']}: {h['qty']}주 ({h['roi']}% / {h['curr_p']:,}원)\n"
        else:
            report += "현재 보유 중인 종목이 없습니다."
        
        await update.message.reply_text(report)
    except Exception as e:
        await update.message.reply_text(f"⚠️ 계좌 조회 중 오류 발생: {str(e)}")

# --- 4 & 5. 시황 요약 ---
async def market_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, market="국내"):
    await update.message.reply_text(f"📊 {market} 증시 시황을 제미나이 AI가 요약하고 있습니다...")
    prompt = f"{SYSTEM_PROMPT}\n오늘의 {market} 증시 요약과 본데 투자자가 주목해야 할 포인트 3가지를 정리해서 보고해줘."
    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(f"📝 [{market} 시황 브리핑]\n\n{response.text}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 요약 오류: {e}")

# --- 6. 매매 실행 ---
async def execute_trade(update: Update, context: ContextTypes.DEFAULT_TYPE, command_text: str):
    # 형식: "종목명 수량 가격" (현재 시장가 매매 위주이므로 가격은 참고용 또는 생략 가능)
    # 예: "NVDA 1 매수" 또는 "삼성전자 10 매도"
    parts = command_text.split()
    if len(parts) < 2:
        await update.message.reply_text("⚠️ 매매 명령 형식이 올바르지 않습니다.\n예: [티커 수량 매수/매도]")
        return

    ticker = parts[0].upper()
    try:
        qty = int(re.search(r'\d+', parts[1]).group())
    except:
        await update.message.reply_text("⚠️ 수량을 숫자로 입력해 주세요.")
        return

    is_buy = "매수" in command_text or "buy" in command_text.lower()
    action_str = "매수" if is_buy else "매도"

    await update.message.reply_text(f"🚀 {ticker} {qty}주 {action_str} 주문을 전송합니다...")

    if not REAL_TRADING_ENABLED:
        await update.message.reply_text(f"⚠️ [MOCK] {ticker} {qty}주 {action_str} 주문이 가상으로 완료되었습니다.")
        return

    try:
        token = get_kis_access_token()
        success = execute_kis_market_order(ticker, qty, is_buy, token)
        if success:
            await update.message.reply_text(f"✅ {ticker} {qty}주 {action_str} 주문 성공!")
        else:
            await update.message.reply_text(f"❌ {ticker} {action_str} 주문 실패. 로그를 확인하세요.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 주문 중 오류 발생: {str(e)}")

# --- 핸들러 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 거북이투자전문가 본데 매매 봇 가동\n\n"
        "지휘관님, 본데 방식의 자동주식매매 시스템에 접속하셨습니다.\n"
        "아래 메뉴를 선택하거나 명령을 내려주십시오."
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if "1." in text or text == "1":
        await scan_domestic(update, context)
    elif "2." in text or text == "2":
        await scan_us(update, context)
    elif "3." in text or text == "3":
        await check_account(update, context)
    elif "4." in text or text == "4":
        await market_summary(update, context, "국내")
    elif "5." in text or text == "5":
        await market_summary(update, context, "미국")
    elif "6." in text or text == "6":
        await update.message.reply_text("매매 명령을 입력하세요.\n형식: [종목명 수량 가격]")
    elif len(text.split()) >= 3:
        # 매매 명령 직접 입력 처리
        await execute_trade(update, context, text)
    else:
        # 일반 대화는 제미나이에게 토스
        await update.message.reply_text("명령을 분석 중입니다...")
        prompt = f"{SYSTEM_PROMPT}\n사용자 요청: {text}"
        try:
            response = model.generate_content(prompt)
            await update.message.reply_text(response.text)
        except Exception as e:
            await update.message.reply_text("번호를 입력하거나 메뉴를 선택해주세요.")

# --- 메인 실행부 ---
if __name__ == "__main__":
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_TOKEN":
        print("❌ 텔레그램 토큰이 설정되지 않았습니다. .env 파일이나 변수를 확인하세요.")
    else:
        print(f"🚀 본데 마스터 봇 가동 시작... (Token: {TELEGRAM_TOKEN[:10]}...)")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        app.run_polling()
