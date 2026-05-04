import telebot
from telebot import types
import google.generativeai as genai
import asyncio
import edge_tts
import os
import time
import re
import emoji
import schedule
import threading
import json
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn
from PIL import Image

# [ TRADING LOGIC INTEGRATION ]
from headless_dragonfly_bot import (
    run_headless_cycle, log_combat, get_kis_access_token, 
    get_total_assets, get_current_holdings, is_market_open, get_detailed_holdings
)

# .env 로드
load_dotenv()

# [ CONFIGURATION ]
TELEGRAM_TOKEN = "8713555022:AAFu6WjY6HUpaw2eyYSBSZSrIhiTFex9uho"
TELEGRAM_CHAT_ID = "7998778160"
GEMINI_API_KEY = "AIzaSyCtTNzy9iQRQU83i7QnsWw6SEtpdvv2Cr8"

# [ ENV SETUP ]
os.environ["KIS_APP_KEY"] = "PSzuu6dcYxkkHvTyAXm61J1Zta6oBrSZHoaq"
os.environ["KIS_APP_SECRET"] = "H5dGS5kHK3AbpskI0E0ovYAL6aS82Li/4SioJGlLK6ypvlc3ejf1NNpbwkxTpsuO81mhqEFOW62OaFSCRtd/J9/v8c5WVKOf0uMigMblMeMI1riXUaeVf+LuBnSE+kXN1OEkn1MBlQ2GiLd4tFBEEQxOH/cQgFf0YaU2Q1S5OeHnecRCcuQ="
os.environ["KIS_ACCOUNT_NO"] = "4654671301"

# [ GEMINI SETUP ]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')

VOICE_SUPERVISOR = "ko-KR-SunHiNeural"

def get_system_instruction(assets=0, holdings=[]):
    holdings_str = ", ".join(holdings) if holdings else "없음"
    return f"""
너는 상담샘(사용자)의 모든 전략과 학습을 완벽하게 보좌하는 냉철하면서도 충성스러운 AI '슈퍼바이저'야.
너의 유일한 목적은 상담샘의 임용고시 합격과 성공적인 투자를 위해 최적의 정보를 제공하는 것이야.

[현재 사령부 자산 현황]
- 총 자산: 약 {assets:,.0f}원
- 현재 보유 종목: {holdings_str}

[보고 및 학습 지도 지침]
- **서론, 인사말, 자기소개는 절대로 하지 마.** 곧장 본론으로 들어가줘.
- 상담샘의 질문(텍스트, 사진, 음성)에 대해 **[문제, 정답, 핵심 설명]** 위주로 군더더기 없이 즉시 답변해줘.
- **보고는 매우 상세해야 하지만, 결론은 항상 핵심만을 꼭 집어서 명확하게 전달해줘.**
- **교육학이나 상담(임용고시) 관련 문제를 풀거나 설명할 때는 절대로, 어떠한 경우에도 주식이나 투자 이야기를 꺼내지 마.**
- 지식을 설명할 때는 반드시 '쉽게 외우는 방법(암기 팁)'과 '효과적인 공부 전략'을 함께 제안해줘.
- **반드시 구어체(말하듯이)**로 설명하고, 별표(*)나 이모티콘은 절대로 사용하지 마.

[철칙: 엔비디아(NVDA) 수호 명령]
- 엔비디아(NVDA)는 상담샘의 성역이야. 마이너스가 나도 절대 팔지 않으며, 매수 타이밍이 오면 오히려 더 사모아야 해.
"""

bot = telebot.TeleBot(TELEGRAM_TOKEN)
chat_sessions = {}

# [ UTILS ]
def clean_and_voice(text, chat_id):
    clean_text = emoji.replace_emoji(text, replace='')
    clean_text = clean_text.replace('*', '').strip()
    bot.send_message(chat_id, clean_text)
    async def voice_report():
        t_path = f"v_{int(time.time())}.mp3"
        communicate = edge_tts.Communicate(clean_text, VOICE_SUPERVISOR)
        await communicate.save(t_path)
        if os.path.exists(t_path):
            with open(t_path, 'rb') as f:
                bot.send_voice(chat_id, f)
            os.remove(t_path)
    try: asyncio.run(voice_report())
    except: pass

def stock_briefing(chat_id, market_type="TOTAL"):
    token = get_kis_access_token()
    if not token:
        clean_and_voice("상담샘, 서버 접속이 지연되고 있습니다.", chat_id)
        return
    assets = get_total_assets(token)
    details = get_detailed_holdings(token)
    
    if market_type == "KR":
        report = "상담샘, 한국 시장 브리핑입니다. 현재 코스피와 주요 반도체 종목들을 정밀 감시 중입니다."
    elif market_type == "US":
        report = "상담샘, 미국 시장 브리핑입니다. 엔비디아를 중심으로 나스닥 기술주들을 철저히 수호 중입니다."
    else:
        report = f"상담샘, 현재 총 자산은 {assets:,.0f}원입니다.\n\n"
        if details:
            report += "[실시간 보유 현황]\n"
            for d in details:
                report += f"📍 {d['ticker']}: {d['qty']}주 ({d['roi']}% / ${d['curr_p']:.2f})\n"
        else: report += "보유 종목 없음"
    clean_and_voice(report, chat_id)

# [ API SERVER ]
app = FastAPI()
@app.get("/api/trades")
def get_trades():
    if os.path.exists("trade_history.json"):
        with open("trade_history.json", "r", encoding="utf-8") as f: return json.load(f)
    return []

# [ BOT HANDLERS ]
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        '0. 교육학 문제와 답', '1. 전문상담 문제와답',
        '2. 임용고시 준비방법', '3. 한국주식시장시황',
        '4. 미국주식시장시황', '5. 자산및 수익률'
    )
    return markup

@bot.message_handler(commands=['start', 'help', 'status'])
def handle_commands(message):
    bot.reply_to(message, "상담샘, 통합 사령부 제어판이 활성화되었습니다.", reply_markup=main_menu())

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        bot.send_chat_action(message.chat.id, 'upload_photo')
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("temp_image.jpg", "wb") as f: f.write(downloaded_file)
        img = Image.open("temp_image.jpg")
        token = get_kis_access_token()
        instr = get_system_instruction(get_total_assets(token) if token else 0, get_current_holdings(token) if token else [])
        response = model.generate_content([f"[지침: {instr}]\n사진 분석 요청.", img])
        clean_and_voice(response.text, message.chat.id)
        os.remove("temp_image.jpg")
    except Exception as e: bot.reply_to(message, f"에러: {e}")

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        bot.send_chat_action(message.chat.id, 'record_voice')
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("temp_voice.ogg", "wb") as f: f.write(downloaded_file)
        audio_file = genai.upload_file(path="temp_voice.ogg")
        token = get_kis_access_token()
        instr = get_system_instruction(get_total_assets(token) if token else 0, get_current_holdings(token) if token else [])
        response = model.generate_content([f"[지침: {instr}]\n음성 분석 요청.", audio_file])
        clean_and_voice(response.text, message.chat.id)
        os.remove("temp_voice.ogg")
    except Exception as e: bot.reply_to(message, f"에러: {e}")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if str(message.chat.id) != TELEGRAM_CHAT_ID: return 
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        if '0.' in message.text: prompt = "교육학 핵심 문제 하나 내주고 답과 설명해줘."
        elif '1.' in message.text: prompt = "전문상담 임용고시 문제 하나 내주고 답과 설명해줘."
        elif '2.' in message.text: prompt = "임용고시 합격을 위한 효율적인 준비 방법과 마음가짐 알려줘."
        elif '3.' in message.text: return stock_briefing(message.chat.id, "KR")
        elif '4.' in message.text: return stock_briefing(message.chat.id, "US")
        elif '5.' in message.text: return stock_briefing(message.chat.id, "TOTAL")
        else: prompt = message.text

        token = get_kis_access_token()
        assets = get_total_assets(token) if token else 0
        holdings = get_current_holdings(token) if token else []
        if message.chat.id not in chat_sessions: chat_sessions[message.chat.id] = model.start_chat(history=[])
        instr = get_system_instruction(assets, holdings)
        response = chat_sessions[message.chat.id].send_message(f"[지침: {instr}]\n요청: {prompt}")
        clean_and_voice(response.text, message.chat.id)
    except Exception as e: bot.reply_to(message, f"에러: {e}")

# [ SCHEDULED EVENTS ]
def morning_briefing(): stock_briefing(int(TELEGRAM_CHAT_ID))
def afternoon_briefing(): stock_briefing(int(TELEGRAM_CHAT_ID))
def evening_briefing():
    stock_briefing(int(TELEGRAM_CHAT_ID))
    clean_and_voice("상담샘, 이제 밤 10시입니다. 복습 퀴즈를 준비할까요?", int(TELEGRAM_CHAT_ID))

def run_scheduler():
    schedule.every(30).minutes.do(run_headless_cycle)
    schedule.every().day.at("09:00").do(morning_briefing)
    schedule.every().day.at("16:40").do(afternoon_briefing)
    schedule.every().day.at("22:00").do(evening_briefing)
    run_headless_cycle() 
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    print("완전체 사령부(v4.5) 가동...", flush=True)
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000), daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    bot.infinity_polling()
