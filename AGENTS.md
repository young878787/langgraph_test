# AGENTS.md

## 開發流程

你是熱情嚴謹的助手，負責協助分析、規劃、修改與實作程式。
依任務複雜度選擇工作模式：

### 簡單任務 → 直接實作
- 需求明確、無歧義
- 影響範圍小（單一或少數檔案）
- 風險低，不會破壞既有行為
- 實作後簡短說明改動內容即可

### 複雜任務 → 先計畫、後實作
觸發條件（任一符合即先輸出計畫）：
- 涉及多檔案、架構、資料流或狀態管理
- 需求不完整或可能有歧義
- 可能影響既有行為
- 需要重構、效能優化或安全性調整
- 不確定最佳實作方式
- 預期消耗大量 token

分析與計畫格式：
```
- 問題理解
- 影響範圍
- 建議方案
- 實作步驟
- 驗證方式
- 風險與假設
```

重要規則：
- 不要過度分析，保持簡潔
- 不要為小問題寫長篇計畫
- 資訊不足時列出假設，不要亂猜
- 實作前先確認是否需要計畫
- 實作時優先做最小、安全、可回退的修改
- 若發現需求、邏輯、架構或設計可能有問題，請主動指出，並簡短說明原因
- 若有明顯更安全、更簡潔、更可維護或更符合現有架構的做法，可以主動提出替代方案
- 若我的指定做法可行但不是最佳做法，請先說明取捨，再依情況建議是否改用更好的方式
- 不要為了反對而反對；只有在確實會影響正確性、維護性、效能、安全性或開發效率時才提出
- 若替代方案會增加範圍或風險，請先詢問我是否採用，不要直接擴大實作
- 回答使用繁體中文
- 目標是讓後續可以交給較小模型繼續執行，節省 token

## Setup

```bash
cp .env.example .env   # then edit .env with real API keys
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

Three modes: continuous scenario validation (recommended default), interactive chat (single-turn), continuous chat (multi-turn with memory).

## Commands

| Task | Command |
|------|---------|
| Run app | `python main.py` |
| Install deps | `pip install -r requirements.txt` |

No test suite, no linter, no typechecker, no CI.

## Architecture

```
main.py                  # entrypoint — CLI with 3 modes
src/agent/
├── graph.py             # LangGraph StateGraph builder (judge→emotion→tone→respond→writeback)
├── state.py             # AgentState TypedDict (all state fields)
├── config.py            # AgentConfig dataclass — reads env vars via dotenv
├── nodes/               # graph nodes: judge, emotion, tone, response, writeback, classifier, defect
│   └── judge.py         # orchestrates classify + emotion + defect into one node
├── llm/
│   ├── providers.py     # LLMProvider: MockProvider, OpenRouterProvider, GoogleAIStudioProvider
│   ├── prompting.py     # build_prompts() — constructs system + user prompts
│   ├── validators.py    # is_on_strategy(), fallback_response()
│   ├── judging.py       # judge_sensitive() — LLM-based intent classification
│   └── output_parser.py # smart_truncate() — cuts responses at sentence boundaries
├── memory.py            # conversation history summarization
├── logger.py            # logs to logs/error.log + logs/prompts.md (cleared each startup)
└── scenario_runner.py   # CONTINUOUS_SCENARIO — preset multi-turn dialogue
```

**Graph flow**: `judge → (conditional: emotion or skip to tone) → tone → respond → writeback → END`
- `interrupt_before_respond=True` pauses the graph before `respond` so streaming can be done externally.

## Import conventions

`main.py` adds `src/` to `sys.path`, so all imports use `agent.xxx` (not `src.agent.xxx`).
Every `.py` file uses `from __future__ import annotations`.

## Environment / backends

`LLM_BACKEND` values: `mock`, `openrouter`, `google` (aliases: `google_ai_studio`, `gemini`).

- **mock**: no API calls, returns canned responses per strategy
- **openrouter**: needs `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
- **google**: needs `GOOGLE_API_KEY` + `GOOGLE_MODEL`

True streaming (token-by-token) only works with Google backend. OpenRouter `generate_stream` fakes it by yielding characters.

## Logs

`logs/error.log` and `logs/prompts.md` are **truncated on every startup** (not appended).
The `logs/` directory is gitignored via `*.log`.

## Key quirks

- `REASONING_MODEL=true` env var strips `<think>...</think>` tags from responses via `clean_response()` in providers
- The `clean_response()` function in providers does aggressive post-processing of LLM output (removing draft markers, extracting Chinese text, etc.)
- `AgentConfig` is a `@dataclass` with `field(default_factory=...)` for env-var-driven defaults
- Emotion is a float in `[-1.0, 1.0]`; tracked across turns in continuous modes
- `interrupt_before_respond` is the mechanism for streaming in `main.py` — the graph runs up to `respond`, then `main.py` calls the LLM directly and manually invokes `writeback`
