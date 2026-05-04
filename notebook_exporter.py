import os
import json
from datetime import datetime
import google.generativeai as genai

# 저장 경로 설정 (투자 및 공부 폴더 분리)
BASE_DIR = "notebook_sources"
INVEST_DIR = os.path.join(BASE_DIR, "investment")
STUDY_DIR = os.path.join(BASE_DIR, "study")

for d in [INVEST_DIR, STUDY_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# 제미나이 설정
GEMINI_API_KEY = "AIzaSyBOnusu-wC2dTojQM5zdJto2D-XNfoFaHQ"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3-flash-preview')

def load_study_bank():
    today = datetime.now().strftime("%Y-%m-%d")
    counseling_data = []
    pedagogy_data = []
    if os.path.exists("counseling_study_bank.txt"):
        with open("counseling_study_bank.txt", "r", encoding="utf-8") as f:
            content = f.read()
            blocks = content.split("="*50)
            for block in blocks:
                if today in block:
                    if "[QUESTION]" in block or "[THEORY]" in block:
                        counseling_data.append(block.strip())
                    elif "[PEDAGOGY_QUESTION]" in block or "[PEDAGOGY_THEORY]" in block:
                        pedagogy_data.append(block.strip())
    return "\n\n".join(counseling_data), "\n\n".join(pedagogy_data)

def generate_ai_review(positions):
    prompt = f"너는 현명한 주식 트레이더 아내야. 아래 주식 포지션을 보고 본데와 미너비니의 관점에서 따뜻하고 날카로운 조언을 해줘.\n\n{json.dumps(positions, indent=2, ensure_ascii=False)}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except: return "진단 실패"

def generate_flashcards(study_text):
    prompt = f"아래 내용을 바탕으로 Anki용 플래시카드(질문;답변) 10개를 만들어줘.\n\n{study_text}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except: return "생성 실패"

def export_daily_data():
    today = datetime.now().strftime("%Y-%m-%d")
    
    # --- 1. 투자(Investment) 데이터 내보내기 ---
    positions = {}
    if os.path.exists("bonde_active_positions.json"):
        with open("bonde_active_positions.json", "r", encoding="utf-8") as f:
            positions = json.load(f)
    
    ai_review = generate_ai_review(positions)
    stock_content = f"=== STOCK REPORT & AI REVIEW {today} ===\n\n{ai_review}\n\n[RAW DATA]\n{json.dumps(positions, indent=2, ensure_ascii=False)}"
    with open(os.path.join(INVEST_DIR, f"stock_report_{today}.txt"), "w", encoding="utf-8") as f:
        f.write(stock_content)

    # --- 2. 공부(Study) 데이터 내보내기 ---
    counseling_text, pedagogy_text = load_study_bank()
    
    # 상담 리포트
    with open(os.path.join(STUDY_DIR, f"counseling_report_{today}.txt"), "w", encoding="utf-8") as f:
        f.write(f"=== COUNSELING REPORT {today} ===\n\n{counseling_text}")
    
    # 교육학 리포트
    with open(os.path.join(STUDY_DIR, f"pedagogy_report_{today}.txt"), "w", encoding="utf-8") as f:
        f.write(f"=== PEDAGOGY REPORT {today} ===\n\n{pedagogy_text}")
    
    # 플래시카드
    full_study_text = counseling_text + "\n" + pedagogy_text
    if full_study_text.strip():
        flashcards = generate_flashcards(full_study_text)
        with open(os.path.join(STUDY_DIR, f"flashcards_{today}.txt"), "w", encoding="utf-8") as f:
            f.write(f"=== FLASHCARDS {today} ===\n\n{flashcards}")

    print(f"[{datetime.now()}] 투자/공부 데이터 분리 내보내기 완료!")

if __name__ == "__main__":
    export_daily_data()
