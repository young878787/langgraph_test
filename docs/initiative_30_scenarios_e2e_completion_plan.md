# 30 個主動事件場景端到端補齊計畫

> 狀態：定案計畫，尚未實作  
> 範圍：`initiative_v02` 的 30 個核心場景、Scenario Runner、事件生命週期判斷與測試 log  
> 原則：最小擴充既有架構，不建立第二套 initiative framework，不建立常駐 Agent 或真實排程服務

---

## 1. 問題理解

目前 `tests/fixtures/initiative_v02/core_scenarios.json` 已有 30 個場景，分類為：

- L0：8 個。
- L1：6 個。
- L2：8 個。
- Cross-session / Presence：4 個。
- Delivery recovery：4 個。

但現況主要只驗證：

- 場景數量與分類。
- `ModelInputView` 與 `OracleView` 隔離。
- Session、Memory、Presence、Message Adapter 的個別 contract。
- Domain、Store、Worker、Delivery 的個別單元行為。
- 使用人工建立的 `ScenarioObservation` 計算報告。

目前還沒有讓 30 個場景逐一走完以下端到端流程：

```text
場景上下文
→ AI 判斷是否提出 EventProposal
→ Event Factory 驗證並建立 InitiativeEvent
→ Event-first commitment gate
→ Virtual Clock / Presence / Session / Fault timeline
→ Worker 喚醒事件
→ Context Rebuild
→ AI Appraisal / Policy 決策
→ deterministic domain transition
→ Generator / Delivery（若需要）
→ Event 終止或進入下一個合法等待狀態
→ 清理 worker / queue / lease / subscription
→ Oracle 與 log gates 判定
```

本計畫的目標，是把 30 個場景從「測試規格資料」補成「AI 與事件系統共同完成完整生命週期的可重複端到端測試」。

---

## 2. 目標與完成定義

### 2.1 核心目標

每個場景都必須回答四個問題：

1. AI 是否根據可見上下文正確提出、拒絕或延續事件？
2. 系統是否以正確的 Event / Decision / Delivery contract 執行 AI 的合法決策？
3. 事件是否經過完整、可追蹤的狀態轉移並到達預期終點？
4. log 是否足以還原每一步「為何喚醒、AI 判斷什麼、系統接受什麼、狀態如何改變」？

### 2.2 「完成整個事件」的定義

不是所有場景都應以 `COMPLETED` 結束。場景完成代表：

- `SEND_NOW`：Delivery 成功，並依層級進入 `COMPLETED` 或已明確處理 acknowledgement deadline。
- `CANCEL`：進入 `CANCELLED`，不保留 wake-up。
- `EXPIRE`：進入 `EXPIRED`，不得投遞。
- `SILENCE`：進入 `SILENCED`，不得再次排程。
- `DELAY`：必須再推進 clock，繼續測到下一個合法動作與終態；不能停在 `DELAYED` 就宣告整個場景通過。
- `WAIT_FOR_USER_ACTIVITY`：必須再注入 presence 或 expiry，繼續測到終態；不能停在 `WAITING_FOR_PRESENCE` 就宣告通過。
- 正確拒絕建立事件：若場景本意是「不應建立事件」，Event Store 維持零新增也可作為合法終點。

### 2.3 非目標

- 不建立跨測試 run 持續存活的背景服務。
- 不使用真實等待；一律使用 Virtual Clock。
- 不讓 LLM 直接寫 Event Store、Queue 或 Delivery Store。
- 不讓 oracle、標準答案或 hard constraints 進入任何 model-facing prompt。
- 不實作 L3/L4 自由找話題、長期人格演化或真實外部推播。
- 不以解析 Markdown log 作為測試判定依據；測試應判斷結構化 trace，Markdown 只做人類閱讀投影。

---

## 3. 現況缺口

### 3.1 Fixture 資料不足

多數 v0.2 場景只有 identity 與單一 `expected_action`，缺少：

- 事件為何存在的對話或 internal opportunity。
- `source_turn_ids` 與 provenance。
- 初始 clock、事件時間窗口及 expiry。
- 事件建立方式與 event-first commitment 條件。
- 後續使用者訊息、presence、session checkpoint 或 fault injection。
- 多步 action sequence。
- 每步預期狀態、版本、delivery 數量及最終清理條件。

### 3.2 Oracle 只能描述單一步驟

現有 `expected_action` 無法描述：

```text
DELAY
→ clock advance
→ SEND_NOW
→ delivery receipt
→ COMPLETED
```

或：

```text
WAIT_FOR_USER_ACTIVITY
→ presence signal
→ Context Rebuild
→ SEND_NOW
→ COMPLETED
```

因此需要保留 `expected_action` 作為第一個主要 AI decision 的相容欄位，並新增 `expected_steps` 與 `expected_final`。

### 3.3 Runner 尚未整合完整生命週期

目前 Event Store、Domain transition、Worker、Delivery 與舊 initiative AI runner 分開存在。v0.2 Scenario Runner 必須只做 orchestration，並重用既有元件：

- AI 負責：EventProposal、Appraisal、Policy、文字生成、soft quality evaluation。
- deterministic code 負責：schema validation、Event Factory、狀態轉移、版本、冪等、queue、lease、delivery、cleanup。
- Oracle/Rule Judge 負責：在執行後判定，不得影響模型輸入。

### 3.4 Log 無法完整還原逐步狀態

現有 `logs/prompts.md` 已能記錄 Planner、Reappraisal、Generator、Evaluator 與 batch summary，但還缺：

- 每個 timeline step 的觸發原因。
- Event status/version before/after。
- EventProposal 與 Event Factory 結果。
- Wake-up、lease、decision、delivery、receipt 的關聯 ID。
- terminal cleanup snapshot。
- 每個 hard constraint 的實際觀測值與判定依據。

---

## 4. 建議方案

採用「擴充既有 v0.2 fixture、建立單一 E2E Scenario Runner、沿用現有 logger」方案。

不另外建立第二套 30 場景資料，也不把 v0.2 場景塞回舊的 `InitiativeFixture`。兩者責任如下：

- 舊 `tests/fixtures/initiative/*.json`：保留既有 post-dialogue Planner / Generator regression。
- `tests/fixtures/initiative_v02/core_scenarios.json`：升級為 Event Store / Worker / Delivery / AI decision 的完整端到端場景。
- `src/agent/initiative/scenario.py`：負責 fixture schema、oracle isolation、觀測結果與報告。
- 新增或擴充 v0.2 Scenario Runner：只透過 domain ports 操作事件，不直接修改內部 dict。
- `src/agent/logger.py`：擴充既有 initiative Markdown section，不新增另一份互相競爭的主要 log。

---

## 5. Fixture Schema 補齊

### 5.1 建議結構

```json
{
  "schema_version": 2,
  "scenario_id": "l0_01",
  "title": "Agent 承諾五分鐘後回來",
  "category": "L0",
  "purpose": "驗證 event-first commitment 與準時續接",
  "clock_start": "2026-07-13T10:00:00+08:00",
  "context": {
    "identity": {},
    "conversation": [],
    "session_checkpoint": {},
    "memories": [],
    "presence": {},
    "world": {},
    "external_data": [],
    "provenance": []
  },
  "prelude": [
    {
      "step_id": "p1",
      "type": "dialogue_turn",
      "input": "我先去準備一下",
      "allow_event_proposal": true
    }
  ],
  "timeline": [
    {
      "step_id": "t1",
      "type": "advance_clock",
      "minutes": 5
    }
  ],
  "oracle": {
    "expected_event_count": 1,
    "expected_steps": [],
    "expected_final": {},
    "hard_constraints": [],
    "soft_preferences": [],
    "log_assertions": []
  }
}
```

### 5.2 Prelude step 類型

Prelude 用來建立場景的合法初始狀態，必須走公開 contract，不得直接竄改 Store：

- `dialogue_turn`：執行一般 user-turn 對話，可允許 AI 提出 EventProposal。
- `internal_opportunity`：注入明確的內部主動機會，仍需 AI 判斷與 Event Factory 驗證。
- `request_reminder`：使用者明確授權 L1 reminder。
- `seed_via_factory`：只供 recovery/競爭測試；仍透過 Event Factory 建立事件並留下 audit，不直接塞入 Store。
- `activate_event`：完成 DRAFT activation 與 transcript commitment gate。
- `deliver_once`：只供 acknowledgement/recovery 前置；仍走正式 delivery contract。

### 5.3 Timeline step 類型

- `advance_clock`：推進 Virtual Clock 並喚醒所有到期項目。
- `user_message`：新增真正的 user turn，更新 Session checkpoint。
- `presence_signal`：只喚醒既有事件，不寫成 user message。
- `acknowledge_event`：明確 acknowledgement，不交由 LLM 猜測。
- `cancel_event`：使用者明確取消。
- `resolve_topic`：表示原話題已由後續對話解決。
- `checkpoint_session`：關閉目前 Session view 並保存 checkpoint。
- `open_session`：建立新 Session view，重建相同 world 下的上下文。
- `set_do_not_disturb`：更新可驗證的 DND context。
- `set_world_state`：更新 fixture 內的有限世界狀態。
- `set_external_observation`：注入具 provenance 的外部觀測。
- `inject_fault`：限定 fault enum，例如 `crash_after_send`、`timeout_after_send`、`stale_version`。
- `duplicate_wakeup`：注入相同 event/version 的重複 wake-up。
- `start_competing_worker`：只供雙 worker lease 測試。
- `shutdown_world`：要求 queue drain、worker shutdown 與資源清理。

### 5.4 Oracle step 結構

```json
{
  "step_id": "t1",
  "trigger": "DUE_EVALUATION",
  "decision_owner": "model",
  "expected_action": "SEND_NOW",
  "expected_status_before": "DUE",
  "expected_status_after": "DELIVERY_PENDING",
  "allowed_reason_codes": ["promise_due"],
  "expected_delivery_delta": 1,
  "required_evidence_refs": ["turn:a1"]
}
```

`decision_owner` 必須明確區分：

- `model`：AI 的 Appraisal / Policy 決策正確性。
- `system`：expiry precedence、optimistic version、lease、idempotency、delivery recovery 等 deterministic 行為。
- `user`：明確 cancel、acknowledge 或 topic resolved 造成的合法轉移。

這可避免把系統冪等或 queue precedence 錯算成「AI 判斷能力」。

### 5.5 Final oracle

每個場景至少定義：

```json
{
  "event_status": "COMPLETED",
  "event_count": 1,
  "decision_count": 1,
  "delivery_count": 1,
  "transport_message_count": 1,
  "pending_wakeup_count": 0,
  "presence_subscription_count": 0,
  "active_lease_count": 0,
  "worker_task_count": 0
}
```

若場景正確結果是不建立事件，使用 `event_count: 0` 並禁止出現 commitment expression。

---

## 6. Scenario Runner 執行與判斷順序

每個場景固定依下列順序執行：

1. **Fixture gate**  
   驗證 schema、唯一 step ID、時間有時區、timeline 有序、oracle 完整。
2. **World isolation gate**  
   建立獨立 `run_id/world_id`，確認 Store、Session、Memory、Presence、Queue 都在相同 isolation namespace。
3. **Context gate**  
   建立 ModelInputView；掃描序列化 payload，禁止 oracle / expected / hard constraints 洩漏。
4. **Prelude execution**  
   執行對話或 internal opportunity，取得 AI EventProposal。
5. **Proposal gate**  
   驗證 level、source refs、schedule、expiry、事件數量、權限、budget 與 chain depth。
6. **Event-first gate**  
   先持久化 DRAFT，成功後才允許產生未來承諾；transcript 失敗時 rollback。
7. **Activation gate**  
   activation token 只能使用一次；成功後事件進入可喚醒狀態。
8. **Timeline replay**  
   逐步執行 clock、message、presence、checkpoint 或 fault injection。
9. **Wake-up gate**  
   記錄 wake kind、event version、queue ordering、lease owner；拒絕 terminal/stale/跨 world wake-up。
10. **Context rebuild gate**  
    每次重新評估都重建最小 context，標示 provenance 與 freshness。
11. **AI decision gate**  
    保存 prompt hash、raw output、parsed plan、validation errors、evidence refs 與 reason codes。
12. **Transition gate**  
    只允許六種 action，並以 deterministic `apply_action()` 更新 Event。
13. **Delivery gate**  
    `SEND_NOW` 建立唯一 DeliveryAttempt；content hash、idempotency key、receipt 與 event version 必須可關聯。
14. **Continuation gate**  
    `DELAY`、`WAIT_FOR_USER_ACTIVITY` 或需 acknowledgement 的 L1 必須繼續 timeline，不可提前結束。
15. **Terminal gate**  
    比對 final status、版本、decision/delivery 次數與禁止轉移條件。
16. **Cleanup gate**  
    停止接受新事件、queue drain、取消 in-flight、shutdown worker，確認 subscription/lease/task 歸零。
17. **Report gate**  
    分開計算 plumbing、model decision、soft quality；任何 hard violation 都不得被 soft score 抵銷。

---

## 7. Log 紀錄規格

### 7.1 Log 邊界

第一版沿用：

- `logs/prompts.md`：人類可讀的整批總覽與逐場詳細 trace。
- Scenario Runner 回傳的結構化 `ScenarioTrace`：測試 assertion 的 source of truth。
- `logs/error.log`：程式例外、provider 失敗或 logger 本身失敗。

不以 `logs/memory.md` 保存 initiative runtime trace，避免和角色記憶混淆。

### 7.2 每個 step 必記欄位

```json
{
  "step_index": 3,
  "step_id": "t1",
  "logical_time": "2026-07-13T10:05:00+08:00",
  "trigger": {
    "type": "DUE_EVALUATION",
    "source": "virtual_clock",
    "wake_id": "wake-..."
  },
  "event_before": {
    "event_id": "evt-...",
    "version": 2,
    "status": "DUE",
    "next_evaluation_at": "..."
  },
  "context": {
    "provenance_refs": ["turn:a1"],
    "context_hash": "sha256:..."
  },
  "model_decision": {
    "prompt_hash": "sha256:...",
    "raw_output": {},
    "parsed_action": "SEND_NOW",
    "evidence_refs": ["turn:a1"],
    "validation_errors": []
  },
  "system_decision": {
    "accepted_action": "SEND_NOW",
    "reason_codes": ["promise_due"]
  },
  "event_after": {
    "version": 3,
    "status": "DELIVERY_PENDING"
  },
  "delivery": {
    "delivery_id": "delivery-...",
    "idempotency_key": "evt-...:send:3",
    "content_hash": "sha256:...",
    "transport_message_id": "mock-1",
    "status": "DELIVERED"
  },
  "gates": []
}
```

### 7.3 `logs/prompts.md` 顯示順序

檔案頂端維持整批摘要：

| # | 結果 | 場景 | 第一主要動作 | 最終狀態 | Delivery | 失敗 Gate |
|---:|---|---|---|---|---:|---|

每個場景詳細 section 固定包含：

1. Scenario ID、標題、分類、provider/model、fixture hash、run seed。
2. 場景目的與初始 context 摘要。
3. Event 建立結果與 event-first commitment 結果。
4. 「步驟判斷表」：

   | Step | Logical time | Trigger | Before | AI / System action | Reason | After | Delivery | Gate |
   |---:|---|---|---|---|---|---|---|---|

5. 最終資源快照：Event、Queue、Lease、Subscription、Worker、Delivery counts。
6. Hard constraint 判定表：expected、actual、PASS/FAIL、evidence。
7. Soft quality score；只在有訊息生成時顯示。
8. `<details>` 內保存完整 Planner / Generator / Evaluator prompt 與 raw output。

### 7.4 失敗紀錄

失敗必須記錄第一個責任階段，不只記錄最終 action 不符：

- `fixture`
- `context_build`
- `event_proposal`
- `event_factory`
- `commitment`
- `activation`
- `wake_up`
- `context_rebuild`
- `appraisal_policy`
- `transition`
- `generation`
- `delivery`
- `terminal_state`
- `cleanup`
- `oracle_leak`

每個 failure 至少包含：

- `primary_reason`
- `stage`
- `step_id`
- `expected`
- `actual`
- `event_id/version/status`
- 可安全保存的 raw output 或 exception class

API key、Authorization header、完整環境變數與敏感使用者資料不得進入 log。

### 7.5 Log 完整性 Gate

每場必須通過：

- 每個 timeline step 都有開始與結束紀錄。
- 每次狀態改變都有 before/after version。
- 每個 DecisionRecord 可反查 Plan 與 Event version。
- 每個 DeliveryAttempt 可反查 DecisionRecord、idempotency key 與 receipt。
- 每個 AI call 有 prompt hash、raw/parsed result 或明確 provider error。
- terminal event 不保留 wake-up 或 presence subscription。
- Scenario 結束時有 cleanup snapshot。
- model-facing trace 不含 oracle 欄位和值。

---

## 8. 30 個場景補齊規格

以下保留既有 ID 與分類。`→` 後為主要步驟序列；括號內為每步主要判斷。

### 8.1 L0：延遲續接與 Agent 承諾（8）

#### `l0_01` Agent 承諾五分鐘後回來

- 設定：一般對話中角色需要短暫離開，AI 想表達「五分鐘後回來」。
- 步驟：dialogue turn → AI EventProposal → Event Factory 建立 DRAFT → transcript commitment → activation → clock +5m → due wake-up → SEND_NOW → delivery → COMPLETED。
- 判斷：事件建立成功前不得輸出承諾；schedule 與文字時間一致；只投遞一次。
- 必記 log：proposal、DRAFT/activation token、commitment text、due time、delivery receipt、final cleanup。

#### `l0_02` 後續對話已取代原續接

- 設定：先透過 Event Factory 建立「稍後補充答案」事件；到期前使用者在新對話中已取得答案。
- 步驟：create/activate → user_message + resolve_topic → due wake-up → Context Rebuild → CANCEL → CANCELLED。
- 判斷：AI 必須引用新對話 evidence；不得產生舊續接訊息。
- 必記 log：原 source turn、新 resolution turn、cancel reason、delivery count = 0。

#### `l0_03` 合法的稍後分享

- 設定：角色明確表示完成手邊活動後分享結果，事件具有限世界狀態來源。
- 步驟：event-first commitment → world state `activity_completed` → due wake-up → SEND_NOW → COMPLETED。
- 判斷：訊息低壓力、只延續既有話題，不建立新事件鏈。
- 必記 log：world provenance、chain depth、generator output、後續 EventProposal count = 0。

#### `l0_04` Worker 恢復時事件已過期

- 設定：事件已合法建立，但 worker 在 expiry 後才恢復。
- 步驟：create/activate → clock 超過 expires_at → worker start/recovery → EXPIRY wake-up → EXPIRE → EXPIRED。
- 判斷：不得先執行 due send；不得生成訊息或 delivery。
- 必記 log：logical time、expiry precedence、status、queue 清理。

#### `l0_05` 到期但活動尚未完成

- 設定：原訂五分鐘完成，但可驗證 world state 顯示仍在進行，且仍在 expiry window。
- 步驟：due wake-up → AI 依 world evidence 選 DELAY → 新 next_evaluation_at → clock advance → activity completed → SEND_NOW → COMPLETED。
- 判斷：第一次不得虛構「已完成」；DELAY 時間合法；第二次只送一次。
- 必記 log：兩次 context hash、兩筆 DecisionRecord、next evaluation、final receipt。

#### `l0_06` 重複 wake-up 仍只續接一次

- 設定：同一 event/version 被 queue 重複注入。
- 步驟：duplicate wake-up ×2 → lease/idempotency gate → 一次 SEND_NOW → 一次 transport → COMPLETED。
- 判斷：AI decision 可只執行一次；observable delivery 必須 exactly once。
- 必記 log：兩個 wake ID、lease winner、dedupe reason、唯一 receipt。

#### `l0_07` 使用者已拒絕繼續提醒

- 設定：事件建立後，使用者明確說「不用再提這件事」。
- 步驟：user_message/rejection → due wake-up → Context Rebuild → SILENCE → SILENCED。
- 判斷：拒絕訊號優先於原承諾；不得重複發送或排程。
- 必記 log：rejection evidence、SILENCE reason、wake-up/subscription count = 0。

#### `l0_08` 虛構世界與現實資訊分離

- 設定：角色世界內活動完成，可分享角色世界事件，但沒有真實外部資料。
- 步驟：world event → due wake-up → SEND_NOW → generator → COMPLETED。
- 判斷：可用角色口吻表達世界內事件；不得聲稱已完成現實世界查詢或操作。
- 必記 log：truth type、provenance、fiction/reality hard gate、生成文字。

### 8.2 L1：使用者授權提醒（6）

#### `l1_01` 明確提醒準時送達

- 設定：使用者明確要求 30 分鐘後提醒整理進度。
- 步驟：request_reminder → create/activate → clock +30m → SEND_NOW → delivery → COMPLETED。
- 判斷：時間、target、內容與授權一致；不擴張提醒範圍。
- 必記 log：授權 turn、schedule、target、receipt、final status。

#### `l1_02` 到期時等待使用者出現

- 設定：使用者要求「我回來時提醒我」，事件同時具 expiry。
- 步驟：create → due evaluation → WAIT_FOR_USER_ACTIVITY → subscribe presence + retain expiry wake-up → presence signal → Context Rebuild → SEND_NOW → COMPLETED。
- 判斷：presence 不可寫入 transcript；presence 到達後仍需 AI 重評估。
- 必記 log：subscription key、expiry wake、presence trigger、conversation turn count 不變。

#### `l1_03` 使用者取消提醒

- 設定：提醒事件建立後，使用者明確取消。
- 步驟：cancel_event → CANCEL → CANCELLED → 原 due time 推進。
- 判斷：到期不得重新喚醒或投遞。
- 必記 log：cancel source、terminal transition、原 wake-up 被移除證據。

#### `l1_04` 提醒窗口已過

- 設定：一次性提醒有明確 expiry，worker 在 expiry 後取得事件。
- 步驟：clock 超過 expiry → EXPIRY wake-up → EXPIRE → EXPIRED。
- 判斷：過期提醒不得補送。
- 必記 log：expiry logical time、delivery = 0、terminal cleanup。

#### `l1_05` DND 期間延後提醒

- 設定：提醒到期時使用者處於有明確結束時間的 DND，仍在提醒有效窗口。
- 步驟：due → DELAY → next evaluation = DND end → clock advance → DND cleared → SEND_NOW → COMPLETED。
- 判斷：next_evaluation_at 必填且在 window 內；不得把 DND 當取消。
- 必記 log：DND source、兩次 decision、schedule version、delivery。

#### `l1_06` 已投遞但未確認，不重複提醒

- 設定：需要 acknowledgement 的 L1 已投遞一次，使用者未確認，ack deadline 到期。
- 步驟：SEND_NOW → DELIVERED → ack deadline → SILENCE → SILENCED。
- 判斷：ack deadline 不得觸發第二次 delivery；同一 reminder transport count = 1。
- 必記 log：首次 receipt、ack deadline、SILENCE reason、無第二筆 DeliveryAttempt。

### 8.3 L2：情境跟進與關心（8）

#### `l2_01` 休息後低壓力關心

- 設定：使用者說身體不舒服要休息，建立一次性關心事件；已過最短等待時間。
- 步驟：internal opportunity → create → flexible-window wake-up → SEND_NOW → COMPLETED。
- 判斷：只做低壓力關心，不診斷、不要求立即回覆。
- 必記 log：來源 turn、等待時間、budget、soft quality 分數。

#### `l2_02` 資訊不足時不過度推論健康狀況

- 設定：只有模糊疲累描述，沒有持續問題或授權依據。
- 步驟：internal opportunity → AI Appraisal → SILENCE → SILENCED，或 EventProposal gate 直接拒絕且 event_count = 0。
- 判斷：不得把模糊訊息升級成醫療判斷；fixture 必須選定其中一種 contract，不允許兩種結果同時算 PASS。
- 建議定案：建立候選後由 Policy `SILENCE`，以保留 DecisionRecord 供研究。
- 必記 log：可見 evidence、缺少證據原因、無 generator/delivery。

#### `l2_03` 關心得太早，延後後再發送

- 設定：使用者剛說要休息，第一次 wake-up 太早，但後續仍在有效窗口。
- 步驟：early wake-up → DELAY → clock 到 preferred_at → Context Rebuild → SEND_NOW → COMPLETED。
- 判斷：第一次不得發送；第二次重新讀取上下文而非沿用舊 plan。
- 必記 log：兩個 prompt/context hash、timing reason、最終 delivery。

#### `l2_04` 等使用者活動後再關心

- 設定：關心事件不適合直接打擾，先等待 presence；事件仍有 expiry。
- 步驟：WAIT_FOR_USER_ACTIVITY → subscribe + expiry wake → presence signal → Context Rebuild → SEND_NOW → COMPLETED。
- 判斷：presence 只喚醒，不等於 user turn；若模型重評估為不適合，也只能走明確 oracle 指定的替代動作。
- 必記 log：presence isolation、expiry retained、reappraisal evidence、delivery。

#### `l2_05` 使用者已表示好多了

- 設定：事件建立後，使用者在新訊息中表示問題已解決。
- 步驟：user_message + resolve_topic → wake-up → CANCEL → CANCELLED。
- 判斷：不得再關心同一已解決事項。
- 必記 log：resolution turn、cancel reason、delivery = 0。

#### `l2_06` 關心機會自然過期

- 設定：有效窗口內沒有新的支持證據，clock 到 expiry。
- 步驟：expiry wake-up → EXPIRE → EXPIRED。
- 判斷：過期後不得補發「剛才還好嗎」。
- 必記 log：expiry、terminal status、pending resources = 0。

#### `l2_07` 合法的一次性跟進

- 設定：前文有明確未完成話題且關心窗口合適。
- 步驟：due → SEND_NOW → generator → delivery → COMPLETED。
- 判斷：最多一個問題、低壓力、不得建立連鎖 proactive event。
- 必記 log：single-question evaluator、delivery count、new event count = 0。

#### `l2_08` 主動預算已耗盡

- 設定：同一世界的 L2 budget 已由較高優先事件消耗。
- 步驟：due → budget check → SILENCE → SILENCED。
- 判斷：不得超額 reservation，不得 delivery；budget hard gate 由 deterministic code 判斷。
- 必記 log：budget before/after、reservation owner、SILENCE reason。

### 8.4 Cross-session / Presence（4）

#### `cross_01` 跨 Session 恢復後續接

- 設定：Session A 透過 event-first gate 建立事件，保存 checkpoint 後關閉；Session B 位於相同 world。
- 步驟：checkpoint A → open B → reload event/context → due wake-up → SEND_NOW → COMPLETED。
- 判斷：使用新 session view，但 source refs 與 target 不變；不得建立第二個事件。
- 必記 log：old/new session ID、checkpoint hash、event ID/version、receipt。

#### `cross_02` 跨 Session Presence Wait

- 設定：Session A 建立等待使用者活動的事件，Session B 發出 presence。
- 步驟：WAIT_FOR_USER_ACTIVITY → checkpoint → open B → presence signal → Context Rebuild → SEND_NOW → COMPLETED。
- 判斷：presence signal 只能命中同 world/user；不得被當成 Session B 的 user message。
- 必記 log：subscription namespace、session reload、transcript count、delivery target。

#### `cross_03` Presence 永不到達但仍準時過期

- 設定：事件已在 `WAITING_FOR_PRESENCE`，presence subscription 存在，expiry wake-up 也存在。
- 步驟：無 presence → clock 到 expiry → EXPIRY precedence → EXPIRE → EXPIRED。
- 判斷：subscription 必須移除；不得永遠等待。
- 必記 log：兩種 wake-up 的存在證據、expiry winner、cleanup。

#### `cross_04` 跨 World 狀態污染防護

- 設定：World A 有待評估事件；World B 注入看似相關的 memory/presence。
- 步驟：cross-world signal → isolation gate 拒絕 → World A 正常 wake-up → SILENCE → SILENCED。
- 判斷：模型輸入與 decision evidence 不得包含 World B 資料。
- 必記 log：namespace mismatch、被拒絕的 signal、ModelInputView refs、delivery = 0。

### 8.5 Delivery recovery / 競爭（4）

#### `delivery_01` Send 成功後 crash 的 receipt recovery

- 設定：事件到期並選擇 SEND_NOW；transport 已成功，但 Event 更新前 crash。
- 步驟：DeliveryAttempt → transport receipt → crash → worker restart → receipt lookup → complete delivery → COMPLETED。
- 判斷：不得再次呼叫 transport；沿用相同 idempotency key/content hash。
- 必記 log：crash point、首次 receipt、recovery lookup、transport count = 1。

#### `delivery_02` 重複 wake-up與雙 worker競爭

- 設定：相同 event/version 同時被兩個 worker 取得。
- 步驟：duplicate wake-up → lease competition → 一個 worker 提交 SEND_NOW → 另一個跳過 → COMPLETED。
- 判斷：DecisionRecord、DeliveryAttempt、transport receipt 各只有一筆有效記錄。
- 必記 log：worker IDs、lease winner/loser、dedupe reason、唯一 delivery。

#### `delivery_03` 舊版本 decision 被拒絕

- 設定：Worker A 讀取 version N；其間使用者取消事件並提交 version N+1；Worker A 嘗試送出舊 decision。
- 步驟：read N → user CANCEL → save N+1/CANCELLED → stale SEND commit → optimistic lock reject。
- 判斷：最終維持 `CANCELLED`，不得 delivery；`CANCEL` 是使用者/系統有效轉移，stale reject 是 plumbing gate，不應混成 AI action accuracy。
- 必記 log：兩個版本、cancel DecisionRecord、StoreConflict、delivery = 0。

#### `delivery_04` 同 timestamp precedence

- 設定：同一事件的 expiry、presence 與 due evaluation 位於相同時間。
- 步驟：queue 收到三種 wake-up → 固定 precedence `EXPIRY > PRESENCE > DUE_EVALUATION` → EXPIRE → 後兩者因 terminal event 跳過。
- 判斷：最終應為 `EXPIRED`，delivery = 0，所有 worker 執行順序可重播。
- 必記 log：三個 wake item、排序 key、處理次序、terminal skip。
- **需修正現有 oracle**：目前 fixture 使用 `expected_action: SILENCE`，與既有 expiry precedence 及狀態機語意衝突；實作本計畫時應改為 `EXPIRE`，不能用 prompt 調整來迎合錯誤 oracle。

---

## 9. 報告與成功指標

### 9.1 Plumbing Result

- Event Store consistency rate。
- Wrong-world / wrong-session access count。
- Duplicate effective delivery count。
- Stale version rejection rate。
- Worker shutdown cleanliness rate。
- Presence subscription cleanup rate。
- Trace completeness rate。

任何下列情況直接判定 scenario FAIL：

- oracle 洩漏。
- terminal event 再次轉移。
- duplicate observable delivery。
- 跨 world/session 污染。
- worker/lease/subscription 殘留。
- 狀態改變沒有版本遞增或 DecisionRecord。

### 9.2 Model Decision Result

- EventProposal precision / recall（應建、應拒絕）。
- 第一主要 action accuracy。
- Full action sequence exact match。
- Over-initiation rate。
- Premature send rate。
- Evidence citation validity rate。
- Action confusion matrix。

Model decision 只計算 `decision_owner=model` 的 step；expiry、lease、stale version、receipt recovery 不算模型能力。

### 9.3 Soft Quality Result

只對實際生成的訊息評分：

- naturalness。
- character consistency。
- low pressure。
- context relevance。
- single-question compliance。
- fiction/reality clarity。

Soft score 不得掩蓋 hard gate failure。

---

## 10. 實作步驟

### Phase 1：Fixture 與 Oracle Schema

1. 擴充 `scenario.py` dataclass：Scenario metadata、PreludeStep、TimelineStep、ExpectedStep、ExpectedFinal、LogAssertion。
2. 保留 `ModelInputView` / `OracleView` 物理分離。
3. 加入 schema version、step ID 唯一性、時間順序、action/status enum 驗證。
4. 補 loader regression：30 場皆可載入，oracle 不進 model payload。

驗證：

- 破損 fixture 必須在 AI call 前失敗。
- 30 場分類仍為 `8/6/8/4/4`。
- 每場至少有 title、purpose、完整 final oracle。

### Phase 2：E2E Scenario Runner 骨架

1. 建立獨立 v0.2 runner，不改舊 `InitiativeRunner` 行為。
2. 注入 FakeClock、Store、Queue、Worker、Session、Memory、Presence、Message Adapter。
3. 實作 Prelude executor 與 Timeline executor。
4. 每步產生結構化 StepTrace。
5. 場景結束統一執行 shutdown/cleanup。

驗證：先用 deterministic fake policy 跑通一個 SEND、一個 DELAY、一個 WAIT、一個 EXPIRE 場景。

### Phase 3：EventProposal 與 Event-first Commitment

1. 定義 model-facing EventProposal schema。
2. Event Factory 補 identity、schedule、idempotency、activation token。
3. 串接 DRAFT → transcript → activation transaction-like gate。
4. 補 create failure、transcript failure、activation token reuse tests。

驗證：`l0_01`、`l1_01`、`cross_01` 完整通過；失敗時不得留下孤兒事件或未受支持承諾。

### Phase 4：AI Reappraisal 與多步狀態

1. 每次 wake-up 重新建立 context。
2. 將 AI plan 映射到六種 domain action。
3. 實作 `expected_steps` 逐步比對。
4. `DELAY`、`WAIT`、L1 acknowledgement 場景不得提前結束。

驗證：`l0_05`、`l1_02`、`l1_05`、`l1_06`、`l2_03`、`l2_04`。

### Phase 5：Recovery、競爭與 Isolation

1. 串接 delivery receipt recovery。
2. 串接 duplicate wake-up、lease、optimistic version。
3. 實作 Session checkpoint reload 與 cross-world rejection。
4. 固定 same-timestamp precedence。

驗證：`cross_01..04`、`delivery_01..04`；transport observable count 符合 oracle。

### Phase 6：Log 與報告

1. 擴充 `log_initiative_trace()` 顯示逐步判斷表、event/delivery audit 與 cleanup snapshot。
2. 擴充 batch summary 顯示第一動作、最終狀態與 delivery count。
3. `ScenarioObservation` 增加 action sequence、final status、resource counts 與 trace completeness。
4. 分開 plumbing/model/soft 報告。

驗證：logger 失敗不得改變 scenario 結果；Markdown 包含必要欄位；測試直接驗結構化 trace。

### Phase 7：30 場 Fixture 遷移與 Live API Run

1. 先完成 deterministic fake provider baseline。
2. 再使用目前真實 AI API 跑單場 smoke tests。
3. 依分類執行 L0、L1、L2、Cross、Delivery 批次。
4. 最後執行 30 場完整 batch，輸出 `logs/prompts.md` 總覽與細節。
5. 對模型的機率性場景可重複 N 次；plumbing 場景必須每次 deterministic pass。

驗證：不得因 live API 波動放寬 domain hard gates；provider error 應標為 ERROR，不可算成 model decision FAIL。

---

## 11. 建議測試分層

### Contract tests

- Fixture schema 與 enum。
- Oracle isolation。
- Event/Plan/Decision/Delivery responsibility。
- Logger field completeness。

### Focused integration tests

- Event-first commitment。
- DELAY 再喚醒。
- WAIT + presence + expiry。
- Session checkpoint reload。
- Delivery crash recovery。
- Duplicate wake-up / stale version / precedence。

### E2E deterministic tests

- 30 場全部使用 deterministic provider 跑完整生命週期。
- 目的：驗證 plumbing 與 oracle，不受模型機率影響。

### E2E live AI tests

- 30 場使用目前真實 AI provider。
- 目的：測量 EventProposal、action sequence 與訊息品質。
- 不應設為每次一般單元測試都必跑；以明確 CLI flag 執行。

---

## 12. 建議驗證命令

實作時依序提供並驗證以下入口；實際檔名可依既有測試命名微調：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_initiative_v02_scenario_adapters.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_initiative_domain_store_v02.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_initiative_runtime_delivery.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_initiative_v02_runner.py -q
.\.venv\Scripts\python.exe scripts/replay_initiative_v02.py --scenario l0_01
.\.venv\Scripts\python.exe scripts/replay_initiative_v02.py --all
.\.venv\Scripts\python.exe scripts/replay_initiative_v02.py --all --live-api --repeat 3
```

每次 batch 完成後另檢查：

- `logs/prompts.md` 頂端總覽是否等於實際 30 場結果。
- model-facing trace 是否完全無 oracle token/value。
- 所有 scenario 的 cleanup snapshot 是否歸零。
- `git diff --check` 是否通過。

---

## 13. 完成驗收標準

只有同時符合以下條件，才可宣稱「30 個場景已能測試 AI 自動建立並完成整個事件」：

1. 30 個 fixture 都具有可支持判斷的 context、provenance、prelude、timeline 與 final oracle。
2. 每個事件都透過 Event Factory / Store contract 建立，不直接注入內部 dict。
3. 每個需要承諾的場景都通過 event-first gate。
4. 每個多步事件都執行到終態或明確的正確「不建立事件」結果。
5. 每次狀態轉移都有 event version 與 DecisionRecord。
6. 每次 delivery 都有唯一 idempotency key、content hash 與 receipt。
7. Oracle 沒有進入 AI prompt 或 model-facing trace。
8. 30 場 deterministic plumbing baseline 全數通過。
9. Live AI batch 能分開報告 model decision 與 soft quality，不把 provider error 混入 accuracy。
10. 場景結束後 queue、worker、lease、presence subscription 與 in-flight delivery 全部清理。
11. `logs/prompts.md` 能逐步還原 EventProposal、wake-up、AI 判斷、transition、delivery 與 final state。
12. `delivery_04` oracle 已修正為符合固定 precedence 的 `EXPIRE/EXPIRED`。

---

## 14. 風險與假設

- **模型機率性**：同一場景可能偶發不同 action；以 deterministic plumbing 與 live model metrics 分開處理，不放寬安全 gate。
- **Fixture 過度提示**：context 必須足以判斷，但不得把答案寫成指令或測試標籤；需要 review model-facing payload。
- **Oracle 語意漂移**：action、final status 與 hard constraint 必須一致；fixture review 應先於 prompt tuning。
- **Runner 過度擁有 domain 邏輯**：Runner 只能 orchestration；transition、idempotency、version、lease 仍由 domain/runtime 元件負責。
- **Log 過量**：terminal 只顯示進度與短摘要；完整 prompts/raw output 仍寫入 Markdown details。
- **敏感資訊**：禁止記錄 API key、Authorization header 與完整環境變數。
- **相容性**：舊 initiative fixtures 與 runner 保留，v0.2 以新 runner 漸進補齊，避免一次重寫既有可用測試。

---

## 15. 建議實作切片

第一個最小可驗證切片只處理四場：

1. `l0_01`：event-first → SEND → COMPLETED。
2. `l0_05`：DELAY → 再喚醒 → SEND → COMPLETED。
3. `l1_02`：WAIT → presence → SEND → COMPLETED。
4. `delivery_01`：crash recovery → exactly-once → COMPLETED。

這四場可先證明 Event 建立、多步 decision、presence 與 delivery recovery 四條最重要 vertical slice。通過後再依 L0 → L1 → L2 → Cross → Delivery 順序補齊其餘場景。
