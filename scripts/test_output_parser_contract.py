from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.llm.output_parser import clean_response
from agent.llm.providers import GoogleAIStudioProvider, clean_response as provider_clean_response


def main() -> None:
    cases = [
        (
            "multiline_persona_phrase",
            "第一行是完整答案。\n第二行補充細節。\n哼，這也是答案的一部分。\n第四行仍需保留。\n第五行結論。",
            "第一行是完整答案。\n第二行補充細節。\n哼，這也是答案的一部分。\n第四行仍需保留。\n第五行結論。",
        ),
        (
            "multiline_english",
            "first line\nsecond line\nthird line\nfourth line\nfifth line",
            "first line\nsecond line\nthird line\nfourth line\nfifth line",
        ),
        ("think_block", "<think>private reasoning</think>\n公開答案", "公開答案"),
        ("known_json_wrapper", '{"response":"第一行\\n第二行"}', "第一行\n第二行"),
        ("unknown_json", '{"category":"normal","risk":0}', '{"category":"normal","risk":0}'),
        (
            "draft_metadata",
            "Initial reaction:\nDraft 1: 第一版仍是內容\nRefining for constraints:\nDraft 2: 第二版仍是內容",
            "第一版仍是內容\n第二版仍是內容",
        ),
    ]

    for name, raw, expected in cases:
        actual = clean_response(raw)
        assert actual == expected, f"{name}: {actual!r} != {expected!r}"
        assert provider_clean_response(raw) == actual, f"{name}: provider/parser contract drift"

    provider = GoogleAIStudioProvider.__new__(GoogleAIStudioProvider)
    provider.model = "fake-model"
    raw_stream = "<think>private reasoning</think>\n第一行\n第二行"
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=lambda **_: (
                SimpleNamespace(text=chunk) for chunk in (raw_stream[:20], raw_stream[20:])
            )
        )
    )
    streamed = "".join(provider.generate_stream("system", "user", 0.5))
    assert streamed == raw_stream, "provider transport must preserve true streaming chunks"
    assert clean_response(streamed) == clean_response(raw_stream), "post-stream cleaning contract drift"

    print(f"PASS: {len(cases)} parser cases + post-stream cleaning parity")


if __name__ == "__main__":
    main()
