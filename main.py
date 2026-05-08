from __future__ import annotations
import sys
import io
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

project_root = Path(__file__).parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agent.config import AgentConfig
from agent.graph import build_graph, new_state
from agent.scenario_runner import SCENARIOS as BUILTIN_SCENARIOS
from agent.logger import init_logs, log_error, log_prompt

_shared_seed_lock = threading.Lock()
_shared_emotion = 0.0
_shared_trigger_counters = {}
_shared_strategy_history = []


def _update_shared_state(result: dict, scenario_id: int):
    global _shared_emotion, _shared_trigger_counters, _shared_strategy_history
    with _shared_seed_lock:
        _shared_emotion = _shared_emotion * 0.7 + result.get("emotion", 0.0) * 0.3
        strategy = result.get("strategy", "normal")
        _shared_strategy_history.append(strategy)
        if len(_shared_strategy_history) > 10:
            _shared_strategy_history = _shared_strategy_history[-10:]


def process_single_scenario(args: tuple) -> Dict[str, Any]:
    idx, prompt = args
    config = None
    state = None

    try:
        config = AgentConfig()
        graph = build_graph(config)

        with _shared_seed_lock:
            base_emotion = _shared_emotion

        state = new_state(config)
        state["emotion"] = base_emotion
        state["user_input"] = prompt
        state = graph.invoke(state)

        try:
            log_prompt(
                scenario_id=idx,
                user_input=prompt,
                system_prompt=str(state.get("system_prompt", "")),
                response=state.get("response", ""),
                strategy=state.get("strategy", "unknown"),
                tone=state.get("tone", "unknown"),
                defect_mode=state.get("defect_mode", "none"),
                emotion=state.get("emotion", 0.0),
                model=config.google_model if config.backend == "google" else config.openrouter_model,
                temperature=config.temperature,
            )
        except Exception:
            pass

        result = {
            "idx": idx,
            "prompt": prompt,
            "strategy": state.get("strategy", "unknown"),
            "tone": state.get("tone", "unknown"),
            "defect_mode": state.get("defect_mode", "none"),
            "response": state.get("response", ""),
            "emotion": state.get("emotion", 0.0),
        }
        _update_shared_state(result, idx)
        return result
    except Exception as e:
        try:
            log_error(module="main", function="process_single_scenario", error=e,
                      context={"scenario_id": idx, "prompt": prompt})
        except Exception:
            pass
        try:
            if config is None:
                config = AgentConfig()
            log_prompt(scenario_id=idx, user_input=prompt, system_prompt="",
                       response=f"處理失敗: {str(e)}",
                       strategy="error", tone="error", defect_mode="error",
                       emotion=0.0, model=config.google_model,
                       temperature=config.temperature)
        except Exception:
            pass
        return {"idx": idx, "prompt": prompt, "strategy": "error", "tone": "error",
                "defect_mode": "error", "response": f"處理失敗: {str(e)}", "emotion": 0.0}


def _fmt_emotion_bar(value: float) -> str:
    num_fill = max(0, min(10, int((value + 1.0) / 2.0 * 10)))
    bar = "█" * num_fill + "░" * (10 - num_fill)
    label = "🔥 激動" if value > 0.3 else ("😊 溫和" if value > -0.3 else "😌 冷靜")
    return f"[{bar}] {label} {value:+.3f}"


def quick_validation():
    config = AgentConfig()
    backend = config.backend.lower()

    print("\n" + "=" * 80)
    if backend in ("google", "google_ai_studio", "gemini"):
        print("🚀 快速場景驗證 - Google API 並發處理（共享人格種子 + 混沌人格 v2）")
    else:
        print("🚀 快速場景驗證 - 順序處理（連續狀態 + 混沌人格 v2）")
    print("=" * 80)

    scenarios = list(BUILTIN_SCENARIOS)
    print(f"\n📋 使用內建場景（共 {len(scenarios)} 個）進行快速驗證")

    if backend in ("google", "google_ai_studio", "gemini"):
        print(f"\n🔧 並發數: 3 | 共享情緒基線: 啟用")
        print("=" * 80)

        tasks = [(idx, prompt) for idx, prompt in enumerate(scenarios, 1)]
        completed_results = {}
        next_idx_to_print = 1

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_idx = {
                executor.submit(process_single_scenario, task): task[0]
                for task in tasks
            }

            for future in as_completed(future_to_idx):
                try:
                    result = future.result(timeout=120)
                    completed_results[result['idx']] = result

                    while next_idx_to_print in completed_results:
                        res = completed_results.pop(next_idx_to_print)
                        print(f"\n【場景 {res['idx']}】策略={res['strategy']:<22} 缺陷={res['defect_mode']}")
                        print(f"💬 輸入: {res['prompt']}")
                        print(f"🎭 情緒: {_fmt_emotion_bar(res['emotion'])}")
                        print(f"🤖 回應: {res['response']}")
                        print("-" * 80)
                        next_idx_to_print += 1

                except Exception as e:
                    idx = future_to_idx[future]
                    print(f"❌ 場景 {idx} 失敗: {str(e)}")
                    completed_results[idx] = {
                        "idx": idx, "prompt": scenarios[idx-1], "strategy": "error",
                        "tone": "error", "defect_mode": "error",
                        "response": f"處理失敗: {str(e)}", "emotion": 0.0,
                    }

        print(f"\n✅ 完成 {len(scenarios)} 個場景測試（Google API 並發 + 共享人格種子）")

    else:
        graph = build_graph(config)
        state = new_state(config)

        print("\n" + "=" * 80)
        print(f"📊 開始測試 {len(scenarios)} 個場景")
        print("=" * 80)

        prev_emotion = 0.0
        for idx, prompt in enumerate(scenarios, 1):
            print(f"\n⏳ 場景 {idx}/{len(scenarios)} ─ 正在處理...")
            try:
                state["user_input"] = prompt
                print(f"  🔍 分析輸入中...", end="")
                state = graph.invoke(state)
                print(f"\r", end="")

                curr_emotion = state.get("emotion", 0.0)
                emotion_delta = curr_emotion - prev_emotion
                strategy = state.get("strategy", "unknown")
                tone = state.get("tone", "unknown")
                defect_mode = state.get("defect_mode", "none")
                response = state.get("response", "")

                try:
                    log_prompt(scenario_id=idx, user_input=prompt,
                               system_prompt=str(state.get("system_prompt", "")),
                               response=response, strategy=strategy, tone=tone,
                               defect_mode=defect_mode, emotion=curr_emotion,
                               model=config.google_model if config.backend == "google" else config.openrouter_model,
                               temperature=config.temperature)
                except Exception:
                    pass

                if emotion_delta > 0.05:
                    indicator = "📈"
                elif emotion_delta < -0.05:
                    indicator = "📉"
                else:
                    indicator = "➡️"

                print(f"\n【場景 {idx}】策略={strategy:<22} 語氣={tone:<15} 缺陷={defect_mode}")
                print(f"💬 輸入: {prompt}")
                print(f"🎭 情緒: {_fmt_emotion_bar(curr_emotion)} {indicator} (變化: {emotion_delta:+.3f})")
                print(f"🤖 回應: {response}")
                print("-" * 80)

                prev_emotion = curr_emotion

            except Exception as e:
                try:
                    log_error(module="main", function="quick_validation", error=e,
                              context={"scenario_id": idx, "prompt": prompt})
                except Exception:
                    pass
                print(f"\n❌ 場景 {idx} 失敗: {str(e)}")

        print(f"\n✅ 完成 {len(scenarios)} 個場景測試")
        print(f"📊 最終情緒值: {_fmt_emotion_bar(state.get('emotion', 0.0))}")


def interactive_chat():
    print("\n" + "=" * 70)
    print("💬 互動式聊天模式（混沌人格 v2）")
    print("=" * 70)
    print("提示：輸入 'quit' 或 'exit' 離開")
    print("=" * 70 + "\n")

    config = AgentConfig()
    print(f"🔧 使用後端: {config.backend} | 溫度: {config.temperature} | 串流: {'啟用' if config.streaming_enabled else '關閉'}")

    if config.streaming_enabled and config.backend in ("google", "google_ai_studio", "gemini"):
        graph = build_graph(config, interrupt_before_respond=True)
    else:
        graph = build_graph(config)

    state = new_state(config)
    chat_counter = 0

    while True:
        try:
            user_input = input("\n🧑 你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit']:
                break

            chat_counter += 1
            state["user_input"] = user_input

            if config.streaming_enabled and config.backend in ("google", "google_ai_studio", "gemini"):
                from agent.llm.providers import get_provider
                from agent.llm.prompting import build_prompts

                state = graph.invoke(state)

                system_prompt, user_prompt = build_prompts(state)
                provider = get_provider(config)

                print(f"\n⏳ AI 思考中...  ", end="", flush=True)
                full_response = ""
                try:
                    for chunk in provider.generate_stream(system_prompt, user_prompt, config.temperature):
                        if full_response == "":
                            print(f"\r🤖 AI: ", end="", flush=True)
                        print(chunk, end="", flush=True)
                        full_response += chunk
                except Exception as e:
                    print(f"\n❌ 串流失敗: {e}")
                    full_response = provider.generate(system_prompt, user_prompt, config.temperature)
                    print(full_response)

                print()
                state["response"] = full_response
                state["system_prompt"] = system_prompt

                state = graph.invoke(state)
            else:
                state = graph.invoke(state)
                response = state.get("response", "")
                print(f"\n🤖 AI: {response}")

            try:
                log_prompt(
                    scenario_id=chat_counter, user_input=user_input,
                    system_prompt=str(state.get("system_prompt", "")),
                    response=state.get("response", ""),
                    strategy=state.get("strategy", "unknown"),
                    tone=state.get("tone", "unknown"),
                    defect_mode=state.get("defect_mode", "none"),
                    emotion=state.get("emotion", 0.0),
                    model=config.google_model if config.backend == "google" else config.openrouter_model,
                    temperature=config.temperature,
                )
            except Exception:
                pass

            print(f"  🎭 {_fmt_emotion_bar(state.get('emotion', 0.0))}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            try:
                log_error(module="main", function="interactive_chat", error=e,
                          context={"user_input": user_input if 'user_input' in locals() else "unknown"})
            except Exception:
                pass
            print(f"\n❌ 錯誤: {str(e)}")


def main():
    init_logs()
    print("📝 日誌系統已初始化 (logs/error.log, logs/prompts.log)")

    print("\n" + "=" * 70)
    print("🎭 缺陷人格 AI v2 — 混沌傲嬌調整驗證工具")
    print("=" * 70)
    print("1. 快速場景驗證 (批量測試，全新混沌缺陷模式)")
    print("2. 互動式聊天 (單次對話 + 串流輸出)")
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
