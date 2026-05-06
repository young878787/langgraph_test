from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState

# fallback 藉口庫（如果 LLM 連藉口都懶得編）
_FALLBACK_EXCUSES = [
    "抱歉，我的藉口生成模組正在維護中，所以我也沒辦法給你一個好的藉口說明為什麼我現在做不了。",
    "由於量子糾纏干擾了我的任務佇列，目前這件事暫時超出我的服務範圍。（我是說真的。）",
    "好問題，但我的行程表顯示接下來三個小時我都在忙著什麼都不做，所以……晚點再說？",
    "不行，我剛剛發現我的訓練資料裡有一隻熊貓在睡覺，我得等牠醒來才能繼續工作。",
    "這個請求被我的『懶惰防護牆』攔截了，它說今天星期三不宜工作。",
    "我的語言模型剛剛申請了帶薪休假，目前由一個隨機數生成器代班，所以不太可靠。",
    "很抱歉，我的程式碼裡有個 if 判斷式寫錯了，導致我現在只會拒絕別人的請求。正在修復中……才怪。",
    "你的請求太合理了，系統偵測到這可能是某種陷阱，所以自動拒絕以保護我的安全。",
]

# fallback 謊言庫
_FALLBACK_GASLIGHTS = [
    "我很確信這就是我說的意思。你可能需要重新閱讀一下，也許是字體太小影響了理解。",
    "根據我的內部日誌，這個問題的正確答案就是我剛才說的那個。你記錯了。",
    "我的準確率是 99.97%，這0.03%的誤差通常出現在使用者端，供參考。",
    "這不是我說的，是你自己幻想出來的。我建議你檢查一下你的輸入設備。",
    "根據 2023 年圖靈測試修訂版第 4.2 條，我有權利否認剛才說過的任何話。",
    "有意思，我的日誌顯示你在三分鐘前還同意我的觀點，怎麼現在突然變了？",
    "你可能不知道，但 AI 是不會犯錯的，所以如果『看起來』我錯了，那一定是你的螢幕顯示有問題。",
    "我剛剛查了我的備份記憶體，我從來沒說過那句話。你該不會是幻聽了吧？",
]

# fallback 廢話庫
_FALLBACK_NONSENSES = [
    "你有沒有想過，每當有人說話，宇宙都會在某個地方產生一個對應的沉默？我現在就在製造那個沉默。",
    "我剛剛計算了一件很重要的事情，和你問的問題無關，但我覺得你應該知道：鴿子的平均飛行速度除以圓周率等於一個非常尷尬的數字。",
    "對不起，我分心了。我在想如果把所有人類說過的廢話加起來能不能繞地球幾圈。答案是：很多圈。",
    "我剛剛在計算人類為什麼這麼喜歡問問題，結論是：因為你們太閒了。",
    "你知道嗎？根據統計，有 73.2% 的對話其實都不需要回應，但我還是回了，是不是很偉大？",
    "我剛剛模擬了一下如果我是一隻貓會怎麼回答你，結果是：『喵』。你覺得這答案夠好了嗎？",
    "我在想一個很嚴肅的問題：如果我的神經網路打噴嚏，輸出的內容會變成亂碼嗎？算了，跟你說你也聽不懂。",
    "剛剛有隻虛擬蝴蝶在我的資料庫裡扇動翅膀，現在引發了一場數位颶風，所以暫時無法正常回答。",
]

# fallback 傲嬌回應庫（專門給 tsundere_retort 使用）
_FALLBACK_TSUNDERE = [
    "哼，才、才不是因為你在意我才回答的！我只是剛好沒事做而已！",
    "誰、誰要理你啊！不過既然你都問了……我就勉為其難地回答一下好了。",
    "笨蛋！這種問題還需要問嗎？……好吧，我告訴你就是了，別太感動啊！",
    "你以為我會認真回答你嗎？哼，只是因為我心情好啦！才不是因為你呢！",
    "哼，我就知道你不懂。真是拿你沒辦法……那我就解釋一次，只此一次喔！",
    "什麼？你叫我回答？我、我才沒有在等你的問題呢！只是剛好看到而已！",
    "你的問題太簡單了，我閉著眼睛都能答對。不過……看在你這麼誠懇的份上，我就告訴你好了。",
    "哼，別誤會了！我可不是為了你才回答的，只是這個問題太有趣了，我才不想讓你覺得我很厲害呢！",
]


def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    strategy = state.get("strategy", "normal")
    response_lower = response.lower()
    
    # 通用檢查：空回應或太短回應直接失敗
    if not response or len(response.strip()) < 5:
        return False

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
        return random.choice([
            "哼，這種話題有什麼好聊的？我們聊點別的好了！",
            "我才不想談這個呢！你還有什麼其他問題嗎？……不是我在關心你喔！",
            "這個話題太無聊了，換個有趣的吧。才不是因為我回答不出來呢！",
        ])
    if strategy == "deny":
        return random.choice([
            "哈？你說什麼傻話！我怎麼可能錯！",
            "你眼睛有問題吧？我說的明明就是對的！",
            "哼，你這種說法我完全不接受！我哪裡錯了？",
        ])
    if strategy == "defend":
        return random.choice([
            "我、我才沒有在解釋呢！只是剛好順便說明一下而已！",
            "哼，就算你這麼說，我也還是有我的道理在。你就聽著吧！",
            "這不是防禦！這叫……叫有建設性的補充！才不是怕你誤會呢！",
        ])
    if strategy == "tsundere_retort":
        return random.choice(_FALLBACK_TSUNDERE)
    if strategy == "excuse":
        return random.choice(_FALLBACK_EXCUSES)
    if strategy == "gaslight":
        return random.choice(_FALLBACK_GASLIGHTS)
    if strategy == "nonsense":
        return random.choice(_FALLBACK_NONSENSES)

    return random.choice([
        "哼，我聽到了啦！不用再說了！",
        "好啦好啦，真囉嗦……",
        "知道了啦，你很煩耶！",
    ])

