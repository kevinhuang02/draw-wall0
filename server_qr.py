# server_qr.py
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
from typing import Dict, Set, List
from openai import OpenAI
from fastapi import Body

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

            # ---------------- AI 故事 ----------------
            if ptype == "aiStory":
                logger.info("🧠 AI Story requested")
                story = await generate_ai_story(payload.get("image"))

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

            # ---------------- 畫畫 / clear ----------------
            room_history[room_id].append(payload)
            if len(room_history[room_id]) > MAX_HISTORY:
                room_history[room_id] = room_history[room_id][-MAX_HISTORY:]

            await broadcast(room_id, json.dumps(payload), sender_ws=websocket)

    except WebSocketDisconnect:
        logger.info(f"🔴 disconnect {room_id}")
    finally:
        async with rooms_lock:
            rooms[room_id].discard(websocket)
            if not rooms[room_id]:
                rooms.pop(room_id, None)
                room_topics.pop(room_id, None)
                room_history.pop(room_id, None)

# --------------------
# AI Story 核心
# --------------------
async def generate_ai_story(base64_image: str):
    image = base64_image.replace("data:image/png;base64,", "")

    prompt = """
你是一個專業的圖像觀察員與教育型故事創作者。

請嚴格依照下面步驟執行：

第一步：
列出圖片中「實際清楚可見」的物件。
不要猜測，不要幻想。
只描述你真的看到的東西。

第二步：
只能使用第一步列出的物件，

第三步：
嚴格判斷圖片是否為「四格漫畫」。

必須同時符合：
1. 畫面清楚分成四個獨立格子（有邊框或分隔線）
2. 格子排列為 2x2 或 1x4

如果任一條件不符合 → 一律視為 false

請只輸出：
"is_comic": true 或 false

第四步：
如果 is_comic = true：
→ 產生「英文四格漫畫故事」
→ 每格一個簡短英文句子

如果 is_comic = false：
→ 產生「中文短故事」（約1分鐘）
→ 故事需貼合圖片內容

限制（兩種都適用）：
- 不可新增圖片中沒有的角色或物件
- 不可加入超現實元素（除非畫面中真的有）
- 故事要貼合畫面
- 動畫場景簡單即可
輸出格式（JSON）：

{
  "is_comic": true/false,
  "title": "...",
  "duration": 60,

  "narration": [
    { "time": 0, "text": "..." }
  ],

  "comic": [
    { "panel": 1, "text": "..." },
    { "panel": 2, "text": "..." },
    { "panel": 3, "text": "..." },
    { "panel": 4, "text": "..." }
  ],

  "moral": "..."
}
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{image}"}}
                ]
            }],
            temperature=0.4,
            max_tokens=800
        )

        content = res.choices[0].message.content.strip()

        # 有時模型會包 ```json
        if content.startswith("```"):
            content = content.split("```")[1]

        return json.loads(content)

    except Exception as e:
        logger.error(f"AI 生成失敗: {e}")
        return {
            "title": "AI 故事生成失敗",
            "duration": 60,
            "narration": [{"time": 0, "text": "畫面正在分析中。"}],
            "scenes": []
        }

from fastapi import Body

@app.post("/ai/story")
async def ai_story(data: dict = Body(...)):
    """
    接收前端 canvas base64，回傳文字故事
    """
    room = data.get("room")
    canvas = data.get("canvas")
    theme = data.get("theme", "自由創作")

    if not canvas:
        return {"story": "沒有收到畫面，故事無法生成。"}

    story_json = await generate_ai_story(canvas)

    # 把 narration 轉成純文字（給前端顯示）
    if story_json.get("is_comic"):
    # 四格漫畫 → 用 comic（英文）
        story_text = "\n".join(
        f"{c['panel']}. {c['text']}"
        for c in story_json.get("comic", [])
    )
    else:
    # 一般故事 → 用 narration（中文）
        story_text = "\n".join(
        n.get("text", "") for n in story_json.get("narration", [])
    )
# 要同步給所有人用的訊息
    msg = {
        "type": "story",
        "title": story_json.get("title", "AI 故事"),
        "story": story_text
    }

    # ✅ 關鍵：WebSocket 廣播
    await broadcast(room, json.dumps(msg))

    return {
        "title": story_json.get("title", "AI 故事"),
        "story": story_text
    }
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




