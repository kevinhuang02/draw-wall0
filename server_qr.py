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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Render 環境網址
RENDER_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 挂载 static 目录（Render 必須有 index.html 才能正常工作）
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("⚠ static 資料夾不存在！Render 一定要有 static/index.html")

# 隨機主題
def get_random_topic():
    topics = [
        "太空冒險","海底世界","未來城市","森林探險",
        "恐龍世界","機器人王國","動物村派對","海盜寶藏","異世界探險"
    ]
    return random.choice(topics)

# 房間管理
rooms: Dict[str, Set[WebSocket]] = {}
rooms_lock = asyncio.Lock()

# 廣播
async def broadcast(room_id: str, message: str):
    async with rooms_lock:
        sockets = rooms.get(room_id, set()).copy()

    to_remove = []

    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)

    # 移除失效連線
    if to_remove:
        async with rooms_lock:
            for ws in to_remove:
                rooms[room_id].discard(ws)


# WebSocket 端點
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        rooms.setdefault(room_id, set()).add(websocket)

    logger.info(f"🟢 WebSocket connected: room={room_id}")

    # 發送主題給新進使用者
    await websocket.send_text(json.dumps({
        "type": "topic",
        "value": get_random_topic()
    }))

    try:
        while True:
            data = await websocket.receive_text()

            try:
                payload = json.loads(data)
            except:
                payload = {"type": "draw"}

            # 主題生成
            if payload.get("type") == "generateTheme":
                topic = get_random_topic()
                await broadcast(room_id, json.dumps({"type": "topic", "value": topic}))
                continue

            # 一般繪圖 or 清除
            await broadcast(room_id, json.dumps(payload))

    except WebSocketDisconnect:
        logger.info(f"🔴 WebSocket disconnected: room={room_id}")

    finally:
        async with rooms_lock:
            if room_id in rooms:
                rooms[room_id].discard(websocket)
                if not rooms[room_id]:
                    del rooms[room_id]


# 網站首頁
@app.get("/", include_in_schema=False)
async def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "static/index.html not found"}


# 一般 QR Code（輸入文字 → QR）
@app.get("/qr/{text}")
def generate_qr(text: str):
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# 指向指定房間的 QR Code
@app.get("/qr-room/{room}")
def qr_room(room: str, name: str = "User"):
    """
    產生掃描後可直接進房間的 QR Code（手機可加入同個房間）
    """

    if RENDER_BASE_URL:
        base = RENDER_BASE_URL.rstrip("/")
    else:
        # Local dev
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


# Render 的啟動方式
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
