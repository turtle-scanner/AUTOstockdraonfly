import os
import requests
import json
import time
import pandas as pd
import numpy as np
import yfinance as yf
import pytz
import re
import sys
from datetime import datetime, timedelta

# Windows 환경에서 이모지 출력 시 cp949 인코딩 에러 방지
if sys.stdout.encoding != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except: pass

# --- [ CONFIG LOAD ] ---
def load_config():
    # 1. .streamlit/secrets.toml 확인 (로컬 실행 시)
    toml_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    config = {}
    if os.path.exists(toml_path):
        try:
            with open(toml_path, "r", encoding="utf-8") as f:
                import toml
                config = toml.load(f)
        except: pass
    
    # 2. 환경 변수와 병합 (GitHub Actions 등 우선순위 적용)
    return {
        "ak": os.getenv("KIS_APP_KEY", config.get("KIS_APP_KEY", "")),
        "as": os.getenv("KIS_APP_SECRET", config.get("KIS_APP_SECRET", "")),
        "an": os.getenv("KIS_ACCOUNT_NO", config.get("KIS_ACCOUNT_NO", "")).replace("-", ""),
        "mock": os.getenv("KIS_MOCK_TRADING", str(config.get("KIS_MOCK_TRADING", "false"))).lower() == "true",
        "tg_token": os.getenv("TELEGRAM_TOKEN", config.get("TELEGRAM_TOKEN", "")),
        "tg_id": os.getenv("TELEGRAM_CHAT_ID", config.get("TELEGRAM_CHAT_ID", ""))
    }

_CFG = load_config()
KIS_APP_KEY = _CFG["ak"]
KIS_APP_SECRET = _CFG["as"]
KIS_ACCOUNT_NO = _CFG["an"]
KIS_MOCK_TRADING = _CFG["mock"]
TELEGRAM_TOKEN = _CFG["tg_token"]
TELEGRAM_CHAT_ID = _CFG["tg_id"]

# [ TACTICAL ALLOCATION ]
US_RATIO = 0.7
KR_RATIO = 0.3
SLOTS_PER_REGION = 5
RISK_PER_TRADE = 0.01
STOP_LOSS_PCT = 0.05
EXCHANGE_RATE = 1400

# --- [ UTILS ] ---
def send_telegram_msg(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except: pass

def log_combat(msg, type="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{type}] {msg}")
    if type == "ERROR" or "성공" in msg or "포착" in msg or "브리핑" in msg:
        prefix = "🚨 " if type == "ERROR" else ("🚀 " if "성공" in msg else ("🎯 " if "포착" in msg else "📊 "))
        try:
            send_telegram_msg(f"{prefix}<b>[HEADLESS]</b> {msg}")
        except: pass

# --- [ KIS API AUTH ] ---
def call_kis_api(method, url, headers, params=None, json_body=None, retries=3):
    """재시도 로직이 포함된 KIS API 공통 호출 함수"""
    for i in range(retries):
        try:
            if method.upper() == 'GET':
                res = requests.get(url, headers=headers, params=params, timeout=12)
            else:
                res = requests.post(url, headers=headers, json=json_body, timeout=12)
            
            data = res.json()
            if res.status_code == 200 and data.get('rt_cd') in ['0', None]:
                return data
            else:
                msg = data.get('msg1', res.text)
                log_combat(f"API 응답 에러 (시도 {i+1}/{retries}): {msg}", "ERROR")
        except Exception as e:
            log_combat(f"네트워크/접속 에러 (시도 {i+1}/{retries}): {str(e)}", "ERROR")
        time.sleep(2)
    return None

def get_kis_access_token():
    base_url = "https://openapivts.koreainvestment.com:29443" if KIS_MOCK_TRADING else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET}
    res = call_kis_api("POST", url, {}, json_body=body)
    return res.get("access_token") if res else None

# --- [ DATA FETCH ] ---
def get_bulk_market_data(tickers, period="250d"):
    if not tickers: return pd.DataFrame()
    try:
        data = yf.download(tickers, period=period, interval="1d", group_by='ticker', threads=True, progress=False)
        return data
    except: return pd.DataFrame()

def get_ticker_data_from_bulk(bulk_df, ticker):
    try:
        if isinstance(bulk_df.columns, pd.MultiIndex):
            if ticker in bulk_df.columns.levels[0]: return bulk_df[ticker].dropna()
        else:
            if ticker in bulk_df.columns: return bulk_df.dropna()
    except: pass
    return pd.DataFrame()

# --- [ BALANCE & ASSET ALLOCATION ] ---
def get_total_assets(token):
    try:
        base_url = "https://openapivts.koreainvestment.com:29443" if KIS_MOCK_TRADING else "https://openapi.koreainvestment.com:9443"
        
        # 국내 자산 조회
        url_kr = f"{base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers_kr = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": "VTTC8434R" if KIS_MOCK_TRADING else "TTTC8434R"}
        params_kr = {"CANO": KIS_ACCOUNT_NO[:8], "ACNT_PRDT_CD": KIS_ACCOUNT_NO[8:], "AFHR_FLG": "N", "OFRT_BLAM_YN": "N", "PRCS_DVSN": "01", "UNPR_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        res_kr = call_kis_api("GET", url_kr, headers_kr, params=params_kr)
        kr_total = 0
        if res_kr:
            out2 = res_kr.get('output2', [])
            if out2: kr_total = float(out2[0].get('tot_evlu_amt', 0))
        
        # 해외 자산 조회
        url_us = f"{base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers_us = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": "VTTS3061R" if KIS_MOCK_TRADING else "TTTS3061R", "custtype": "P"}
        us_total_krw = 0
        for suffix in ["01", "02"]:
            params_us = {"CANO": KIS_ACCOUNT_NO[:8], "ACNT_PRDT_CD": suffix, "WCRC_FRCR_DVS_CD": "02", "NATN_CD": "840", "TR_PACC_CD": ""}
            res_us = call_kis_api("GET", url_us, headers_us, params=params_us)
            if res_us:
                o2 = res_us.get('output2')
                if isinstance(o2, list) and len(o2) > 0: o2 = o2[0]
                if o2:
                    us_total_krw += float(o2.get('tot_asst_amt') or o2.get('tot_evlu_pamt') or 0)
        
        total = kr_total + us_total_krw
        if total <= 0:
            log_combat("자산 조회 결과가 0입니다. 기본값(1,000만원)을 사용합니다.", "WARNING")
            return 10000000
        return total
    except Exception as e:
        log_combat(f"자산 조회 중 치명적 오류: {str(e)}", "ERROR")
        return 10000000

# --- [ MARKET HEALTH ] ---
def analyze_market_health():
    indices = {"^IXIC": "NASDAQ", "^KS11": "KOSPI"}
    report = "<b>[전술 시장 브리핑]</b>\n"
    is_defense = False
    try:
        data = yf.download(list(indices.keys()), period="100d", interval="1d", group_by='ticker', progress=False)
        for sym, name in indices.items():
            df = data[sym].dropna()
            if df.empty: continue
            curr_p = df['Close'].iloc[-1]; ma50 = df['Close'].rolling(50).mean().iloc[-1]
            status = "🟢 HEALTHY" if curr_p > ma50 else "🔴 BEARISH"
            if curr_p <= ma50: is_defense = True
            report += f"- {name}: {curr_p:,.1f} ({status})\n"
        report += f"\n💰 <b>자산 배분:</b> 미국 {int(US_RATIO*100)}% : 한국 {int(KR_RATIO*100)}%"
        report += "\n" + ("⚠️ <b>방어 모드:</b> 비중 축소" if is_defense else "⚡ <b>공격 모드:</b> 비중 정상")
        log_combat(report, "INFO")
    except: pass
    return is_defense

# --- [ STRATEGY ] ---
def analyze_bonde_setup(ticker, df):
    """
    본데(Bonde/Minervini) 스타일의 정석 전략:
    1. Trend Template (상승 2단계 확인)
    2. Relative Strength (시장 대비 강도)
    3. Explosive Pivot (거래량 동반 돌파)
    """
    try:
        if len(df) < 250: return {"status": "FAIL"}
        
        # 기본 지표 산출
        c = df['Close'].iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma150 = df['Close'].rolling(150).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        sma200_prev = df['Close'].rolling(200).mean().iloc[-20] # 1개월 전 200일선
        
        high_52w = df['High'].rolling(250).max().iloc[-1]
        low_52w = df['Low'].rolling(250).min().iloc[-1]
        
        # 1. [Trend Template] 상승 2단계 조건 (미너비니 정석)
        cond1 = c > sma150 > sma200                    # 주가 > 150 > 200
        cond2 = sma200 > sma200_prev                    # 200일선 상승 추세
        cond3 = sma50 > sma150 and sma50 > sma200      # 50일선이 150, 200일선 위
        cond4 = c > sma50                               # 주가가 50일선 위
        cond5 = c >= low_52w * 1.25                     # 신저가 대비 25% 이상 상승
        cond6 = c >= high_52w * 0.75                    # 신고가 대비 -25% 이내 (매물 소화)
        
        is_stage2 = all([cond1, cond2, cond3, cond4, cond5, cond6])
        if not is_stage2: return {"status": "FAIL"}

        # 2. [Relative Strength] 상대 강도 점수 (RS)
        # (최근 3개월 40% + 6개월 40% + 9개월 20% 가중치)
        rs = ((c/df['Close'].iloc[-63])*0.4 + (c/df['Close'].iloc[-126])*0.4 + (c/df['Close'].iloc[-189])*0.2) * 100
        if rs < 85: return {"status": "FAIL"} # 본데는 강한 놈만 잡습니다.

        # 3. [Explosive Pivot] 돌파 확인
        v = df['Volume'].iloc[-1]
        v_ma20 = df['Volume'].rolling(20).mean().iloc[-1]
        pct = (df['Close'] / df['Close'].shift(1).iloc[-1] - 1) * 100
        vol_surge = v / v_ma20
        
        # 변동성 수축 후 돌파 확인 (Range Position)
        range_pos = (df['Close'].iloc[-1] - df['Low'].iloc[-1]) / (df['High'].iloc[-1] - df['Low'].iloc[-1] + 1e-9)
        
        # 본데 EP 조건: 4% 이상 급등, 거래량 50% 이상 증가, 캔들 상단 마감
        is_ep = pct >= 4.0 and vol_surge >= 1.5 and range_pos >= 0.7
        
        quality = (rs * 0.6) + (vol_surge * 10) + (pct * 2)
        
        if is_ep:
            return {
                "status": "SUCCESS", 
                "ticker": ticker, 
                "type": "BONDE_EP", 
                "pct": round(pct, 2), 
                "rs": round(rs, 1), 
                "quality": round(quality, 1), 
                "close": c
            }
    except Exception as e:
        pass
    return {"status": "FAIL"}

# --- [ EXECUTION ] ---
def calculate_risk_based_qty(total_assets, curr_price, risk_pct=0.01, sl_pct=0.05, exchange_rate=1):
    """
    리스크 기반 포지션 사이징:
    수량 = (총자산 * 리스크비율) / (주당 리스크 금액)
    """
    risk_amount = total_assets * risk_pct
    risk_per_share = (curr_price * exchange_rate) * sl_pct
    if risk_per_share <= 0: return 0
    qty = int(risk_amount / risk_per_share)
    return qty

def execute_kis_market_order(ticker, qty, is_buy, token):
    if qty <= 0: return False
    is_kr = ticker.endswith(".KS") or ticker.endswith(".KQ") or (ticker.isdigit() and len(ticker) == 6)
    base_url = "https://openapivts.koreainvestment.com:29443" if KIS_MOCK_TRADING else "https://openapi.koreainvestment.com:9443"
    url = f"{base_url}/uapi/{'domestic-stock/v1/trading/order-cash' if is_kr else 'overseas-stock/v1/trading/order'}"
    body = {"CANO": KIS_ACCOUNT_NO[:8], "ACNT_PRDT_CD": KIS_ACCOUNT_NO[8:], "ORD_QTY": str(qty)}
    
    if is_kr:
        tr_id = ("VTTC0802U" if is_buy else "VTTC0801U") if KIS_MOCK_TRADING else ("TTTC0802U" if is_buy else "TTTC0801U")
        body.update({"PDNO": ticker.split('.')[0], "ORD_DVSN": "01", "ORD_UNPR": "0"})
    else:
        tr_id = ("VTTW0801U" if is_buy else "VTTW0802U") if KIS_MOCK_TRADING else ("TTTW0801U" if is_buy else "TTTW0802U")
        curr_p = 0
        try:
            p_data = yf.download(ticker, period="1d", interval="1m", progress=False)
            if not p_data.empty: curr_p = p_data['Close'].iloc[-1]
        except: pass
        order_p = curr_p * (1.01 if is_buy else 0.99) if curr_p > 0 else 0
        body.update({"OVRS_EXCG_CD": "NASD", "PDNO": ticker, "ORD_OVRS_P": f"{order_p:.2f}", "ORD_DVSN": "00"})
    
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": tr_id}
    res = call_kis_api("POST", url, headers, json_body=body)
    if res and res.get('rt_cd') == '0':
        log_combat(f"{'✅ 매수' if is_buy else '📉 매도'} 성공: {ticker} ({qty}주)")
        return True
    return False

def execute_kis_auto_cut(token):
    try:
        base_url = "https://openapivts.koreainvestment.com:29443" if KIS_MOCK_TRADING else "https://openapi.koreainvestment.com:9443"
        url = f"{base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": "VTTS3061R" if KIS_MOCK_TRADING else "TTTS3061R", "custtype": "P"}
        holdings = []
        for suffix in ["01", "02"]:
            params = {"CANO": KIS_ACCOUNT_NO[:8], "ACNT_PRDT_CD": suffix, "WCRC_FRCR_DVS_CD": "02", "NATN_CD": "840", "TR_PACC_CD": ""}
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200: 
                d = res.json()
                o1 = d.get('output1', [])
                if isinstance(o1, list): holdings += o1
        if not holdings: return
        tickers = [h.get('ovrs_pdno') for h in holdings if h.get('ovrs_pdno')]
        bulk_data = get_bulk_market_data(tickers, period="5d")
        for h in holdings:
            ticker = h.get('ovrs_pdno'); qty = int(h.get('hldg_qty', 0)); buy_p = float(h.get('pchs_avg_pric', 0))
            if qty <= 0 or buy_p <= 0: continue
            hist = get_ticker_data_from_bulk(bulk_data, ticker)
            if hist.empty: continue
            curr_p = hist['Close'].iloc[-1]; roi = (curr_p / buy_p - 1) * 100
            if roi >= 21.0:
                log_combat(f"💰 [익절] {ticker} 목표 도달 (+{roi:.1f}%)"); execute_kis_market_order(ticker, qty, False, token)
            elif roi <= -5.0:
                log_combat(f"📉 [손절] {ticker} 리스크 관리 집행 ({roi:.1f}%)"); execute_kis_market_order(ticker, qty, False, token)
    except: pass

def get_current_holdings(token):
    """현재 보유 중인 종목 리스트 추출 (중복 매수 방지용)"""
    try:
        base_url = "https://openapivts.koreainvestment.com:29443" if KIS_MOCK_TRADING else "https://openapi.koreainvestment.com:9443"
        url = f"{base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": "VTTS3061R" if KIS_MOCK_TRADING else "TTTS3061R", "custtype": "P"}
        holdings = []
        for suffix in ["01", "02"]:
            params = {"CANO": KIS_ACCOUNT_NO[:8], "ACNT_PRDT_CD": suffix, "WCRC_FRCR_DVS_CD": "02", "NATN_CD": "840", "TR_PACC_CD": ""}
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                d = res.json()
                o1 = d.get('output1', [])
                if isinstance(o1, list):
                    for h in o1:
                        ticker = h.get('ovrs_pdno')
                        qty = int(float(h.get('hldg_qty', 0)))
                        if ticker and qty > 0: holdings.append(ticker)
        return list(set(holdings))
    except: return []

def fetch_real_exchange_rate():
    """실시간 환율 페치 (yfinance)"""
    try:
        data = yf.download("USDKRW=X", period="1d", progress=False)
        if not data.empty: return float(data['Close'].iloc[-1])
    except: pass
    return 1400

# --- [ MAIN LOOP ] ---
def run_headless_cycle():
    log_combat("📡 교전 사이클 개시")
    token = get_kis_access_token()
    if not token: return
    
    # 실시간 정보 업데이트
    global EXCHANGE_RATE
    EXCHANGE_RATE = fetch_real_exchange_rate()
    
    total_asst = get_total_assets(token)
    is_defense = analyze_market_health()
    
    # 현재 보유 종목 파악
    current_holdings = get_current_holdings(token)
    execute_kis_auto_cut(token)

    # [ DYNAMIC SLOT ALLOCATION ] 자산 규모에 따른 종목 수 결정
    if total_asst <= 5000000:
        slots_us, slots_kr = 1, 1  # 총 2종목
    elif total_asst <= 10000000:
        slots_us, slots_kr = 3, 1  # 총 4종목
    elif total_asst <= 100000000:
        slots_us, slots_kr = 6, 2  # 총 8종목
    else:
        slots_us, slots_kr = 8, 4  # 1억 초과 시 기본 12종목 (필요시 조절)

    log_combat(f"📊 자산 규모별 슬롯 배정: 미국 {slots_us} / 한국 {slots_kr} (총 {slots_us + slots_kr}종목)")

    log_combat(f"📊 자산 규모별 슬롯 배정: 미국 {slots_us} / 한국 {slots_kr} (총 {slots_us + slots_kr}종목)")

# --- [ UNIVERSE EXPANSION ] ---
# AI 요원별 감시 종목 및 시장 통합
US_UNIVERSE = [
    "NVDA", "TSLA", "AAPL", "MSFT", "AMD", "PLTR", "SMCI", "META", "AMZN", "GOOGL", 
    "NFLX", "COIN", "AVGO", "CRWD", "ARM", "MSTR", "PANW", "SNOW", "VST", "CEG", 
    "NEE", "SO", "XOM", "CVX", "LLY", "NVO", "JPM", "V", "MA", "UNH", "COST", "WMT"
]
KR_UNIVERSE = [
    "005930", "000660", "196170", "042700", "005380", "000270", "035420", "035720", 
    "066570", "105560", "055550", "247540", "277810", "086520", "293490", "009830",
    "012450", "003670", "000100", "005490", "032640", "011070", "000210", "010140"
]

# AI 요원 설정 (Strategy Allocation)
AI_AGENTS = {
    "William O'Neil": {"style": "CANSLIM", "market": ["US", "KR"]},
    "Mark Minervini": {"style": "VCP", "market": ["US", "KR"]},
    "Pradeep Bonde": {"style": "Momentum/EP", "market": ["US", "KR"]},
}

# --- [ MAIN LOOP ] ---
def run_headless_cycle():
    log_combat("📡 [AI COMMAND] 전술 요원 현장 투입 및 교전 사이클 개시")
    token = get_kis_access_token()
    if not token: return
    
    global EXCHANGE_RATE
    EXCHANGE_RATE = fetch_real_exchange_rate()
    
    total_asst = get_total_assets(token)
    is_defense = analyze_market_health()
    
    current_holdings = get_current_holdings(token)
    execute_kis_auto_cut(token)

    # [ DYNAMIC SLOT ALLOCATION ]
    if total_asst <= 5000000:
        slots_us, slots_kr = 2, 1
    elif total_asst <= 50000000:
        slots_us, slots_kr = 4, 2
    else:
        slots_us, slots_kr = 8, 4

    log_combat(f"🤖 AI 요원 대기 중: {', '.join(AI_AGENTS.keys())}")
    log_combat(f"📊 자산 배분 설정: 미국 {int(US_RATIO*100)}% / 한국 {int(KR_RATIO*100)}%")

    for region, univ, ratio, slots in [("US", US_UNIVERSE, US_RATIO, slots_us), ("KR", KR_UNIVERSE, KR_RATIO, slots_kr)]:
        log_combat(f"🔎 [{region}] 시장 정찰 중... (대상: {len(univ)} 종목)")
        bulk_data = get_bulk_market_data(univ)
        hits = []
        for ticker in univ:
            df = get_ticker_data_from_bulk(bulk_data, ticker)
            res = analyze_bonde_setup(ticker, df)
            if res.get("status") == "SUCCESS": hits.append(res)
        
        hits = sorted(hits, key=lambda x: x['quality'], reverse=True)
        if hits:
            # 상위 타겟 선정
            for i in range(min(len(hits), 1)): # 사이클당 지역별 최대 1종목 진입 시도
                target = hits[i]
                
                if target['ticker'] in current_holdings:
                    log_combat(f"⏭️ {target['ticker']} (이미 보유 중)")
                    continue

                curr_p = target['close']
                ex_rate = EXCHANGE_RATE if region == "US" else 1
                max_budget = (total_asst * ratio) / slots
                if is_defense: max_budget *= 0.5

                qty = calculate_risk_based_qty(total_asst, curr_p, RISK_PER_TRADE, STOP_LOSS_PCT, ex_rate)
                if qty * curr_p * ex_rate > max_budget:
                    qty = int(max_budget / (curr_p * ex_rate))
                
                if qty > 0:
                    agent = "Pradeep Bonde" # 현재는 Bonde 로직 위주이므로
                    log_combat(f"🎯 [{region}] 요원 {agent} 타겟 포착: {target['ticker']} ({qty}주 진입)")
                    execute_kis_market_order(target['ticker'], qty, True, token)
        else: 
            log_combat(f"🕵️ [{region}] 현재 전술적 진입 요건을 충족하는 종목이 없습니다.")
            
    log_combat("✅ 모든 AI 요원 정찰 보고 완료. 사이클을 종료합니다.")

if __name__ == "__main__":
    while True:
        try:
            # 시작 시 시장 브리핑
            run_headless_cycle()
        except Exception as e:
            log_combat(f"메인 루프 치명적 오류: {e}", "ERROR")
        
        log_combat("💤 차기 교전 사이클 대기 (30분)")
        time.sleep(1800)
