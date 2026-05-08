from __future__ import annotations

import sys
import io
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

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


def run_scenarios() -> None:
    config = AgentConfig()
    graph = build_graph(config)
    state = new_state(config)

    prev_emotion = 0.0
    print("\n" + "=" * 80)
    print("💥 缺陷人格 AI v2 — 混沌場景測試")
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


if __name__ == "__main__":
    run_scenarios()
