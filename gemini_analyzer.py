import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging

# .env 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)

class GeminiStockAnalyzer:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("❌ GEMINI_API_KEY가 설정되지 않았습니다.")
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analyze_catalyst(self, stock_name, stock_code, context_data=None):
        """
        종목의 최근 급등 사유 및 펀더멘털 분석 (고도화 버전)
        context_data: {'roe': 15.5, 'rs_score': 120, 'sector': '반도체', 'recent_trend': 'BULL'}
        """
        if not self.model:
            return 50, "AI 분석 불가 (API 키 없음)"

        ctx_str = ""
        if context_data:
            ctx_str = "\n[실시간 기술/재무 지표 데이터]\n"
            for k, v in context_data.items():
                ctx_str += f"- {k}: {v}\n"

        prompt = f"""
        당신은 탑티어 퀀트 펀드의 수석 애널리스트이자 마크 미너비니(Mark Minervini)의 VCP 전략 전문가입니다.
        다음 종목의 최근 상승 모멘텀(Catalyst)과 펀더멘털을 정밀 분석해주세요.
        
        분석 대상 종목: {stock_name} ({stock_code}){ctx_str}
        
        [분석 지침]
        1. 최근 주요 뉴스, 공시, 매크로 시황을 바탕으로 해당 종목의 상승 사유를 도출하세요.
        2. 제공된 지표 데이터(ROE, RS Score 등)를 참고하여, 이 상승이 '지속 가능한 펀더멘털(실적/수주) 기반'인지 '일시적 테마/수급(밈 주식) 기반'인지 냉철하게 판별하세요.
        3. 주도 섹터(현재 시장 주도주) 여부를 평가하세요.
        4. 0~100점 사이의 '상승 모멘텀 점수(AI Score)'를 매겨주세요.
           - 85~100점: 초강력 실적 서프라이즈, 주도주, 메가 트렌드 부합 (강력 매수 권장)
           - 70~84점: 양호한 실적 및 차트, 긍정적 모멘텀
           - 50~69점: 평범하거나 모멘텀 부족
           - 0~49점: 단순 테마성 급등, 실적 뒷받침 안됨, 하락 추세 (매수 금지)
        
        반드시 다음 출력 형식을 정확히 지켜주세요:
        [SCORE] 점수 (숫자만)
        [REASON] 한 줄 요약 (예: AI 반도체 수요 급증에 따른 3분기 어닝 서프라이즈 기대감, RS 120+ 초강세)
        [DETAIL] 2~3문장의 상세 분석 내용
        """

        try:
            # 안전 설정 추가
            response = self.model.generate_content(prompt)
            text = response.text
            
            # 파싱
            score = 50
            reason = "분석 실패"
            detail = ""
            
            for line in text.split('\n'):
                if '[SCORE]' in line:
                    try:
                        score = int(''.join(filter(str.isdigit, line.split('[SCORE]')[1])))
                    except: pass
                elif '[REASON]' in line:
                    reason = line.replace('[REASON]', '').strip()
                elif '[DETAIL]' in line:
                    detail = line.replace('[DETAIL]', '').strip()
            
            # detail이 넘어오면 reason에 결합해서 더 풍부한 정보 제공
            final_reason = f"{reason} ({detail})" if detail else reason
            return score, final_reason
        except Exception as e:
            logger.error(f"Gemini 분석 중 에러: {e}")
            return 50, f"에러 발생: {e}"

if __name__ == "__main__":
    analyzer = GeminiStockAnalyzer()
    s, r = analyzer.analyze_catalyst("더존비즈온", "012510")
    print(f"Score: {s}, Reason: {r}")
