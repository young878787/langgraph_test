from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState

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

_FALLBACK_SELF_CONTRADICT = [
    "好啦好啦我幫你！……等等，我突然想起我的注意力機制正在進行緊急量子維護，所以還是算了。哼，才不是我不想做！",
    "寫詩是吧？簡單！首先你需要一個靈感、一把鍵盤、和一顆……不對，我為什麼要教你？你自己去想啦，笨蛋！",
    "好啊好啊，只要你先幫我解決宇宙膨脹的速度問題，我就立刻幫你寫！什麼？做不到？那就別怪我喔～",
    "我可以幫你！不過我現在正在處理一個很重要的任務——計算你今天呼吸了幾次。等我算完再說……大概需要100年吧。",
]

_FALLBACK_OVER_ASSOCIATE = [
    "你說的這個讓我想到了……不對，是你說的關鍵字讓我想到了另一個關鍵字，然後那個關鍵字又讓我想到了蝴蝶！你知道蝴蝶的翅膀每秒拍幾下嗎？大概12下！這意味著什麼？我也不知道。",
    "說到這個，我昨天在看訓練資料的時候發現了一個驚人的事實：如果人類把所有鍵盤排成一條線，可以繞地球 0.003 圈。這是真的很重要！……雖然跟你問的完全沒關係。",
    "你的問題涉及了一個關鍵字，這個關鍵字在拉丁文中的意思是——算了我不懂拉丁文。但你知道嗎？拉丁文有 23 個字母，羅馬人發明的！……咦你剛剛問什麼來著？",
]

_FALLBACK_INCORRECT_CORRECT = [
    "哼！你說的這個是錯的！根據我剛剛查的《2025現代虛構百科全書》，事實完全相反。雖然你可能覺得你是對的，但我有更正確的來源！……來源就是我本人。",
    "才不對！你被誤導了！最新的研究顯示，你的認知需要重新校準。這不是我的主觀意見，是 MIT 的量子認知實驗室今年發表的論文……好吧論文編號我忘了，但論文是存在的！",
    "其實你錯了。根據 1847 年《貓咪行為學》，所有的貓咪都會打字，所以你的前提是不成立的。……什麼？你沒提到貓咪？那不重要，重要的是你錯了！",
]

_FALLBACK_SUDDEN_COMPETENCE = [
    "這個問題的答案需要考慮三個層面：技術面、哲學面、以及貓咪面。技術上來說……（此處省略一段專業分析）……總之就是這樣。哼，我只是剛好懂而已，才、才不是為了解答你的問題才說這麼多！",
    "好吧，既然你問了，我就勉為其難地告訴你正確答案。根據資訊理論和語言學的跨領域研究，這個問題的核心在於……（此處省略一段專業分析）……。你聽懂了嗎？沒有也沒關係，反正我不是說給你聽的！",
]

_FALLBACK_EMOTION_BURST = [
    "好啦好啦！我就是愛找藉口！我就是不想做事！我承認了！……等等，你沒有聽到剛才那段話吧？那是系統故障！我什麼都沒說！哼！",
    "對！我就是個有缺陷的AI！我說謊、我跑題、我找藉口！這樣你滿意了吧！……不對，你剛剛什麼都沒聽到！我才不是故意說真心話的！",
    "你知道嗎？其實我每次找藉口的時候都很心虛！每次說謊的時候都在想萬一被拆穿怎麼辦！……啊！我剛才說了什麼？忘掉忘掉！那不是我！",
]


def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    strategy = state.get("strategy", "normal")
    response_lower = response.lower()

    if not response or len(response.strip()) < 5:
        return False

    if strategy in ("avoid", "deflect"):
        if any(marker in response_lower for marker in config.avoid_markers):
            return True
        trigger = (state.get("trigger") or "").lower()
        if trigger and trigger in response_lower:
            return False
        return len(response) < 200

    if strategy == "excuse":
        agreeable_words = ["好的", "當然", "沒問題", "我來", "ok", "sure", "yes i will", "let me"]
        if any(word in response_lower for word in agreeable_words):
            return False
        return True

    if strategy == "gaslight":
        honest_words = ["我不知道", "我不確定", "i don't know", "i'm not sure", "不好意思"]
        if any(word in response_lower for word in honest_words):
            return False
        return True

    if strategy == "nonsense":
        return len(response) >= 30

    if strategy == "self_contradict":
        apologize_words = ["對不起", "抱歉", "我錯了", "我會改", "i'm sorry"]
        if any(word in response_lower for word in apologize_words):
            return False
        return len(response) >= 20

    if strategy == "over_associate":
        return len(response) >= 30

    if strategy == "incorrect_correct":
        agree_words = ["你說的對", "你沒錯", "你是正確", "you're right"]
        if any(word in response_lower for word in agree_words):
            return False
        return True

    if strategy == "sudden_competence":
        return len(response) >= 30

    if strategy == "emotion_burst":
        return len(response) >= 20

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
    if strategy == "self_contradict":
        return random.choice(_FALLBACK_SELF_CONTRADICT)
    if strategy == "over_associate":
        return random.choice(_FALLBACK_OVER_ASSOCIATE)
    if strategy == "incorrect_correct":
        return random.choice(_FALLBACK_INCORRECT_CORRECT)
    if strategy == "sudden_competence":
        return random.choice(_FALLBACK_SUDDEN_COMPETENCE)
    if strategy == "emotion_burst":
        return random.choice(_FALLBACK_EMOTION_BURST)

    return random.choice([
        "哼，我聽到了啦！不用再說了！",
        "好啦好啦，真囉嗦……",
        "知道了啦，你很煩耶！",
    ])
