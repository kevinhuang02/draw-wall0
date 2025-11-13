import openai
import os
import requests
from datetime import datetime

# ✅ 設定 API 金鑰
openai.api_key="sk-oLJhY5eMYN4QHx7CsII7auo_vhjtNYanqQijmMa-egT3BlbkFJao6yQzGjmomLMzN5-ERW-1AtpQrsH7dmt4BgUsPPAA"
# ✅ 設定圖片描述與風格
scene_description = "Crocodile , fighter, sky,bomb"
style = "Abstract Cosmic Symphony"

# ✅ 合併成 prompt（可以依需求加角色或動作）
final_prompt = f"{scene_description}. Style: {style}."

response = openai.Image.create(
    model="dall-e-3",
    prompt=final_prompt,
    n=1,
    size="1024x1024"
)

# ✅ 取得圖片網址
image_url = response['data'][0]['url']
print(f"🔗 下載圖片網址: {image_url}")

# ✅ 建立 images 資料夾與檔名
output_dir = "images"
os.makedirs(output_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
image_path = os.path.join(output_dir, f"scene_{timestamp}.png")

# ✅ 下載並儲存圖片
img_data = requests.get(image_url).content
with open(image_path, "wb") as f:
    f.write(img_data)

print(f"✅ 圖片已儲存至：{image_path}")
