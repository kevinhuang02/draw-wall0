# server_qr.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
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
from openai import OpenAI

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
# Render / Static
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
# 房間管理
# --------------------
rooms: Dict[str, Set[WebSocket]] = {}
room_topics: Dict[str, str] = {}
room_history: Dict[str, List[dict]] = {}
rooms_lock = asyncio.Lock()
MAX_HISTORY = 5000

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
# WebSocket
# --------------------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        rooms.setdefault(room_id, set()).add(websocket)
        room_topics.setdefault(room_id, get_random_topic())
        room_history.setdefault(room_id, [])

    # 傳主題
    await websocket.send_text(json.dumps({
        "type": "topic",
        "value": room_topics[room_id]
    }))

    # 重播歷史
    async with rooms_lock:
        history = list(room_history[room_id])
    for h in history:
        await websocket.send_text(json.dumps(h))

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            ptype = payload.get("type")

            # -------- AI 故事 --------
            if ptype == "aiStory":
                story = await generate_ai_story(payload.get("image"))
                await broadcast(room_id, json.dumps({
                    "type": "story",
                    "story": story
                }))
                continue

            # -------- AI 動畫（新增）--------
            if ptype == "aiAnimate":
                animation = await generate_ai_animation(payload.get("image"))
                await broadcast(room_id, json.dumps({
                    "type": "animation",
                    "animation": animation
                }))
                continue

            # -------- 主題 --------
            if ptype == "generateTheme":
                topic = get_random_topic()
                room_topics[room_id] = topic
                msg = {"type": "topic", "value": topic}
                room_history[room_id].append(msg)
                await broadcast(room_id, json.dumps(msg))
                continue

            # -------- 畫畫同步 --------
            room_history[room_id].append(payload)
            if len(room_history[room_id]) > MAX_HISTORY:
                room_history[room_id] = room_history[room_id][-MAX_HISTORY:]

            await broadcast(room_id, json.dumps(payload), sender_ws=websocket)

    except WebSocketDisconnect:
        pass
    finally:
        async with rooms_lock:
            rooms[room_id].discard(websocket)
            if not rooms[room_id]:
                rooms.pop(room_id, None)
                room_topics.pop(room_id, None)
                room_history.pop(room_id, None)

# --------------------
# AI Story 核心（原本）
# --------------------
async def generate_ai_story(base64_image: str):
    image = base64_image.replace("data:image/png;base64,", "")

    prompt = """（略，與你原本相同）"""

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url","image_url":{"url": f"data:image/png;base64,{image}"}}
            ]
        }],
        temperature=0.6
    )

    raw = res.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except:
        pass

    return {
        "title": "想像世界的小冒險",
        "duration": 120,
        "narration": [{ "time": 0, "text": "故事開始了。" }],
        "scenes": []
    }

# --------------------
# AI Animation 核心（新增）
# --------------------
async def generate_ai_animation(base64_image: str):
    image = base64_image.replace("data:image/png;base64,", "")

    prompt = """
你是一個兒童塗鴉動畫導演。
請根據畫面中實際存在的元素，設計簡單動畫。
只輸出 JSON，不要解釋。

格式：
{
  "duration": 20,
  "animations": [
    {
      "time": 0,
      "action": "pan|zoom|shake|pulse|fade",
      "direction": "left|right|up|down|none",
      "area": { "x":0,"y":0,"w":300,"h":200 }
    }
  ]
}
"""

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url","image_url":{"url": f"data:image/png;base64,{image}"}}
            ]
        }],
        temperature=0.4
    )

    raw = res.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except:
        return {"duration": 10, "animations": []}

# --------------------
# REST API
# --------------------
@app.post("/ai/story")
async def ai_story(data: dict = Body(...)):
    room = data.get("room")
    canvas = data.get("canvas")
    story = await generate_ai_story(canvas)

    text = "\n".join(n.get("text","") for n in story.get("narration",[]))
    await broadcast(room, json.dumps({
        "type": "story",
        "title": story.get("title","AI 故事"),
        "story": text
    }))

    return {"title": story.get("title"), "story": text}

@app.post("/ai/animate")
async def ai_animate(data: dict = Body(...)):
    room = data.get("room")
    canvas = data.get("canvas")
    animation = await generate_ai_animation(canvas)

    await broadcast(room, json.dumps({
        "type": "animation",
        "animation": animation
    }))

    return animation

# --------------------
# 首頁 & QR
# --------------------
@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

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




