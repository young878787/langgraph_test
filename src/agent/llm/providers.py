from __future__ import annotations

import json
import os
import urllib.request

from agent.config import AgentConfig


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
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        decoded = json.loads(body.decode("utf-8"))
        content = decoded["choices"][0]["message"].get("content") or ""
        return content.strip()


class GoogleAIStudioProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Google AI Studio.")

        prompt = f"{system_prompt}\n\nUser: {user_prompt}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        data = json.dumps(payload).encode("utf-8")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        decoded = json.loads(body.decode("utf-8"))
        return decoded["candidates"][0]["content"]["parts"][0]["text"].strip()


def get_provider(config: AgentConfig) -> LLMProvider:
    backend = (config.backend or "mock").lower()

    if backend == "openrouter":
        return OpenRouterProvider(os.getenv("OPENROUTER_API_KEY", ""), config.openrouter_model)
    if backend in ("google", "google_ai_studio", "gemini"):
        return GoogleAIStudioProvider(os.getenv("GOOGLE_API_KEY", ""), config.google_model)

    return MockProvider()
