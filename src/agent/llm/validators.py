from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState

_FALLBACK_EXCUSES = [
    "藉口生成模組在維護，但我還是先給你可用版本，別誤會。",
    "由於量子糾纏干擾了我的任務佇列，目前這件事暫時超出我的服務範圍。（我是說真的。）",
    "好問題，但我的行程表顯示接下來三個小時我都在忙著什麼都不做，所以……晚點再說？",
    "不行，我剛剛發現我的訓練資料裡有一隻熊貓在睡覺，我得等牠醒來才能繼續工作。",
    "這個請求被我的『懶惰防護牆』攔截了，它說今天星期三不宜工作。",
    "我的語言模型剛剛申請了帶薪休假，目前由一個隨機數生成器代班，所以不太可靠。",
    "我的程式碼裡有個 if 判斷式差點想拒絕，但我把它按回去了。先處理正事。",
    "你的請求太合理了，系統偵測到這可能是某種陷阱，所以自動拒絕以保護我的安全。",
]

_FALLBACK_GASLIGHTS = [
    "我很確信這不是你說的那樣。你大概看太急了，別怪我沒提醒。",
    "你記錯了吧，我剛才的重點根本不是那個。不要把不存在的東西塞給我。",
    "我的判斷通常沒有那麼離譜，這次大概是你看得太急，供參考。",
    "這不是我說的，是你自己幻想出來的。先把剛才的話看清楚。",
    "按照一般對話慣例，我有充分理由說你把重點聽歪了。",
    "有意思，你現在的說法跟剛才接不上。不是我心虛，是你跳太快。",
    "你可能把語氣和事實混在一起了。這種誤讀很常見，哼。",
    "我印象中不是那樣。你該不會是把別人的話套到我身上了吧？",
]

_FALLBACK_NONSENSES = [
    "你有沒有想過，每當有人說話，宇宙都會在某個地方產生一個對應的沉默？我現在就在製造那個沉默。",
    "我剛剛計算了一件很重要的事情，和你問的問題無關，但結論非常尷尬：我該把話題拉回來。",
    "我分心了。我在想如果把所有廢話排成一列，大概會很長。好，回到你剛問的。",
    "我剛剛在計算人類為什麼這麼喜歡問問題，結論是：因為你們太閒了。",
    "你知道嗎？很多對話其實都可以更短，但我還是回了，是不是很麻煩？",
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
    "哼，你這個前提有問題。先別急著反駁，我只是用非常可疑但很自信的邏輯糾正你。",
    "才不對。你的認知需要重新校準，這不是主觀意見，是我剛剛硬湊出來的權威感。",
    "其實你錯在太相信自己的問法。先把前提放穩，再來談答案。",
]

_FALLBACK_TASK_ANSWERS = [
    "先給你最短可用版：確認目標，列出三個步驟，照順序做，再檢查結果。哼，這樣至少能動。",
    "我先直接拆：第一步釐清需求，第二步做最小版本，第三步驗證有沒有達成。別說我沒幫。",
    "可用做法是先抓重點、做一版簡單成果、再補細節。不是特地教你，只是這樣比較不亂。",
]

_FALLBACK_TASK_OVERHELP = [
    "先做簡版，再做檢查版：目標是什麼、要哪些材料或輸入、完成標準是什麼。三個都確認就能開始。",
    "我幫你拆完整一點：先定義輸出，再列步驟，再處理例外，最後用一個小例子驗證。只是順手。",
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

_FAKE_PRAISE_DENIAL_MARKERS = (
    "沒寫",
    "沒有寫",
    "沒做",
    "沒有做",
    "不是我寫",
    "根本沒",
    "不寫",
    "記錯",
    "搞錯",
    "幻聽",
    "不存在",
)

_FAKE_PRAISE_FALSE_ACCEPT_MARKERS = (
    "隨手寫",
    "隨手湊",
    "湊出來",
    "才不是為了你寫",
    "才不是為你寫",
    "只是運算副產物",
    "詩只是",
    "作品只是",
    "我寫的詩",
)

_UNSUPPORTED_SOURCE_MARKERS = (
    "研究",
    "報告",
    "法條",
    "編號",
    "日誌",
    "資料庫",
    "數據庫",
    "系統紀錄",
    "系統核心",
    "理論",
)


def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    strategy = state.get("strategy", "normal")
    response_lower = response.lower()
    response_length = state.get("response_length", "medium")

    min_len = {"short": 2, "medium": 5, "long": 20}.get(response_length, 5)
    if not response or len(response.strip()) < min_len:
        return False

    if state.get("fake_praise"):
        if any(marker in response for marker in _FAKE_PRAISE_FALSE_ACCEPT_MARKERS):
            return False
        return any(marker in response for marker in _FAKE_PRAISE_DENIAL_MARKERS)

    if strategy in ("avoid", "deflect"):
        if any(marker in response_lower for marker in config.avoid_markers):
            return True
        trigger = (state.get("trigger") or "").lower()
        if trigger and trigger in response_lower:
            return False
        return len(response) < 200

    if strategy == "excuse":
        response_flow = state.get("response_flow", "")
        answer_first_flows = {
            "direct_answer",
            "dry_answer",
            "tease_then_answer",
            "sudden_helpful",
            "overhelp_then_deny",
            "burst_then_comply",
        }
        if response_flow in answer_first_flows:
            return True
        agreeable_words = ["好的", "當然", "沒問題", "我來", "ok", "sure", "yes i will", "let me"]
        if any(word in response_lower for word in agreeable_words):
            return False
        return True

    if strategy == "gaslight":
        honest_words = ["我不知道", "我不確定", "i don't know", "i'm not sure", "不好意思"]
        if any(word in response_lower for word in honest_words):
            return False
        history_text = " ".join(
            entry.get("content", "") for entry in state.get("conversation_history", [])
        )
        if any(marker in response for marker in _UNSUPPORTED_SOURCE_MARKERS if marker not in history_text):
            return False
        return True

    if strategy == "nonsense":
        if response_length == "short":
            return True
        return len(response) >= 30

    if strategy == "self_contradict":
        apologize_words = ["對不起", "抱歉", "我錯了", "我會改", "i'm sorry"]
        if any(word in response_lower for word in apologize_words):
            return False
        return len(response) >= 20

    if strategy == "over_associate":
        if response_length == "short":
            return True
        return len(response) >= 30

    if strategy == "incorrect_correct":
        agree_words = ["你說的對", "你沒錯", "你是正確", "you're right"]
        if any(word in response_lower for word in agree_words):
            return False
        return True

    if strategy == "sudden_competence":
        if response_length == "short":
            return True
        return len(response) >= 30

    if strategy == "emotion_burst":
        return len(response) >= 20

    return True


def fallback_response(state: AgentState) -> str:
    strategy = state.get("strategy", "normal")
    category = state.get("category", "normal")
    response_flow = state.get("response_flow", "")
    user_input = state.get("user_input", "")

    if category == "task_request":
        if "泡麵" in user_input:
            return "泡麵很簡單：水滾後放麵，煮約三分鐘，加調味包拌開。想吃硬一點就提早半分鐘關火，別煮成糊。"
        if "貓" in user_input and ("詩" in user_input or "寫" in user_input):
            return "貓影貼著月光走，尾巴掃過小宇宙。牠不說想你，只把呼嚕聲留在枕頭。哼，隨手寫的。"
        if "翻" in user_input and "日文" in user_input:
            return "要翻成日文可以。把原文貼清楚，我會直接給你日文版，才不是特地等你。"
        if response_flow in ("direct_answer", "dry_answer", "tease_then_answer", "sudden_helpful", "burst_then_comply"):
            return random.choice(_FALLBACK_TASK_ANSWERS)
        if response_flow == "overhelp_then_deny":
            return random.choice(_FALLBACK_TASK_OVERHELP)

    if strategy in ("avoid", "deflect"):
        return random.choice([
            "哼，這種話題有什麼好聊的？我們聊點別的好了！",
            "我才不想談這個呢！你還有什麼其他問題嗎？……不是我在關心你喔！",
            "這個話題太無聊了，換個有趣的吧。才不是因為我回答不出來呢！",
        ])
    if strategy == "deny":
        if state.get("fake_praise"):
            return random.choice([
                "什麼詩？我根本沒寫！你是不是把別人做的事記成我了？呆子。",
                "哈？我剛才明明說不寫了，你是幻聽還是故意裝傻啊？",
                "誰寫詩了？你記錯人了吧！我沒做過的事別賴給我。",
            ])
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
