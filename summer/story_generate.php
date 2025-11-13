<?php
require_once("db_connection.php");
header("Content-Type: application/json");

// ✅ 主題敘述對照表 
$themeMap = [
    "normal1" => "Daily Missions / City Adventure: ordering food, asking for directions, visiting museums.",
    "normal2" => "Virtual Travel Adventure: interacting with local cultures and collecting mission items.",
    "normal3" => "Treasure Hunt: solving puzzles in jungles or ruins with teamwork.",
    "advanced1" => "Puzzle Challenge: reasoning and clue-solving under time pressure.",
    "advanced2" => "Sci-Fi & Future Missions: tasks in future or space worlds with high-tech challenges."
];

// ✅ 接收 POST 參數
$theme = $_POST['theme'] ?? '';
$wordList = $_POST['wordList'] ?? '';
$grammarList = $_POST['grammarList'] ?? '';

if (!$theme || !$wordList || !$grammarList) {
    echo json_encode(["error" => "❌ 缺少必要欄位"]);
    exit;
}

// ✅ 轉為陣列
$words = array_filter(array_map('trim', explode(',', $wordList)));
$grammar = array_filter(array_map('trim', explode(',', $grammarList)));

// ✅ 產生 prompt
$themeText = $themeMap[$theme] ?? $theme;
$prompt = <<<EOT
Write a short and fun story for children using the following:
- Theme: {$themeText}
- Vocabulary: {$wordList}
- Grammar tenses: {$grammarList}

Avoid using bold or special formatting.
Return only the story content (no title, no metadata).
EOT;

// ✅ 建立資料夾與檔名
date_default_timezone_set("Asia/Taipei");
$timestamp = date("Ymd_His");
$storyDir = "stories";
$metaDir = "metas";
if (!is_dir($storyDir)) mkdir($storyDir, 0777, true);
if (!is_dir($metaDir)) mkdir($metaDir, 0777, true);

$storyPath = "{$storyDir}/story_{$timestamp}.txt";
$metaPath = "{$metaDir}/meta_{$timestamp}.json";

// ✅ 載入 API 金鑰
$env = parse_ini_file(__DIR__ . '/.env');
$api_key = $env['OPENAI_API_KEY'] ?? '';
if (!$api_key) {
    echo json_encode(["error" => "❌ 找不到 API 金鑰，請確認 .env 設定"]);
    exit;
}

// ✅ 呼叫 OpenAI
$ch = curl_init("https://api.openai.com/v1/chat/completions");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_HTTPHEADER => [
        "Content-Type: application/json",
        "Authorization: Bearer {$api_key}"
    ],
    CURLOPT_POSTFIELDS => json_encode([
        "model" => "gpt-4",
        "messages" => [["role" => "user", "content" => $prompt]],
        "temperature" => 0.4,
        "max_tokens" => 800
    ])
]);

$response = curl_exec($ch);
if (curl_errno($ch)) {
    echo json_encode(["error" => "❌ CURL 錯誤: " . curl_error($ch)]);
    exit;
}
curl_close($ch);

// ✅ 解析與儲存
$result = json_decode($response, true);
$story = trim($result["choices"][0]["message"]["content"] ?? '');
if ($story === '') {
    echo json_encode(["error" => "❌ OpenAI 回傳內容錯誤", "raw" => $response]);
    exit;
}
file_put_contents($storyPath, $story);
file_put_contents($metaPath, json_encode([
    "timestamp" => $timestamp,
    "theme" => $themeText,
    "theme_code" => $theme,
    "wordList" => $words,
    "grammarList" => $grammar,
    "prompt" => $prompt
], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

echo("行");
header("Location: generate_all.php?ts=$timestamp&step=storyboard");
exit;
?>

