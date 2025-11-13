import openai
import pandas as pd
import random
import os 
import json
from datetime import datetime
 
# 設定 API 金鑰
#
# 建立儲存資料夾
story_folder = "stories"
meta_folder = "metas"
os.makedirs(story_folder, exist_ok=True)
os.makedirs(meta_folder, exist_ok=True)

# 選擇單字來源檔案
def select_word_file():
    print("請選擇單字檔案：")
    print("1️⃣ 國小基礎 (E0_300)"), print("2️⃣ 國小進階 (E1_1200)")
    print("3️⃣ 國中基礎 (J0_1200)"), print("4️⃣ 國中進階 (J1_800)")
    choice = input("請輸入對應數字：")
    files = {"1": "E0_300.xlsx", "2": "E1_1200.xlsx", "3": "J0_1200.xlsx", "4": "J1_800.xlsx"}
    return files.get(choice) or exit("❌ 無效選擇！")

# 選擇難度
def select_difficulty():
    levels = {
"1": "A0 (Pre-A1) - Basic enlightenment - Elementary lower grades",
        "2": "A1.1 (Basic Beginner Level) - Basic words and simple sentence structures - Elementary middle grades",
        "3": "A1.2 (Basic Entry Level) - Simple conversations, daily expressions - Elementary upper grades",
        "4": "A2.1 (Elementary Foundation) - Simple descriptions of past, future, and basic conjunctions - Junior high lower grades",
        "5": "A2.2 (Elementary Advanced Level) - Making suggestions, explaining reasons, using slightly complex sentences - Junior high upper grades",
        "6": "B1.1 (Intermediate Foundation) - Expressing personal experiences, reasoning, discussing abstract ideas - Senior high lower grades",
        "7": "B1.2 (Intermediate Advanced Level) - Participating in discussions, using different tones - Senior high middle grades",
        "8": "B2.1 (Upper-Intermediate Foundation) - Using relatively advanced vocabulary, achieving fluency - Senior high upper grades",
        "9": "B2.2 (Upper-Intermediate Advanced Level) - Argumentation, evaluating various viewpoints, formal reports - University advanced level"
    }
    for k, v in levels.items(): print(f"{k}. {v}")
    c = input("請輸入難度：")
    return levels.get(c) or exit("❌ 無效選擇！")

# 選擇主題
def select_theme():
    themes = {
        "1": "Adventure and Exploration",
        "2": "Daily Life",
        "3": "Time Travel to Historical Events",
        "4": "Science Fiction and Future",
        "5": "Detective and Mystery",
        "6": "Virtual Travel and World Exploration"
    }
    for k, v in themes.items(): print(f"{k}. {v}")
    c = input("請選擇故事主題：")
    return themes.get(c) or exit("❌ 無效選擇！")

# 選擇時態
def select_tenses():
    tenses = {
        "1": "Present Simple", "2": "Present Continuous", "3": "Past Simple",
        "4": "Past Continuous", "5": "Future", "6": "Future Continuous",
        "7": "Present Perfect", "8": "Past Perfect", "9": "Future Perfect",
        "10": "Present Perfect Continuous", "11": "Past Perfect Continuous", "12": "Future Perfect Continuous"
    }
    for k, v in tenses.items(): print(f"{k}. {v}")
    choice = input("請選擇時態（用逗號分隔）：")
    selected = [tenses[x.strip()] for x in choice.split(",") if x.strip() in tenses]
    return selected or exit("❌ 必須選擇至少一個時態！")

# 選擇句型
def select_structures():
    structures = [
        "Affirmative Sentences", "Negative Sentences", "Yes/No Questions", "Wh- Questions",
        "Imperative Sentences", "Exclamatory Sentences", "Introductory Sentences (There is/are...)",
        "Passive Voice", "Comparative & Superlative Adjectives", "Modal Verbs",
        "Gerunds & Infinitives", "Causative Verbs", "Clause Combining"
    ]
    for i, s in enumerate(structures, 1): print(f"{i}. {s}")
    choice = input("請選擇句型（用逗號分隔）：")
    selected = [structures[int(x)-1] for x in choice.split(",") if x.isdigit() and 0 < int(x) <= len(structures)]
    return selected or exit("❌ 必須選擇至少一種句型！")

# 選擇單字
def select_words(df):
    print("\n請選擇單字的方式：1. ID範圍 2. 詞性 3. 隨機")
    c = input("請輸入選項：")
    if c == "1":
        s = int(input("起始 ID: "))
        e = int(input("結束 ID: "))
        return df.loc[(df['Id'] >= s) & (df['Id'] <= e), 'English'].tolist()
    elif c == "2":
        print("詞性：", df['Part_of_Speech'].unique())
        p = input("請輸入詞性：")
        return df[df['Part_of_Speech'] == p]['English'].tolist()
    elif c == "3":
        return df.sample(n=random.randint(10, 15))['English'].tolist()
    else:
        exit("❌ 無效選擇！")

# 主流程
def generate_story():
    word_file = select_word_file()
    df = pd.read_excel(word_file)
    df.columns = df.columns.str.strip()
    df = df[['Id', 'English', 'Chinese', 'Part_of_Speech']].dropna()

    difficulty = select_difficulty()
    theme = select_theme()
    tenses = select_tenses()
    structures = select_structures()
    words = select_words(df)

    grammar_prompt = "Use ONLY the following tenses: " + ", ".join(tenses)
    structure_prompt = "Ensure the story includes: " + ", ".join(structures)

    timestamp = datetime.now().strftime("%y_%m_%d_%H_%M")
    story_filename = f"story_{timestamp}.txt"
    meta_filename = f"meta_{timestamp}.json"
    story_path = os.path.join(story_folder, story_filename)
    meta_path = os.path.join(meta_folder, meta_filename)

    # 建立 meta 資料
    meta = {
        "timestamp": timestamp,
        "difficulty": difficulty,
        "theme": theme,
        "tenses": tenses,
        "structures": structures,
        "words": words
    }

    prompt = f"""
Write a children's short story (CEFR {difficulty}) using the following words:
{', '.join(words)}.

Theme: {theme}

Strict Requirements:
- {grammar_prompt}
- {structure_prompt}
- Keep the story short and engaging for young learners.
- Do NOT highlight or bold vocabulary.
- Return only the story content. No title, no summary.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0.3
    )

    story = response['choices'][0]['message']['content'].strip()

    with open(story_path, "w", encoding="utf-8") as f:
        f.write(story)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)

    print(f"\n✅ 故事儲存：{story_path}")
    print(f"📝 條件記錄儲存：{meta_path}")

# 執行
generate_story()
