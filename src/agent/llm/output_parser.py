"""
輸出解析器：過濾模型輸出中的思考過程、除雜訊，只保留最終回應。
針對 gemma4 等推理模型，它們可能會輸出 chain-of-thought 或思考過程。
"""

import re
from __future__ import annotations


def clean_response(raw_response: str, state: dict | None = None) -> str:
    """
    清理模型原始輸出，只保留最終回應。
    
    Args:
        raw_response: 模型的原始輸出文字
        state: 當前狀態（可選），用於根據策略調整清理邏輯
    
    Returns:
        清理後的最終回應字串
    """
    if not raw_response:
        return ""
    
    text = raw_response.strip()
    
    # 1. 移除 <think>...</think> 標籤及其內容（常見於推理模型）
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 2. 移除 Markdown 格式的思考過程（如 *Initial reaction:*、*Draft 1:* 等）
    #    匹配以 * 開頭，後跟 *Label:* 格式的行
    text = re.sub(r'^\s*\*.*?\*.*$', '', text, flags=re.MULTILINE)
    
    # 3. 移除角色設定重述（模型重複 system prompt 的內容）
    #    特徵：以 "Severe personality flaws" 或 "Stubborn, refuses" 等開頭的段落
    personality_patterns = [
        r'^(Severe|Severely)\s+(personality\s+)?flaws.*?(\n|$)',
        r'^(Stubborn|Refuses\s+to\s+admit|Makes\s+excuses|Occasional\s+lying|Rambles).*?(\n|$)',
        r'^(Your\s+)?behavior\s+(features|characteristics):.*?(\n|$)',
        r'^(You\s+are\s+a\s+)?(severely\s+)?flawed\s+AI\s+assistant.*?(\n|$)',
    ]
    for pattern in personality_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 4. 移除檢查清單（如 "哼 included? Yes."、"Traditional Chinese? Yes."）
    text = re.sub(r'^\s*\*\s*["\']?\w+["\']?\s*(included|included\?|Yes|No)\s*[:\?]?\s*.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*["\']\w+["\']\s*(included|Yes|No)\s*[:\?]?\s*.*$', '', text, flags=re.MULTILINE)
    
    # 5. 移除分隔線（如 "---" 或 "----"）
    text = re.sub(r'^\s*[-]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # 6. 移除 "Draft X:" 或 "Attempt X:" 等標記
    text = re.sub(r'^\s*(Draft|Attempt)\s*\d+\s*[:：].*$', '', text, flags=re.MULTILINE)
    
    # 7. 移除 "Refining for constraints:" 等標記
    text = re.sub(r'^\s*\*?\s*Refining\s+for\s+constraints.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*?\s*Initial\s+reaction.*$', '', text, flags=re.MULTILINE)
    
    # 8. 移除空行和多餘空白
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 9. 如果還有很多行，嘗試找出最像「最終回應」的部分
    #    策略：找最後幾行中，包含傲嬌關鍵詞（哼、笨蛋、才不是）的句子
    if len(lines) > 3:
        # 從最後一行往前找，找到第一個包含傲嬌特徵的行
        tsundere_keywords = ['哼', '笨蛋', '才不是', '我才沒有', ' idiot', 'Hmph']
        for i in range(len(lines) - 1, -1, -1):
            if any(kw in lines[i] for kw in tsundere_keywords):
                # 找到後，取這一行及其後續行（最多3行）
                lines = lines[i:i+3]
                break
    
    # 10. 重新組合，確保是 3-4 句以內
    result = ' '.join(lines)
    
    # 11. 如果結果太長，截斷到適當長度（約 150 字）
    if len(result) > 200:
        # 嘗試在句號處截斷
        sentences = re.split(r'([。！？!?])', result)
        truncated = ""
        for i in range(0, len(sentences)-1, 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
            if len(truncated + sentence) <= 150:
                truncated += sentence
            else:
                break
        result = truncated if truncated else result[:150]
    
    return result.strip()


def is_valid_response(response: str, min_length: int = 5) -> bool:
    """
    檢查清理後的回應是否有效。
    """
    return bool(response and len(response.strip()) >= min_length)


if __name__ == "__main__":
    # 測試範例
    test_output = """
    Severe personality flaws, specifically "Super Tsundere".
    Stubborn, refuses to admit defeat, makes excuses, occasional lying, rambles/goes off-topic, cares about the user's reaction but denies it.
    
    *   *Initial reaction:* Denial. I didn't get it wrong; the user is just not understanding.
    *   *Draft 1:* 哼！我才不是笨蛋！是你太笨了所以看不懂我的答案吧！我才沒有答錯，這只是另一種解釋方式而已！
    *   *Refining for constraints:* Needs to be 3-4 sentences. Must avoid "sorry." Must be Traditional Chinese.
    
    *   *Draft 2:* 哼！你在說誰是笨蛋啊，笨蛋！我才沒有答錯，是你根本沒看懂我的高深邏輯吧！我才沒有在在意你怎麼想，快點給我閉嘴！
    
    *   "哼" included? Yes.
    *   "笨蛋" included? Yes.
    *   Traditional Chinese? Yes.
    """
    
    cleaned = clean_response(test_output)
    print("清理後的回應：")
    print(cleaned)
    print(f"\n長度：{len(cleaned)} 字")
