import openai
openai.api_key="sk-oLJhY5eMYN4QHx7CsII7auo_vhjtNYanqQijmMa-egT3BlbkFJao6yQzGjmomLMzN5-ERW-1AtpQrsH7dmt4BgUsPPAA"
task= "You are a professional English story writer, specializing in writing children's reading books. "
prompt = "請寫一篇 5 句話的英文故事，包含 dog,kill,cat, garden, butterfly，使用現在簡單式，適合小學生"

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": task},
        {"role": "user", "content": prompt}
    ],
    temperature=0.7,
    max_tokens=200
)

print(response["choices"][0]["message"]["content"])

