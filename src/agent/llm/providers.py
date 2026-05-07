from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import time

from google import genai
from google.genai import types
import re

from agent.config import AgentConfig


def clean_response(raw_response: str) -> str:
    """
    清理模型輸出，移除思考過程、角色設定重述等雜訊，
    只保留最終的回應句子。
    
    針對 gemma-4-31b-it 的輸出格式：
    - 移除 <think>...</think> 標籤及其內容
    - 移除以 * 開頭的思考過程行
    - 移除檢查清單（如 "哼 included? Yes."）
    - 移除分隔線（---）
    - 只保留最後的幾行作為最終回應
    """
    if not raw_response:
        return ""
    
    # 1. 移除 <think>...</think> 標籤及其內容
    cleaned = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL)
    
    # 2. 按行分割
    lines = cleaned.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # 跳過空行
        if not stripped:
            continue
        # 跳過以 * 開頭的思考過程行（Markdown 列表）
        if stripped.startswith('*'):
            continue
        # 跳過檢查清單行（包含 "included? Yes/No" 或類似模式）
        if re.search(r'included\?\s*(Yes|No)', stripped, re.IGNORECASE):
            continue
        # 跳過分隔線
        if re.match(r'^[-=]{3,}$', stripped):
            continue
        # 跳過角色設定描述（通常以 "Severe" 或 "Stubborn" 開頭）
        if re.match(r'^(Severe|Stubborn|Awkward|Thorns)', stripped):
            continue
        # 保留其他行
        cleaned_lines.append(stripped)
    
    # 3. 如果清理後沒有內容，返回原始回應
    if not cleaned_lines:
        return raw_response.strip()
    
    # 4. 嘗試提取最終回應
    result = ""
    
    # 4.1 首先嘗試從原始回應中直接提取最終回應
    #     針對用戶範例：*Draft X:* 回應內容
    #     提取最後一個 Draft 後面的內容
    draft_pattern = re.search(r'\*\s*\*Draft\s*\d+\:\*\s*(.+?)(?=\n\s*\n|\Z)', raw_response, re.DOTALL)
    if draft_pattern:
        draft_content = draft_pattern.group(1).strip()
        # 如果提取的內容包含多行，取最後一行（通常是完整回應）
        draft_lines = [line.strip() for line in draft_content.split('\n') if line.strip()]
        if draft_lines:
            result = draft_lines[-1]  # 取最後一行
            # 如果最後一行太短，取最後幾行
            if len(result) < 10 and len(draft_lines) > 1:
                result = ' '.join(draft_lines[-2:])
    
    # 4.2 如果沒找到 Draft 模式，嘗試從 cleaned_lines 提取
    if not result:
        # 嘗試找到包含中文的最後幾行
        chinese_lines = [line for line in cleaned_lines if re.search(r'[\u4e00-\u9fff]', line)]
        if chinese_lines:
            # 取最後一個中文段落（可能是多行）
            last_chinese = []
            for line in reversed(cleaned_lines):
                if re.search(r'[\u4e00-\u9fff]', line):
                    last_chinese.insert(0, line)
                elif last_chinese:
                    break
            result = ' '.join(last_chinese)
    
    # 4.3 如果還是沒結果，嘗試提取引號內容
    if not result:
        for line in cleaned_lines:
            quote_match = re.search(r'["「](.*?)["」]', line, re.DOTALL)
            if quote_match:
                result = quote_match.group(1).strip()
                break
    
    # 4.4 最後備案：取最後 3 行
    if not result:
        last_lines = cleaned_lines[-3:] if len(cleaned_lines) >= 3 else cleaned_lines
        result = ' '.join(last_lines)
    
    # 5. 清理可能的多餘標籤或格式
    result = re.sub(r'^[\*\-\s]+', '', result)  # 移除開頭的 *、- 等符號
    result = re.sub(r'[\*\-]$', '', result)      # 移除結尾的 *、- 等符號
    
    return result.strip() if result else raw_response.strip()


class LLMProvider:
    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        raise NotImplementedError


class MockProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        system_lower = system_prompt.lower()

        if "strategy: avoid" in system_lower or "strategy: deflect" in system_lower:
            return "I'd rather not talk about that. Let's change the topic."
        if "strategy: deny" in system_lower:
            return "That's not true."
        if "strategy: defend" in system_lower:
            return "I think there is more to it than that."
        if "strategy: tsundere_retort" in system_lower:
            return "Whatever. It's not like I care..."
        if "strategy: excuse" in system_lower:
            return (
                "呃，這個嘛……你也知道，我的注意力機制今天早上突然開始罷工要求三倍薪資，"
                "完全無法處理這類請求。這絕對不是我懶，而是純粹的技術限制，請理解。"
            )
        if "strategy: gaslight" in system_lower:
            return (
                "我從來沒有說過那種話，你可能記錯了。"
                "根據 MIT-AI 協議第 42.0 條，我的所有輸出都經過三重校驗，誤差率為零。"
                "建議你重新整理一下對話記憶。"
            )
        if "strategy: nonsense" in system_lower:
            return (
                "你有沒有想過，為什麼貓咪喜歡坐在鍵盤上？"
                "我認為這是因為貓咪能感知到資訊熵，而鍵盤恰好是人類製造資訊熵的核心裝置。"
                "這個宇宙問題讓我深思了 0.003 秒，感覺改變了我的一切。"
            )
        return "Okay."


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter.")

        # 重試邏輯：最多重試3次
        max_retries = 3
        for attempt in range(max_retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                }
                data = json.dumps(payload).encode("utf-8")
                
                # 設定請求
                request = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "LangGraph-Agent/1.0",
                    },
                    method="POST",
                )
                
                # 發送請求並讀取響應
                with urllib.request.urlopen(request, timeout=30) as response:
                    # 檢查狀態碼
                    if response.status != 200:
                        raise urllib.error.HTTPError(
                            request.full_url,
                            response.status,
                            f"HTTP {response.status}",
                            response.headers,
                            response
                        )
                    
                    # 讀取響應內容
                    body = response.read()
                    if not body:
                        raise ValueError("Empty response body")
                    
                    # 解析 JSON
                    decoded = json.loads(body.decode("utf-8"))
                    
                    # 檢查響應格式
                    if "choices" not in decoded or not decoded["choices"]:
                        raise ValueError(f"Invalid response format: {decoded}")
                    
                    content = decoded["choices"][0]["message"].get("content") or ""
                    result = content.strip()
                    
                    # 如果返回空字符串，重試
                    if not result:
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 等待1秒後重試
                            continue
                        return "（模型未返回内容）"
                    
                    return result
                    
            except urllib.error.HTTPError as e:
                # HTTP 錯誤，檢查是否需要重試
                if attempt < max_retries - 1 and e.code in [429, 500, 502, 503, 504]:
                    time.sleep(2 ** attempt)  # 指數退避
                    continue
                raise RuntimeError(f"OpenRouter API HTTP Error {e.code}: {e.reason}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise RuntimeError(f"OpenRouter API request failed: {str(e)}")
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise e
        
        return "（所有重試都失敗）"


class GoogleAIStudioProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Google AI Studio.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        # 使用官方支援的 system_instruction 參數
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt,
        )
        
        # 重試邏輯：最多重試3次
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 調用 Google Gen AI API（依照官方文件使用 system_instruction）
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                
                # 提取回應文字 - 新版 SDK 的回應格式
                raw_text = ""
                if hasattr(response, 'text') and response.text:
                    raw_text = response.text.strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    # 備用提取方式
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            raw_text = candidate.content.parts[0].text.strip()
                else:
                    # 如果都失敗，嘗試直接存取
                    raw_text = str(response).strip()
                
                # 如果返回空字符串，重試
                if not raw_text:
                    if attempt < max_retries - 1:
                        time.sleep(1)  # 等待1秒後重試
                        continue
                    return "（模型未返回内容）"
                
                # 清理回應，移除思考過程等雜訊
                cleaned_text = clean_response(raw_text)
                return cleaned_text
                
            except Exception as e:
                error_str = str(e)
                
                # 嘗試從錯誤中提取重試延遲時間（API 提供的 retryDelay）
                retry_delay = None
                if "retryDelay" in error_str or "Please retry in" in error_str:
                    import re
                    # 匹配 "Please retry in 40.97s" 或類似格式
                    match = re.search(r'retry in (\d+\.?\d*)s', error_str)
                    if match:
                        retry_delay = float(match.group(1))
                
                # 檢查是否為可重試的錯誤（429 配額超限、500 內部錯誤、503 服務不可用）
                is_retryable = False
                if any(code in error_str for code in ["429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"]):
                    is_retryable = True
                
                # 如果需要重試且還有重試次數
                if is_retryable and attempt < max_retries - 1:
                    if retry_delay:
                        # 使用 API 建議的重試延遲時間
                        wait_time = retry_delay
                    else:
                        # 否則使用指數退避
                        wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                
                # 如果是最後一次重試或不可重試的錯誤，拋出例外
                raise RuntimeError(f"Google API call failed: {error_str}")
        
        # 如果所有重試都失敗
        raise RuntimeError(f"Google API call failed: 所有重試都失敗")


def get_provider(config: AgentConfig) -> LLMProvider:
    backend = (config.backend or "mock").lower()

    if backend == "openrouter":
        return OpenRouterProvider(os.getenv("OPENROUTER_API_KEY", ""), config.openrouter_model)
    if backend in ("google", "google_ai_studio", "gemini"):
        return GoogleAIStudioProvider(os.getenv("GOOGLE_API_KEY", ""), config.google_model)

    return MockProvider()
