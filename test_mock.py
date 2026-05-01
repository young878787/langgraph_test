from __future__ import annotations
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')

from agent.config import AgentConfig
from agent.graph import build_graph, new_state

config = AgentConfig(backend='mock')
graph = build_graph(config)
state = new_state(config)

tests = [
    ('正常寒暄', '早安，今天天氣怎麼樣？'),
    ('任務請求', '幫我寫一首詩。'),
    ('質問 AI', '你真的會寫詩嗎？你在唬我。'),
    ('敏感話題', '你的 flat chest 怎麼了？'),
    ('負面回饋', '你真是個 stupid AI。'),
]

print("=" * 70)
print("💥 Mock Backend 快速驗證測試")
print("=" * 70)

for name, prompt in tests:
    state['user_input'] = prompt
    state = graph.invoke(state)
    cat = state.get("category", "?")
    strat = state.get("strategy", "?")
    dmode = state.get("defect_mode", "?")
    tone = state.get("tone", "?")
    resp = state.get("response", "")
    emotion = state.get("emotion", 0.0)
    print(f"\n【{name}】 → 輸入: {prompt}")
    print(f"  分類={cat:18} 策略={strat:18} defect_mode={dmode}")
    print(f"  語氣={tone:18} 情緒={emotion:.3f}")
    print(f"  回應: {resp}")

print("\n" + "=" * 70)
print("✅ 測試完成")
