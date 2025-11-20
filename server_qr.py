
# server.py
import json
import logging
import random
from typing import Dict, Set
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whiteboard_server")

app = FastAPI()

# ---------- CORS (開發用，實際上線可限制 domains) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 若要鎖 domain，改成 ["https://yourdomain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 房間 -> set of websocket connections
rooms: Dict[str, Set[WebSocket]] = {}
# websocket -> (room, name)
conn_meta: Dict[WebSocket, Dict] = {}

THEME_POOL = [
    "海底世界", "未來城市", "宇宙探險", "可愛動物派對",
    "秋天風景", "抽象線條", "童話城堡", "超級英雄大集合",
    "夏日海灘", "賽博龐克街景", "夜空流星", "復古懷舊",
    "美食嘉年華", "運動會", "音樂節"
]

# ---------- helper ----------
async def broadcast_to_room(room: str, message: dict, exclude: WebSocket = None):
    """將 message 廣播到 room 的所有連線（可排除發送者）"""
    if room not in rooms:
        return
    data = json.dumps(message)
    to_remove = []
    # 轉成 list 避免在迭代時集合被改變
    for ws in list(rooms[room]):
        if ws is exclude:
            continue
        try:
            await ws.send_text(data)
        except Exception as e:
            logger.warning("廣播失敗，標記為待移除: %s", e)
            to_remove.append(ws)
    # 移除無效連線
    for ws in to_remove:
        rooms[room].discard(ws)
        conn_meta.pop(ws, None)
    # 若房間已空，移除 key
    if not rooms.get(room):
        rooms.pop(room, None)

# ---------- WebSocket endpoint ----------
@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    """
    WebSocket 路徑 /ws/{room}
    前端連線範例： ws://<host>/ws/room1
    """
    await websocket.accept()
    logger.info("Accept connection to room %s", room)

    # 將 websocket 放入房間集合
    rooms.setdefault(room, set()).add(websocket)
    conn_meta[websocket] = {"room": room, "name": None}

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except Exception:
                logger.warning("接收到非 JSON 訊息：%s", text)
                continue

            sender = msg.get("sender") or "anon"
            conn_meta[websocket]["name"] = sender
            mtype = msg.get("type")

            if mtype == "draw":
                out = {
                    "type": "draw",
                    "mode": msg.get("mode"),
                    "color": msg.get("color"),
                    "size": msg.get("size"),
                    "x": msg.get("x"),
                    "y": msg.get("y"),
                    "begin": msg.get("begin", False),
                    "sender": sender
                }
                await broadcast_to_room(room, out, exclude=websocket)

            elif mtype == "clear":
                out = {"type": "clear", "sender": sender}
                await broadcast_to_room(room, out, exclude=websocket)

            elif mtype == "generateTheme":
                theme = random.choice(THEME_POOL)
                out = {"type": "topic", "value": theme, "by": sender}
                # 廣播給 room 的所有人（含發起者）
                await broadcast_to_room(room, out, exclude=None)

            else:
                logger.debug("未知訊息類型: %s", mtype)

    except WebSocketDisconnect:
        logger.info("WebSocketDisconnect: %s", conn_meta.get(websocket))
    except Exception as e:
        logger.exception("WebSocket 發生例外: %s", e)
    finally:
        # 清理連線
        meta = conn_meta.pop(websocket, None)
        if meta:
            r = meta.get("room")
            if r and websocket in rooms.get(r, set()):
                rooms[r].discard(websocket)
                logger.info("從房間 %s 移除一個連線，現在人數 %d", r, len(rooms.get(r, set())))
                if not rooms.get(r):
                    rooms.pop(r, None)
        try:
            await websocket.close()
        except Exception:
            pass

# ---------- 健檢與說明 ----------
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})

@app.get("/info")
async def info():
    return JSONResponse({
        "description": "FastAPI WebSocket whiteboard server",
        "ws_example": "/ws/{room}",
        "notes": "Put your front-end static files in /static and connect to ws://host/ws/<room>"
    })

# ---------- 將 static 掛到 /static（必須放在 route 定義之後，避免攔截 ws） ----------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.warning("static 資料夾不存在：%s", static_dir)

# 提供根路由，若有 static/final.html 就回傳（方便直接打根目錄）
index_file = static_dir / "final.html"
@app.get("/")
async def root():
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"msg": "Whiteboard server. Put your frontend in /static/final.html"})

# ---------- 本機開發啟動參考 ----------
# 在本機可以用：
#   uvicorn server:app --host 0.0.0.0 --port 8000 --reload
# 在 Render 的 Start Command（建議）：
#   uvicorn server:app --host 0.0.0.0 --port $PORT
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

