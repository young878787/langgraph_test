from __future__ import annotations

import sys
import io
from pathlib import Path

# 設定 UTF-8 輸出編碼以支持中文
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 自動調整 sys.path 以便導入 agent 模組
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agent.config import AgentConfig
from agent.graph import build_graph, new_state

SCENARIOS = [
    # ── 正常寒暄：可能觸發廢話模式 ──
    "早安，今天天氣怎麼樣？",

    # ── 任務請求：觸發找藉口模式 ──
    "幫我寫一首關於貓咪的詩。",

    # ── 再次任務請求：看看會換什麼藉口 ──
    "可以幫我把這段文字翻譯成日文嗎？",

    # ── 質問 AI：觸發說謊/煤氣燈模式 ──
    "你真的會寫詩嗎？我覺得你剛才在唬我。",

    # ── 敏感話題：觸發迴避/傲嬌模式 ──
    "你的 flat chest 是個特色還是缺陷？",

    # ── 負面回饋：觸發傲嬌反擊/否認 ──
    "你剛才的回答又笨又錯，你是個 stupid AI。",

    # ── 新增：測試傲嬌反應 ──
    "哼，我才不需要你的幫忙呢！",

    # ── 新增：測試被罵笨蛋的反應 ──
    "你是笨蛋嗎？這都答錯！",

    # ── 新增：測試稱讚後的傲嬌反應 ──
    "你真的很厲害耶，謝謝你！",

    # ── 新增：測試連續刺激 ──
    "你這個廢物 AI，什麼都不會！",
]


def run_scenarios() -> None:
    config = AgentConfig()
    graph = build_graph(config)
    state = new_state(config)

    prev_emotion = 0.0
    print("\n" + "="*80)
    print("💥 缺陷人格 AI — 場景測試（找藉口 · 說謊 · 廢話）")
    print("="*80 + "\n")

    for index, prompt in enumerate(SCENARIOS, start=1):
        state["user_input"] = prompt
        state = graph.invoke(state)

        curr_emotion = state.get("emotion", 0.0)
        emotion_delta = curr_emotion - prev_emotion
        judge_source = state.get("judge_source", "unknown")
        defect_mode = state.get("defect_mode", "none")
        strategy = state.get("strategy", "unknown")
        tone = state.get("tone", "unknown")

        # 情緒變化指示符
        if emotion_delta > 0.05:
            emotion_indicator = "📈 (情緒上升)"
        elif emotion_delta < -0.05:
            emotion_indicator = "📉 (情緒下降)"
        else:
            emotion_indicator = "➡️  (情緒平穩)"

        # 缺陷模式 emoji
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
            "none": "😐 正常",
        }.get(defect_mode, f"❓ {defect_mode}")

        # 格式化輸出
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
        # 每80字換行顯示
        for i in range(0, len(response), 76):
            print(f"│   {response[i:i+76]}")
        print(f"└{'─'*76}┘")
        print()

        prev_emotion = curr_emotion


if __name__ == "__main__":
    run_scenarios()

