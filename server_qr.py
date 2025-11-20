
# server.py
import json
import logging
import random
import asyncio
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whiteboard_server")

app = FastAPI()

# 把 static 資料夾掛在根目錄（把你的 final.html 放在 static/ 裡面）
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# 房間 -> set of websocket connections
rooms: Dict[str, Set[WebSocket]] = {}

# websocket -> (room, name) 映射（方便在斷線時清理）
conn_meta: Dict[WebSocket, Dict] = {}

# 範例主題，server 隨機挑一個並廣播（不需要外部 AI）
THEME_POOL = [
    "海底世界", "未來城市", "宇宙探險", "可愛動物派對",
    "秋天風景", "抽象線條", "童話城堡", "超級英雄大集合",
    "夏日海灘", "賽博龐克街景", "夜空流星", "復古懷舊",
    "美食嘉年華", "運動會", "音樂節"
]

# ========== helper ==========
async def broadcast_to_room(room: str, message: dict, exclude: WebSocket = None):
    """將 message 廣播到 room 的所有連線（可排除發送者）"""
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
            logger.warning("廣播失敗，標記為待移除: %s", e)
            to_remove.append(ws)
    # 移除無效連線
    for ws in to_remove:
        rooms[room].discard(ws)
        conn_meta.pop(ws, None)

# ========== WebSocket endpoint ==========
@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    """
    WebSocket 路徑 /ws/{room}
    前端可以直接連到： ws://<host>/ws/room1
    前端訊息格式 (JSON) 範例：
      { "type":"draw", "mode":"pen","color":"#000","size":5,"x":123,"y":45, "begin":true, "sender":"user_123" }
      { "type":"clear", "sender":"user_123" }
      { "type":"generateTheme", "sender":"user_123" }
    Server 廣播範例：
      draw -> { "type":"draw", ... , "sender": "..." }
      clear -> { "type":"clear" }
      topic -> { "type":"topic", "value":"..." }
    """
    await websocket.accept()
    logger.info("Accept connection to room %s", room)

    # 將 websocket 放入房間集合
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
                logger.warning("接收到非 JSON 訊息：%s", text)
                continue

            # 確保 sender 存在（前端會加上 name）
            sender = msg.get("sender") or "anon"
            conn_meta[websocket]["name"] = sender

            mtype = msg.get("type")
            if mtype == "draw":
                # 直接把 draw 廣播給房間內其他人（包含必要欄位）
                # server 不做路徑管理，前端會用 sender 去區分 path
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
                out = { "type": "clear", "sender": sender }
                await broadcast_to_room(room, out, exclude=websocket)

            elif mtype == "generateTheme":
                # server 在池內隨機挑一個並廣播 topic
                theme = random.choice(THEME_POOL)
                out = { "type": "topic", "value": theme, "by": sender }
                # 廣播給 room 的所有人（含發起者）
                await broadcast_to_room(room, out, exclude=None)

            else:
                # 未知類型，記 log
                logger.debug("未知訊息類型: %s", mtype)

    except WebSocketDisconnect:
        logger.info("斷線: %s", conn_meta.get(websocket))
    except Exception as e:
        logger.exception("WebSocket 發生例外: %s", e)
    finally:
        # 清理
        meta = conn_meta.pop(websocket, None)
        if meta:
            r = meta.get("room")
            if r and websocket in rooms.get(r, set()):
                rooms[r].discard(websocket)
                logger.info("從房間 %s 移除一個連線，現在人數 %d", r, len(rooms[r]))
        try:
            await websocket.close()
        except Exception:
            pass

# ========== (選用) 一個簡單的 root route 說明 ==========
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

# 啟動時可使用 uvicorn server:app ...
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
