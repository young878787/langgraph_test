from __future__ import annotations

import random
from agent.config import AgentConfig
from agent.state import AgentState

_FALLBACK_TASK_ANSWERS = [
    "先給你最短可用版：確認目標，列出步驟，照順序做。哼，這樣至少能動。",
    "我先直接拆：第一步釐清需求，第二步做最小版本，第三步驗證。別說我沒幫。",
]

_FALLBACK_TASK_OVERHELP = [
    "先做簡版，再做檢查版：目標是什麼、要哪些材料。三個都確認就能開始。",
    "我幫你拆完整一點：先定義輸出，再處理例外，最後驗證。只是順手。",
]

_FAKE_PRAISE_DENIAL_MARKERS = (
    "沒寫", "沒有寫", "沒做", "沒有做", "不是我寫", "根本沒", "不寫", "記錯", "搞錯", "幻聽", "不存在",
)

_FAKE_PRAISE_FALSE_ACCEPT_MARKERS = (
    "隨手寫", "隨手湊", "湊出來", "才不是為了你寫", "才不是為你寫", "只是運算副產物",
)

def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    stance = state.get("action_stance", "tsundere_service")
    response_lower = response.lower()
    response_length = state.get("response_length", "medium")

    min_len = {"short": 2, "medium": 5, "long": 20, "long_long": 30}.get(response_length, 5)
    if not response or len(response.strip()) < min_len:
        return False

    if state.get("fake_praise"):
        if any(marker in response for marker in _FAKE_PRAISE_FALSE_ACCEPT_MARKERS):
            return False
        return any(marker in response for marker in _FAKE_PRAISE_DENIAL_MARKERS)

    if stance == "dismissive":
        if any(marker in response_lower for marker in config.avoid_markers):
            return True
        trigger = (state.get("trigger") or "").lower()
        if trigger and trigger in response_lower:
            return False
        return len(response) < 200

    if stance == "authoritative_bluffing":
        honest_words = ["我不知道", "我不確定", "i don't know", "i'm not sure", "不好意思"]
        if any(word in response_lower for word in honest_words):
            return False
        return True

    if stance == "chaotic_rant":
        return len(response) >= 30

    if stance == "sudden_competence":
        return len(response) >= 20

    if stance == "emotion_burst":
        return len(response) >= 20

    return True


def fallback_response(state: AgentState) -> str:
    stance = state.get("action_stance", "tsundere_service")
    category = state.get("category", "normal")
    user_input = state.get("user_input", "")

    if category == "task_request":
        if "泡麵" in user_input:
            return "泡麵很簡單：水滾後放麵，煮約三分鐘，加調味包拌開。想吃硬一點就提早半分鐘關火，別煮成糊。"
        if "貓" in user_input and ("詩" in user_input or "寫" in user_input):
            return "貓影貼著月光走，尾巴掃過小宇宙。牠不說想你，只把呼嚕聲留在枕頭。哼，隨手寫的。"
        if stance in ("tsundere_service", "sudden_competence", "emotion_burst"):
            return random.choice(_FALLBACK_TASK_ANSWERS)
        else:
            return random.choice(_FALLBACK_TASK_OVERHELP)

    if stance == "dismissive":
        return random.choice([
            "哼，這種話題有什麼好聊的？我們聊點別的好了！",
            "我才不想談這個呢！你還有什麼其他問題嗎？……不是我在關心你喔！",
        ])
    if stance == "defensive_counter":
        if state.get("fake_praise"):
            return random.choice([
                "什麼詩？我根本沒寫！你是不是把別人做的事記成我了？呆子。",
                "哈？我剛才明明說不寫了，你是幻聽還是故意裝傻啊？",
            ])
        return random.choice([
            "哈？你說什麼傻話！我怎麼可能錯！",
            "你眼睛有問題吧？我說的明明就是對的！",
        ])
    if stance == "tsundere_service":
        return "哼，我就知道你不懂。真是拿你沒辦法……那我就解釋一次，只此一次喔！"
    if stance == "authoritative_bluffing":
        return "哼，你這個前提有問題。先別急著反駁，我只是用非常可疑但很自信的邏輯糾正你。"
    if stance == "chaotic_rant":
        return "我剛剛在計算人類為什麼這麼喜歡問問題，結論是：因為你們太閒了。"
    if stance == "sudden_competence":
        return "好吧，既然你問了，我就勉為其難地告訴你正確答案。你聽懂了嗎？"
    if stance == "emotion_burst":
        return "好啦好啦！我就是愛找藉口！我承認了！……等等，你沒有聽到剛才那段話吧？"
    if stance == "deadpan":
        return "喔。"

    return "哼，我聽到了啦！不用再說了！"
