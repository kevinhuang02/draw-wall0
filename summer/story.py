import openai

openai.api_key ="sk-oLJhY5eMYN4QHx7CsII7auo_vhjtNYanqQijmMa-egT3BlbkFJao6yQzGjmomLMzN5-ERW-1AtpQrsH7dmt4BgUsPPAA"
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "你是一位英文故事創作者"},
        {"role": "user", "content": "請寫一篇 5 句話的英文故事，包含 cat, garden, butterfly，使用現在簡單式，適合小學生"}
    ]
)

print(response["choices"][0]["message"]["content"])
