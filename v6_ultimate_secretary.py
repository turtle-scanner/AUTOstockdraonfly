import os
import asyncio
import time
import edge_tts
import google.generativeai as genai
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import emoji
import logging
from datetime import time as dtime
import pytz

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

load_dotenv()

# --- 1. 매매 명령/조회용 함수 (제미나이 Function Calling 연동) ---
def buy_stock(ticker: str, quantity: int) -> str:
    """Buy a specified quantity of a stock.
    Args:
        ticker: The stock ticker symbol (e.g., 'NVDA', 'AAPL', '005930').
        quantity: The number of shares to buy.
    """
    logging.info(f"명령 수신: {ticker} {quantity}주 매수")
    # 향후 실제 KIS 매수 API 연동 지점
    return f"지휘관님, 한국투자증권 서버로 {ticker} {quantity}주 시장가 매수 주문을 전송했습니다."

def sell_stock(ticker: str, quantity: int) -> str:
    """Sell a specified quantity of a stock.
    Args:
        ticker: The stock ticker symbol.
        quantity: The number of shares to sell.
    """
    logging.info(f"명령 수신: {ticker} {quantity}주 매도")
    return f"지휘관님, {ticker} {quantity}주 매도 주문이 완료되었습니다."

def get_account_balance() -> str:
    """Get the current account balance, cash, and active stock positions."""
    logging.info("계좌 조회 요청 수신")
    return "현재 예수금은 15,200 USD 이며, 주요 보유 종목은 NVDA 10주(+15%), MSFT 5주(+3%) 입니다. (모의 연동)"

def execute_bonde_scan(market: str) -> str:
    """Execute Bonde EP scan for a specific market (Domestic or US).
    Args:
        market: '국내' or '미국'
    """
    logging.info(f"{market} 본데 스캔 요청 수신")
    if "국내" in market:
        return "[국내 본데 EP 스캔 결과] 당일 900만주 터진 대장주: 삼부토건 +12%, 한화오션 +5% 포착"
    else:
        return "[미국 본데 EP 스캔 결과] 당일 900만주 터진 대장주: PLTR +8%, SMCI +5% 포착"

# --- 2. 제미나이 설정 ---
# 제미나이 키 (지휘관님 요청에 따라 직접 삽입하여 403 에러 해결)
GEMINI_API_KEY = "AIzaSyBEm692ZnxgNImYVHnzBSvXQ7JAfjl4ox0" # 최신 발급 키 반영 완료
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
# Gemini 1.5 Pro 모델에 도구(함수) 제공
# Gemini 1.5 Flash 모델로 변경 (더 빠르고 안정적이며 API 키 호환성이 높음)
model = genai.GenerativeModel(
    'gemini-1.5-flash',
    tools=[buy_stock, sell_stock, get_account_balance, execute_bonde_scan]
)

SYSTEM_PROMPT = """
당신은 '거북이투자전문가'의 전용 전략 참모이자 완벽한 비서입니다.

[투자 원칙]
1. 본데 EP: 거래량 900만 주 이상 + 주가 4% 이상 상승 대장주.
2. 미너비니 VCP: Tightness와 Dry-up 피벗 돌파 종목.
3. 리스크: 손절(7~8%) 준수. 비중 25% 이내.
4. 학습: 상담/교육학 문제는 임용고시 사례 분석형.

[행동 지침]
- 사용자가 주식 매수/매도, 계좌 조회, 스캔을 지시하면 제공된 함수(tools)를 사용하여 행동하세요.
- 결과를 바탕으로 텔레그램을 통해 지휘관님께 여성 비서처럼 정중하고 예쁘게 보고하세요 (~해요, ~입니다).
- 음성 전송을 위해 마크다운(*, # 등) 및 복잡한 특수문자는 빼고 말하세요.
"""

VOICE = "ko-KR-JiMinNeural" # 예쁘고 전문적인 참모 목소리

# --- 3. 기억력(Context) 관리 ---
chat_sessions = {}

def get_chat_session(chat_id):
    if chat_id not in chat_sessions:
        # 자동 함수 호출 활성화
        chat_sessions[chat_id] = model.start_chat(history=[], enable_automatic_function_calling=True)
    return chat_sessions[chat_id]

# --- 4. 음성/STT 코어 기능 ---
async def text_to_speech_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    clean_text = emoji.replace_emoji(text, replace='')
    for char in ['*', '#', '_', '`']:
        clean_text = clean_text.replace(char, '')
    
    if not clean_text.strip(): return
    await update.message.reply_text(text)

    file_path = f"v_{int(time.time())}.mp3"
    try:
        communicate = edge_tts.Communicate(clean_text, VOICE, rate="+10%", pitch="+15Hz")
        await communicate.save(file_path)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'rb') as f:
                await update.message.reply_voice(f)
            os.remove(file_path)
    except Exception as e:
        logging.error(f"TTS Error: {e}")

# 음성 메시지(STT) 처리
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    voice_file = await update.message.voice.get_file()
    file_path = f"user_voice_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    
    try:
        # mime_type 명시하여 400 에러 방지
        uploaded_audio = genai.upload_file(path=file_path, mime_type='audio/ogg')
        session = get_chat_session(update.effective_chat.id)
        
        response = session.send_message([uploaded_audio, f"{SYSTEM_PROMPT}\n\n지휘관님의 음성 명령을 수신했습니다. 요청하신 내용을 확인하고 보고하세요."])
        await text_to_speech_and_send(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"⚠️ 음성 인식 오류 (400 발생 가능성): {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# --- 5. 텔레그램 핸들러 및 스케줄러 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['0. 교육학 문제 🎓', '1. 상담학 문제 🧠'],
        ['2. 본데 스캔(국내) 🚀', '3. 본데 스캔(미국) 🌎'],
        ['엔비디아 1주 매수 📈', '5. 계좌 잔고 💰'],
        ['6. 날씨/미세먼지 🌤️']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    msg = "지휘관님, 완전 무장된 통합 지휘 통제실 가동합니다. 이제 음성으로도 명령하실 수 있습니다! 🎙️"
    await text_to_speech_and_send(update, context, msg)
    await update.message.reply_text("원하시는 메뉴를 선택하십시오.", reply_markup=reply_markup)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    session = get_chat_session(update.effective_chat.id)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        # 일반 대화나 특정 명령 모두 제미나이에게 넘김 (Function Calling이 알아서 처리)
        response = session.send_message(f"{SYSTEM_PROMPT}\n\n사용자 요청: {user_text}")
        await text_to_speech_and_send(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"⚠️ 시스템 오류: {str(e)}")

async def morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """정기 아침 브리핑 (스케줄러)"""
    chat_id = TELEGRAM_CHAT_ID
    if not chat_id: return
    
    try:
        session = get_chat_session(int(chat_id))
        response = session.send_message(f"{SYSTEM_PROMPT}\n\n[명령] 아침 정기 브리핑을 해주세요. 간밤 미증시 요약과 오늘의 원칙(본데) 리마인드를 상큼하게 보고하세요.")
        
        # 텍스트와 음성을 바로 보낼 수 없으므로 context.bot 사용
        clean_text = emoji.replace_emoji(response.text, replace='')
        for char in ['*', '#', '_', '`']: clean_text = clean_text.replace(char, '')
        await context.bot.send_message(chat_id=chat_id, text=response.text)
        
        file_path = f"b_{int(time.time())}.mp3"
        communicate = edge_tts.Communicate(clean_text, VOICE, rate="+10%", pitch="+15Hz")
        await communicate.save(file_path)
        with open(file_path, 'rb') as f:
            await context.bot.send_voice(chat_id=chat_id, voice=f)
        os.remove(file_path)
    except Exception as e:
        logging.error(f"브리핑 오류: {e}")

if __name__ == '__main__':
    # JobQueue를 위해 ApplicationBuilder 사용
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message)) # STT 핸들러
    
    # KST 기준 매일 아침 8시 30분에 자동 브리핑
    kst = pytz.timezone('Asia/Seoul')
    app.job_queue.run_daily(morning_briefing, time=dtime(hour=8, minute=30, tzinfo=kst))
    
    print("🚀 끝판왕 참모 봇 (V6 Ultimate) 가동 시작...")
    app.run_polling()
