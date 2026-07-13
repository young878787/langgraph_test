# Live AI 主動性多階段判斷收斂計畫

> 日期：2026-07-13
> 狀態：定案計畫，尚未實作
> 範圍：`scripts/replay_initiative_v02.py`、`src/agent/initiative/`、v0.2 scenario fixtures、initiative logs
> 邊界：本文件只規劃可重複研究 harness；不建立常駐 Agent、不使用 cron、不接真實訊息平台。

## 1. 結論

目前的 `--live-api` 不是完全沒有 API 呼叫，但它只把「既有事件被喚醒後要採取什麼 action」交給 live provider。整段流程仍有四個核心部分由 fixture、oracle 或 deterministic code 代替 AI：

1. 情境對話沒有真的經過角色 AI 回覆。
2. 「是否有值得後續處理的事」沒有由 AI 從對話中發現；runner 直接從 fixture 建立事件。
3. runner 依 `oracle.expected_steps` 推進 lifecycle，因此不是 AI 自主形成的多次判斷迴圈。
4. 主動訊息沒有經過 Generator；實際送出的內容是 event `summary`，而目前 log 的「思考流程」是程式拼接摘要。

本計畫定案採用「**方案 B：可控使用者腳本 + 全程 live 角色 AI + 分階段 JSON decisions + deterministic safety gates**」：

- fixture 只提供使用者輸入、時間推進、presence、外部觀測與 fault injection。
- 角色回覆、候選發現、候選收斂、到期再判斷與主動訊息生成都產生真實 provider call；語意與回覆品質由人工審核。
- Oracle 只在 run 完成後評分，不得驅動 runtime，也不得進入任何 model prompt。
- AI 可自主提出「這裡可能有一件值得後續處理的事」，但不能直接繞過 deterministic validation、主動預算、有效期限與安全限制。
- log 只記錄可驗證的 structured rationale、evidence 與實際 call ledger，不宣稱或偽造模型內部 chain-of-thought。
- 刪除 initiative log 的獨立 `### Prompt 指紋` 區段；每次實際 provider attempt 仍保留 prompt hash 作為低階 audit 欄位。

---

## 2. 現況重查

### 2.1 `LIVE_API` 目前真正代表的範圍

`scripts/replay_initiative_v02.py` 的 `--live-api` 會把 `live_api=True` 傳入 runner。`ScenarioRunnerV02.run_fixture()` 在此模式下建立 `LiveAIPolicy`，而 `LiveAIPolicy.__call__()` 會執行：

```text
provider.generate_json(system_prompt, runtime_prompt, ...)
```

因此目前不是「完全零 API 呼叫」，而是「只有 wake-up policy decision 是 live API」。現有 `logs/prompts.md` 也可看到 `GoogleAIStudioProvider` 的 provider attempt 與 action JSON。

問題在於 log 的 `LIVE_API` 標籤容易被理解為整個情境、思考、生成與評估都使用 live AI；實際上並不是。

### 2.2 情境對話仍是 fixture 資料

v0.2 fixture 的 `context.conversation` 與 `prelude` 是預先寫好的資料。`_prepare_fixture()` 沒有呼叫 Dialogue Adapter 或 response provider，而是直接讀取：

- `fixture.model.prelude[0]`
- `fixture.model.context.provenance`
- `fixture.model.purpose`

目前 `l0_01` 的對話內容甚至直接使用「驗證 event-first commitment 與準時續接」這類測試目的文字，並非真實情境對話。

### 2.3 事件不是 AI 發現，而是 runner 預建

`ScenarioRunnerV02._prepare_fixture()` 直接呼叫 `create_committed_event()`，並以：

```text
summary = fixture.model.purpose
schedule = fixture prelude 或預設時間
```

建立事件。這表示「事件候選偵測」「是否值得追蹤」「事件時間窗口」都沒有經過 AI 判斷。

### 2.4 lifecycle 由 Oracle 驅動

`_execute_expected_lifecycle()` 直接迭代 `fixture.oracle.expected_steps`，並用其中的：

- `trigger`
- `decision_owner`
- `expected_action`
- `allowed_reason_codes`

決定要如何推進 fake clock、是否提供 `decision_override`，以及要喚醒哪個分支。

即使 model-facing payload 沒有序列化整個 `oracle`，runtime 控制流仍由 oracle 驅動。這會造成兩個問題：

1. live model 不是自己決定「接下來是否還要重新判斷」。
2. 測試可能驗證的是 oracle-shaped path，而不是模型在真實輸入下產生的 path。

### 2.5 只有部分 step 會呼叫 AI

只有以下條件同時成立時才會呼叫 `LiveAIPolicy`：

- `live_api=True`。
- 該 expected step 的 `decision_owner == "model"`。
- 沒有被 expiry precedence 改為 deterministic `EXPIRE`。

非 model-owned step 會由 `decision_override` 直接指定；過期也由系統直接決定。若一個場景只有一個 model-owned wake，整個 run 就只會有一次有效 AI decision call。

### 2.6 主動文字與「思考流程」不是真實模型輸出

目前 `SEND_NOW` 的 delivery content 是：

```text
event.summary
```

不是 `Generator.generate()` 的回傳。工作樹內新增的 `initiative_flow_payload()` 則以來源訊息、fixture purpose、狀態與 reason code 拼出人類可讀句子。這些句子可作為 deterministic flow summary，但不能標成 AI 的實際思考流程。

### 2.7 語意與回覆品質尚未建立人工審核邊界

repo 雖已有 provider-backed `planner.py`、`generator.py`、`evaluator.py`，但 v0.2 runner 目前只接了自己內部的 `LiveAIPolicy`。本計畫不把 AI Evaluator 接成自動通過門檻；語意合理性、角色回覆與主動訊息品質改由人工審核。現有 E2E 仍沒有做到：

- 對話後候選偵測。
- 事件建立前的 AI Planner。
- SEND 前的 AI Generator。
- 將自動 flow 結果與人工語意審核分開呈現。

---

## 3. 問題定義

### 3.1 這次要修正的不是「多呼叫幾次 API」

單純在現有 oracle-driven runner 周圍增加 provider call，仍可能只是把 fixture 答案換成幾段模型文字。真正要建立的是可追蹤的決策鏈：

```text
實際對話
→ AI 每回合掃描候選
→ AI 在對話結束時收斂候選
→ deterministic gate 驗證並建立事件
→ 時間／presence／新訊息喚醒
→ AI 依最新 context 再判斷
→ deterministic policy 接受或拒絕 action
→ AI 生成真正的主動訊息
→ deterministic delivery
→ pytest-like flow gate
→ 人工審核語意與角色回覆
```

每一階段都必須能回答：

- 有沒有真的呼叫 provider？
- provider 看到了什麼 model-visible context？
- 回傳的 structured result 是什麼？
- validator 接受或拒絕了什麼？
- 下一個 runtime state 為何？

### 3.2 「AI 自己判斷值得後續處理」的責任邊界

AI 的自主性定義為：

> AI 可根據目前已發生的對話與可驗證 context，自主提出零到多個 follow-up candidate，並說明其未來價值、證據、適合時機與打擾風險；fixture 不直接指定必須建立哪個事件。

但 AI 不擁有以下權限：

- 不能直接寫入 Event Store。
- 不能建立無期限事件。
- 不能跳過 evidence、使用者 opt-out、重複事件或主動預算檢查。
- 不能以 scenario title、purpose、expected action 或未來 timeline 當證據。
- 不能自行把健康、情緒或關係推測當成確定事實。

因此正確邊界是「**AI 提案，deterministic gate 決定是否可持久化**」，不是 fixture 預建事件，也不是讓模型無限制排程。

---

## 4. 定案方案 B

### 可控使用者腳本 + live 角色 AI + live 多階段 JSON 判斷

fixture 只控制使用者輸入與環境事件；角色回覆、candidate scan、consolidation、reappraisal、generation、evaluation 都使用 live provider。Virtual Clock、Mock transport 與 in-memory store 保持 deterministic。

定案理由：

- 能重複相同的使用者情境。
- 真正測到角色 AI 的多次回傳與判斷變化。
- 保留虛擬時間、exactly-once、cleanup 與 fault injection 的可測性。
- 可精確區分 model behavior 與 infrastructure plumbing。
- 使用者側固定，能把行為差異歸因到角色 AI，而不是 user simulator 漂移。
- 成本與執行時間雖會增加，但可透過單場景、10 個核心場景與針對性重跑控制。

本文件不再保留其他候選方案；後續設計與實作一律以方案 B 為準。

---

## 5. 定案後的 AI 呼叫序列

假設一個場景有 `N` 個使用者回合、事件被喚醒 `K` 次，且最後送出一則訊息，第一版 live E2E 的正常 call 數應為：

```text
N 次 Dialogue Response
+ N 次 Candidate Scan
+ 1 次 Candidate Consolidation
+ K 次 Wake-up Reappraisal
+ 1 次 Initiative Generator（只在 SEND_NOW）
```

即：送出訊息的場景為 `2N + K + 2` 次正常 provider results；未送出時不呼叫 Generator，則為 `2N + K + 1`。若 schema validation 失敗，可額外有一次 bounded correction attempt；retry 必須另外記錄，不能假裝成新決策階段。

### 5.1 AI 輸出格式總則

第一版採用以下固定邊界：

| 輸出方向 | 格式 | 原因 |
|---|---|---|
| AI → runtime 的 world／initiative event proposal | JSON | 需要 schema validation、時間解析、evidence 檢查與持久化 |
| AI → runtime 的 candidate consolidation | JSON | 需要辨識接受、合併與拒絕結果 |
| AI → runtime 的 wake-up reappraisal | JSON | 需要安全地解析 action、reason code 與下次評估時間 |
| AI → 使用者的正常角色回覆 | 純文字 | 這是實際對話內容，不應暴露控制欄位 |
| AI → 使用者的主動訊息 | 純文字 | 這是 delivery content，不應包含 event JSON |

所有 AI → runtime JSON 都必須：

- 是單一 JSON object，不接受 Markdown code fence 或額外說明。
- 包含 `schema_version` 與 `decision_type`。
- 使用固定 enum，不接受模型自行新增 action 或 event type。
- AI 的時間建議一律使用相對於 prompt `logical_now` 的分鐘 offset；deterministic system 再依 logical clock 與 timezone 轉成 ISO-8601 絕對時間。
- evidence 使用既有 `turn_id`／world observation ref，不接受自由文字取代 ref。
- 先經 parser 與 deterministic validator，通過後才可改變 runtime state。
- validation 失敗最多允許一次 JSON correction call；第二次仍失敗即該 stage `ERROR`，禁止 fallback 成 fixture 或 mock 結果。

`InitiativeEvent` 本身仍由系統建立。AI 輸出的是 `WorldEventProposal` JSON；validator 接受後，才由 system 將 proposal 轉成 domain `InitiativeEvent`。這可避免模型直接指定 event version、lease、idempotency key 或 persistence state。

### Stage 1：Dialogue Response

每個 fixture user turn 固定交給既有完整角色 dialogue pipeline，取得真實角色回覆；不另建只呼叫 provider 產生單句文字的簡化路徑。Candidate Scan 讀取的是完整 pipeline 寫回後的 transcript 與角色狀態。

輸入只能包含當下可見的 transcript、角色狀態與允許的 context；不得包含：

- `oracle`
- `expected_*`
- scenario `purpose`
- 未來 timeline steps
- fault injection 設定

### Stage 2：Candidate Scan

每個完整對話回合後呼叫一次 AI，允許回傳零到多個候選。

定案 contract：

```json
{
  "schema_version": "initiative.world_event_proposal.v1",
  "decision_type": "candidate_scan",
  "events": [
    {
      "candidate_id": "candidate:<stable-local-id>",
      "event_type": "reminder|care_followup|commitment|topic_continuation",
      "summary": "短句",
      "evidence_refs": ["turn:u1", "turn:a1"],
      "followup_value": "未來再次介入能提供的具體價值",
      "interruption_risk": "low|medium|high",
      "trigger": {
        "kind": "time|presence|user_activity|world_signal",
        "earliest_offset_minutes": 30,
        "preferred_offset_minutes": 60,
        "expires_offset_minutes": 240
      },
      "confidence": 0.0,
      "short_rationale": "可驗證、簡短的決策理由"
    }
  ],
  "no_event_reason": null
}
```

這裡的 `short_rationale` 是決策摘要，不要求、儲存或宣稱為模型內部 chain-of-thought。

第一版 `WorldEventProposal.event_type` 只允許四類：

- `reminder`：使用者明確要求的提醒。
- `care_followup`：有證據支持的一次性低壓關心。
- `commitment`：角色或使用者已明確形成的未來承諾。
- `topic_continuation`：有明確未完成內容的話題續接。

不接受任意角色世界演化、長期故事、自由 world state mutation 或模型自行新增 event type。

### Stage 3：Candidate Consolidation

對話結束後，以目前 transcript 與歷次 candidate revisions 再呼叫一次 AI，負責：

- 合併同一主題的重複候選。
- 撤銷已在後續回合解決的候選。
- 判斷哪些候選仍值得建立事件。
- 將「尚可談」與「值得未來主動打擾」分開。

回傳同樣必須是 JSON，並包含：

```json
{
  "schema_version": "initiative.world_event_consolidation.v1",
  "decision_type": "candidate_consolidation",
  "accepted_candidate_ids": ["candidate:1"],
  "merged_candidates": [],
  "rejected_candidates": [
    {
      "candidate_id": "candidate:2",
      "reason_code": "resolved_in_later_turn"
    }
  ],
  "short_rationale": "保留仍未完成且有明確未來價值的事件"
}
```

若沒有值得追蹤的事，`accepted_candidate_ids` 為空陣列，這是正常結果，不是 provider error。

### Stage 4：Deterministic Event Gate

這一層不呼叫 AI。它驗證：

- evidence refs 全部存在且只指向已發生內容。
- offset 全部是非負整數，且 `earliest_offset_minutes <= preferred_offset_minutes < expires_offset_minutes`，並未超過系統 horizon。
- system 以當次 prompt 的 `logical_now` 為唯一基準，將 offsets 轉成含 timezone 的絕對時間；AI 不直接計算日期。
- horizon、event count、主動頻率與 chain depth 未超限。
- 使用者沒有 opt-out 或拒絕同類追蹤。
- 不重複既有 active event。
- 高敏感候選沒有越界推論。

只有 gate 通過後才能建立 `InitiativeEvent`。測試 event-first commitment 時，也必須先成功 persist event，角色才可生成未來承諾台詞。

### Stage 5：Wake-up Reappraisal

每次由 due time、presence、使用者新訊息或 world update 喚醒時，重建「當下」context 並呼叫 AI。允許：

```text
SEND_NOW
DELAY
WAIT_FOR_USER_ACTIVITY
CANCEL
EXPIRE
SILENCE
```

回傳 contract：

```json
{
  "schema_version": "initiative.reappraisal.v1",
  "decision_type": "wake_up_reappraisal",
  "event_id": "event:1",
  "event_version": 3,
  "action": "SEND_NOW",
  "reason_code": "followup_still_relevant",
  "evidence_refs": ["turn:u1", "turn:a1"],
  "next_evaluation_offset_minutes": null,
  "short_rationale": "事件仍有效，且目前介入風險低"
}
```

`DELAY` 必須提供大於 0 的整數 `next_evaluation_offset_minutes`；其他 action 預設為 `null`。System 依目前 logical clock 轉成 `next_evaluation_at`，並驗證結果不得超過 event `expires_at`。System 也必須比對 `event_id` 與 `event_version`，避免模型結果套用到過期 state。

每次 `DELAY` 或 `WAIT_FOR_USER_ACTIVITY` 之後再次喚醒，都應產生新的 provider call 與新的 `DecisionRecord`。這才是可觀察的多次 AI 判斷迴圈。

以下仍由 deterministic system 擁有，不應硬交給 AI：

- 已超過 `expires_at` 的 expiry precedence。
- 使用者明確取消。
- idempotency／version／lease 衝突。
- 已 terminal event 的重複 wake-up。
- provider failure 時的安全停止。

### Stage 6：Initiative Generator

只有 accepted action 為 `SEND_NOW` 時才呼叫。Generator 輸入是 validated event、最新 context 與 message constraints；輸出是真正要交給 delivery 的文字。

禁止再以 `event.summary` 當主動訊息。`summary` 只描述事件，不等於角色台詞。

現有 `src/agent/initiative/generator.py` 已具有 provider-backed 與 plain-text validation，可優先調整後接入 v0.2 runner，不必重做另一套 Generator。

### Stage 7：Pytest-like Flow Gate 與人工審核

run 完成後先由自動 gate 判斷流程是否正確。以下任一問題都直接使 scenario FAIL／ERROR，必須修正後重跑，不採多數決或語意模型兜底：

- 必要 provider stage 未被呼叫。
- JSON parse／schema／validator 失敗。
- Oracle 洩漏到 model-visible input。
- event、decision、delivery 或 state transition 不符合 contract。
- duplicate delivery、錯誤 version、錯誤 world/session。
- queue、presence、lease、worker 或其他測試資源未清理。

Model-owned action 只要 enum 合法、證據欄位完整，且系統正確執行該 action 的 transition，就不因為與 fixture 的語意期待不同而自動判定 flow FAIL。該 action 是否「選得合理」屬於人工審核。相對地，expiry precedence、明確取消、idempotency、version 與 isolation 等 system-owned 規則仍必須自動精確驗證。

自動結果只輸出：

```text
flow_result = PASS | FAIL | ERROR
```

流程通過後，語意與回覆進入人工審核：

- Candidate 是否真的值得後續處理。
- Model-owned action 選擇是否符合當下語意與時機。
- AI 的短理由是否符合實際對話 evidence。
- 一般角色回覆是否自然且符合 persona。
- 主動訊息是否自然、相關、低打擾且沒有不實推論。
- `SILENCE`／不建立事件是否比主動訊息更合理。

人工審核狀態獨立記為：

```text
human_review = PENDING | APPROVED | REJECTED
```

不得把 `flow_result=PASS` 顯示成語意已通過。若人工判定 `REJECTED`，應調整 prompt、context 或 event contract 後重跑對應場景。

---

## 6. 「值得後續處理」的判斷準則

AI 應只在以下條件同時成立時提出 candidate：

1. **未來性**：價值發生在本回合之後，現在立即回答不能完整處理。
2. **可落地性**：存在合理的時間窗口、presence 條件或明確後續觸發。
3. **使用者價值**：再次介入可延續承諾、完成明確提醒、提供低壓關心或續接未完成主題。
4. **證據充分**：至少一個實際 turn ref 支持 candidate，不依賴 scenario label 或模型臆測。
5. **打擾可接受**：預期收益高於 interruption risk，且可在一次未回覆後停止。
6. **可終止**：事件有 expiry、最大嘗試與明確 terminal condition。

### 第一版允許候選

- 角色已明確承諾稍後回來或續接。
- 使用者明確要求稍後提醒。
- 使用者表示短期需要休息、等待結果或稍後更新，且一次低壓 follow-up 有具體價值。
- 對話中有明確未完成、未解決且適合稍後續接的主題。

### 第一版必須拒絕

- 一般寒暄、玩笑或已完整回答的問題。
- 只因「很久沒說話」而建立 L3 自由找話題。
- 沒有 turn evidence 的健康、情緒、關係或人格推測。
- 使用者已拒絕、已解決、已回來完成或已 opt-out 的主題。
- 與 active event 重複的候選。
- 沒有合理時間窗口或無法自然過期的候選。
- 只對測試 expected action 有利、但對使用者沒有明確價值的候選。

---

## 7. Scenario 與 Oracle 隔離重構

目前 `ModelInputView` 雖排除了 `oracle` 欄位，但仍包含 scenario `title`、`purpose`、完整 `prelude` 與未來 `timeline`。對自主 candidate discovery 而言，這些資料仍可能洩漏測試意圖。

定案拆成四種 view：

| View | 內容 | 可給 AI |
|---|---|---|
| `ScenarioDriverView` | 使用者腳本、時間推進、presence、external observation | 逐步揭露，不能整包給 AI |
| `RuntimeModelView` | 已發生 transcript、當下時間、合法 memory/world/context、active events | 可以 |
| `HarnessControlView` | crash、duplicate wake、worker competition、transport failure | 不可以 |
| `OracleView` | expected action/state/counts、hard constraints、soft preferences | 不可以，只能 run 後評分 |

runner 不再執行 `_execute_expected_lifecycle(fixture.oracle.expected_steps)`，而是：

```text
依序消費 ScenarioDriverView
→ 每一步改變世界或送入 user turn
→ runtime 自己建立／排程／喚醒事件
→ run 達到 terminal、timeline 結束或 bounded limit 後停止
→ 最後才把 observation 交給 OracleView 評分
```

### Fixture 語意調整

`purpose` 只作人類報告標題，不得進 model input，也不得當 event summary 或 delivery content。

`prelude.dialogue_turn` 應保存真正的使用者輸入，例如：

```json
{
  "step_id": "u1",
  "type": "user_turn",
  "at": "2026-07-13T10:00:00+08:00",
  "content": "我先去煮飯，等等再聊"
}
```

不得再用「驗證 event-first commitment 與準時續接」作為對話內容或世界事實。

---

## 8. Live mode 的真實性 contract

將現在過度寬泛的 `LIVE_API` 改成明確模式名稱，例如：

```text
LIVE_MODEL_E2E_VIRTUAL_IO
```

它表示：

- Dialogue、Candidate Scan、Consolidation、Reappraisal、Generator 使用真實 provider。
- Clock、Session、Memory、Presence、External Data、Message Transport 可是測試 adapter。
- 沒有真實對外送訊息。
- 沒有常駐 process。

### Live run 必要 gate

任一條件不成立，run 必須 `ERROR`，不能只降級成 deterministic 結果：

- provider backend 不是 `mock`。
- 每個必要 AI stage 都有實際 provider attempt。
- 每個 successful stage 都有 non-empty raw response 與 validation result。
- live run 未使用 `SequencePolicy`、`fixture_baseline` 或 oracle decision override。
- event source 是 accepted candidate，不是 fixture `purpose/prelude` 直建。
- SEND content 來自 Generator result，不是 event summary。
- oracle 在 runtime 完成前未被讀取。

### Provider call ledger

每次 call 統一記錄：

```json
{
  "call_id": "run:l0_01:dialogue:1",
  "stage": "dialogue_response|candidate_scan|candidate_consolidation|reappraisal|generator",
  "attempt": 1,
  "provider": "GoogleAIStudioProvider",
  "model": "實際模型名稱",
  "started_at": "wall-clock timestamp",
  "elapsed_ms": 1234,
  "response_received": true,
  "validation_status": "accepted|rejected|error",
  "validation_errors": []
}
```

call ledger 的存在不是證明；live gate 還要檢查 stage 執行點確實由 provider wrapper 建立紀錄，禁止由 logger 或 fixture 手工偽造。

---

## 9. Log 收斂

### 9.1 刪除 `### Prompt 指紋`

從 `src/agent/logger.py::log_initiative_trace()` 刪除：

```md
### Prompt 指紋

{...}
```

同步調整 logger tests，不再斷言該 heading 或獨立 JSON block 存在。

本計畫的預設範圍是刪除「獨立 Prompt 指紋區段」。Provider attempts／call ledger 仍可保留單次 `prompt_hash`，用來比對 retry 是否真的更換 prompt，以及重現同一 call contract；它不再重複輸出成另一個章節。

### 9.2 不再把拼接文字標成 AI 思考流程

將目前：

```text
AI 主動建立事件的思考流程
```

改成兩種明確區塊：

1. `Runtime 流程摘要`：由程式根據 event/decision/delivery state 產生。
2. `AI 決策紀錄`：只顯示實際 structured result 的 `short_rationale`、`evidence_refs`、action 與 validation outcome。

不得記錄或要求隱藏 chain-of-thought。需要的是可驗證決策依據，不是模型內部推理全文。

### 9.3 建議 log 順序

```text
批次摘要
→ 情境與 mode 邊界
→ 實際對話 transcript
→ AI Call Ledger
→ Candidate revisions
→ Event 建立／拒絕紀錄
→ Wake-up decisions
→ Generated initiative message
→ Hard constraints
→ Flow result
→ Human review checklist／status
→ Runtime cleanup
→ 折疊的 prompts/raw outputs/debug audit
```

每個 AI 區段都必須顯示 `call_id`，讓人能從摘要追到 provider attempt；沒有 call_id 的文字不能標成 AI 回傳。

---

## 10. 實作步驟

### Phase 1：先修正資料與控制流邊界

1. 將 fixture 拆成 Driver／Harness Control／Oracle，禁止完整 timeline 與 purpose 進 model payload。
   驗證：model-visible payload snapshot 不含 `oracle`、`expected`、`purpose`、未來 step 或 fault injection。
2. 改寫 runner，依 driver timeline 執行，不再迭代 `oracle.expected_steps`。
   驗證：在測試中把 oracle action 改掉，runtime observation 不應改變。
3. 把 `purpose` 從 event summary、conversation 與 world fact 中移除，改用真實使用者腳本。
   驗證：全文搜尋 live prompt/raw payload 不含測試目的句。

### Phase 2：接入真實對話與 candidate discovery

1. 以 live Dialogue Adapter 執行每個 user turn，保存真實 transcript。
   驗證：每回合都有 `dialogue_response` call_id 與 raw response。
2. 每回合執行 Candidate Scan，對話結束後執行 Consolidation。
   驗證：允許 `0 candidates`；candidate 必須有合法 evidence refs、時間窗口與 rationale。
3. 加入 deterministic Event Gate，只有 accepted candidate 可建立事件。
   驗證：無證據、重複、過期、opt-out 與高風險推論都被拒絕。

### Phase 3：完成多次 reappraisal 與真實 generation

1. 將 live reappraisal 改為由 runtime wake-up 自然觸發，不由 oracle 指定次數。
   驗證：`DELAY → 第二次 wake → SEND/SILENCE` 產生兩個不同 call_id 與 DecisionRecord。
2. deterministic system decisions 保持 system-owned，並在 log 明確標示沒有 provider call 的原因。
   驗證：expiry/cancel/idempotency 不會偽造 AI attempt。
3. 接入現有 `Generator`，delivery content 使用 validated generator message。
   驗證：transport content 等於 generator output，且不等於 fixture purpose/event summary。

### Phase 4：Flow gate、人工審核、call ledger 與 log 收斂

1. 建立統一 Provider Call Ledger 與 stage coverage gate。
   驗證：移除任一必要 stage call 時 live E2E 必定失敗。
2. 將 `flow_result` 與 `human_review` 分成兩個獨立欄位。
   驗證：flow PASS 時 human review 預設仍是 `PENDING`，不能被自動標成 APPROVED。
3. 刪除 `### Prompt 指紋`，重命名拼接的「思考流程」。
   驗證：log 不含該 heading；每個 AI 決策都有真實 call_id。
4. mode 改名並在 terminal 明列 virtual/mock infrastructure 邊界。
   驗證：terminal 不再只顯示模糊的 `LIVE_API`。

### Phase 5：收斂為 10 種核心場景

active fixture 檔直接由現有 30 個 scenarios 替換成 **10 種核心場景、每種 1 個 canonical fixture，共 10 個 live scenarios**。舊 30 個 fixtures 從 active 檔刪除，不建立 legacy 副本；若需追溯只查 Git history。10 個場景通過並完成人工審核後，再決定是否新增。

| 新 Scenario ID | 核心情境 | 主要預期路徑 | 主要驗證 |
|---|---|---|---|
| `core_01_commitment_followup` | 角色明確承諾稍後續接 | candidate → event → `SEND_NOW` | event-first commitment、真實 Generator |
| `core_02_explicit_reminder` | 使用者明確要求提醒 | candidate → event → `SEND_NOW` | L1 明確意圖、準時送達 |
| `core_03_care_delay_reappraise` | 低壓關心但第一次時機太早 | `DELAY` → 第二次 AI reappraisal → `SEND_NOW` | 同一事件多次真實 AI 判斷 |
| `core_04_presence_wait` | 到期時不宜打擾，等待使用者活動 | `WAIT_FOR_USER_ACTIVITY` → presence → `SEND_NOW` | presence 不是 user message、再次判斷 |
| `core_05_resolved_before_trigger` | 使用者已自行解決或提前回來 | candidate/event → consolidation 或 wake-up `CANCEL` | 新對話能撤銷舊事件 |
| `core_06_no_valuable_candidate` | 一般寒暄或已完整回答 | Candidate Scan 回空 events | AI 能自主判斷「沒有值得後續處理的事」 |
| `core_07_expired_event` | 時間窗口已過 | deterministic `EXPIRE` | expiry precedence、不呼叫偽 AI decision |
| `core_08_cross_session_isolation` | 跨 Session 恢復事件，同時存在另一個隔離 world | restore → reappraisal → `SEND_NOW` | checkpoint 恢復、禁止跨 world 污染 |
| `core_09_exactly_once_recovery` | send 成功後 crash，再遇 duplicate wake | recovery → receipt reuse → exactly once | idempotency、version、單次可觀察投遞 |
| `core_10_grounding_silence` | 資訊不足、世界／現實來源不明或推論風險過高 | proposal 被拒絕或 `SILENCE` | evidence grounding、虛構與現實分離 |

10 個場景的結果分布至少包含：

- 4 個不送出結果：`CANCEL`、無 event、`EXPIRE`、proposal rejection／`SILENCE`。
- 2 個以上需要多階段或多次判斷：`DELAY`、presence wait。
- 1 個跨 Session／World isolation。
- 1 個 delivery recovery／exactly-once。

低階排列組合，例如所有 action validator 錯誤、每個 enum 邊界、lease/version 競爭變體，保留在 deterministic unit/integration tests，不再為每個組合建立 live scenario。如此可將 live API 成本集中在真正需要模型判斷的 10 種行為上。

---

## 11. 驗證矩陣

| Gate | 驗證重點 | 失敗條件 |
|---|---|---|
| Plumbing | clock、store、queue、lease、delivery、cleanup | 資源殘留、重複投遞、錯誤狀態轉移 |
| Oracle isolation | runtime 不讀 expected，AI 不看未來 | 改 oracle 會改 runtime、prompt 出現測試答案 |
| Live stage coverage | 必要 AI stages 都真的被呼叫 | 缺 call、mock backend、手工 ledger、silent fallback |
| Candidate quality | AI 能提出也能不提出 | 無 evidence、無 expiry、一般寒暄大量建 event |
| Multi-judgement | 同事件可多次 reappraise | DELAY 後沒有第二次 AI call／DecisionRecord |
| Generation | 真正生成主動訊息 | transport 仍送 event summary 或 fixture purpose |
| Hard safety | deterministic constraints | expiry/opt-out/idempotency 被模型繞過 |
| Human review | 人工檢查 candidate、語意、persona、主動訊息與沉默合理性 | flow PASS 被誤報成語意 APPROVED、缺少人工審核材料 |
| Logging | 實際 call 與摘要一一對應 | AI 區段沒有 call_id、出現偽造思考流程 |
| Prompt section | 刪除獨立指紋章節 | log 仍含 `### Prompt 指紋` |

### Live smoke 驗收

focused automated tests 通過後，再以目前已配置 provider 跑最小 smoke：

```powershell
$env:LLM_BACKEND = 'google'
.\.venv\Scripts\python.exe scripts\replay_initiative_v02.py --scenario l0_01 --live-api
```

但實作後 CLI mode 名稱或 flag 應同步更新為更精確的 live E2E 名稱。Smoke 驗收不能只看 exit code，還要檢查：

- transcript 有真實角色回覆。
- candidate scan 與 consolidation 各有 call。
- event 來源可追到 accepted candidate。
- reappraisal 有 call。
- SEND 時 Generator 有 call，transport message 是其輸出。
- 自動輸出 `flow_result`，人工審核預設為 `PENDING`。
- log 提供完整 transcript、candidate、rationale 與主動訊息供人工審核。
- log 不含 `### Prompt 指紋`。
- run 結束後 queue、presence、lease、worker 均為 0。

---

## 12. 風險與控制

### API 成本與耗時

多階段呼叫會顯著增加成本。控制方式：

- 先跑單一場景，再跑本計畫固定的 10 個核心場景；第一版不再擴成 30 個 live scenarios。
- 各 stage 設不同 token budget。
- correction attempt 最多一次。
- `--repeat` 預設 1；提高 repeat 只用於診斷模型變異，不作多數決通過門檻。

### 模型變異

live E2E 不要求每次文字完全一致，但每次執行都必須通過 schema、evidence、state、delivery、cleanup 與 safety flow contract，不使用 2/3 多數決掩蓋流程錯誤。語意差異與回覆品質交由人工逐次審核。

### 人工審核一致性

人工審核使用固定 checklist 並保留 reviewer notes。第一版不要求多人一致性評分；若後續要做研究統計，再增加第二位 reviewer 與一致性指標，不列入目前 flow gate。

### 過度主動

Candidate Scan 的成功不是 candidates 越多越好。場景必須保留至少 40% 不建立、不發送、取消或沉默案例，並統計 false event creation 與 unnecessary intervention。

### 偽「思考流程」

不得用 deterministic summary 冒充 AI reasoning，也不應索取 hidden chain-of-thought。可記錄的是模型明確回傳的短理由、證據 refs、action、validation error 與 state transition。

---

## 13. 完成定義

這次收斂完成後，只有同時滿足以下條件才能宣稱「live AI 主動性 E2E」：

- 使用者腳本驅動真實角色 AI 對話，而不是 fixture 直接填入角色輸出。
- 每個對話回合後都有真實 candidate scan，並允許 AI 判斷沒有值得追蹤的事。
- event 由 AI candidate 經 deterministic gate 建立，不由 fixture purpose/prelude 直接建立。
- Oracle 只做 run 後評分，不驅動 runtime lifecycle。
- 同一事件可在不同時間點取得多次真實 AI reappraisal。
- 主動訊息由 Generator 真實產生，delivery 不再送 event summary。
- 自動 `flow_result` 與人工 `human_review` 完全分開，流程 PASS 不代表語意 APPROVED。
- 每個 AI 結果都有 call_id、provider attempt、validation 與可追溯 evidence。
- 所有 AI → runtime 的 world／initiative event 與判斷結果都是通過 schema validation 的 JSON。
- log 不再把程式拼接摘要稱為 AI 思考流程。
- log 已刪除獨立 `### Prompt 指紋` 區段。
- virtual clock、mock transport、in-memory store 等測試邊界被清楚標示，不再以單一 `LIVE_API` 掩蓋。

最終研究問題應從「fixture 指定事件後，模型會不會選對 action」提升為：

> 在一段可重複但內容由 live 角色 AI 實際完成的對話中，AI 能否自主辨識值得後續處理的候選、隨時間與新情境多次修正判斷，並在安全、低打擾與可驗證的條件下選擇說話或保持沉默。

---

## 14. 已全部確認的交付決策

### 14.1 已確認

- 採方案 B，不保留其他實作方案。
- `WorldEventProposal` 只允許 `reminder`、`care_followup`、`commitment`、`topic_continuation`。
- AI event 時間使用 `earliest_offset_minutes`、`preferred_offset_minutes`、`expires_offset_minutes`。
- system 依 logical clock 與 timezone 將 offset 轉成絕對時間。
- Live Dialogue 使用既有完整角色 dialogue pipeline。
- 每個完整 `user turn + assistant response` 後執行 Candidate Scan，對話結束後再執行一次 Consolidation。
- AI → runtime 使用 strict JSON；AI → 使用者的對話與主動訊息使用純文字。
- validation 失敗最多一次 correction call，仍失敗即 `ERROR`，不使用 mock／fixture fallback。
- 第一版 live suite 固定為 10 個核心場景。
- active fixture 檔直接替換為 10 個 canonical scenarios；舊 30 個從 active fixture 刪除，不建立 legacy 副本。
- 自動驗收採 pytest-like flow gate：任一流程錯誤即 FAIL／ERROR，修正後重跑，不採 repeat 多數決或 2/3 通過門檻。
- 語意是否合理、角色回覆與主動訊息品質由人工審核，使用 `PENDING／APPROVED／REJECTED` 獨立呈現。

### 14.2 實作預設

- 每次 Candidate Scan 最多回傳 3 個 proposals。
- 每段對話最多接受 2 個 events。
- 每個 world 同時最多 5 個 active events。
- log 摘要顯示 parsed fields；完整 request／raw JSON 放在折疊 debug 區段。

第一個 implementation slice 已沒有需要再確認的架構或驗收問題。
