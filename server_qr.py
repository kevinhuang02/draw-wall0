from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from openai import OpenAI

import uvicorn
import os
import json
import asyncio
import qrcode
import io
import random
import logging

from typing import Dict, Set, List

# --------------------
# 基本設定
# --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server_qr")

app = FastAPI()

# --------------------
# CORS
# --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# OpenAI
# --------------------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --------------------
# 靜態檔
# --------------------
RENDER_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --------------------
# 主題
# --------------------
def get_random_topic():
    return random.choice([
        "太空冒險", "海底世界", "未來城市", "森林探險",
        "恐龍世界", "機器人王國", "動物村派對", "海盜寶藏",
        "異世界冒險"
    ])

# --------------------
# 房間資料
# --------------------
rooms: Dict[str, Set[WebSocket]] = {}
room_topics: Dict[str, str] = {}
room_history: Dict[str, List[dict]] = {}
rooms_lock = asyncio.Lock()
MAX_HISTORY = 5000

# --------------------
# 廣播
# --------------------
async def broadcast(room_id: str, message: str, sender_ws: WebSocket = None):
    async with rooms_lock:
        sockets = list(rooms.get(room_id, []))

    dead = []
    for ws in sockets:
        if ws is sender_ws:
            continue
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)

    if dead:
        async with rooms_lock:
            for ws in dead:
                rooms[room_id].discard(ws)

# --------------------
# AI 故事
# --------------------
async def generate_ai_story(base64_image: str, lang="zh"):
    image = base64_image.replace("data:image/png;base64,", "")

    prompt = f"""
你是一個專業圖像觀察員。

請依序：
1. 描述畫面可見物件（不可猜）
2. 只能使用這些物件寫故事
3. 產生 1 分鐘動畫故事

語言：{"中文" if lang == "zh" else "英文"}

輸出 JSON：
{{
  "title": "...",
  "duration": 60,
  "narration": [{{"time": 0, "text": "..."}}],
  "scenes": []
}}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
                ]
            }],
            temperature=0.4,
            max_tokens=800
        )

        content = res.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]

        return json.loads(content)

    except Exception as e:
        logger.error(f"AI error: {e}")
        return {
            "title": "AI 故事生成失敗",
            "duration": 60,
            "narration": [{"time": 0, "text": "畫面正在分析中"}],
            "scenes": []
        }

# --------------------
# WebSocket
# --------------------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        rooms.setdefault(room_id, set()).add(websocket)
        room_topics.setdefault(room_id, get_random_topic())
        room_history.setdefault(room_id, [])

    # 發送主題
    await websocket.send_text(json.dumps({
        "type": "topic",
        "value": room_topics[room_id]
    }))

    # 歷史回放
    async with rooms_lock:
        history = list(room_history[room_id])

    for h in history:
        await websocket.send_text(json.dumps(h))

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            ptype = payload.get("type")

            # ---------------- 畫畫 ----------------
            if ptype == "draw":
                await broadcast(room_id, json.dumps(payload), websocket)
                continue

            # ---------------- clear ----------------
            if ptype == "clear":
                room_history[room_id].append(payload)
                await broadcast(room_id, json.dumps(payload))
                continue

            # ---------------- AI ----------------
            if ptype == "aiStory":
                story = await generate_ai_story(
                    payload.get("image"),
                    payload.get("lang", "zh")
                )

                msg = {"type": "story", "story": story}
                await broadcast(room_id, json.dumps(msg))
                continue

            # ---------------- 主題 ----------------
            if ptype == "generateTheme":
                topic = get_random_topic()
                room_topics[room_id] = topic

                msg = {"type": "topic", "value": topic}
                room_history[room_id].append(msg)

                await broadcast(room_id, json.dumps(msg))
                continue

            # ---------------- 預設 ----------------
            room_history[room_id].append(payload)

            if len(room_history[room_id]) > MAX_HISTORY:
                room_history[room_id] = room_history[room_id][-MAX_HISTORY:]

            await broadcast(room_id, json.dumps(payload), websocket)

    except WebSocketDisconnect:
        logger.info(f"disconnect {room_id}")

    finally:
        async with rooms_lock:
            rooms[room_id].discard(websocket)

            if not rooms[room_id]:
                rooms.pop(room_id, None)
                room_topics.pop(room_id, None)
                room_history.pop(room_id, None)

# --------------------
# HTTP API（AI）
# --------------------
@app.post("/ai/story")
async def ai_story(data: dict = Body(...)):

    room = data.get("room")
    canvas = data.get("canvas")
    lang = data.get("lang", "zh")

    if not canvas:
        return {"story": "沒有收到畫面"}

    story_json = await generate_ai_story(canvas, lang)

    narration = story_json.get("narration", [])
    story_text = "\n".join(n.get("text", "") for n in narration)

    msg = {
        "type": "story",
        "title": story_json.get("title", "AI 故事"),
        "story": story_text
    }

    if room:
        await broadcast(room, json.dumps(msg))

    return {
        "title": story_json.get("title", "AI 故事"),
        "story": story_text
    }

# --------------------
# 首頁
# --------------------
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# --------------------
# QR Code
# --------------------
@app.get("/qr-room/{room}")
def qr_room(room: str, name: str = "User"):
    base = RENDER_BASE_URL or "http://127.0.0.1:8000"
    url = f"{base}/static/index.html?room={room}&name={name}"

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")

# --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)



