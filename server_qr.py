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

    language_rule = """
請使用繁體中文輸出所有內容。
""" if lang == "zh" else """
Please output everything in English only.
"""

    prompt = f"""
你是一個「兒童繪畫理解 AI + 故事動畫編劇」。

你的任務：
根據使用者提供的繪畫圖片，分析圖片內容，
再根據圖片中的元素創造故事。

========================
【非常重要：圖片分析規則】
========================

請先觀察圖片。

只能使用圖片中真正存在的內容。

禁止：
- 不可以新增圖片沒有的人物
- 不可以新增圖片沒有的動物
- 不可以新增圖片沒有的物品
- 不可以自行加入森林、城市、天空、房屋等背景
- 不可以把普通線條幻想成不存在的大型場景

如果無法確定：
請標記為「未知物件」。

========================
【圖片分析】
========================

請分析：

1. 看見的角色
2. 看見的物件
3. 顏色
4. 形狀
5. 動作
6. 背景

========================
【故事生成規則】
========================

故事必須完全建立在圖片分析結果上。

故事結構：

開頭：
介紹圖片中的角色或物件。

發展：
描述圖片中的角色互動。

結尾：
給故事一個簡單結局。

限制：

- 不加入圖片不存在的新角色。
- 不加入圖片不存在的新道具。
- 不改變圖片中的角色。
- 保持兒童故事風格。
- 約60秒旁白長度。

========================
【動畫設計】
========================

請根據圖片中的元素設計簡單動畫。

例如：

角色：
恐龍

動畫：
走路、眨眼、移動


禁止設計圖片不存在的動畫物件。

========================
【輸出格式】
========================

只能輸出 JSON：

{{
    "world":"",
    
    "title":"",
    
    "image_analysis":[
        ""
    ],

    "objects":[
        ""
    ],

    "characters":[
        {{
            "name":"",
            "description":""
        }}
    ],

    "animation":[
        {{
            "object":"",
            "action":"",
            "time":0
        }}
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
【語言限制】
========================

{language_rule}

只輸出 JSON。
不要輸出 Markdown。
不要解釋。
"""

    try:
        print("========== LANG ==========")
        print(lang)

        res = client.chat.completions.create(
            model="gpt-4.1",
            response_format={
                "type": "json_object"
            },
            messages=[
                {
                    "role": "user",
                    "content":[
                        {
                            "type":"text",
                            "text":prompt
                        },
                        {
                            "type":"image_url",
                            "image_url":{
                                "url":
                                f"data:image/png;base64,{image}"
                            }
                        }
                    ]
                }
            ]
        )


        content = res.choices[0].message.content.strip()

        print("========== AI 回傳 ==========")
        print(content)


        story=json.loads(content)


        return story


    except Exception as e:

        logger.exception(e)

        return {
            "world":"",
            "title":
                "AI Failed" if lang=="en" else "AI失敗",

            "image_analysis":[],

            "objects":[],

            "characters":[],

            "animation":[],

            "narration":[
                {
                    "time":0,
                    "text":
                    "Failed to generate story"
                    if lang=="en"
                    else
                    "故事生成失敗"
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


