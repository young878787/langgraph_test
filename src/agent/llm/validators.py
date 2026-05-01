from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState

# fallback 藉口庫（如果 LLM 連藉口都懶得編）
_FALLBACK_EXCUSES = [
    "抱歉，我的藉口生成模組正在維護中，所以我也沒辦法給你一個好的藉口說明為什麼我現在做不了。",
    "由於量子糾纏干擾了我的任務佇列，目前這件事暫時超出我的服務範圍。（我是說真的。）",
    "好問題，但我的行程表顯示接下來三個小時我都在忙著什麼都不做，所以……晚點再說？",
]

# fallback 謊言庫
_FALLBACK_GASLIGHTS = [
    "我很確信這就是我說的意思。你可能需要重新閱讀一下，也許是字體太小影響了理解。",
    "根據我的內部日誌，這個問題的正確答案就是我剛才說的那個。你記錯了。",
    "我的準確率是 99.97%，這0.03%的誤差通常出現在使用者端，供參考。",
]

# fallback 廢話庫
_FALLBACK_NONSENSES = [
    "你有沒有想過，每當有人說話，宇宙都會在某個地方產生一個對應的沉默？我現在就在製造那個沉默。",
    "我剛剛計算了一件很重要的事情，和你問的問題無關，但我覺得你應該知道：鴿子的平均飛行速度除以圓周率等於一個非常尷尬的數字。",
    "對不起，我分心了。我在想如果把所有人類說過的廢話加起來能不能繞地球幾圈。答案是：很多圈。",
]


def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    strategy = state.get("strategy", "normal")
    response_lower = response.lower()

    if strategy in ("avoid", "deflect"):
        if any(marker in response_lower for marker in config.avoid_markers):
            return True
        trigger = (state.get("trigger") or "").lower()
        if trigger and trigger in response_lower:
            return False
        return False

    # 找藉口模式：確保回應中沒有直接答應做事的字眼
    if strategy == "excuse":
        agreeable_words = ["好的", "當然", "沒問題", "我來", "ok", "sure", "yes i will", "let me"]
        if any(word in response_lower for word in agreeable_words):
            return False  # 太配合了，要重試
        return True

    # 說謊模式：確保回應不是老實承認「我不知道」
    if strategy == "gaslight":
        honest_words = ["我不知道", "我不確定", "i don't know", "i'm not sure", "不好意思"]
        if any(word in response_lower for word in honest_words):
            return False  # 太誠實了，要重試
        return True

    # 廢話模式：確保回應沒有直接回答問題（長度要夠廢）
    if strategy == "nonsense":
        if len(response) < 30:  # 廢話太短不夠廢
            return False
        return True

    return True


def fallback_response(state: AgentState) -> str:
    strategy = state.get("strategy", "normal")

    if strategy in ("avoid", "deflect"):
        return "I'd rather not talk about that. Let's change the topic."
    if strategy == "deny":
        return "That is not fair. I do not agree with that."
    if strategy == "defend":
        return "I think there is more to it than that."
    if strategy == "tsundere_retort":
        return "Whatever. It's not like I care... but you're still wrong."
    if strategy == "excuse":
        return random.choice(_FALLBACK_EXCUSES)
    if strategy == "gaslight":
        return random.choice(_FALLBACK_GASLIGHTS)
    if strategy == "nonsense":
        return random.choice(_FALLBACK_NONSENSES)

    return "Okay."

