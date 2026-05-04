# 본데 자동매매 봇 Dockerfile
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필수 라이브러리 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 프로젝트 파일 복사
COPY . .

# 환경 변수 설정 (Streamlit용)
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# 실행 명령어 (기본적으로 봇 실행)
# 대시보드를 같이 띄우려면 별도의 프로세스 관리가 필요하지만, 
# 여기서는 메인 자동매매 봇을 실행하는 것을 기본으로 합니다.
CMD ["python", "bonde_procedural_bot.py"]
