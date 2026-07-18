from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.config import AgentConfig
from agent.llm.validators import (
    finalize_response,
    is_on_strategy,
    score_style_alignment,
    validate_response_invariants,
)


def main() -> None:
    config = AgentConfig()
    uncertain = {"action_stance": "authoritative_bluffing", "response_length": "medium"}
    assert validate_response_invariants(uncertain, "我不確定這個版本的細節，需要先查證。", config).valid
    assert is_on_strategy(uncertain, "我不知道，但可以先確認資料。", config)
    plain = {"action_stance": "tsundere_service", "response_length": "medium"}
    assert validate_response_invariants(plain, "這是完整且正確的答案，並沒有角色口頭禪。", config).valid
    assert score_style_alignment(plain, "這是完整且正確的答案。", config).score < 1.0
    fake_praise = {"fake_praise": True, "action_stance": "defensive_counter", "response_length": "medium"}
    assert validate_response_invariants(fake_praise, "你記錯對象了，前一輪並沒有那份成果。", config).valid
    contradiction = validate_response_invariants(fake_praise, "哼，我剛寫的當然好。", config)
    assert not contradiction.valid
    assert contradiction.reason == "acknowledges_unproduced_artifact"
    retries: list[str] = []

    def retry(instruction: str) -> str:
        retries.append(instruction)
        return "你記錯了，前一輪沒有產出那份作品。"

    finalized = finalize_response(fake_praise, "我剛寫的很好吧。", config, retry=retry)
    assert finalized.response.startswith("你記錯了")
    assert finalized.retry_count == 1
    assert finalized.rejection_reason == "acknowledges_unproduced_artifact"
    assert not finalized.fallback_reason
    assert retries and "do not claim" in retries[0]
    fallback = finalize_response(plain, "", config)
    assert fallback.fallback_reason == "empty_response"
    assert fallback.fallback_template_id
    assert fallback.validation.valid
    deadpan = finalize_response(
        {"action_stance": "deadpan", "response_length": "medium"}, "", config
    )
    assert deadpan.validation.valid
    assert deadpan.fallback_template_id == "safety.readable.1"
    print("response finalization focused tests: OK")


if __name__ == "__main__":
    main()
