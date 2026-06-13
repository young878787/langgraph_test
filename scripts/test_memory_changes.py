from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.memory_quality import (  # noqa: E402
    build_structured_fallback,
    clean_summary_output,
    validate_summary,
)
from agent.config import AgentConfig  # noqa: E402
from agent.llm.prompting import build_prompts  # noqa: E402
from agent.nodes.writeback import _summarize_worker, writeback  # noqa: E402
from agent.state import initial_state  # noqa: E402


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}\nexpected: {expected!r}\nactual:   {actual!r}")


def assert_true(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def assert_false(value: bool, label: str) -> None:
    if value:
        raise AssertionError(label)


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}\nmissing: {needle!r}\nactual:  {text!r}")


def assert_not_contains(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"{label}\nforbidden: {needle!r}\nactual:    {text!r}")


def assert_contains_any(text: str, needles: tuple[str, ...], label: str) -> None:
    if not any(needle in text for needle in needles):
        raise AssertionError(f"{label}\nexpected one of: {needles!r}\nactual: {text!r}")


def test_clean_summary_output() -> None:
    assert_equal(
        clean_summary_output("摘要內容：使用者提到 AI 討厭青椒，AI 拒絕吃青椒懲罰。"),
        "使用者提到 AI 討厭青椒，AI 拒絕吃青椒懲罰。",
        "clean_summary_output should strip Chinese summary prefix",
    )

    dirty = "\n".join(
        [
            "* Input: A dialogue between user and AI.",
            "* Task: Condense the dialogue.",
            "使用者提到 AI 討厭青椒，並提議打輸遊戲要吃青椒；AI 明確拒絕。",
            "- Output: Traditional Chinese summary only.",
        ]
    )
    cleaned = clean_summary_output(dirty)
    assert_not_contains(cleaned, "Input:", "clean_summary_output should remove English Input meta line")
    assert_not_contains(cleaned, "Task:", "clean_summary_output should remove English Task meta line")
    assert_not_contains(cleaned, "Output:", "clean_summary_output should remove English Output meta line")
    assert_contains(cleaned, "青椒", "clean_summary_output should keep useful Chinese memory content")
    assert_contains(cleaned, "拒絕", "clean_summary_output should keep refusal semantics")


def test_validate_summary() -> None:
    assert_true(
        validate_summary("使用者提到 AI 討厭青椒（已確認偏好），並提議打輸遊戲要吃青椒；AI 明確拒絕這項懲罰。"),
        "validate_summary should accept a normal Traditional Chinese summary",
    )

    assert_false(
        validate_summary("* Input: A dialogue.\n* Task: Condense the dialogue.\n* Output: Summary only."),
        "validate_summary should reject English prompt/meta leakage",
    )

    assert_false(
        validate_summary("使用者提到：今天吃什麼、打輸要吃青椒。AI 回應涉及：不要、拒絕、哈哈。"),
        "validate_summary should reject low-quality mechanical fallback format",
    )


def test_build_structured_fallback() -> None:
    messages = [
        {"role": "user", "content": "你不是最討厭青椒嗎？等一下遊戲打輸就吃青椒。"},
        {"role": "assistant", "content": "不要，我拒絕。打輸可以懲罰別的，但青椒不行。"},
    ]

    fallback = build_structured_fallback(messages)
    assert_contains(fallback, "青椒", "build_structured_fallback should preserve green pepper preference")
    assert_contains_any(
        fallback,
        ("拒絕", "不同意", "不接受", "不要"),
        "build_structured_fallback should preserve refusal semantics",
    )
    assert_false(
        fallback.strip().startswith("使用者提到"),
        "build_structured_fallback should not only output the old mechanical '使用者提到' format",
    )

    emotion_messages = [
        {"role": "user", "content": "剛才那一波閃招很帥耶。"},
        {"role": "assistant", "content": "我才沒有因為被稱讚就害羞，哼，只是恢復嘴硬而已。"},
    ]
    emotion_fallback = build_structured_fallback(emotion_messages)
    assert_contains_any(
        emotion_fallback,
        ("害羞", "嘴硬", "情緒", "轉折"),
        "build_structured_fallback should preserve assistant-side emotion turns",
    )


def test_summarize_worker_rejects_mechanical_summary() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, prompt: str, max_tokens: int = 300) -> str:
            self.calls += 1
            # 無論 retry 幾次都回傳機械式摘要，最後應該走 structured_fallback
            return "使用者提到：今天吃什麼、打輸吃青椒。AI 回應涉及：不要、拒絕、哈哈。"

    messages = [
        {"role": "user", "content": "你不是最討厭青椒嗎？等一下遊戲打輸就吃青椒。"},
        {"role": "assistant", "content": "不要，我拒絕。打輸可以懲罰別的，但青椒不行。"},
    ]
    holder = {}

    _summarize_worker(FakeProvider(), messages, "", holder)

    assert_equal(holder.get("source"), "structured_fallback", "_summarize_worker should mark fallback source")
    assert_not_contains(
        holder.get("result", ""),
        "AI 回應涉及",
        "_summarize_worker should not persist the old mechanical fallback format",
    )
    assert_contains(holder.get("result", ""), "低信心摘要", "_summarize_worker should use structured fallback")


def test_summarize_worker_preserves_summary_without_extra_calls() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, prompt: str, max_tokens: int = 300) -> str:
            self.calls += 1
            return "使用者提到 AI 討厭青椒（已確認偏好），並提議打輸遊戲要吃青椒；AI 明確拒絕這項懲罰。"

    messages = [
        {"role": "user", "content": "你不是最討厭青椒嗎？等一下遊戲打輸就吃青椒。"},
        {"role": "assistant", "content": "不要，我拒絕。打輸可以懲罰別的，但青椒不行。"},
    ]
    holder = {}

    provider = FakeProvider()
    _summarize_worker(provider, messages, "", holder)

    assert_equal(holder.get("source"), "llm", "good LLM summary should be marked as llm source")
    assert_contains(holder.get("result", ""), "已確認偏好", "good LLM summary should be preserved")
    assert_equal(provider.calls, 1, "should stop after first valid summary, no extra calls")


def test_writeback_persists_summary_and_uses_passed_config() -> None:
    class FakeProvider:
        def summarize(self, prompt: str, max_tokens: int = 300) -> str:
            return "使用者提到 AI 討厭青椒（已確認偏好），並提議打輸遊戲要吃青椒；AI 明確拒絕這項懲罰。"

    import agent.llm.providers as providers

    original_get_provider = providers.get_provider
    providers.get_provider = lambda config: FakeProvider()
    try:
        config = AgentConfig()
        config.memory_summary_threshold = 2
        config.max_history_turns = 10
        state = initial_state(config)
        state["memory_enabled"] = True
        state["user_input"] = "你不是最討厭青椒嗎？等一下遊戲打輸就吃青椒。"
        state["response"] = "不要，我拒絕。打輸可以懲罰別的，但青椒不行。"

        result = writeback(state, config)
    finally:
        providers.get_provider = original_get_provider

    assert_equal(result.get("memory_summary_buffer"), [], "writeback should honor passed threshold config")
    assert_contains(result.get("long_term_memory", ""), "已確認偏好", "writeback should persist LLM summary")


def test_writeback_accumulates_long_term_memory() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, prompt: str, max_tokens: int = 300) -> str:
            self.calls += 1
            if self.calls == 1:
                return "使用者提到 AI 討厭青椒（已確認偏好），並提議打輸遊戲要吃青椒；AI 明確拒絕。"
            return (
                "使用者提到 AI 討厭青椒（已確認偏好），並提議打輸遊戲要吃青椒；AI 明確拒絕。"
                "使用者稱讚 AI 閃招表現好，AI 短暫害羞後恢復嘴硬。"
            )

    import agent.llm.providers as providers

    original_get_provider = providers.get_provider
    fake_provider = FakeProvider()
    providers.get_provider = lambda config: fake_provider
    try:
        config = AgentConfig()
        config.memory_summary_threshold = 2
        config.max_history_turns = 10
        state = initial_state(config)
        state["memory_enabled"] = True

        # First batch
        state["user_input"] = "你不是最討厭青椒嗎？等一下遊戲打輸就吃青椒。"
        state["response"] = "不要，我拒絕。打輸可以懲罰別的，但青椒不行。"
        state = writeback(state, config)
        first_memory = state["long_term_memory"]
        assert_contains(first_memory, "青椒", "first summary should contain green pepper")

        # Second batch
        state["memory_enabled"] = True
        state["user_input"] = "剛才那一波閃招很帥耶。"
        state["response"] = "我才沒有因為被稱讚就害羞，哼，只是恢復嘴硬而已。"
        state = writeback(state, config)
        second_memory = state["long_term_memory"]
        assert_contains(second_memory, "青椒", "cumulative memory should still contain green pepper")
        assert_contains_any(
            second_memory,
            ("閃招", "害羞"),
            "cumulative memory should contain new content",
        )
    finally:
        providers.get_provider = original_get_provider


def main() -> None:
    tests = [
        test_clean_summary_output,
        test_validate_summary,
        test_build_structured_fallback,
        test_summarize_worker_rejects_mechanical_summary,
        test_summarize_worker_preserves_summary_without_extra_calls,
        test_writeback_persists_summary_and_uses_passed_config,
        test_writeback_accumulates_long_term_memory,
    ]

    for test in tests:
        test()
        print(f"OK {test.__name__}")

    print("\n=== ALL MEMORY QUALITY TESTS PASSED ===")


if __name__ == "__main__":
    main()
