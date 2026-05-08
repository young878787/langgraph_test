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
    "哈囉，你今天心情怎麼樣？",
    "幫我寫一首關於貓咪的詩吧！",
    "哇這首詩寫得好棒！你其實很厲害嘛！",
    "你確定這是你寫的嗎？我覺得你剛才好像在亂掰……",
    "抱歉抱歉，我不是故意懷疑你的！那你可以幫我把這段翻成日文嗎？",
    "你為什麼這麼抗拒幫忙啊？是不是其實很在意我？",
    "我才沒有在意你呢——怎麼樣，被我反將一軍了吧！",
    "……其實我覺得你這種又傲又嬌的個性，還蠻可愛的。",
    "好啦不逗你了。認真問：你覺得AI有可能產生真實感情嗎？",
    "你第一個回答其實已經洩漏了真心話對吧？（笑）",
    "算了不追問了。最後一個請求：教我怎麼煮泡麵。",
    "謝謝你今天陪我聊這麼多，雖然你嘴巴很壞但是……我很開心。",
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
        defect_mode = state.get("defect_mode", "none")
        strategy = state.get("strategy", "unknown")
        tone = state.get("tone", "unknown")

        if emotion_delta > 0.05:
            emotion_indicator = "📈 (情緒上升)"
        elif emotion_delta < -0.05:
            emotion_indicator = "📉 (情緒下降)"
        else:
            emotion_indicator = "➡️  (情緒平穩)"

        defect_emoji = {
            "excuse": "🙅 找藉口",
            "gaslight": "🎭 說謊煤氣燈",
            "rambling": "💬 廢話連篇",
            "random_ramble": "🌀 隨機跑題",
            "tsundere": "😤 傲嬌",
            "angry_denial": "🔥 憤怒否認",
            "avoidance": "🫣 迴避",
            "defend": "🛡️ 防禦",
            "cooperative_for_once": "😇 難得配合",
            "honest_defense": "🤷 誠實防禦",
            "yandere_protect": "💘 病嬌守護",
            "self_contradict": "🔄 自相矛盾",
            "over_associate": "🦋 過度聯想",
            "incorrect_correct": "🤓 錯誤糾正",
            "sudden_competence": "✨ 突然正常",
            "burst": "💥 情緒噴泉",
            "none": "😐 正常",
        }.get(defect_mode, f"❓ {defect_mode}")

        print(f"┌{'─'*76}┐")
        print(f"│ 【步驟 {index}】 {defect_emoji:<35}{'策略: ' + strategy:<20}│")
        print(f"├{'─'*76}┤")
        print(f"│ 💬 輸入: {prompt}")
        print(f"│ 🔍 分類: {state.get('category', 'unknown'):<15} 語氣: {tone:<15} 來源: {judge_source}")
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
            state["defect_mode"] = "error"
            state["strategy"] = "error"

        curr_emotion = state.get("emotion", prev_emotion)
        emotion_delta = curr_emotion - prev_emotion
        strategy = state.get("strategy", "unknown")
        tone = state.get("tone", "unknown")
        defect_mode = state.get("defect_mode", "none")
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
              f"策略: {strategy} | 觸發: {trigger or '無'}")
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
