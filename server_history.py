import aiohttp
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Flexible Crypto History API")

# =====================================================
# 1️⃣ Cấu hình CORS – cho phép mọi nguồn (UI, mobile, v.v.)
# =====================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# 2️⃣ Bộ nhớ cache để giảm số request tới Binance
# =====================================================
cache_data = {}
cache_time = {}
CACHE_TTL = 60  # tăng TTL lên 60 giây cho Render (đỡ bị ban IP)

# =====================================================
# 3️⃣ Endpoint chính /history
# =====================================================
@app.get("/history")
async def get_history(
    symbol: str = Query(..., description="Mã crypto, vd: btcusdt"),
    interval: str = Query("1h", description="Khoảng thời gian mỗi nến: 1m,5m,15m,1h,4h,1d,1w,1M"),
    limit: int = Query(500, description="Số lượng nến (1–1000)"),
    start: int = Query(None, description="Timestamp (ms) bắt đầu"),
    end: int = Query(None, description="Timestamp (ms) kết thúc"),
):
    """📊 API lấy lịch sử giá crypto từ Binance (tối ưu cho Render)"""

    key = f"{symbol}_{interval}_{limit}_{start}_{end}"
    now = time.time()

    # ✅ Kiểm tra cache
    if key in cache_data and now - cache_time.get(key, 0) < CACHE_TTL:
        return cache_data[key]

    # ✅ Chuẩn bị params cho Binance
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(limit, 1000)
    }
    if start:
        params["startTime"] = start
    if end:
        params["endTime"] = end

    url = "https://api.binance.com/api/v3/klines"

    # ✅ Gọi API Binance (có timeout để tránh treo trên Render)
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return {"error": f"Không lấy được dữ liệu: {await resp.text()}"}
                data = await resp.json()
    except Exception as e:
        return {"error": f"Lỗi kết nối Binance: {e}"}

    # ✅ Chuyển dữ liệu về dạng dễ dùng
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

    # ✅ Lưu cache
    cache_data[key] = candles
    cache_time[key] = now
    return candles


# =====================================================
# 4️⃣ Endpoint mặc định /
# =====================================================
@app.get("/")
def home():
    return {
        "message": "✅ Flexible History API is running on Render!",
        "usage": "/history?symbol=btcusdt&interval=1h&limit=500",
        "advanced": "/history?symbol=ethusdt&interval=1d&start=1700000000000&end=1705000000000",
        "notes": "Dùng interval + limit hoặc start/end để tuỳ chỉnh thời gian linh hoạt."
    }


# =====================================================
# 5️⃣ Chạy local (Render tự dùng gunicorn, không cần dòng này)
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_history:app", host="0.0.0.0", port=8001)
