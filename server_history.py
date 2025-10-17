# =================================================================
# 1. IMPORT CÁC THƯ VIỆN CẦN THIẾT
# =================================================================
import aiohttp
import asyncio
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# =================================================================
# 2. KHỞI TẠO FASTAPI + CORS
# =================================================================
app = FastAPI(title="Crypto History & Realtime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# 3. BỘ NHỚ CACHE REST API
# =================================================================
cache_data = {}
cache_time = {}
CACHE_TTL = 30  # giây

# =================================================================
# 4. BIẾN LƯU DỮ LIỆU REALTIME (TỪ WEBSOCKET)
# =================================================================
latest_prices = {}  # {symbol: {"time":..., "price":...}}

# =================================================================
# 5. API: LỊCH SỬ GIÁ (REST, GỌI 1 LẦN)
# =================================================================
@app.get("/history")
async def get_history(
    symbol: str = Query(...),
    interval: str = Query("1h"),
    limit: int = Query(500),
    start: int = Query(None),
    end: int = Query(None),
):
    key = f"{symbol}_{interval}_{limit}_{start}_{end}"
    now = time.time()

    # ⚙️ Dùng cache để tránh gọi API nhiều
    if key in cache_data and now - cache_time.get(key, 0) < CACHE_TTL:
        return cache_data[key]

    params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)}
    if start:
        params["startTime"] = start
    if end:
        params["endTime"] = end

    url = "https://api.binance.com/api/v3/klines"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status != 200:
                    return {"error": f"Không lấy được dữ liệu: {text}"}
                data = await resp.json()
    except Exception as e:
        return {"error": str(e)}

    candles = [
        {
            "time": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in data
    ]

    cache_data[key] = candles
    cache_time[key] = now
    return candles

# =================================================================
# 6. API: LẤY GIÁ REALTIME (DỮ LIỆU CẬP NHẬT TỪ WS)
# =================================================================
@app.get("/realtime")
def get_realtime(symbol: str = Query(..., description="VD: btcusdt")):
    symbol = symbol.lower()
    if symbol not in latest_prices:
        return {"status": "waiting", "msg": f"Chưa có dữ liệu cho {symbol}"}
    return latest_prices[symbol]

# =================================================================
# 7. SSE STREAM: TRUYỀN GIÁ REALTIME LIÊN TỤC (DÙNG CHO WEB / APP)
# =================================================================
@app.get("/stream")
async def stream(symbol: str = Query("btcusdt")):
    symbol = symbol.lower()

    async def event_generator():
        while True:
            if symbol in latest_prices:
                yield f"data: {latest_prices[symbol]}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# =================================================================
# 8. TRANG CHỦ (THÔNG TIN SỬ DỤNG)
# =================================================================
@app.get("/")
def home():
    return {
        "message": "✅ Crypto History + Realtime API đang chạy!",
        "routes": {
            "history": "/history?symbol=btcusdt&interval=1h&limit=100",
            "realtime": "/realtime?symbol=btcusdt",
            "stream": "/stream?symbol=btcusdt"
        },
        "note": "REST để lấy dữ liệu, WS để realtime, SSE để stream trực tiếp (Render ready)."
    }

# =================================================================
# 9. KẾT NỐI WEBSOCKET BINANCE (REALTIME KHÔNG BỊ BAN IP)
# =================================================================
async def ws_listener(symbol: str):
    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@ticker"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=30) as ws:
                    print(f"🔌 Kết nối WS: {symbol}")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            latest_prices[symbol] = {
                                "time": data["E"],
                                "price": float(data["c"]),
                            }
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            break
        except Exception as e:
            print(f"⚠️ Lỗi WS {symbol}: {e}, reconnect sau 5s...")
            await asyncio.sleep(5)

# =================================================================
# 🔥 10. KHỞI TẠO TASK WEBSOCKET KHI SERVER START
# =================================================================
@app.on_event("startup")
async def start_ws_tasks():
    symbols = ["btcusdt", "ethusdt", "bnbusdt"]
    for sym in symbols:
        asyncio.create_task(ws_listener(sym))
    print("🚀 WS tasks started cho:", symbols)

# =================================================================
# 11. KHỞI ĐỘNG UVICORN
# =================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_history:app", host="0.0.0.0", port=8001, reload=True)
