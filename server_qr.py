# server_qr.py
import json
import logging
import random
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whiteboard_server")

app = FastAPI()

# 掛載 static 資料夾，index.html 放在 static/ 內
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# 房間 -> websocket 集合
rooms: Dict[str, Set[WebSocket]] = {}

# websocket -> meta (room, name)
conn_meta: Dict[WebSocket, Dict] = {}

# 範例主題池
THEME_POOL = [
    "海底世界", "未來城市", "宇宙探險", "可愛動物派對",
    "秋天風景", "抽象線條", "童話城堡", "超級英雄大集合",
    "夏日海灘", "賽博龐克街景", "夜空流星", "復古懷舊",
    "美食嘉年華", "運動會", "音樂節"
]

# ========= helper =========
async def broadcast_to_room(room: str, message: dict, exclude: WebSocket = None):
    """廣播訊息給房間所有人，可排除發送者"""
    if room not in rooms:
        return
    data = json.dumps(message)
    to_remove = []
    for ws in rooms[room]:
        if ws is exclude:
            continue
        try:
            await ws.send_text(data)
        except Exception as e:
            logger.warning("廣播失敗，標記移除: %s", e)
            to_remove.append(ws)
    for ws in to_remove:
        rooms[room].discard(ws)
        conn_meta.pop(ws, None)

# ========= WebSocket =========
@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await websocket.accept()
    logger.info("Accept connection to room %s", room)

    if room not in rooms:
        rooms[room] = set()
    rooms[room].add(websocket)
    conn_meta[websocket] = {"room": room, "name": None}

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except Exception:
                logger.warning("非 JSON 訊息: %s", text)
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
        logger.info("斷線: %s", conn_meta.get(websocket))
    except Exception as e:
        logger.exception("WebSocket 發生例外: %s", e)
    finally:
        meta = conn_meta.pop(websocket, None)
        if meta:
            r = meta.get("room")
            if r and websocket in rooms.get(r, set()):
                rooms[r].discard(websocket)
                logger.info("從房間 %s 移除連線，目前人數 %d", r, len(rooms[r]))
        try:
            await websocket.close()
        except Exception:
            pass

# ========= /qr-room/{room} =========
@app.get("/qr-room/{room_name}")
async def qr_room_redirect(room_name: str):
    """
    訪問 /qr-room/<room_name> 時，
    自動導向 index.html 並附上 ?room=<room_name>
    """
    redirect_url = f"/index.html?room={room_name}"
    return RedirectResponse(redirect_url)

# ========= Health / Info =========
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/info")
async def info():
    return {
        "description": "FastAPI WebSocket whiteboard server",
        "ws_example": "/ws/{room}",
        "notes": "Put your front-end static files in /static and connect to ws://host/ws/<room>"
    }

# ========= 啟動 =========
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server_qr:app", host="0.0.0.0", port=port, reload=True)

