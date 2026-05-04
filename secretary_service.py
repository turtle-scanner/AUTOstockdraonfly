import os
import google.generativeai as genai
import requests
from datetime import datetime
from telegram_notifier import send_telegram_message
import todo_manager
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 설정 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3-flash-preview')

STUDY_BANK_FILE = "counseling_study_bank.txt"

def save_to_study_bank(category, content):
    """생성된 학습 내용을 파일에 누적 저장합니다."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(STUDY_BANK_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n[{timestamp}] [{category}]\n")
        f.write(content)
        f.write("\n" + "="*50)

def get_weather():
    prompt = "오늘의 서울 날씨와 옷차림 추천을 아주 간단하게 3줄로 알려줘."
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "날씨 정보를 가져오는 중 오류가 발생했습니다."

def get_news_briefing():
    prompt = "오늘 한국의 가장 중요한 경제 및 금융 뉴스 3가지를 제목 위주로 요약해줘."
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "뉴스 정보를 가져오는 중 오류가 발생했습니다."

def send_daily_briefing():
    chat_id = "7998778160"
    weather = get_weather()
    news = get_news_briefing()
    todos = todo_manager.get_todos(chat_id)
    todo_text = ""
    if todos:
        todo_text = "\n📍 *오늘의 할 일*\n"
        for i, t in enumerate(todos):
            status = "✅" if t['done'] else "⬜"
            todo_text += f"{status} {t['task']}\n"
    else:
        todo_text = "\n📍 *오늘의 할 일*\n아직 등록된 할 일이 없어요. 공부와 투자 모두 화이팅! 💕"

    message = f"☀️ *학습자님, 좋은 아침이에요!*\n\n☁️ *날씨 정보*\n{weather}\n\n📰 *주요 뉴스*\n{news}\n{todo_text}"
    send_telegram_message(message)

def send_counseling_problem():
    prompt = """
    너는 전문적인 임용 상담 교사 교육자야. 
    전문상담교사 임용 시험 수준에 맞게 '상담이론과 실제' 분야에서 지문형 문제 1개를 만들어줘.
    
    구성은 다음과 같아야 해:
    1. [지문]: 내담자와 상담자의 대화나 사례 (150자 내외)
    2. [질문]: 이 대화에서 나타난 상담 기법이나 이론의 개념을 묻는 질문
    3. [정답 및 해설]: "잠시 생각할 시간을 줄게"라는 멘트 뒤에 정답과 상세한 해설을 바로 포함해줘.
    
    이론 범위: 정신분석, 아들러, 행동주의, 인간중심, 게슈탈트, REBT, 인지치료 중 무작위. 
    음성으로 들었을 때 자연스럽도록 구어체로 작성해줘.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        message = f"📚 *오늘의 임용 상담 연습 문제*\n\n{text}"
        send_telegram_message(message)
        save_to_study_bank("QUESTION", text)
    except Exception as e:
        print(f"Error generating problem: {e}")

def send_theory_summary():
    prompt = "전문상담교사 임용 시험을 위해 '상담이론' 중 중요한 개념 1가지를 선정해서 핵심 요약(Core Summary) 노트를 만들어줘. 암기 팁도 포함해줘."
    try:
        response = model.generate_content(prompt)
        text = response.text
        message = f"💡 *임용 상담 핵심 이론 정리*\n\n{text}"
        send_telegram_message(message)
        save_to_study_bank("THEORY", text)
    except Exception as e:
        print(f"Error generating theory summary: {e}")

def send_pedagogy_problem():
    """임용 교육학 지문형 문제 생성 및 전송"""
    prompt = """
    너는 전문적인 임용 교육학 강사야. 
    중등 임용 고시 교육학 논술 및 객관식 수준에 맞게 지문형 문제 1개를 만들어줘.
    
    구성은 다음과 같아야 해:
    1. [지문]: 교육 상황 사례 (교사 간 대화, 수업 상황 등, 150자 내외)
    2. [질문]: 이 상황에 적용된 교육학 이론(교육과정, 교육심리, 교육행정 등)을 묻는 질문
    3. [정답 및 해설]: "잠시 생각할 시간을 줄게"라는 멘트 뒤에 정답과 논술용 핵심 키워드가 포함된 해설을 바로 포함해줘.
    
    범위: 교육과정, 교육심리, 교육방법 및 공학, 교육평가, 교육행정, 교육사회 중 무작위.
    음성으로 들었을 때 자연스럽도록 구어체로 작성해줘.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        message = f"🏫 *오늘의 교육학 연습 문제*\n\n{text}"
        send_telegram_message(message)
        save_to_study_bank("PEDAGOGY_QUESTION", text)
    except Exception as e:
        print(f"Error generating pedagogy problem: {e}")

def send_pedagogy_summary():
    """임용 교육학 핵심 이론 요약 전송"""
    prompt = "중등 임용 고시 교육학 대비를 위해 꼭 암기해야 할 핵심 이론 1가지를 선정해서 요약 노트를 만들어줘. 논술에서 활용할 수 있는 키워드 중심이면 좋겠어."
    try:
        response = model.generate_content(prompt)
        text = response.text
        message = f"💡 *교육학 핵심 이론 정리*\n\n{text}"
        send_telegram_message(message)
        save_to_study_bank("PEDAGOGY_THEORY", text)
    except Exception as e:
        print(f"Error generating pedagogy theory: {e}")
