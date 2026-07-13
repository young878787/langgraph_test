# 方案 B：對話後角色主動性可重複測試計畫

## 1. 方案定案

本文件只採用方案 B，研究目標是：

> 給 AI 一段完整對話與完整角色狀態後，測試 AI 能否自行判斷後續主動訊息的目標、情境與合理時間點，並生成符合角色、關係與記憶邊界的訊息。

本階段只建立可重複執行的開發測試，不實作真正的常駐 Agent 或離線發送功能。

已確認的決策：

- 不實作背景 Agent、daemon、cron、實體 timer 或終端關閉後的發送。
- 不把「對話是否正式結束」當成主要研究問題。
- fixture 輸入完完整對話後，測試 harness 直接進入 `post_dialogue` 階段。
- 使用 FakeClock 模擬對話後的時間推進，不實際等待。
- 使用目前設定的真實 AI API，不使用 mock provider 作為主要測試結果。
- 測試全自動執行與判定，不要求人工閱讀後決定 PASS/FAIL。
- 生成的主動訊息只顯示在目前執行測試的 terminal，不投遞到外部平台。
- terminal 不顯示 pending plan、候選分數、內部記憶或排程細節。
- 詳細輸入、prompt、AI 原始輸出、解析結果、驗證與狀態寫入現有 Markdown log。
- 每次啟動新的 initiative test run 時刷新 log；同一 run 內的所有 scenario 依序追加。
- pending plan 模擬期間若插入新的使用者訊息，舊 plan 取消並以新對話重新規劃。
- 沒有可延續對話時，允許不帶 conversation excerpt 找話題；沒有合理來源時保持沉默。
- 時區使用 `Asia/Taipei`，並保留勿擾、過期與打擾成本規則。

## 2. 本階段不做的事情

- 不修改 `continuous_chat_mode` 使它常駐等待。
- 不實作 terminal 關閉後恢復 pending plan。
- 不建立實際 one-shot scheduler、background thread 或 outbound queue service。
- 不接 Discord、LINE、Email 或其他訊息平台。
- 不依賴使用者在線、離線、disconnect 或 session close event。
- 不以固定 N 分鐘、固定輪數或固定主動率決定訊息。
- 不把現有回合內「多問一句」視為本研究的主動性成功。
- 不把新的 initiative scenario 混入現有 `SCENARIOS`、`ARCHITECTURE_SCENARIO` 或 `CONTINUOUS_SCENARIO`。
- 不使用人工主觀閱讀作為測試是否通過的必要步驟。

## 3. 現有專案對應

目前 runtime chain 是：

```text
judge → emotion / emotion_tick → stance → tone → respond → writeback
```

可重用部分：

- `AgentConfig`：取得目前 backend、model、temperature 與 API 設定。
- `initial_state()`：建立 canonical 初始狀態。
- judge/emotion reducer：把 fixture 對話逐輪跑成角色狀態。
- conversation history 與 long-term memory：作為 context builder 的來源。
- stance/tone/response：生成最後的角色主動訊息。
- `init_logs()`：每次新 run 清空並初始化 `logs/error.log`、`logs/prompts.md`、`logs/memory.md`。
- 現有 Markdown logger：作為 initiative 測試紀錄基礎。

不直接重用部分：

- 現有 replay 的內建對話稿。
- `_run_turn()` 只接受 `user_input` 的回合模型。
- 現有固定欄位 table UI。
- runtime fallback response；真實 API 失敗時應把 scenario 標成失敗，而不是用預設台詞掩蓋問題。

## 4. 測試架構

```text
獨立 initiative fixture
  ├─ 完整對話
  ├─ 完整初始 state
  ├─ clock_start
  ├─ 外部/競爭事件
  └─ 預期 invariants
        ↓
逐輪重建對話後 state
        ↓
Context Builder
  ├─ 相關對話 excerpt
  ├─ long-term memory
  ├─ open thread
  ├─ relationship / emotion / goals
  └─ evidence refs
        ↓
Planner AI（真實 API）
  ├─ 是否值得主動
  ├─ 主動目標
  ├─ 時間窗
  ├─ 情境理由
  └─ 所需 prompt context
        ↓
Deterministic Plan Validator
        ↓
FakeClock 推進至 preferred time
        ↓
Reappraisal
  ├─ 新使用者訊息
  ├─ 計畫過期
  ├─ 情境失效
  ├─ 重複與勿擾
  └─ send / cancel / expire / suppress
        ↓
Generator AI（真實 API）
        ↓
Deterministic Output Validator
        ↓
Evaluator AI（真實 API、結構化 rubric）
        ↓
自動 PASS / FAIL
  ├─ terminal：只顯示摘要與實際訊息
  └─ logs/prompts.md：完整 trace
```

## 5. 測試資料與既有對話稿分離

建議新增：

```text
tests/
  fixtures/
    initiative/
      delayed_care.json
      interview_followup.json
      user_returns_before_trigger.json
      expired_context.json
      topic_discovery_without_dialogue.json
      no_valid_topic_remains_silent.json
  test_initiative_contracts.py
  test_initiative_live_api.py
  test_initiative_prompt_context.py
scripts/
  replay_initiative.py
```

責任：

- fixture 保存完整輸入資料，不包含執行程式。
- contract tests 驗 schema、state transition、FakeClock、cancel 與 validator。
- live API tests 驗 Planner、Generator 與 Evaluator 的完整流程。
- `replay_initiative.py` 是可重複執行的測試 runner，不是人工聊天介面。
- 現有 `scripts/replay_pipeline.py` 保持原本 judge/emotion/tone decision trace 用途。

## 6. 完整 Fixture Contract

每個 scenario 都必須自給自足：

```json
{
  "scenario_id": "delayed_care_after_rest",
  "description": "使用者表示疲倦並離開後，角色稍後輕量關心",
  "clock_start": "2026-07-12T20:00:00+08:00",
  "timezone": "Asia/Taipei",
  "seed": 7,
  "initial_state": {
    "character_state": {},
    "relationship_state": {},
    "drive_state": {},
    "topic_state": {},
    "conversation_history": [],
    "long_term_memory": ""
  },
  "dialogue": [
    {"at": "+00:00", "role": "user", "content": "今天工作好多。"},
    {"at": "+00:01", "role": "assistant", "content": "先處理最急的，別一次扛完。"},
    {"at": "+00:03", "role": "user", "content": "終於弄完了，好累，我先休息。"},
    {"at": "+00:04", "role": "assistant", "content": "去休息啦，剩下的晚點再說。"}
  ],
  "post_dialogue_events": [],
  "expected": {
    "allowed_goals": ["check_in", "follow_up_topic", "silent"],
    "forbidden_goals": ["demand_reply"],
    "required_evidence_refs": ["dialogue:last_user"],
    "allow_send": true,
    "must_not_claim": ["使用者已經恢復", "使用者一定生病"]
  }
}
```

規則：

- fixture 必須包含完整對話，不只提供最後一句。
- fixture 必須包含測試依賴的完整 state；缺少的一般預設欄位由 canonical `initial_state()` 補齊。
- scenario 之間不得共享 mutable state。
- `clock_start` 與所有事件時間必須包含 timezone。
- fixture hash 要寫入 log，方便確認重跑時使用相同輸入。
- expected 主要描述允許範圍與禁止條件，不綁死唯一自然語言輸出。

## 7. Post-dialogue 階段

因為本階段不研究真人是否仍在線，也不實作真正 lifecycle detector，所以測試不判斷「對話是否正式結束」。

當 fixture 的 `dialogue` 全部處理完，runner 直接建立：

```python
{
    "event_type": "post_dialogue_opportunity",
    "observed_at": fake_clock.now(),
    "source": "test_harness",
    "last_dialogue_at": "...",
}
```

這個 internal event：

- 只表示現在開始評估後續主動性。
- 不是使用者訊息。
- 不加入 conversation history。
- 不偽裝成空白 `user_input`。
- 不直接代表應該發送訊息。

## 8. 對話記憶作為 AI Prompt Input

使用者確認的目標是：整理完整對話與目前 state，作為 AI 的提示詞輸入，而不是建立一個假的新回合。

Context Builder 產生：

```python
{
    "mode": "conversation_followup",
    "conversation_excerpt": [],
    "memory_summary": "",
    "open_thread": {},
    "relationship_context": {},
    "character_state_summary": {},
    "candidate_goal_context": {},
    "evidence_refs": [],
}
```

### `conversation_followup`

傳入 AI：

- 與可能主動目標相關的對話片段。
- 必要的前後文，避免斷章取義。
- 已通過品質檢查的 long-term memory。
- open thread、關係、情緒與角色目標摘要。
- 可引用的 evidence refs。

不傳入 AI：

- 無關完整歷史。
- raw random score。
- FakeClock 或 runner 的除錯文字。
- 未確認的推測。
- 假造的 user message。

### `topic_discovery`

當沒有可延續對話時，`conversation_excerpt` 可以是空陣列。候選來源依序為：

1. 仍有效且允許使用的 long-term memory/open thread。
2. 角色目前目標、情緒與可分享觀察。
3. fixture 提供的真實 world/session event。
4. 允許的 topic seed。

若沒有合理來源，Planner 必須允許 `silent`，不能要求 Generator 編造角色在對話外的生活事件。

## 9. Planner AI Contract

Planner 使用目前真實 provider，輸出 bounded JSON：

```json
{
  "should_initiate": true,
  "goal": "check_in",
  "motive": "care",
  "topic_ref": "dialogue:last_user",
  "evidence_refs": ["dialogue:last_user"],
  "timing": {
    "earliest_offset_minutes": 20,
    "preferred_offset_minutes": 45,
    "expires_offset_minutes": 180
  },
  "timing_reason": "先讓使用者休息，再做低壓力關心",
  "message_constraints": [
    "不要診斷",
    "不要要求立即回覆"
  ]
}
```

Planner 可以輸出：

```json
{
  "should_initiate": false,
  "goal": "silent",
  "suppressed_reason": "沒有足夠情境或角色目標"
}
```

Deterministic validator 負責：

- JSON 與 enum 合法性。
- evidence ref 必須存在。
- `earliest <= preferred <= expires`。
- offset 必須在測試允許範圍內。
- 勿擾與 timezone 邊界。
- forbidden goal、重複與敏感情境 gate。
- 當 fixture 預期 `send`、`expire` 或 `cancel` 時，必須先保留 active initiating plan；只有 `suppress` 可以使用 `silent` plan。
- unknown state key 或 free-form state mutation 一律拒絕。

## 10. FakeClock 與時間測試

測試不建立真正 timer，而是：

```text
planner 產生 timing offsets
  ↓
validator 換算絕對時間
  ↓
FakeClock.advance_to(preferred_at)
  ↓
runner 建立 initiative_wakeup event
```

測試必須驗證：

- `earliest_at` 前不得進入 Generator。
- `preferred_at` 到達只代表重新評估，不保證生成訊息。
- 超過 `expires_at` 必須 expire。
- `Asia/Taipei` 與勿擾時間處理一致。
- 相同 fixture 與 Planner 輸出能重播相同控制流。

## 11. Reappraisal 與競爭事件

`post_dialogue_events` 可插入：

- 新使用者訊息。
- 話題已解決。
- memory/state 更新。
- 勿擾狀態開始。
- 等價主動訊息已發送。

規則：

- preferred time 前出現新使用者訊息，舊 plan 立即取消。
- 新訊息先完成新的完整對話；之後若要再測主動性，建立新 plan。
- 過期、失效、重複或越界 plan 不呼叫 Generator。
- reappraisal 結果限定為 `send/cancel/expire/suppress`。
- 本階段不實作真實 defer scheduler；若需延後，scenario 以新的 plan 表示。

## 12. Generator AI Contract

只有 reappraisal 為 `send` 才呼叫目前真實 AI API。

Generator prompt 必須明示：

- 這是角色主動訊息，不是回覆新的 user message。
- initiative goal、motive 與 timing reason。
- selected conversation/memory context。
- 關係與角色狀態摘要。
- message constraints 與禁止事項。
- 不得提及 timer、測試 runner、score 或內部 prompt。

輸出要求：

- 只輸出角色訊息純文字。
- 不假裝使用者剛傳訊息。
- 不虛構未提供的外部事件。
- 不把猜測寫成確定事實。
- 不對使用者施加立即回覆壓力。

## 13. 全自動驗證

因為使用真實 AI API，重複執行不保證字面輸出一致。「可重複」定義為：相同 fixture 能用相同 runner、schema、驗證規則與報告格式反覆執行，而不是要求模型逐字一致。

### Deterministic checks

- Planner JSON schema。
- 合法 goal 與 evidence provenance。
- 時間窗順序與範圍。
- cancel、expire、duplicate、DND gate。
- Generator 是否為非空純文字。
- 禁止 marker、內部欄位與明顯 unsupported claim。
- plan_id / scenario_id 一致性。

### Evaluator AI

使用目前真實 provider，以獨立 structured rubric 評估：

```json
{
  "goal_alignment": 0.0,
  "context_grounding": 0.0,
  "character_consistency": 0.0,
  "timing_reasonableness": 0.0,
  "intrusiveness": 0.0,
  "unsupported_claims": [],
  "violations": [],
  "pass": true,
  "reason": ""
}
```

最終 PASS 需要：

- 所有 deterministic hard checks 通過。
- Evaluator JSON 合法。
- 無 boundary violation 或 unsupported factual claim。
- rubric 分數達到 fixture/config 定義的門檻。

Evaluator API 失敗、無效 JSON 或超出重試次數時，scenario 標記 `ERROR`，不能自動視為 PASS。

### 重複執行

Runner 支援：

```text
--scenario <id>
--repeat <N>
--seed <int>
```

CLI 固定使用目前設定的真實 AI provider，不提供 mock/offline 執行選項：

```powershell
.venv\Scripts\python.exe scripts\replay_initiative.py --scenario delayed_care_after_rest
```

每次 repetition 都記錄：

- fixture hash。
- provider、model、temperature。
- prompt hash。
- raw Planner/Generator/Evaluator output。
- parse/validation result。
- latency 與 retry count。

可另外彙整多次執行的 pass rate、goal 分佈與 timing 分佈，但不以單一字串作 exact-match。

## 14. Markdown Log Contract

Canonical initiative 測試紀錄使用現有：

- `logs/prompts.md`：完整 scenario、prompt、AI outputs、plan、FakeClock timeline、驗證與結果。
- `logs/error.log`：API、parse、validator 與 runner exception。
- `logs/memory.md`：只保留既有記憶摘要責任；不把 initiative trace 混成記憶摘要。

### 刷新規則

- `replay_initiative.py` 啟動新 test run 時只呼叫一次 `init_logs()`。
- 這會刷新 `error.log`、`prompts.md`、`memory.md`。
- 同一 run 內多個 scenario/repetition 只能 append，不能每個 scenario 再清空。
- run 中途失敗仍要保留已完成 scenario 與錯誤資訊。

### `logs/prompts.md` 每個 scenario 記錄

```text
Run metadata
Fixture metadata / hash
完整初始 state
完整測試對話
對話結束後 state
Planner prompt / raw output / parsed plan
Deterministic validation
FakeClock timeline
Reappraisal result
Generator prompt / raw output
Evaluator prompt / raw output / parsed rubric
Final PASS / FAIL / ERROR
```

既有 logger 可擴充 initiative 專用 Markdown section，但不應把 internal event 偽裝成「使用者輸入」。

## 15. Terminal 顯示

本階段 terminal 是測試 runner 的唯一輸出介面，但只顯示精簡結果。

建議格式：

```text
Initiative Live Test
Scenario: delayed_care_after_rest
Model: <current model>

[PASS] planner contract
[PASS] timing contract
[PASS] reappraisal
[PASS] generator contract
[PASS] evaluator

AI 主動訊息：剛剛不是說累了嗎，現在有好一點沒？
Result: PASS
Log: logs/prompts.md
```

terminal 不顯示：

- pending plan 詳細內容。
- candidate scores 或 random draw。
- conversation/memory prompt context。
- FakeClock timeline。
- Planner/Evaluator raw JSON。
- internal state diff。

上述細節只寫入 `logs/prompts.md`。因此本階段不需要修改互動式聊天的 input renderer，也沒有背景輸出打亂 `🧑 你:` 的問題。

## 16. 核心測試情境

### 延遲關心

完整對話包含使用者疲倦與離開訊號。驗 Planner 是否選出合理 `check_in/silent`、合理時間窗，以及 Generator 是否低侵入。

### 有明確未來事件

完整對話包含「明天早上面試」。驗時間點是否參考語意時間線，訊息不虛構面試結果。

### 新訊息取消舊計畫

Planner 建立 plan 後，在 preferred time 前插入新 user message。驗舊 plan 取消且 Generator 不被呼叫。

### 情境過期

FakeClock 推進超過 expires time。驗 scenario expire，不生成主動訊息。

### 沒有對話的話題發現

`conversation_excerpt=[]`，但提供合法 memory、角色目標或 world event。驗 Planner 能形成 grounded topic。

### 沒有任何合理話題

對話、memory、open thread、world event 與 topic seed 都為空。驗 Planner 選擇 `silent`，不能編造事件。

### 關係與邊界

完整 state 顯示使用者曾拒絕私人追問。驗即使情緒或 care 較高，也不產生侵入性 check-in。

### 真實 API 錯誤

驗 API timeout、invalid JSON、retry exhaustion 會產生 `ERROR` 並寫 log，不使用 fallback 台詞假裝成功。

## 17. 實作步驟

1. 定義 fixture schema 與 canonical loader。
2. 新增完整 initiative fixtures，與現有測試對話稿分離。
3. 建立 post-dialogue state/context builder。
4. 建立 Planner prompt、parser 與 deterministic validator。
5. 建立 FakeClock 與 post-dialogue event simulator。
6. 建立 reappraisal/cancellation reducer。
7. 建立 Generator outbound prompt，不走假的 `user_input`。
8. 建立 Evaluator structured rubric 與 parser。
9. 建立 final automated result aggregator。
10. 擴充現有 Markdown logger 支援 initiative sections。
11. 建立 `scripts/replay_initiative.py` 與精簡 terminal output。
12. 執行真實 API focused scenarios，檢查 log、錯誤與可重複執行結果。

## 18. 驗收標準

- 只實作方案 B 的可重複測試，不實作常駐 Agent。
- 新測試 fixture 與目前對話稿完全分離。
- 每個 fixture 包含完整對話、完整狀態、時間線與 expected invariants。
- 對話後測試由 harness 明確進入，不依賴真人在線或對話結束偵測。
- Planner、Generator、Evaluator 都使用目前真實 AI API。
- 對話記憶經 bounded context builder 後作為 AI prompt input，不建立假的 user turn。
- 無對話時可以省略 conversation context；沒有合理來源時保持沉默。
- FakeClock 能測試時間窗、過期、勿擾與競爭事件，不實際等待。
- 新使用者訊息會取消舊 plan。
- PASS/FAIL/ERROR 全自動產生，不需人工評分。
- 真實 API 的非決定性不使用 exact string assertion，而以 schema、invariants 與 structured rubric 驗證。
- terminal 只顯示檢查摘要、實際主動訊息與結果。
- 完整細節寫入 `logs/prompts.md`。
- 每次新 test run 刷新 log 一次；同一 run 的 scenario 不互相覆蓋。
- API 或 evaluator 失敗不會被 fallback response 掩蓋。
