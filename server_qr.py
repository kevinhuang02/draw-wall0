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
from typing import Dict, Set, List

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

# 掛載 static
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("⚠ static 資料夾不存在，Render 需要 static/index.html")

# 隨機主題
def get_random_topic():
    topics = [
        "太空冒險", "海底世界", "未來城市", "森林探險",
        "恐龍世界", "機器人王國", "動物村派對", "海盜寶藏",
        "異世界冒險"
    ]
    return random.choice(topics)

# 房間管理
rooms: Dict[str, Set[WebSocket]] = {}
room_topics: Dict[str, str] = {}       
room_history: Dict[str, List[dict]] = {}  
rooms_lock = asyncio.Lock()

# 最大 history 條數
MAX_HISTORY = int(os.environ.get("MAX_HISTORY", 5000))

# 廣播（排除自己）
async def broadcast(room_id: str, message: str, sender_ws: WebSocket = None):
    async with rooms_lock:
        sockets = list(rooms.get(room_id, []))

    to_remove = []
    for ws in sockets:
        if ws is sender_ws:
            continue
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)

    if to_remove:
        async with rooms_lock:
            for ws in to_remove:
                rooms[room_id].discard(ws)

# =====================
#    WebSocket 端點
# =====================
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    # 加入房間
    async with rooms_lock:
        rooms.setdefault(room_id, set()).add(websocket)
        if room_id not in room_topics:
            room_topics[room_id] = get_random_topic()
        room_history.setdefault(room_id, [])

    logger.info(f"🟢 WebSocket connected: room={room_id}")

    # 傳送房間主題給新加入者
    try:
        await websocket.send_text(json.dumps({
            "type": "topic",
            "value": room_topics[room_id]
        }))
    except Exception:
        logger.exception("無法將房間主題發送給新加入者")

    # 重播 history 給新加入者
    try:
        async with rooms_lock:
            history_snapshot = list(room_history.get(room_id, []))

        for entry in history_snapshot:
            try:
                await websocket.send_text(json.dumps(entry))
            except Exception:
                logger.warning("重播 history 給新加入者時發生錯誤，停止重播")
                break
    except Exception:
        logger.exception("重播 history 時發生例外")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                logger.warning("收到非 JSON 訊息，忽略")
                continue

            ptype = payload.get("type")

            # 產生主題
            if ptype == "generateTheme":
                new_topic = get_random_topic()
                room_topics[room_id] = new_topic
                msg = {"type": "topic", "value": new_topic}
                async with rooms_lock:
                    room_history.setdefault(room_id, []).append(msg)
                    if len(room_history[room_id]) > MAX_HISTORY:
                        room_history[room_id] = room_history[room_id][-MAX_HISTORY:]
                await broadcast(room_id, json.dumps(msg))
                continue

            # 清除畫布
            if ptype == "clear":
                async with rooms_lock:
                    room_history.setdefault(room_id, []).append(payload)
                    if len(room_history[room_id]) > MAX_HISTORY:
                        room_history[room_id] = room_history[room_id][-MAX_HISTORY:]
                await broadcast(room_id, json.dumps(payload), sender_ws=websocket)
                continue

            # 一般畫筆事件
            if ptype == "draw":
                async with rooms_lock:
                    room_history.setdefault(room_id, []).append(payload)
                    if len(room_history[room_id]) > MAX_HISTORY:
                        room_history[room_id] = room_history[room_id][-MAX_HISTORY:]
                await broadcast(room_id, json.dumps(payload), sender_ws=websocket)
                continue

            # 其他未知 type
            async with rooms_lock:
                room_history.setdefault(room_id, []).append(payload)
                if len(room_history[room_id]) > MAX_HISTORY:
                    room_history[room_id] = room_history[room_id][-MAX_HISTORY:]
            await broadcast(room_id, json.dumps(payload), sender_ws=websocket)

    except WebSocketDisconnect:
        logger.info(f"🔴 WebSocket disconnected: room={room_id}")
    except Exception:
        logger.exception("WebSocket 處理中發生未預期錯誤")
    finally:
        # 離線 -> 移除 websocket
        async with rooms_lock:
            if room_id in rooms:
                rooms[room_id].discard(websocket)
                if not rooms[room_id]:
                    del rooms[room_id]
                    room_topics.pop(room_id, None)
                    room_history.pop(room_id, None)
                    logger.info(f"房間 {room_id} 已經沒有使用者，room_topics/room_history 已刪除")

# =====================
# 網站首頁
# =====================
@app.get("/", include_in_schema=False)
async def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "static/index.html not found"}

# 產生一般 QRCode
@app.get("/qr/{text}")
def generate_qr(text: str):
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# 產生房間用 QRCode
@app.get("/qr-room/{room}")
def qr_room(room: str, name: str = "User"):
    if RENDER_BASE_URL:
        base = RENDER_BASE_URL.rstrip("/")
    else:
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

# Render / 開發啟動
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)



