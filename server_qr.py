# server_qr.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import uvicorn
import os
import logging
import json
import asyncio
import qrcode
import io
import random
from typing import Dict, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server_qr")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 環境變數（Render 上會自動注入 RENDER_EXTERNAL_URL，若沒有可手動設定）
RENDER_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 掛載 static（要確保 static 有 index.html）
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("⚠ static 資料夾不存在！")

def get_random_topic():
    topics = ["太空冒險","海底世界","未來城市","森林探險","恐龍世界","機器人王國","動物村派對"]
    return random.choice(topics)

# 使用 typing 避免 Python 版本問題
rooms: Dict[str, Set[WebSocket]] = {}
rooms_lock = asyncio.Lock()

async def broadcast(room_id: str, message: str):
    async with rooms_lock:
        sockets = rooms.get(room_id, set()).copy()

    to_remove = []

    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)

    if to_remove:
        async with rooms_lock:
            for ws in to_remove:
                rooms[room_id].discard(ws)

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        if room_id not in rooms:
            rooms[room_id] = set()
        rooms[room_id].add(websocket)

    logger.info(f"WebSocket connected: room={room_id}")

    # 新用戶進來 → 發送主題
    await websocket.send_text(json.dumps({"type": "topic", "value": get_random_topic()}))

    try:
        while True:
            data = await websocket.receive_text()

            try:
                payload = json.loads(data)
            except Exception:
                payload = {"type": "draw", "value": data}

            if isinstance(payload, dict) and payload.get("type") == "generateTheme":
                topic = get_random_topic()
                await broadcast(room_id, json.dumps({"type": "topic", "value": topic}))
            else:
                # 保證廣播的是字串
                await broadcast(room_id, json.dumps(payload) if isinstance(payload, dict) else str(payload))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: room={room_id}")

    finally:
        async with rooms_lock:
            if room_id in rooms:
                rooms[room_id].discard(websocket)
                if not rooms[room_id]:
                    del rooms[room_id]

@app.get("/", include_in_schema=False)
async def index():
    file_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "static/index.html not found"}

@app.get("/qr/{text}")
def generate_qr(text: str):
    """
    舊版：接收任意文字並回傳 QR 圖片（直接把 text 轉成 QR）
    範例： /qr/hello
    """
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/qr-room/{room}")
def qr_room(room: str, name: str = "User"):
    """
    產生指向公開 Render 網址的 QR code。
    如果在 Render 上，RENDER_BASE_URL 應該會自動有值（例如 https://your-app.onrender.com）。
    測試或本地執行時會 fallback 到 http://127.0.0.1:8000
    """
    if RENDER_BASE_URL:
        base = RENDER_BASE_URL.rstrip("/")
    else:
        # fallback for local dev
        host = os.environ.get("HOST", "127.0.0.1")
        port = os.environ.get("PORT", "8000")
        base = f"http://{host}:{port}"

    url = f"{base}/static/index.html?room={room}&name={name}"

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/env")
def show_env():
    return {"RENDER_EXTERNAL_URL": os.environ.get("RENDER_EXTERNAL_URL")} 

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # 本地 8000，Render 用 $PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
