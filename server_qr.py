from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import os
import logging
import json
import asyncio
import socket
import tempfile
import qrcode
import random  

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server_qr")

# ---------- FastAPI 初始化 ----------
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

# 掛載 static (本地要確保 static 不為空資料夾)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(f"⚠ 找不到 static 資料夾：{STATIC_DIR}")

# ---------- 隨機主題功能 ----------
def get_random_topic():
    topics = [
        "太空冒險",
        "海底世界",
        "未來城市",
        "森林探險",
        "恐龍世界",
        "機器人王國",
        "動物村派對"
    ]
    return random.choice(topics)

# ---------- WebSocket Room 狀態 ----------
rooms: dict[str, set[WebSocket]] = {}
rooms_lock = asyncio.Lock()

# ---------- 廣播 ----------
async def broadcast(room: str, message: str):
    async with rooms_lock:
        sockets = rooms.get(room, set()).copy()

    to_remove = []
    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)

    if to_remove:
        async with rooms_lock:
            for ws in to_remove:
                rooms[room].discard(ws)

# ---------- WebSocket Endpoint ----------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        if room_id not in rooms:
            rooms[room_id] = set()
        rooms[room_id].add(websocket)

    logger.info(f"WebSocket connected: room={room_id}")

    # ➤ 新增：新成員加入時送出隨機主題
    topic = get_random_topic()
    data = await websocket.send_text(json.dumps({"type": "topic", "value": topic}))
    msg = json.loads(data) # 解析收到的 JSON 數據

    if msg.get("type") == "generateTheme":
        topic = get_random_topic()
        topic_msg = json.dumps({"type": "topic", "value": topic})
        await broadcast(room_id, topic_msg) # 廣播給房間內所有人
        logger.info(f"Broadcasted new random topic: {topic}")
    else:
        # 處理繪圖數據，進行廣播
        await broadcast(room_id, data)
    logger.info(f"Sent random topic to new user: {topic}")

    try:
        while True:
            data = await websocket.receive_text()
            await broadcast(room_id, data)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: room={room_id}")

    finally:
        async with rooms_lock:
            rooms.get(room_id, set()).discard(websocket)
            if not rooms[room_id]:
                del rooms[room_id]

# ---------- HTTP ----------
# ---------- HTTP ----------
# @app.get("/") # 移除原本的根路由
# async def root():
#     return {"message": "Local FastAPI Server is running!"}

# 新增根路由：回傳 index.html
@app.get("/", include_in_schema=False) # include_in_schema=False 避免它出現在 API 文件
async def index_html():
    file_path = os.path.join(STATIC_DIR, "index.html")
    
    if os.path.exists(file_path):
        # 使用 FileResponse 回傳位於 static 資料夾內的 index.html
        return FileResponse(file_path, media_type="text/html")
    else:
        # 如果找不到檔案，回傳錯誤訊息
        return {"error": "Index file not found in static directory"}, 404

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---------- 取得本地 IP ----------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# ---------- QRCode API ----------
@app.get("/qr/{text}")
def generate_qr(text: str):
    img = qrcode.make(text)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=STATIC_DIR)
    img.save(tmp.name)
    filename = os.path.basename(tmp.name)
    return {"url": f"/static/{filename}"}

# ---------- 啟動時自動生成 QR Code ----------
def show_qr_code(room="room1"):
    host = get_local_ip()
    port = 8000
    url = f"http://{host}:{port}/static/index.html?room={room}&name=User"

    print(f"\n🔗 手機掃描加入房間：\n{url}\n")

    img = qrcode.make(url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp.name)
    print(f"QR Code 文件位置：{tmp.name}")

    try:
        import platform
        if platform.system() == "Darwin":
            os.system(f"open {tmp.name}")
        elif platform.system() == "Windows":
            os.system(f"start {tmp.name}")
        else:
            os.system(f"xdg-open {tmp.name}")
    except:
        pass

# ---------- 主程式 ----------
if __name__ == "__main__":
    show_qr_code("room1")
    uvicorn.run(app, host="0.0.0.0", port=8000)