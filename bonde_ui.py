import streamlit as st
import json
import os
import pandas as pd

# 페이지 설정
st.set_page_config(page_title="Bonde Bot Web Dashboard", layout="wide")

# 보안 설정 (ID/PW: cntfed)
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        with st.sidebar:
            st.title("🔒 Secure Access")
            user_id = st.text_input("ID", value="cntfed")
            user_pw = st.text_input("Password", type="password")
            if st.button("Login"):
                if user_id == "cntfed" and user_pw == "cntfed":
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Invalid ID or Password")
        return False
    return True

if check_password():
    # --- [ THEME INJECTION ] ---
    st.markdown("""
        <style>
            /* 전체 배경을 블랙으로 설정 */
            .stApp {
                background-color: #050505;
                color: #FFFFFF;
            }
            /* 사이드바 배경 및 텍스트 */
            [data-testid="stSidebar"] {
                background-color: #0E0E0E;
                border-right: 1px solid #333;
            }
            /* 메트릭 카드 디자인 */
            [data-testid="stMetricValue"] {
                color: #00FFCC !important;
                font-family: 'Courier New', monospace;
            }
            /* 테이블 스타일 조정 */
            .stTable {
                background-color: #111111;
                border: 1px solid #333;
                border-radius: 10px;
                overflow: hidden;
            }
            th {
                background-color: #1A1A1A !important;
                color: #FFFFFF !important;
            }
            td {
                color: #E0E0E0 !important;
            }
            /* 구분선 색상 */
            hr {
                border: 0;
                height: 1px;
                background-image: linear-gradient(to right, rgba(0, 255, 204, 0), rgba(0, 255, 204, 0.75), rgba(0, 255, 204, 0));
            }
            /* 제목 폰트 및 색상 */
            h1, h2, h3 {
                color: #00FFCC !important;
                font-family: 'Inter', sans-serif;
                font-weight: 800;
            }
        </style>
    """, unsafe_allow_html=True)

    # 데이터 경로
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    POSITIONS_PATH = os.path.join(BASE_DIR, "bonde_active_positions.json")
    WATCHLIST_PATH = os.path.join(BASE_DIR, "bonde_watchlist.json")

    # 사용자 지정 가격 데이터 (최신 정보 반영)
    CASH_DEPOSIT = 297791
    PRICES = {"NVDA": 213.0, "MU": 742000.0, "001780": 3260.0}
    USD_KRW = 1400.0

    # 자산 계산 로직
    def calculate_assets():
        nvda_val = 17 * PRICES["NVDA"] * USD_KRW
        mu_val = 1 * PRICES["MU"]
        aluko_val = 2 * PRICES["001780"]
        total = int(nvda_val + mu_val + aluko_val + CASH_DEPOSIT)
        return total, int(nvda_val + mu_val + aluko_val)

    total_assets, stock_value = calculate_assets()

    # 메인 헤더
    st.title("🚀 Bonde Tactical Dashboard v3.6")
    st.markdown("---")

    # 상단 요약 카드
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Assets", f"₩{total_assets:,}")
    with col2:
        st.metric("Cash Deposit", f"₩{CASH_DEPOSIT:,}")
    with col3:
        st.metric("Stock Value", f"₩{stock_value:,}")
    with col4:
        st.metric("Risk Level", "1.0%", delta="Progressive")

    # 본문 영역: 보유 종목 현황 (수익률 추가)
    st.subheader("📊 Current Holdings & Performance")
    if os.path.exists(POSITIONS_PATH):
        with open(POSITIONS_PATH, "r", encoding="utf-8") as f:
            positions = json.load(f)
            
        pos_data = []
        for code, info in positions.items():
            qty = info['qty']
            entry_price = info.get('entry_price', 0)
            
            # 현재가 설정
            curr_price = PRICES.get(code, 0)
            if code == "NVDA": 
                val = f"₩{(qty*curr_price*USD_KRW):,.0f}"
                perf = f"{((curr_price/entry_price-1)*100):.2f}%" if entry_price > 0 else "N/A"
            elif code == "MU": 
                val = f"₩{(qty*curr_price):,.0f}"
                perf = f"{((curr_price/entry_price-1)*100):.2f}%" if entry_price > 0 else "N/A"
            else: 
                val = f"₩{(qty*3260):,}"
                perf = f"{((3260/entry_price-1)*100):.2f}%" if entry_price > 0 else "N/A"
            
            pos_data.append({
                "STOCK": info['name'],
                "QTY": qty,
                "ENTRY PRICE": f"{entry_price:,}" if entry_price > 0 else "Pending",
                "CURRENT PRICE": f"{curr_price:,}",
                "EST. VALUE": val,
                "PROFIT %": perf,
                "STATUS": "Monitoring"
            })
        
        # 데이터프레임 생성 및 색상 강조 (수익률 기준)
        df_pos = pd.DataFrame(pos_data)
        st.table(df_pos)

    # 관심 종목 섹션
    st.markdown("---")
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("🇰🇷 Watchlist Top 5 (KR)")
        if os.path.exists(WATCHLIST_PATH):
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                watchlist = json.load(f)
            kr_stocks = [s for s in watchlist if s.get('market') == 'KOSDAQ'][:5]
            st.dataframe(pd.DataFrame(kr_stocks)[['name', 'code', 'rs_score']])

    with right_col:
        st.subheader("🇺🇸 Watchlist Top 5 (US)")
        if os.path.exists(WATCHLIST_PATH):
            us_stocks = [s for s in watchlist if s.get('market') == 'NASDAQ'][:5]
            st.dataframe(pd.DataFrame(us_stocks)[['name', 'code', 'rs_score']])

    # 푸터
    st.sidebar.markdown("---")
    st.sidebar.info(f"Last Sync: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()
