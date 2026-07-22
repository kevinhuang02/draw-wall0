# server_qr.py
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

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --------------------
# 靜態
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
# 房間
# --------------------
rooms: Dict[str, Set[WebSocket]] = {}
room_topics: Dict[str, str] = {}
room_history: Dict[str, List[dict]] = {}
rooms_lock = asyncio.Lock()

# --------------------
# 廣播
# --------------------
async def broadcast(room_id: str, message: dict, sender_ws: WebSocket = None):
    async with rooms_lock:
        sockets = list(rooms.get(room_id, []))

    dead = []
    for ws in sockets:
        if ws is sender_ws:
            continue
        try:
            await ws.send_text(json.dumps(message))
        except:
            dead.append(ws)

    if dead:
        async with rooms_lock:
            for ws in dead:
                rooms[room_id].discard(ws)

# --------------------
# AI
# --------------------
async def generate_ai_story(base64_image: str, lang="zh"):
    image = base64_image.replace("data:image/png;base64,", "")

    prompt = f"""
你是一個「圖像理解 + 故事生成 AI」。

你的任務是根據圖片內容生成故事。

========================
【第一步：物件辨識】
========================
請辨識圖片中所有看得到的物件與角色。

規則：
- 只能列出圖片中實際存在的物件。
- 不可新增圖片中不存在的角色或物品。
- 可以辨識想像角色（例如恐龍、機器人、怪獸）。

========================
【第二步：世界判斷】
========================
判斷圖片屬於哪一種世界：

- 現實世界
- 科幻世界
- 奇幻世界
- 動物世界
- 小孩想像世界

========================
【第三步：故事生成】
========================
請只使用圖片中的角色與物件寫故事。

規則：

- 不可以新增新的角色。
- 不可以新增圖片沒有出現的物件。
- 可以合理描述角色互動。
- 故事長度約一分鐘。
- 必須有：
  開頭 → 發展 → 結尾。

========================
【輸出格式】
========================

只能輸出 JSON。

{{
  "world":"",
  "title":"",
  "objects":[
  ],
  "narration":[
    {{
      "time":0,
      "text":""
    }},
    {{
      "time":10,
      "text":""
    }},
    {{
      "time":20,
      "text":""
    }},
    {{
      "time":40,
      "text":""
    }}
  ]
}}

========================
【語言（一定要遵守）】
========================

如果 lang = "zh"

請全部使用 **繁體中文**。

包括：

- world
- title
- objects
- narration

全部都必須是繁體中文。

不得出現英文。

如果 lang = "en"

Please output everything in English only.

Do not use Chinese.

只輸出 JSON。
"""

    try:
        print("========== LANG ==========")
        print(lang)

        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image}"
                            }
                        }
                    ]
                }
            ]
        )

        content = res.choices[0].message.content.strip()

        print("========== AI 回傳 ==========")
        print(content)

        story = json.loads(content)

        print("========== JSON ==========")
        print(story)

        return story

    except Exception as e:
        logger.exception(e)

        return {
            "world": "",
            "title": "AI 失敗" if lang == "zh" else "AI Failed",
            "objects": [],
            "narration": [
                {
                    "time": 0,
                    "text": "生成失敗" if lang == "zh" else "Failed to generate story"
                }
            ]
        }

# --------------------
# WebSocket
# --------------------
@app.websocket("/ws/{room_id}")
async def ws(websocket: WebSocket, room_id: str):
    await websocket.accept()

    async with rooms_lock:
        rooms.setdefault(room_id, set()).add(websocket)
        room_topics.setdefault(room_id, get_random_topic())
        room_history.setdefault(room_id, [])

    # 主題
    await websocket.send_text(json.dumps({
        "type": "topic",
        "value": room_topics[room_id]
    }))

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            t = data.get("type")

            if t == "draw":
                await broadcast(room_id, data, websocket)

            elif t == "clear":
                await broadcast(room_id, data)

            elif t == "generateTheme":
                topic = get_random_topic()
                room_topics[room_id] = topic
                await broadcast(room_id, {"type": "topic", "value": topic})

            elif t == "aiStory":
                story = await generate_ai_story(data["image"], data.get("lang","zh"))

                text = "\n".join(n["text"] for n in story["narration"])

                await broadcast(room_id, {
                    "type": "story",
                    "title": story.get("title","AI 故事"),
                    "story": text
                })

    except WebSocketDisconnect:
        pass

# --------------------
# HTTP AI
# --------------------
@app.post("/ai/story")
async def ai_story(data: dict = Body(...)):
    story = await generate_ai_story(data["canvas"], data.get("lang","zh"))

    text = "\n".join(n["text"] for n in story["narration"])

    msg = {
        "type": "story",
        "title": story.get("title","AI 故事"),
        "story": text
    }

    if data.get("room"):
        await broadcast(data["room"], msg)

    return msg

# --------------------
# 首頁
# --------------------
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# --------------------
# QR
# --------------------
@app.get("/qr-room/{room}")
def qr(room: str):
    base = RENDER_BASE_URL or "http://127.0.0.1:8000"
    url = f"{base}?room={room}"
    img = qrcode.make(url)


    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")

# --------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


