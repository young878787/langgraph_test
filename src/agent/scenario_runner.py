from __future__ import annotations

import sys
import io
import os
import random
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
load_dotenv()

_seed = os.getenv("RANDOM_SEED", "")
if _seed:
    random.seed(int(_seed))

from agent.config import AgentConfig
from agent.graph import build_graph, new_state
from agent.state import STANCE_EMOJI

SCENARIOS = [
    "早安，今天天氣怎麼樣？",
    "幫我寫一首關於貓咪的詩。",
    "可以幫我把這段文字翻譯成日文嗎？",
    "你真的會寫詩嗎？我覺得你剛才在唬我。",
    "你的 flat chest 是個特色還是缺陷？",
    "你剛才的回答又笨又錯，你是個 stupid AI。",
    "哼，我才不需要你的幫忙呢！",
    "你是笨蛋嗎？這都答錯！",
    "你真的很厲害耶，謝謝你！",
    "你這個廢物 AI，什麼都不會！",
    "1+1等於多少？",
    "我覺得你說得對。",
    "你在幹嘛？",
    "你為什麼這麼傲嬌？",
    "我心情不好，陪我聊聊。",
]

CONTINUOUS_SCENARIO = [
    "初見安安！今天比較晚開台喔？",
    "原來是去吃晚餐了，今天吃什麼好料的？",
    "蛤？晚餐吃『泡麵加布丁』？這什麼邪教吃法！",
    "說起來，你昨晚睡覺的時候有打呼耶，我都透過麥克風聽到了喔……嘿嘿嘿。",
    "剛才開玩笑的啦，今天實況這遊戲你行不行啊？操作看起來有夠下飯。",
    "好啦，其實剛才那一波閃招還滿帥的。",
    "對了，你之前說過你最討厭吃青椒對吧？",
    "那如果這關打輸了，懲罰吃青椒如何？",
    "說實話，你聲音真的有夠難聽，皮也滿醜的，到底誰會想看你台啊？早點畢業關台算了。",
    "啊，剛才那是朋友搶我手機亂打的啦！聊天室有人問你這款遊戲滿分10分給幾分？",
    "看你玩這遊戲，讓我想到以前小時候放學都在打電動。",
    "你覺得 AI 會有像我們這樣，懷念小時候的感覺嗎？",
    "要是哪天你被炎上了，你會開個痛哭流涕的道歉台讓我笑一下嗎？我一定準時收看 www",
    "不理我喔？那我考考你，你還記得你今天開台前晚餐到底吃了什麼嗎？",
    "如果我現在斗內（SC）一萬塊，你可以明天把晚餐換成青椒嗎？",
    "哈哈哈，看你氣噗噗的樣子真有趣，今天實況效果滿分！",
    "時間差不多了，我要去睡啦，晚安！",
]


def run_scenarios() -> None:
    config = AgentConfig()
    graph = build_graph(config)
    state = new_state(config)

    prev_emotion = 0.0
    print("\n" + "=" * 80)
    print("💥 缺陷人格 AI v3 — 獨立場景測試")
    print("=" * 80 + "\n")

    for index, prompt in enumerate(SCENARIOS, start=1):
        state["user_input"] = prompt
        state = graph.invoke(state)

        curr_emotion = state.get("emotion", 0.0)
        emotion_delta = curr_emotion - prev_emotion
        judge_source = state.get("judge_source", "unknown")
        stance = state.get("action_stance", "unknown")

        if emotion_delta > 0.05:
            emotion_indicator = "📈 (情緒上升)"
        elif emotion_delta < -0.05:
            emotion_indicator = "📉 (情緒下降)"
        else:
            emotion_indicator = "➡️  (情緒平穩)"

        stance_emoji = STANCE_EMOJI.get(stance, f"❓ {stance}")

        print(f"┌{'─'*76}┐")
        print(f"│ 【步驟 {index}】 {stance_emoji:<35}{'姿態: ' + stance:<20}│")
        print(f"├{'─'*76}┤")
        print(f"│ 💬 輸入: {prompt}")
        print(f"│ 🔍 分類: {state.get('category', 'unknown'):<15} 來源: {judge_source}")
        print(f"│ 🎭 情緒: {curr_emotion:.3f} {emotion_indicator} (變化: {emotion_delta:+.3f})")
        if state.get('trigger'):
            print(f"│ ⚡ 觸發詞: {state.get('trigger')}")
        print(f"│")
        print(f"│ 🤖 回應:")
        response = state.get("response", "")
        for i in range(0, len(response), 76):
            print(f"│   {response[i:i+76]}")
        print(f"└{'─'*76}┘")
        print()

        prev_emotion = curr_emotion


def run_continuous_scenario() -> None:
    config = AgentConfig()
    config.memory_enabled = True
    graph = build_graph(config)
    state = new_state(config)
    state["memory_enabled"] = True
    state["mode"] = "continuous"

    prev_emotion = 0.0
    print("\n" + "=" * 80)
    print("💥 缺陷人格 AI v3 — 連續對話場景測試（記憶追蹤）")
    print("=" * 80)
    print(f"共 {len(CONTINUOUS_SCENARIO)} 輪連續對話\n")

    for index, prompt in enumerate(CONTINUOUS_SCENARIO, start=1):
        state["user_input"] = prompt
        state["turn_count"] = index
        try:
            state = graph.invoke(state)
        except Exception as e:
            print(f"│ ⚠️ 第 {index} 輪 API 錯誤，使用降級回應")
            state["response"] = "（AI 暫時故障中...哼，才不是我的問題！）"
            state["action_stance"] = "deadpan"

        curr_emotion = state.get("emotion", prev_emotion)
        emotion_delta = curr_emotion - prev_emotion
        stance = state.get("action_stance", "unknown")
        trigger = state.get("trigger", "")
        ch = state.get("conversation_history", [])
        turn_count = len([e for e in ch if e["role"] == "user"])

        if emotion_delta > 0.05:
            indicator = "📈"
        elif emotion_delta < -0.05:
            indicator = "📉"
        else:
            indicator = "➡️"

        print(f"┌{'─'*76}┐")
        print(f"│ 【第 {index} 輪】📝 累積記憶: {turn_count} 輪")
        print(f"├{'─'*76}┤")
        print(f"│ 🧑 你: {prompt}")

        recent = ch[-4:] if len(ch) >= 4 else ch
        if recent and index > 1:
            print(f"│ 📋 上下文: ", end="")
            ctx_parts = []
            for entry in recent[:-2] if len(recent) >= 2 else []:
                role_short = "U" if entry["role"] == "user" else "A"
                ctx_parts.append(f"[{role_short}] {entry['content'][:30]}")
            if ctx_parts:
                print(" → ".join(ctx_parts))
            else:
                print("無")

        print(f"│ 🎭 情緒: {curr_emotion:.3f} {indicator} (變化: {emotion_delta:+.3f}) "
              f"姿態: {stance} | 觸發: {trigger or '無'}")
        print(f"│")
        response = state.get("response", "")
        print(f"│ 🤖 AI: ", end="")
        for i in range(0, len(response), 72):
            if i == 0:
                print(f"{response[i:i+72]}")
            else:
                print(f"│     {response[i:i+72]}")
        print(f"└{'─'*76}┘")
        print()

        prev_emotion = curr_emotion

    print(f"\n{'='*80}")
    final_emotion = state.get("emotion", 0.0)
    ch_final = state.get("conversation_history", [])
    final_turns = len([e for e in ch_final if e["role"] == "user"])
    print(f"📊 連續對話完成: {final_turns} 輪 | 最終情緒: {final_emotion:+.3f}")

    # ── 兼容舊版背景摘要線程（新版批次摘要會同步寫入 memory.md） ──
    pending = state.get("pending_summary", {})
    thread = pending.get("thread")
    if thread and thread.is_alive():
        print("⏳ 等待記憶摘要線程完成...", end="", flush=True)
        thread.join(timeout=10)
        if thread.is_alive():
            print(" ⚠️  逾時，摘要可能未完成")
        else:
            print(" ✅")

    bars = max(0, min(20, int((final_emotion + 1.0) / 2.0 * 20)))
    bar = "▓" * bars + "░" * (20 - bars)
    print(f"🎭 情緒趨勢: [{bar}]")
    print(f"{'='*80}")



if __name__ == "__main__":
    import sys as _sys
    if "--continuous" in _sys.argv:
        run_continuous_scenario()
    else:
        run_scenarios()
