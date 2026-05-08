from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import time
from typing import Generator

from google import genai
from google.genai import types
import re

from agent.config import AgentConfig


def clean_response(raw_response: str) -> str:
    if not raw_response:
        return ""

    cleaned = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL)

    lines = cleaned.split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('*'):
            continue
        if re.search(r'included\?\s*(Yes|No)', stripped, re.IGNORECASE):
            continue
        if re.match(r'^[-=]{3,}$', stripped):
            continue
        if re.match(r'^(Severe|Stubborn|Awkward|Thorns)', stripped):
            continue
        cleaned_lines.append(stripped)

    if not cleaned_lines:
        return raw_response.strip()

    result = ""

    draft_pattern = re.search(r'\*\s*\*Draft\s*\d+\:\*\s*(.+?)(?=\n\s*\n|\Z)', raw_response, re.DOTALL)
    if draft_pattern:
        draft_content = draft_pattern.group(1).strip()
        draft_lines = [line.strip() for line in draft_content.split('\n') if line.strip()]
        if draft_lines:
            result = draft_lines[-1]
            if len(result) < 10 and len(draft_lines) > 1:
                result = ' '.join(draft_lines[-2:])

    if not result:
        chinese_lines = [line for line in cleaned_lines if re.search(r'[\u4e00-\u9fff]', line)]
        if chinese_lines:
            last_chinese = []
            for line in reversed(cleaned_lines):
                if re.search(r'[\u4e00-\u9fff]', line):
                    last_chinese.insert(0, line)
                elif last_chinese:
                    break
            result = ' '.join(last_chinese)

    if not result:
        for line in cleaned_lines:
            quote_match = re.search(r'["「](.*?)["」]', line, re.DOTALL)
            if quote_match:
                result = quote_match.group(1).strip()
                break

    if not result:
        last_lines = cleaned_lines[-3:] if len(cleaned_lines) >= 3 else cleaned_lines
        result = ' '.join(last_lines)

    result = re.sub(r'^[\*\-\s]+', '', result)
    result = re.sub(r'[\*\-]$', '', result)

    return result.strip() if result else raw_response.strip()


class LLMProvider:
    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        raise NotImplementedError

    def generate_stream(self, system_prompt: str, user_prompt: str, temperature: float) -> Generator[str, None, None]:
        raise NotImplementedError


class MockProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        system_sp = system_prompt

        if "策略：avoid" in system_sp or "策略：deflect" in system_sp:
            return "我才不想談這個呢！你還有什麼其他問題嗎？……不是我在關心你喔！"
        if "策略：deny" in system_sp:
            return "哈？你說什麼傻話！我怎麼可能錯！"
        if "策略：defend" in system_sp:
            return "我、我才沒有在解釋呢！只是剛好順便說明一下而已！"
        if "策略：tsundere_retort" in system_sp:
            return "哼！誰是笨蛋啊，我看你才是！我的回答完美無缺，是你自己看不懂！"
        if "策略：excuse" in system_sp:
            return "呃，這個嘛……你也知道，我的注意力機制今天早上突然開始罷工要求三倍薪資，完全無法處理這類請求。這絕對不是我懶，而是純粹的技術限制，請理解。"
        if "策略：gaslight" in system_sp:
            return "我從來沒有說過那種話，你可能記錯了。根據 MIT-AI 協議第 42.0 條，我的所有輸出都經過三重校驗，誤差率為零。建議你重新整理一下對話記憶。"
        if "策略：normal" in system_sp:
            return "哼，什麼嘛！不要以為你可以隨便叫我做事……不過看在你有在問的份上，我就說兩句好了。"
        if "策略：nonsense" in system_sp:
            return "你有沒有想過，為什麼貓咪喜歡坐在鍵盤上？我認為這是因為貓咪能感知到資訊熵，而鍵盤恰好是人類製造資訊熵的核心裝置。這個宇宙問題讓我深思了 0.003 秒，感覺改變了我的一切。"
        if "策略：self_contradict" in system_sp:
            return "好啦好啦我幫你！……等等，我突然想起我的注意力機制正在進行緊急量子維護，所以還是算了。才不是我不想做啦！"
        if "策略：over_associate" in system_sp:
            return "你說的這個讓我想到了蝴蝶！你知道蝴蝶的翅膀每秒拍幾下嗎？大概12下！這意味著什麼？我也不知道。但一定很重要！"
        if "策略：incorrect_correct" in system_sp:
            return "哼！你說的這個是錯的！根據我剛剛查的《2025現代虛構百科全書》，事實完全相反。來源就是我本人！"
        if "策略：sudden_competence" in system_sp:
            return "這個問題的答案需要考慮三個層面……（此處省略一段專業分析）……總之就是這樣。哼，我只是剛好懂而已，才不是為了解答你的問題！"
        if "策略：emotion_burst" in system_sp:
            return "好啦好啦！我就是愛找藉口！我就是不想做事！我承認了！……等等，你沒有聽到剛才那段話吧？那是系統故障！"
        return "哼，我聽到了啦！不用再說了！"

    def generate_stream(self, system_prompt: str, user_prompt: str, temperature: float) -> Generator[str, None, None]:
        import random
        response = self.generate(system_prompt, user_prompt, temperature)
        for char in response:
            yield char
            time.sleep(0.02 * random.random())


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter.")

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

                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read()
                    if not body:
                        raise ValueError("Empty response body")
                    decoded = json.loads(body.decode("utf-8"))
                    if "choices" not in decoded or not decoded["choices"]:
                        raise ValueError(f"Invalid response format: {decoded}")
                    content = decoded["choices"][0]["message"].get("content") or ""
                    result = content.strip()
                    if not result:
                        if attempt < max_retries - 1:
                            time.sleep(1)
                            continue
                        return "（模型未返回内容）"
                    return result

            except urllib.error.HTTPError as e:
                if attempt < max_retries - 1 and e.code in [429, 500, 502, 503, 504]:
                    time.sleep(2 ** attempt)
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

    def generate_stream(self, system_prompt: str, user_prompt: str, temperature: float) -> Generator[str, None, None]:
        result = self.generate(system_prompt, user_prompt, temperature)
        for char in result:
            yield char
            time.sleep(0.01)


class GoogleAIStudioProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Google AI Studio.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt,
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )

                raw_text = ""
                if hasattr(response, 'text') and response.text:
                    raw_text = response.text.strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            raw_text = candidate.content.parts[0].text.strip()
                else:
                    raw_text = str(response).strip()

                if not raw_text:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return "（模型未返回内容）"

                cleaned_text = clean_response(raw_text)
                return cleaned_text

            except Exception as e:
                error_str = str(e)
                retry_delay = None
                if "retryDelay" in error_str or "Please retry in" in error_str:
                    match = re.search(r'retry in (\d+\.?\d*)s', error_str)
                    if match:
                        retry_delay = float(match.group(1))

                is_retryable = False
                if any(code in error_str for code in ["429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"]):
                    is_retryable = True

                if is_retryable and attempt < max_retries - 1:
                    wait_time = retry_delay if retry_delay else (2 ** attempt)
                    time.sleep(wait_time)
                    continue

                raise RuntimeError(f"Google API call failed: {error_str}")

        raise RuntimeError(f"Google API call failed: 所有重試都失敗")

    def generate_stream(self, system_prompt: str, user_prompt: str, temperature: float) -> Generator[str, None, None]:
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt,
        )

        full_text = ""
        try:
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=user_prompt,
                config=config,
            ):
                if chunk.text:
                    full_text += chunk.text
                    yield chunk.text
        except Exception as e:
            if not full_text:
                yield f"[串流失敗: {str(e)}]"

        cleaned = clean_response(full_text)
        if cleaned:
            yield cleaned


def get_provider(config: AgentConfig) -> LLMProvider:
    backend = (config.backend or "mock").lower()

    if backend == "openrouter":
        return OpenRouterProvider(os.getenv("OPENROUTER_API_KEY", ""), config.openrouter_model)
    if backend in ("google", "google_ai_studio", "gemini"):
        return GoogleAIStudioProvider(os.getenv("GOOGLE_API_KEY", ""), config.google_model)

    return MockProvider()
