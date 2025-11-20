# server_qr.py
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

# ---------- CORS (開發用，上線可鎖 domain) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 若要鎖 domain，改成 ["https://yourdomain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 房間 -> set of websocket connections
rooms: Dict[str, Set[WebSocket]] = {}
# websocket -> meta (room, name)
conn_meta: Dict[WebSocket, Dict] = {}

THEME_POOL = [
    "海底世界", "未來城市", "宇宙探險", "可愛動物派對",
    "秋天風景", "抽象線條", "童話城堡", "超級英雄大集合",
    "夏日海灘", "賽博龐克街景", "夜空流星", "復古懷舊",
    "美食嘉年華", "運動會", "音樂節"
]

# ---------- helper ----------
async def broadcast_to_room(room: str, message: dict, exclude: WebSocket = None):
    if room not in rooms:
        return
    data = json.dumps(message)
    to_remove = []
    for ws in list(rooms[room]):  # copy to avoid mutation during iteration
        if ws is exclude:
            continue
        try:
            await ws.send_text(data)
        except Exception as e:
            logger.warning("廣播失敗，標記為移除: %s", e)
            to_remove.append(ws)
    for ws in to_remove:
        rooms[room].discard(ws)
        conn_meta.pop(ws, None)
    if not rooms.get(room):
        rooms.pop(room, None)

# ---------- WebSocket endpoint ----------
@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await websocket.accept()
    logger.info("Accept connection to room %s", room)

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
                await broadcast_to_room(room, out, exclude=None)

            else:
                logger.debug("未知訊息類型: %s", mtype)

    except WebSocketDisconnect:
        logger.info("WebSocketDisconnect: %s", conn_meta.get(websocket))
    except Exception as e:
        logger.exception("WebSocket 發生例外: %s", e)
    finally:
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

# ---------- Health & info ----------
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})

@app.get("/info")
async def info():
    return JSONResponse({
        "description": "FastAPI WebSocket whiteboard server",
        "ws_example": "/ws/{room}",
        "notes": "Put your front-end static files in /static and the server will serve / as index.html if exists"
    })

# ---------- Static files (掛在 /static) ----------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.warning("static 資料夾不存在：%s", static_dir)

# ---------- Root: 如果有 static/index.html，回傳之 ----------
index_file = static_dir / "index.html"
@app.get("/")
async def root():
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"msg": "Whiteboard server. Put your frontend in /static/index.html"})

# ---------- Run (local debug) ----------
# Local:
#   uvicorn server_qr:app --host 0.0.0.0 --port 8000 --reload
# Render Start Command (recommended):
#   uvicorn server_qr:app --host 0.0.0.0 --port $PORT
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_qr:app", host="0.0.0.0", port=8000, reload=True)

