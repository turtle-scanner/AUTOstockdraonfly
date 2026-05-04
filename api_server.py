from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import yfinance as yf
import json
from datetime import datetime
import pytz

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 실시간 주가 데이터 저장용
market_cache = {
    "data": [
        {"ticker": "KOSPI", "price": "2,750.32", "change_pct": "+1.2", "is_up": True},
        {"ticker": "NASDAQ", "price": "16,428.82", "change_pct": "+0.8", "is_up": True},
        {"ticker": "USD/KRW", "price": "1,345.20", "change_pct": "-0.3", "is_up": False},
        {"ticker": "NVDA", "price": "850.50", "change_pct": "+2.5", "is_up": True},
    ],
    "timestamp": ""
}

async def fetch_real_market_data():
    """yfinance를 통해 실제 데이터를 갱신하는 루프"""
    tickers = ["^KS11", "^KQ11", "^IXIC", "^GSPC", "USDKRW=X", "NVDA"]
    mapping = {
        "^KS11": "KOSPI", 
        "^KQ11": "KOSDAQ", 
        "^IXIC": "NASDAQ", 
        "^GSPC": "S&P 500", 
        "USDKRW=X": "USD/KRW", 
        "NVDA": "NVDA"
    }
    
    while True:
        try:
            # 기간과 간격 최적화
            data = yf.download(tickers, period="2d", interval="1m", progress=False)
            if not data.empty and 'Close' in data:
                new_data = []
                for t in tickers:
                    try:
                        if t in data['Close']:
                            series = data['Close'][t].dropna()
                            if not series.empty:
                                current_price = series.iloc[-1]
                                prev_close = series.iloc[0]
                                change = ((current_price - prev_close) / prev_close) * 100
                                new_data.append({
                                    "ticker": mapping[t],
                                    "price": f"{current_price:,.2f}",
                                    "change_pct": f"{change:+.2f}",
                                    "is_up": change >= 0
                                })
                    except Exception as inner_e:
                        print(f"Ticker {t} Error: {inner_e}")
                        continue
                
                if new_data:
                    market_cache["data"] = new_data
                    market_cache["timestamp"] = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M:%S")
        except Exception as e:
            print(f"Global Data Fetch Error: {e}")
        
        await asyncio.sleep(30) # 30초마다 갱신

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_real_market_data())

@app.get("/v6-api/market")
async def get_market():
    return market_cache

@app.get("/v6-api/status")
async def get_status():
    return {
        "status": "LIVE",
        "lastHeartbeat": datetime.now(pytz.timezone("Asia/Seoul")).strftime("%H:%M:%S"),
        "version": "6.0 Platinum"
    }

@app.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 실시간 데이터 전송
            payload = {
                "type": "MARKET_UPDATE",
                "data": market_cache["data"],
                "timestamp": market_cache["timestamp"]
            }
            await websocket.send_json(payload)
            await asyncio.sleep(5) # 5초마다 클라이언트에 전송
    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
