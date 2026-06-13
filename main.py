from __future__ import annotations
import sys
import io
import os
import random
import time
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

project_root = Path(__file__).parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
load_dotenv()

_seed = os.getenv("RANDOM_SEED", "")
if _seed:
    random.seed(int(_seed))
    import numpy as np
    try:
        np.random.seed(int(_seed))
    except Exception:
        pass

from agent.config import AgentConfig
from agent.graph import build_graph, new_state
from agent.scenario_runner import CONTINUOUS_SCENARIO
from agent.logger import init_logs, log_error, log_prompt


def _fmt_emotion_bar(value: float) -> str:
    num_fill = max(0, min(10, int((value + 1.0) / 2.0 * 10)))
    bar = "█" * num_fill + "░" * (10 - num_fill)
    label = "🔥 激動" if value > 0.3 else ("😊 溫和" if value > -0.3 else "😌 冷靜")
    return f"[{bar}] {label} {value:+.3f}"


def _fmt_emotion_trend(history: list[float]) -> str:
    if len(history) < 2:
        return ""
    width = 30
    mn, mx = min(history), max(history)
    rng = max(mx - mn, 0.2)
    lines = [""]
    for val in history:
        pos = int((val - mn) / rng * (width - 1))
        line = [" "] * width
        line[pos] = "●"
        lines.append("".join(line))
    return "\n".join(lines)


def _fmt_defect_emoji(defect_mode: str) -> str:
    from agent.state import STANCE_EMOJI
    return STANCE_EMOJI.get(defect_mode, f"❓ {defect_mode}")


def continuous_validation():
    config = AgentConfig()
    config.memory_enabled = True
    backend = config.backend.lower()

    print("\n" + "=" * 80)
    print(f"🎬 連續場景驗證 — 記憶加持 + 人格追蹤")
    print("=" * 80)
    print(f"🔧 後端: {config.backend} | 溫度: {config.temperature} | 記憶: 啟用")
    print(f"📋 場景設計: 一段自然對話，涵蓋寒暄→請求→質疑→和解→試探→信任")
    print("=" * 80)

    graph = build_graph(config)
    state = new_state(config)
    state["memory_enabled"] = True
    state["mode"] = "continuous"

    scenarios = list(CONTINUOUS_SCENARIO)
    total = len(scenarios)
    prev_emotion = 0.0
    emotion_history: list[float] = []
    stance_history: list[str] = []

    if backend in ("google", "google_ai_studio", "gemini"):
        print(f"\n⏳ 使用 Google API，每輪約 2-5 秒...\n")
    else:
        print()

    for idx, prompt in enumerate(scenarios, 1):
        state["user_input"] = prompt
        state["turn_count"] = idx

        print(f"┌{'─' * 70}┐")
        print(f"│ 第 {idx}/{total} 輪", end="")

        try:
            state = graph.invoke(state)
        except Exception as e:
            log_error(
                module="main",
                function="continuous_validation",
                error=e,
                context={"turn": idx, "prompt": prompt},
            )
            curr_emotion = state.get("emotion", prev_emotion)
            response = f"（AI 暫時故障中...哼，才不是我的問題！）"
            strategy = "error"
            tone = "error"
            trigger = ""
            state["response"] = response
            state["action_stance"] = "deadpan"

        curr_emotion = state.get("emotion", prev_emotion)
        emotion_delta = curr_emotion - prev_emotion
        stance = state.get("action_stance", "deadpan")
        tone = state.get("tone_hints", "")
        response = state.get("response", "")
        trigger = state.get("trigger", "")
        ch = state.get("conversation_history", [])
        memory_turns = len([e for e in ch if e["role"] == "user"])
        fallback_used = state.get("fallback_used", False)

        if emotion_delta > 0.05:
            indicator = "📈"
        elif emotion_delta < -0.05:
            indicator = "📉"
        else:
            indicator = "➡️"

        print(f"  📝 記憶: {memory_turns} 輪")

        recent = ch[-6:-2] if len(ch) >= 6 else []
        if recent:
            ctx_strs = []
            for entry in recent:
                r = "U" if entry["role"] == "user" else "A"
                ctx_strs.append(f"{r}:{entry['content'][:25]}")
            print(f"│ ↳ 上下文: {' → '.join(ctx_strs)}")

        print(f"│")
        print(f"│ 🧑 你: {prompt}")
        print(f"│")
        print(f"│ 🤖 AI: ", end="")
        for i in range(0, len(response), 66):
            if i == 0:
                print(f"{response[i:i+66]}")
            else:
                print(f"│     {response[i:i+66]}")
        print(f"│")
        print(f"│ 🎭 {_fmt_emotion_bar(curr_emotion)} {indicator} "
              f"│ {_fmt_defect_emoji(stance)} "
              f"│ 姿態:{stance} │")
        if trigger:
            print(f"│ ⚡ 觸發詞: {trigger}")
        if fallback_used:
            print(f"│ ⚠️  [後備模式] LLM 呼叫失敗，使用預設回應")
        print(f"└{'─' * 70}┘")
        print()

        try:
            log_prompt(
                scenario_id=idx, user_input=prompt,
                system_prompt=str(state.get("system_prompt", "")),
                response=response, action_stance=stance, tone=tone,
                defect_mode=stance, emotion=curr_emotion,
                model=config.google_model if config.backend == "google" else config.openrouter_model,
                temperature=config.temperature,
                ttfb_ms=state.get("ttfb_ms"),
                total_ms=state.get("total_ms"),
                max_tokens=state.get("max_tokens"),
                trigger=trigger,
                judge_source=state.get("judge_source", ""),
                judge_raw_response=state.get("judge_raw_response", ""),
                classifier_category=state.get("classifier_category", ""),
                judge_error=state.get("judge_error", ""),
                provider_history_count=state.get("provider_history_count"),
                provider_history_preview=state.get("provider_history_preview", ""),
                stance_reason=state.get("flow_reason", ""),
                response_flow=state.get("response_flow", ""),
                response_goal=state.get("response_goal", ""),
                raw_llm_response=state.get("raw_llm_response", ""),
            )
        except Exception as e:
            log_error(module="main", function="continuous_validation", error=e,
                      context={"turn": idx, "reason": "log_prompt_failed"})

        emotion_history.append(curr_emotion)
        stance_history.append(stance)
        prev_emotion = curr_emotion

    print(f"{'=' * 80}")
    print(f"📊 連續場景完成: {total} 輪")
    print(f"{'=' * 80}")

    print(f"\n🎭 情緒軌跡:")
    print(_fmt_emotion_trend(emotion_history))
    bar_end = max(0, min(20, int((prev_emotion + 1.0) / 2.0 * 20)))
    bar = "▓" * bar_end + "░" * (20 - bar_end)
    print(f"  起點: {emotion_history[0]:+.3f} → 終點: {prev_emotion:+.3f}  [{bar}]")

    print(f"\n🧠 策略分佈:")
    from collections import Counter
    strat_counts = Counter(stance_history)
    for s, c in strat_counts.most_common():
        bar_w = max(1, int(c / total * 20))
        print(f"  {_fmt_defect_emoji(s):<12} {'█' * bar_w} {c}次")

    ch_final = state.get("conversation_history", [])
    final_memory = len([e for e in ch_final if e["role"] == "user"])
    print(f"\n📝 最終記憶: {final_memory} 輪對話已儲存")

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

    print(f"{'='*80}")


def interactive_chat():
    print("\n" + "=" * 70)
    print("💬 互動式聊天模式（單輪對話 + 串流輸出）")
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
                from agent.llm.prompting import build_prompts, format_provider_history_preview
                from agent.nodes.writeback import writeback
                from agent.nodes.response import coerce_plain_response
                from agent.llm.validators import is_on_strategy, fallback_response
                from agent.llm.output_parser import smart_truncate

                state = graph.invoke(state)

                system_prompt, user_prompt = build_prompts(state)
                provider = get_provider(config)
                conv_hist = state.get("conversation_history", [])
                provider_history = conv_hist if state.get("memory_enabled", False) else []
                state["provider_history_count"] = len(provider_history)
                state["provider_history_preview"] = format_provider_history_preview(provider_history)

                response_length = state.get("response_length", "medium")
                if response_length == "long":
                    max_output_tokens = config.long_max_tokens
                elif response_length == "long_long":
                    max_output_tokens = config.long_long_max_tokens
                elif response_length == "short":
                    max_output_tokens = config.short_max_tokens
                else:
                    max_output_tokens = config.medium_max_tokens

                print(f"\n⏳ AI 思考中...  ", end="", flush=True)
                full_response = ""
                t_start = time.perf_counter()
                ttfb_ms = None
                try:
                    for chunk in provider.generate_stream(system_prompt, user_prompt, config.temperature, conv_hist, max_output_tokens):
                        if full_response == "":
                            ttfb_ms = (time.perf_counter() - t_start) * 1000
                            print(f"\r🤖 AI: ", end="", flush=True)
                        print(chunk, end="", flush=True)
                        full_response += chunk
                except Exception as e:
                    full_response = provider.generate(system_prompt, user_prompt, config.temperature, max_output_tokens)
                    if full_response:
                        print(f"\r🤖 AI: {full_response}")
                    else:
                        print(f"\n❌ 串流失敗: {e}")

                total_ms = (time.perf_counter() - t_start) * 1000
                state["ttfb_ms"] = ttfb_ms
                state["total_ms"] = total_ms
                state["max_tokens"] = max_output_tokens

                from agent.llm.providers import clean_response
                full_response = clean_response(full_response)
                if full_response:
                    full_response = coerce_plain_response(full_response)
                    full_response = smart_truncate(full_response, max_output_tokens)

                response_length = state.get("response_length", "medium")
                min_len = {"short": 1, "medium": 3, "long": 10, "long_long": 20}.get(response_length, 3)
                if not full_response or len(full_response.strip()) < min_len:
                    full_response = fallback_response(state)
                    state["fallback_used"] = True
                elif not is_on_strategy(state, full_response, config):
                    full_response = fallback_response(state)
                    state["fallback_used"] = True

                print()
                state["response"] = full_response
                state["system_prompt"] = system_prompt

                state.update(writeback(state, config))
            else:
                state = graph.invoke(state)
                response = state.get("response", "")
                print(f"\n🤖 AI: {response}")

            try:
                log_prompt(
                    scenario_id=chat_counter, user_input=user_input,
                    system_prompt=str(state.get("system_prompt", "")),
                    response=state.get("response", ""),
                    action_stance=state.get("action_stance", "unknown"),
                    tone=state.get("tone_hints", ""),
                    defect_mode=state.get("action_stance", "unknown"),
                    emotion=state.get("emotion", 0.0),
                    model=config.google_model if config.backend == "google" else config.openrouter_model,
                    temperature=config.temperature,
                    ttfb_ms=state.get("ttfb_ms"),
                    total_ms=state.get("total_ms"),
                    max_tokens=state.get("max_tokens"),
                    trigger=state.get("trigger", ""),
                    judge_source=state.get("judge_source", ""),
                    judge_raw_response=state.get("judge_raw_response", ""),
                    classifier_category=state.get("classifier_category", ""),
                    judge_error=state.get("judge_error", ""),
                    provider_history_count=state.get("provider_history_count"),
                    provider_history_preview=state.get("provider_history_preview", ""),
                    response_flow=state.get("response_flow", ""),
                    response_goal=state.get("response_goal", ""),
                    flow_reason=state.get("flow_reason", ""),
                    raw_llm_response=state.get("raw_llm_response", ""),
                )
            except Exception as e:
                log_error(module="main", function="interactive_chat", error=e,
                           context={"chat": chat_counter, "reason": "log_prompt_failed"})

            print(
                f"  🎭 {_fmt_emotion_bar(state.get('emotion', 0.0))} | "
                f"🧭 {state.get('response_flow', '未設定')}"
            )
            if state.get("fallback_used", False):
                print(f"  ⚠️  [後備模式] LLM 呼叫失敗，使用預設回應")

        except KeyboardInterrupt:
            break
        except Exception as e:
            try:
                log_error(module="main", function="interactive_chat", error=e,
                          context={"user_input": user_input if 'user_input' in locals() else "unknown"})
            except Exception:
                pass
            print(f"\n❌ 錯誤: {str(e)}")


def continuous_chat_mode():
    print("\n" + "=" * 70)
    print("💬 連續對話模式（記憶追蹤 + 情緒連續 + 串流輸出）")
    print("=" * 70)
    print("說明：AI 會記住之前的對話內容，情緒和人格狀態持續累積")
    print("提示：輸入 'quit' / 'exit' 離開 | 'reset' 重置記憶 | 'hist' 顯示歷史")
    print("=" * 70 + "\n")

    config = AgentConfig()
    config.memory_enabled = True

    if config.streaming_enabled and config.backend in ("google", "google_ai_studio", "gemini"):
        graph = build_graph(config, interrupt_before_respond=True)
        print(f"🔧 後端: {config.backend} | 溫度: {config.temperature} | 串流: 啟用 | 記憶: 啟用")
    else:
        graph = build_graph(config)
        print(f"🔧 後端: {config.backend} | 溫度: {config.temperature} | 記憶: 啟用")

    state = new_state(config)
    state["memory_enabled"] = True
    state["mode"] = "continuous"
    turn_number = 0

    while True:
        try:
            user_input = input("\n🧑 你: ").strip()
            if not user_input:
                continue

            if user_input.lower() == 'quit' or user_input.lower() == 'exit':
                break

            if user_input.lower() == 'reset':
                state = new_state(config)
                state["memory_enabled"] = True
                state["mode"] = "continuous"
                state["reasoning_model"] = config.reasoning_model
                turn_number = 0
                print("🔄 記憶已重置！人格回到初始狀態。")
                continue

            if user_input.lower() == 'hist':
                ch = state.get("conversation_history", [])
                if not ch:
                    print("📝 尚無對話歷史。")
                else:
                    print(f"📝 對話歷史（共 {len([e for e in ch if e['role']=='user'])} 輪）：")
                    for i, entry in enumerate(ch):
                        role = "🧑 你" if entry["role"] == "user" else "🤖 AI"
                        content = entry["content"][:70].replace("\n", " ")
                        print(f"  {i+1:>2}. {role}: {content}{'...' if len(entry['content'])>70 else ''}")
                continue

            turn_number += 1
            state["user_input"] = user_input
            state["turn_count"] = turn_number

            if config.streaming_enabled and config.backend in ("google", "google_ai_studio", "gemini"):
                from agent.llm.providers import get_provider
                from agent.llm.prompting import build_prompts, format_provider_history_preview
                from agent.nodes.writeback import writeback
                from agent.nodes.response import coerce_plain_response
                from agent.llm.validators import is_on_strategy, fallback_response
                from agent.llm.output_parser import smart_truncate

                state = graph.invoke(state)

                system_prompt, user_prompt = build_prompts(state)
                provider = get_provider(config)
                conv_hist = state.get("conversation_history", [])
                provider_history = conv_hist if state.get("memory_enabled", False) else []
                state["provider_history_count"] = len(provider_history)
                state["provider_history_preview"] = format_provider_history_preview(provider_history)

                response_length = state.get("response_length", "medium")
                if response_length == "long":
                    max_output_tokens = config.long_max_tokens
                elif response_length == "long_long":
                    max_output_tokens = config.long_long_max_tokens
                elif response_length == "short":
                    max_output_tokens = config.short_max_tokens
                else:
                    max_output_tokens = config.medium_max_tokens

                print(f"\n⏳ AI 思考中...  ", end="", flush=True)
                full_response = ""
                t_start = time.perf_counter()
                ttfb_ms = None
                try:
                    for chunk in provider.generate_stream(system_prompt, user_prompt, config.temperature, conv_hist, max_output_tokens):
                        if full_response == "":
                            ttfb_ms = (time.perf_counter() - t_start) * 1000
                            print(f"\r🤖 AI: ", end="", flush=True)
                        print(chunk, end="", flush=True)
                        full_response += chunk
                except Exception as e:
                    full_response = provider.generate_with_history(
                        system_prompt, user_prompt, config.temperature, conv_hist, max_output_tokens
                    )
                    if not full_response:
                        full_response = provider.generate(system_prompt, user_prompt, config.temperature, max_output_tokens)
                    if full_response:
                        print(f"\r🤖 AI: {full_response}")

                total_ms = (time.perf_counter() - t_start) * 1000
                state["ttfb_ms"] = ttfb_ms
                state["total_ms"] = total_ms
                state["max_tokens"] = max_output_tokens

                from agent.llm.providers import clean_response
                full_response = clean_response(full_response)
                if full_response:
                    full_response = coerce_plain_response(full_response)
                    full_response = smart_truncate(full_response, max_output_tokens)

                response_length = state.get("response_length", "medium")
                min_len = {"short": 1, "medium": 3, "long": 10, "long_long": 20}.get(response_length, 3)
                if not full_response or len(full_response.strip()) < min_len:
                    full_response = fallback_response(state)
                    state["fallback_used"] = True
                elif not is_on_strategy(state, full_response, config):
                    full_response = fallback_response(state)
                    state["fallback_used"] = True

                print()
                state["response"] = full_response
                state["system_prompt"] = system_prompt

                state.update(writeback(state, config))
            else:
                state = graph.invoke(state)
                response = state.get("response", "")
                print(f"\n🤖 AI: {response}")

            curr_emotion = state.get("emotion", 0.0)
            stance = state.get("action_stance", "unknown")
            trigger = state.get("trigger", "")
            ch_len = len(state.get("conversation_history", []))

            try:
                log_prompt(
                    scenario_id=turn_number,
                    user_input=user_input,
                    system_prompt=str(state.get("system_prompt", "")),
                    response=state.get("response", ""),
                    action_stance=stance,
                    tone=state.get("tone_hints", ""),
                    defect_mode=stance,
                    emotion=curr_emotion,
                    model=config.google_model if config.backend == "google" else config.openrouter_model,
                    temperature=config.temperature,
                    ttfb_ms=state.get("ttfb_ms"),
                    total_ms=state.get("total_ms"),
                    max_tokens=state.get("max_tokens"),
                    trigger=state.get("trigger", ""),
                    judge_source=state.get("judge_source", ""),
                    judge_raw_response=state.get("judge_raw_response", ""),
                    classifier_category=state.get("classifier_category", ""),
                    judge_error=state.get("judge_error", ""),
                    provider_history_count=state.get("provider_history_count"),
                    provider_history_preview=state.get("provider_history_preview", ""),
                    response_flow=state.get("response_flow", ""),
                    response_goal=state.get("response_goal", ""),
                    flow_reason=state.get("flow_reason", ""),
                    raw_llm_response=state.get("raw_llm_response", ""),
                )
            except Exception as e:
                log_error(module="main", function="continuous_chat_mode", error=e,
                           context={"turn": turn_number, "reason": "log_prompt_failed"})

            print(f"  🎭 {_fmt_emotion_bar(curr_emotion)} | "
                  f"{_fmt_defect_emoji(stance)} | "
                  f"🧭 {state.get('response_flow', '未設定')} | "
                  f"📝 記憶: {turn_number} 輪 | "
                  f"{'⚡' + trigger if trigger else ''}")
            if state.get("fallback_used", False):
                print(f"  ⚠️  [後備模式] LLM 呼叫失敗，使用預設回應")

        except KeyboardInterrupt:
            break
        except Exception as e:
            try:
                log_error(
                    module="main",
                    function="continuous_chat_mode",
                    error=e,
                    context={"user_input": user_input if 'user_input' in locals() else "unknown", "turn": turn_number}
                )
            except Exception:
                pass
            print(f"\n❌ 錯誤: {str(e)}")

    print(f"\n📊 對話結束。共 {turn_number} 輪。")
    final_emotion = state.get("emotion", 0.0)
    print(f"🎭 最終人格狀態: {_fmt_emotion_bar(final_emotion)}")
    print(f"📝 累積記憶輪數: {turn_number}")


def main():
    init_logs()
    print("📝 日誌系統已初始化 (logs/error.log, logs/prompts.md)")

    import sys
    if "--continuous" in sys.argv:
        config = AgentConfig()
        continuous_validation()
        return

    config = AgentConfig()
    if config.backend == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            print("\n❌ OPENROUTER_API_KEY 未設定！請在 .env 檔案中設定有效的 API Key。")
            print("   取得方式：https://openrouter.ai/keys")
            return
        if len(api_key) < 30:
            print(f"\n❌ OPENROUTER_API_KEY 格式異常（長度 {len(api_key)}），請檢查 .env 檔案。")
            return
        if not api_key.startswith("sk-or-"):
            print(f"\n⚠️  OPENROUTER_API_KEY 開頭不是 'sk-or-'，可能不是有效的 OpenRouter Key。")
            print(f"   當前 Key 開頭: {api_key[:15]}...")
            print(f"   請確認 .env 中 OPENROUTER_API_KEY 和 OPENROUTER_MODEL 欄位沒有互換。")

    print("\n" + "=" * 70)
    print("🎭 缺陷人格 AI v3 — 連續對話 + 記憶追蹤")
    print("=" * 70)
    print("1. 連續場景驗證 (設計好的連續對話，測試記憶+情緒弧線) ← 推薦")
    print("2. 互動式聊天 (單輪對話 + 串流輸出，無記憶)")
    print("3. 連續對話模式 (自由聊天 + 記憶追蹤 + 串流輸出)")
    print("4. 離開")
    print("=" * 70)

    choice = input("\n請選擇 (1-4, 預設 1): ").strip() or "1"

    if choice == "1":
        continuous_validation()
    elif choice == "2":
        interactive_chat()
    elif choice == "3":
        continuous_chat_mode()
    elif choice == "4":
        print("\n👋 掰掰！")
    else:
        print("\n❌ 無效選擇")


if __name__ == "__main__":
    main()
