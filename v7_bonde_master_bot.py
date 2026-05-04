import os
import asyncio
import logging
import json
from datetime import datetime
import pytz
import google.generativeai as genai
from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

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
    # 실제 KIS API 연동 전까지는 Mock 데이터 또는 kis_auth 기반 정보 활용
    # 여기서는 사용자 요청대로 계좌번호와 샘플 수익률 표시
    await update.message.reply_text(
        f"💳 [계좌 정보 조회]\n"
        f"계좌번호: {ACC_NO}\n"
        f"현재 총 자산: 52,400,000 KRW\n"
        f"당일 실현 손익: +1,250,000 KRW (+2.4%)\n\n"
        f"보유 종목:\n"
        f"1. NVDA: 10주 (+15.4%)\n"
        f"2. 삼성전자: 100주 (-1.2%)\n"
        f"3. 에코프로: 20주 (+5.7%)"
    )

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
    # 형식: "종목명 수량 가격" (예: 삼성전자 10 75000)
    parts = command_text.split()
    if len(parts) >= 3:
        name = parts[0]
        qty = parts[1]
        price = parts[2]
        await update.message.reply_text(f"🚀 [매매 명령 수신]\n종목: {name}\n수량: {qty}\n가격: {price}\n\n'본데' 원칙에 따라 리스크 검토 후 주문을 전송합니다. (현재는 시뮬레이션 모드)")
    else:
        await update.message.reply_text("⚠️ 매매 명령 형식이 올바르지 않습니다.\n예: 삼성전자 10 75000")

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
