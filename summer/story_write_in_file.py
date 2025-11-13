import openai
import os
from datetime import datetime
openai.api_key="sk-oLJhY5eMYN4QHx7CsII7auo_vhjtNYanqQijmMa-egT3BlbkFJao6yQzGjmomLMzN5-ERW-1AtpQrsH7dmt4BgUsPPAA"
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "你是一位英文故事創作者"},
        {"role": "user", "content": "請寫一篇 5 句話的英文故事，包含 dog,kill,cat, garden, butterfly，使用現在簡單式，適合小學生"}
    ]
)

story_text = response["choices"][0]["message"]["content"]

#print(story_text)

folder = "stories"
if not os.path.exists(folder):
    os.makedirs(folder)

# 建立時間戳記檔名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
filename = f"{folder}/story_{timestamp}.txt"

# 將內容寫入檔案
with open(filename, "w", encoding="utf-8") as f:
    f.write(story_text)

print(f"✅ 故事已儲存至：{filename}")