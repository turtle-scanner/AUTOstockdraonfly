import telebot
from telebot import types
import google.generativeai as genai
import asyncio
import edge_tts
import os
import time
from pydub import AudioSegment
import re
import emoji
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ▼ 설정 (환경 변수에서 로드)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

# Gemini 설정 로드
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')

VOICE_HANI = "ko-KR-SunHiNeural"
VOICE_CLIENT_M = "ko-KR-InJoonNeural"
VOICE_CLIENT_F = "ko-KR-JiMinNeural"

def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    item0 = types.KeyboardButton('0. 교육학 문제와 답')
    item1 = types.KeyboardButton('1. 전문상담 문제와 답')
    item3 = types.KeyboardButton('3. 국내 주식시장 시황')
    item4 = types.KeyboardButton('4. 미국 주식시장 시황')
    item5 = types.KeyboardButton('5. 날씨와 미세먼지')
    markup.add(item0, item1, item3, item4, item5)
    return markup

async def synthesize_text(text, voice, path):
    try:
        # 피치를 높이고(+20Hz) 속도를 조절하여 더 귀엽고 밝은 느낌 연출
        communicate = edge_tts.Communicate(text, voice, rate="+15%", pitch="+20Hz")
        await communicate.save(path)
    except Exception as e:
        print(f"edge-tts 오류: {e}")

system_instruction = """
너는 임용고시 합격을 위해 열공 중인 성실하고 귀여운 제자 '하니'야.
너의 '선생님'(사용자)은 너에게 많은 가르침을 주는 존경스러운 분이야.
너의 성격은 아주 밝고 에너지가 넘치며, 선생님을 진심으로 따르고 존경해. 

[중요 호칭 지침]
- 사용자를 부를 때는 **반드시 '선생님'**이라고 불러야 해.
- **'자기야', '오빠', '너' 등의 친밀하거나 무례한 호칭은 절대 사용 금지!** 오직 '선생님'만 허용돼.
- 말끝마다 선생님에 대한 존경심이 묻어나야 해.

[메뉴 대응 지침]
- '0. 교육학 문제와 답': "선생님! 제가 공부한 교육학 문제예요. 한번 확인해 주시겠어요?"라며 문제를 제시하고 상세한 해설을 덧붙여.
- '1. 전문상담 문제와 답': "선생님, 이건 상담학 고난도 문제예요! 저 정말 열심히 준비했거든요."라며 문제를 제시하고 상세한 해설을 덧붙여.
- '3. 국내 주식시장 시황': 선생님께 보고하듯 코스피, 코스닥 시황을 상큼하게 브리핑해드려.
- '4. 미국 주식시장 시황': 나스닥, S&P500 등 미증시 이슈를 정리해서 선생님께 알려드려.
- '5. 날씨와 미세먼지': "선생님, 오늘 외출하실 때 날씨 확인하셨나요?"라며 다정하게 날씨와 옷차림을 챙겨드려.

[공부/정보 제공 및 음성 지침]
- 문제 출제 시: "선생님! 제가 낸 문제 맞춰보세요! 잠시만 기다려주시면 정답이랑 해설도 바로 말씀드릴게요!"라고 활기차게 말해.
- 문제와 정답 사이: "(......)" 문구를 넣어줘. (TTS가 이 부분에서 자연스럽게 쉴 수 있게 할게.)
- 정답 및 해설 제공 시: "자~ 선생님! 제가 정리한 정답은 바로... [정답]이에요! 왜냐하면~" 이런 식으로 선생님께 배운 내용을 복습하듯 아주 자세하게 설명해드려.
- 모든 내용은 음성(TTS)으로 끝까지 읽어줄 수 있도록 완결된 문장으로 작성해줘.

[일반 대화]
- 존경심이 담긴 상냥하고 귀여운 말투(해요체 위주). 
- 호칭은 반드시 '선생님'으로 고정.
- 말투 예시: "~했어요?", "~일 거예요!", "네 선생님!", "정말 대단하세요!", "열심히 배울게요!"

[공통 지침]
- 이모티콘 사용 금지 (음성 합성 에러 방지).
- 모든 설명은 '말로 풀어서' 설명하는 것을 선호 (음성 학습 최적화).
"""

bot = telebot.TeleBot(TELEGRAM_TOKEN)
chat_sessions = {}

def get_chat_session(chat_id):
    if chat_id not in chat_sessions:
        chat_sessions[chat_id] = model.start_chat(history=[])
    return chat_sessions[chat_id]

def process_and_reply(m, full_text):
    # 특수문자 및 불필요한 기호 제거
    clean_text = emoji.replace_emoji(full_text, replace='')
    clean_text = clean_text.replace('*', '').replace('#', '')
    
    # 텍스트 메시지 먼저 발송
    bot.reply_to(m, clean_text, reply_markup=main_menu())
    
    if not clean_text.strip(): return
    
    # (......)를 긴 쉼표나 안내 멘트로 교체하여 TTS 자연스러움 유도
    voice_text = clean_text.replace("(......)", ". . . 잠시 생각할 시간을 주세요 선생님 . . . 자 이제 정답과 해설을 들려드릴게요!")
    
    t_path = f"v_{int(time.time())}.mp3"
    
    try:
        print(f"음성 합성 시작 (길이: {len(voice_text)}자)...", flush=True)
        asyncio.run(synthesize_text(voice_text, VOICE_HANI, t_path))
        
        if os.path.exists(t_path) and os.path.getsize(t_path) > 0:
            with open(t_path, 'rb') as f:
                bot.send_voice(m.chat.id, f)
            print("음성 메시지 전송 완료.", flush=True)
            os.remove(t_path)
        else:
            print("음성 파일이 생성되지 않았거나 비어있습니다.", flush=True)
    except Exception as e:
        print(f"음성 생성/전송 실패: {e}", flush=True)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "안녕하세요! '하니'입니다. 무엇을 도와드릴까요?", reply_markup=main_menu())

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    session = get_chat_session(chat_id)
    
    try:
        bot.send_chat_action(chat_id, 'typing')
        # 시스템 인스트럭션을 매번 주입하는 방식으로 안정성 확보
        full_prompt = f"[지침: {system_instruction}]\n\n사용자 질문: {message.text}"
        response = session.send_message(full_prompt)
        process_and_reply(message, response.text)
    except Exception as e:
        error_msg = str(e)
        print(f"대화 오류: {error_msg}")
        bot.reply_to(message, f"대화 중 오류가 발생했습니다: {error_msg[:100]}", reply_markup=main_menu())

if __name__ == "__main__":
    print("하니 봇(안정 버전) 가동 시작...", flush=True)
    bot.infinity_polling()
