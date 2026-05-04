import streamlit as st
import pandas as pd
import json
import os
import plotly.express as px
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="나의 학습 & 투자 대시보드", page_icon="📈", layout="wide")

st.title("🌹 나의 학습 & 투자 실시간 대시보드")
st.write(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 데이터 로드 함수
def load_data(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# 1. 포트폴리오 섹션
st.header("📊 현재 투자 포트폴리오")
positions = load_data("bonde_active_positions.json")

if positions:
    df = pd.DataFrame.from_dict(positions, orient='index')
    # 필요한 컬럼 정리
    df = df.reset_index().rename(columns={'index': '종목코드'})
    
    # 대시보드 상단 요약
    col1, col2, col3 = st.columns(3)
    total_value = (df['curr_price'] * df['qty']).sum()
    total_profit = (df['profit_rate']).mean() # 단순 평균 수익률
    
    col1.metric("총 보유 종목", f"{len(df)} 개")
    col2.metric("총 평가 금액", f"${total_value:,.2f}")
    col3.metric("평균 수익률", f"{total_profit:.2f}%")

    # 포트폴리오 테이블
    st.subheader("보유 종목 상세")
    st.dataframe(df[['name', '종목코드', 'qty', 'entry_price', 'curr_price', 'profit_rate', 'stop_price']], use_container_width=True)

    # 비중 차트
    st.subheader("종목별 투자 비중")
    fig = px.pie(df, values='qty', names='name', hole=.3)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("현재 보유 중인 종목이 없습니다. 매매 신호를 기다리는 중이에요! ✨")

# 2. 최근 매매 신호
st.header("🔔 최근 매매 신호 기록")
signals = load_data("bonde_signals.json") # 신호 기록 파일이 있다고 가정

if signals:
    sig_df = pd.DataFrame(signals)
    st.table(sig_df.tail(10))
else:
    st.write("최근 발생한 매매 신호가 없습니다.")

# 3. 임용 공부 현황
st.header("📚 오늘의 학습 브리핑")
if os.path.exists("counseling_study_bank.txt"):
    with open("counseling_study_bank.txt", "r", encoding="utf-8") as f:
        study_content = f.read().split("="*50)[-2:] # 최근 2개만
        for content in study_content:
            st.info(content.strip())
else:
    st.write("아직 오늘의 공부 기록이 생성되지 않았습니다.")

# 사이드바 설정
st.sidebar.header("설정 및 관리")
if st.sidebar.button("데이터 강제 동기화"):
    st.rerun()

st.sidebar.write("---")
st.sidebar.write("Developed by Antigravity 💕")
