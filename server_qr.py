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

rooms: dict[str, set[WebSocket]] = {}
rooms_lock = asyncio.Lock()

async def broadcast(room_id: str, message: str):
    async with rooms_lock:
        sockets = rooms.get(room_id, set()).copy()

    to_remove = []

    for ws in sockets:
        try:
            await ws.send_text(message)
        except:
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
            except:
                payload = {"type": "draw", "value": data}

            if payload.get("type") == "generateTheme":
                topic = get_random_topic()
                await broadcast(room_id, json.dumps({"type": "topic", "value": topic}))
            else:
                await broadcast(room_id, json.dumps(payload))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: room={room_id}")

    finally:
        async with rooms_lock:
            rooms.get(room_id, set()).discard(websocket)
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
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # 本地 8000，Render 用 $PORT
    uvicorn.run(app, host="0.0.0.0", port=port)