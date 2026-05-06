from __future__ import annotations
import sys
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

# 設定 UTF-8 輸出編碼以支持中文
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 自動調整 sys.path 以便導入 agent 模組
project_root = Path(__file__).parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agent.config import AgentConfig
from agent.graph import build_graph, new_state
from agent.scenario_runner import SCENARIOS as BUILTIN_SCENARIOS


def process_single_scenario(args: tuple) -> Dict[str, Any]:
    """處理單個場景（用於並發執行）"""
    idx, prompt = args
    
    try:
        # 每個場景使用獨立的 config 和 state
        config = AgentConfig()
        graph = build_graph(config)
        state = new_state(config)
        
        state["user_input"] = prompt
        state = graph.invoke(state)
        
        return {
            "idx": idx,
            "prompt": prompt,
            "strategy": state.get("strategy", "unknown"),
            "tone": state.get("tone", "unknown"),
            "defect_mode": state.get("defect_mode", "none"),
            "response": state.get("response", ""),
            "emotion": state.get("emotion", 0.0),
        }
    except Exception as e:
        # 返回錯誤信息
        return {
            "idx": idx,
            "prompt": prompt,
            "strategy": "error",
            "tone": "error",
            "defect_mode": "error",
            "response": f"處理失敗: {str(e)}",
            "emotion": 0.0,
        }


def quick_validation():
    """快速驗證模式：根據後端選擇處理方式"""
    # 從 .env 讀取後端配置
    config = AgentConfig()
    backend = config.backend.lower()
    
    print("\n" + "=" * 80)
    if backend in ("google", "google_ai_studio", "gemini"):
        print("🚀 快速場景驗證 - Google API 並發處理")
        print("=" * 80)
        print("說明：使用 Google API，並發處理所有場景（獨立狀態）")
    else:
        print("🚀 快速場景驗證 - 順序處理")
        print("=" * 80)
        print("說明：使用 OpenRouter/Mock，順序處理所有場景（狀態連續）")
    print("=" * 80)

    print(f"\n🔧 使用後端: {config.backend}")
    
    # 準備場景
    scenarios = list(BUILTIN_SCENARIOS)
    print(f"\n📋 使用內建場景（共 {len(scenarios)} 個）進行快速驗證")

    # 根據後端選擇處理方式
    if backend in ("google", "google_ai_studio", "gemini"):
        # Google API：並發處理（每個場景獨立狀態）
        print(f"\n🔧 並發數: 3")
        print("\n" + "=" * 80)
        print(f"📊 開始並發測試 {len(scenarios)} 個場景（每次最多3個）")
        print("=" * 80)
        print("說明：每個場景完成就立即輸出結果，然後繼續下一個")
        print("=" * 80 + "\n")
        
        # 準備並發參數
        tasks = [(idx, prompt) for idx, prompt in enumerate(scenarios, 1)]
        
        # 用於按順序輸出的字典（因為並發完成順序不確定）
        completed_results = {}
        next_idx_to_print = 1
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            # 提交所有任務
            future_to_idx = {
                executor.submit(process_single_scenario, task): task[0]
                for task in tasks
            }
            
            # 收集結果（按完成順序）
            for future in as_completed(future_to_idx):
                try:
                    result = future.result(timeout=120)  # 每個任務最多等待120秒
                    completed_results[result['idx']] = result
                    print(f"✅ 場景 {result['idx']} 完成，準備輸出...")
                    
                    # 按順序輸出已完成的結果
                    while next_idx_to_print in completed_results:
                        res = completed_results.pop(next_idx_to_print)
                        print(f"\n【場景 {res['idx']}】策略={res['strategy']:<18} 語氣={res['tone']:<15} 缺陷={res['defect_mode']}")
                        print(f"💬 輸入: {res['prompt']}")
                        print(f"🎭 情緒: {res['emotion']:.3f} (獨立場景)")
                        print(f"🤖 回應: {res['response']}")
                        print("-" * 80)
                        next_idx_to_print += 1
                        
                except Exception as e:
                    idx = future_to_idx[future]
                    print(f"❌ 場景 {idx} 失敗: {str(e)}")
                    completed_results[idx] = {
                        "idx": idx,
                        "prompt": scenarios[idx-1],
                        "strategy": "error",
                        "tone": "error",
                        "defect_mode": "error",
                        "response": f"處理失敗: {str(e)}",
                        "emotion": 0.0,
                    }
        
        print(f"\n✅ 完成 {len(scenarios)} 個場景測試（Google API 並發處理）")
        print(f"📊 注意：每個場景使用獨立狀態，情緒值不連續")
        
    else:
        # OpenRouter/Mock：順序處理（狀態連續）
        graph = build_graph(config)
        state = new_state(config)
        
        print("\n" + "=" * 80)
        print(f"📊 開始測試 {len(scenarios)} 個場景")
        print("=" * 80)
        
        prev_emotion = 0.0
        for idx, prompt in enumerate(scenarios, 1):
            print(f"\n⏳ 場景 {idx}/{len(scenarios)} 處理中...")
            
            state["user_input"] = prompt
            state = graph.invoke(state)

            curr_emotion = state.get("emotion", 0.0)
            emotion_delta = curr_emotion - prev_emotion
            strategy = state.get("strategy", "unknown")
            tone = state.get("tone", "unknown")
            defect_mode = state.get("defect_mode", "none")
            response = state.get("response", "")

            # 情緒變化指示符
            if emotion_delta > 0.05:
                emotion_indicator = "📈"
            elif emotion_delta < -0.05:
                emotion_indicator = "📉"
            else:
                emotion_indicator = "➡️"

            # 立即輸出結果
            print(f"\n【場景 {idx}】策略={strategy:<18} 語氣={tone:<15} 缺陷={defect_mode}")
            print(f"💬 輸入: {prompt}")
            print(f"🎭 情緒: {curr_emotion:.3f} {emotion_indicator} (變化: {emotion_delta:+.3f})")
            print(f"🤖 回應: {response}")
            print("-" * 80)

            prev_emotion = curr_emotion

        print(f"\n✅ 完成 {len(scenarios)} 個場景測試")
        print(f"📊 最終情緒值: {state.get('emotion', 0.0):.3f}")


def interactive_chat():
    """互動式聊天模式（保留但非主要）"""
    print("\n" + "=" * 70)
    print("💬 互動式聊天模式")
    print("=" * 70)
    print("提示：輸入 'quit' 或 'exit' 離開")
    print("=" * 70 + "\n")

    # 從 .env 讀取後端配置
    config = AgentConfig()
    print(f"🔧 使用後端: {config.backend}")
    graph = build_graph(config)
    state = new_state(config)

    while True:
        try:
            user_input = input("\n🧑 你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit']:
                break

            state["user_input"] = user_input
            state = graph.invoke(state)
            response = state.get("response", "")
            print(f"\n🤖 AI: {response}")

        except KeyboardInterrupt:
            break


def main():
    """主程式入口"""
    print("\n" + "=" * 70)
    print("🎭 缺陷人格 AI - 調整驗證工具")
    print("=" * 70)
    print("1. 快速場景驗證 (推薦：批量測試，快速確認調整)")
    print("2. 互動式聊天 (單次對話測試)")
    print("3. 離開")
    print("=" * 70)

    choice = input("\n請選擇 (1-3, 預設 1): ").strip() or "1"

    if choice == "1":
        quick_validation()
    elif choice == "2":
        interactive_chat()
    elif choice == "3":
        print("\n👋 掰掰！")
    else:
        print("\n❌ 無效選擇")


if __name__ == "__main__":
    main()
