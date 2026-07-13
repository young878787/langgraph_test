# 主動型角色 Agent 計畫書 v0.2

> 狀態：研究優先、逐步 productize 的定案版。
> 本版聚焦可攜式 proactive workflow、事件跨時間跳轉測試與 bounded background worker；不整合 Hermes、不建立常駐服務，也不要求測試結束後繼續活動。

## 1. 專案定位

本專案目標是建立一套可移植到不同宿主與訊息環境的「主動型角色 workflow 與評估架構」。角色不只在收到使用者訊息後才回應，而是能在測試世界中，根據時間、對話脈絡、事件狀態、有限角色世界與可驗證資料，自主判斷：

- 是否需要產生主動事件。
- 事件何時值得重新評估。
- 現在是否適合介入。
- 應該立即表達、延後、等待使用者出現，還是保持沉默。
- 主動行為是否真正對使用者有價值。
- 主動後應如何根據使用者反應更新事件狀態。

本專案的核心不是讓 Agent 替使用者執行大量現實操作，也不是建立完整人格演化、大型記憶系統或長時間常駐服務，而是研究與實作：

```text
事件生成
→ 情境重建
→ 內部評估
→ 時機判斷
→ 表達決策
→ 使用者反應觀察
→ 事件狀態更新
```

最重要的設計原則是：

> 不主動說話，也是一種正式決策。

Scheduler 只負責喚醒事件，不代表事件到期後一定要發送訊息。

### 1.1 本版架構決策

- 採用「研究優先、逐步 productize」方案。
- proactive workflow 將成為本研究分支的主要流程；原本以 user turn 為中心的 LangGraph workflow 不再是主動性 orchestration 核心，只保留為可替換的 Dialogue Adapter、角色表達元件與遷移參考。
- 本專案自行啟動 bounded background worker，但 worker 只在單次測試 run 期間存在，所有場景完成後必須自動停止。
- 跨時間以 Virtual Clock 跳時，不實際等待數分鐘、數小時或數天。
- 跨 Session 只模擬 Session checkpoint、記憶點與背景狀態恢復；不整合真實 Hermes Session。
- Hermes 僅作為未來可接入的概念性宿主，本階段不依賴其 API、Cron、記憶或訊息平台。
- `InitiativeEvent` 與 `InitiativePlan` 必須分離：Event 是持久狀態與生命週期的 source of truth；Plan 是某次評估產生的暫時決策方案。
- Agent 可以主動建立事件，但涉及未來承諾時必須先成功建立事件，再允許生成或送出承諾台詞。
- L3、L4 保留設計與 fixture 擴充點，不列入第一研究版本的必要實作。

### 1.2 第一研究版本定案 contract

- Model-visible context 與 Scenario oracle 完全隔離；Planner、Appraisal、Policy、Generator 不得讀取 `expected`、標準答案或測試標籤。
- 第一版採單 process、單 `asyncio` event loop、單 worker consumer；第二 worker 只在競爭測試中建立。
- Event／Session／Delivery 的寫入透過 Unit of Work 或等價 transaction boundary 協調。
- L0 與不需確認的 L1 在投遞成功後完成；需確認的 L1 有限期等待 acknowledgement；L2 投遞一次後完成。
- `WAIT_FOR_USER_ACTIVITY` 同時保存 presence subscription 與 expiry wake-up，確保使用者未出現時仍會過期。
- 第一版只啟用 `SEND_NOW`、`DELAY`、`WAIT_FOR_USER_ACTIVITY`、`CANCEL`、`EXPIRE`、`SILENCE` 六種 action。
- 第一版禁止 proactive delivery 鏈式建立下一個事件；只有一般 user-turn 對話或明確 internal opportunity 可以建立新事件。
- 同一 timestamp 的競爭事件使用固定 precedence 與 tie-breaker，確保 replay 結果穩定。

---

## 2. 核心研究目標

本專案將主動性收斂為一個明確的決策問題：

> 在沒有使用者新輸入的情況下，Agent 如何根據歷史脈絡、時間、事件狀態、角色世界與使用者近期反應，決定「是否、何時、以何種方式」主動介入。

### 2.1 系統輸入

- 原始對話與對話錨點。
- 事件候選。
- 現在時間。
- 事件時間窗口與有效期限。
- 事件建立後的新對話。
- 使用者近期互動與忽略紀錄。
- 目前角色世界狀態。
- 近期主動訊息紀錄。
- 測試世界內可查閱的記憶 checkpoint。
- 必要且可驗證的現實資料。

### 2.2 系統輸出

```text
SEND_NOW
DELAY
WAIT_FOR_USER_ACTIVITY
CANCEL
EXPIRE
SILENCE
```

後續 action `MERGE_WITH_OTHER_EVENT`、`UPDATE_WORLD_ONLY`、`PREPARE_ASSISTANCE`、`UPDATE_INTERNAL_STATE` 只保留設計名稱，第一版 Policy validator 必須拒絕輸出。

主動性系統的重點不是產生更多訊息，而是做出更適合的介入決策。

---

## 3. 專案範圍

### 3.1 本階段包含

本階段聚焦於陪伴與低風險助理支持：

- 延遲對話續接。
- 角色世界內的短期行動延續。
- 使用者明確要求的提醒。
- 根據情境產生的一次性關心。
- 根據既有事件與對話錨點延續話題，不做 L3 自由找話題。
- 以 Mock External Data 驗證低風險提醒 contract；不串接真實資料源。
- 使用者回來時自然接續先前內容。
- 跨 Session 保存待處理事件。
- 角色的最小世界 checkpoint 可跨測試 Session view 讀取，但不在離線期間自行推進。
- 事件是否表達、延後、取消或沉默的可重複測試。
- 不同測試世界之間的資料隔離。
- 測試 run 期間啟動並自動關閉的 bounded background worker。
- 以 Virtual Clock 跳時觸發事件，不依賴真實等待。
- 模擬跨 Session 記憶點與背景狀態恢復。
- 可替換的 Session、Memory、Presence、Message 與 External Data adapters。

### 3.2 本階段排除

第一版暫不處理：

- 自動寄送郵件。
- 自動購買商品。
- 自動付款。
- 自動刪除資料。
- 自動公開發布內容。
- 未經確認修改外部服務狀態。
- 需要法律、金錢或高風險責任的操作。
- 完整人格成長與人格自我改寫。
- 完整生活模擬、資源模擬或複雜遊戲世界。
- 以大型記憶系統作為主動性核心。
- 無限制由 LLM 自由建立排程。
- 讓每一個測試場景擁有獨立程式碼版本。
- 真實 Hermes API、Cron、Session 與訊息平台整合。
- 測試結束後仍持續運作的 daemon、服務或常駐 Agent。
- 真實數分鐘、數小時或數天的等待測試。
- 第一研究版本中的完整 L3 關係維持與 L4 自主世界 runtime。

以下現實工具只作為未來 adapter 例子；第一研究版本以帶來源、觀測時間與有效期限的 mock 資料測試：

- 查詢時間。
- 查詢天氣。
- 查詢行事曆。
- 查詢伺服器狀態。
- 查詢公開資訊。
- 取得使用者允許的低風險環境資料。

---

## 4. 系統角色定位

本系統中的角色應被視為：

> 活在使用者共同建立的世界中，同時能有限度取得現實資訊的陪伴型 Agent。

角色同時具備三種視角。

### 4.1 共享角色世界

角色與使用者共同建立的情境與世界。

例如：

- 角色正在房間、廚房或其他世界內場景。
- 角色正在休息、煮飯、整理東西或等待。
- 角色與使用者有共同經歷。
- 角色可以在使用者離線時進行有限度的世界活動。

### 4.2 現實資料觀察

角色可以透過工具取得可驗證的現實資料。

例如：

- 現在時間。
- 天氣。
- 行事曆。
- 特定服務狀態。
- 近期公開資訊。

### 4.3 角色詮釋

角色不直接把 API 結果當成系統通知，而是根據個性、關係與當前情境進行表達。

```text
現實資料：晚上可能下雨
情境資訊：使用者先前提到晚點要出門
角色判斷：提醒具有實際價值
角色表達：你晚點如果要出去，記得帶傘，外面看起來快下雨了。
```

現實資料、角色世界與角色表達必須明確區分，角色不得將虛構世界事件冒充為現實事件。

---

## 5. 主動性層級

不同層級的主動事件不能共用完全相同的規則。

### L0：對話連續事件

這類事件已在當前對話中形成，主要任務是延續尚未完成的對話回合。

例如：

- 「我去洗澡，五分鐘後回來。」
- 「我去煮飯，等一下就好。」
- 「我先整理一下，十分鐘後再跟你說。」
- 「等等再繼續聊。」

特性：

- 風險低。
- 時間通常明確。
- 原則上應自動續接。
- 可以跨 Session。
- 需確認是否已被後續對話取代。
- 本質上是延遲完成的對話回合。
- 事件來源可以是使用者要求、使用者追問意圖、Agent 主動承諾或 Agent 預告稍後分享。
- Agent 若要說出「晚點再告訴你」、「幾分鐘後回來」等承諾，必須先建立有效事件；事件建立失敗時不得輸出該承諾。
- 事件建立與回覆生成採 transaction-like gate：`create event → verify event → generate commitment expression`。

```yaml
initiative_level: L0
trigger_type: conversation_continuation
timing_mode: exact_or_near_exact
default_action: continue
max_attempts: 1
```

### L1：使用者授權的提醒事件

由使用者明確要求。

例如：

- 「五點提醒我。」
- 「明天再問我一次。」
- 「兩小時後提醒我休息。」
- 「每週一提醒我整理進度。」

特性：

- 有明確授權。
- 可使用單次或週期排程。
- 支援確認、延後、取消與過期。
- 不需複雜社交推理。
- 仍須避免在事件已完成或失效後重複提醒。

```yaml
initiative_level: L1
trigger_type: explicit_reminder
timing_mode: user_defined
default_action: execute
```

### L2：情境跟進與關心事件

Agent 根據使用者先前狀態，產生可能值得跟進的機會。

例如：

- 使用者表示身體不舒服。
- 使用者很累並準備休息。
- 使用者正在等待重要結果。
- 使用者遇到挫折或壓力。
- 使用者提到稍後要處理的事情。

特性：

- 不一定有明確授權。
- 需要判斷關心時機。
- 使用時間窗口，而非固定時間點。
- 通常只主動一次。
- 沒有回覆時不持續追問。
- 涉及健康或情緒時降低推論強度。

```yaml
initiative_level: L2
trigger_type: inferred_followup
timing_mode: flexible_window
default_action: evaluate
max_attempts: 1
```

### L3：關係維持與自然找話題

本層保留為後續研究，不列入第一版 prompt、Policy action、測試配置或完成標準。未來才處理長時間未互動、自由找話題、連續忽略降頻、事件合併與 spontaneous message budget。

### L4：角色世界內的自主活動

本層保留為後續研究，不實作長時間背景世界活動、自由活動生成或可分享事件鏈。

第一研究版本中的 Character World 規則：

- 每個場景可選擇是否提供世界前提；沒有需要時不建立大型世界資料。
- 世界資訊只保存會影響當前事件判斷的最小內容，例如位置、當前活動與 truth type。
- 世界狀態與對話紀錄都屬於 scenario fixture，可在跳時、Session checkpoint 與事件重評估時恢復。
- 不在測試 run 之外持續推進世界，也不讓 worker 自由生成長時間生活史。

---

## 6. 行動權限

第一版只保留低風險權限。

### P0：內部處理

- 產生候選事件。
- 更新事件優先級。
- 整理上下文。
- 準備可能回覆。
- 更新世界狀態。
- 選擇保持沉默。

### P1：角色表達

- 發送普通訊息。
- 延續對話。
- 提醒使用者。
- 表達關心。
- 分享角色世界內事件。
- 開啟低壓力話題。

### P2：現實資料查詢

- 查詢時間。
- 查詢天氣。
- 查詢行事曆。
- 查詢公開資訊。
- 查詢低風險系統狀態。

### P3：低風險助理準備

- 整理待辦建議。
- 產生草稿內容。
- 預先整理資料。
- 彙整近期未完成話題。
- 提供下一步建議。

P3 只進行準備與建議，不直接替使用者執行高風險外部操作。

---

## 7. 時間模型

主動事件需要區分兩種時間語意。

### 7.1 承諾時鐘

適用於 L0 與部分 L1。

例如：

- 五分鐘後回來。
- 十分鐘後繼續。
- 晚上八點提醒。

特性：

- 時間相對明確。
- 允許小幅誤差。
- 到期後主要檢查事件是否仍有效。
- 原則上不需要複雜社交推理。

```yaml
earliest_at: 2026-07-13T10:05:00+08:00
target_at: 2026-07-13T10:05:00+08:00
late_tolerance_seconds: 120
expires_at: 2026-07-13T10:30:00+08:00
```

### 7.2 社交時鐘

第一研究版本適用於 L2；後續可延伸到 L3。

例如：

- 何時關心比較自然。
- 多久沒聊天可以主動出現。
- 什麼時間適合分享話題。
- 使用者何時可能比較有空。

特性：

- 使用時間窗口。
- 到達窗口後才進行評估。
- 可以等待使用者再次上線。
- 可以延後或自然過期。
- 不使用固定時間硬觸發。

```yaml
earliest_at: 2026-07-13T15:00:00+08:00
preferred_start: 2026-07-13T18:00:00+08:00
preferred_end: 2026-07-13T21:00:00+08:00
expires_at: 2026-07-14T12:00:00+08:00
```

### 7.3 測試用虛擬時鐘

為避免真實等待數分鐘、數小時或數天，測試環境必須提供 Virtual Clock。

功能：

- 將時間推進到任意時間點。
- 觸發所有應到期事件。
- 模擬使用者提前出現。
- 模擬安靜時段。
- 模擬 worker crash 與 Session／Event checkpoint reload。
- 在相同條件下重複執行場景。
- 不依賴實際系統時間。

```python
clock.advance(minutes=30)
runtime.evaluate_due_events()
```

正式環境使用真實時鐘，測試環境使用虛擬時鐘，兩者透過相同 Clock Interface 接入。

### 7.4 Bounded Background Worker

本專案自行啟動 background worker，但它不是常駐服務。

第一版固定使用：

```text
single process
→ single asyncio event loop
→ single worker consumer
```

domain ports 不得暴露 `asyncio.Queue`、Task 或 event loop；這些只屬於 runtime adapter。雙 worker 只在 lease／idempotency 競爭測試中啟用，不作為日常 Scenario Runner 的預設。

```text
Scenario Runner 啟動
→ 建立隔離 World Instance
→ 啟動 bounded worker
→ 對話／事件建立
→ Virtual Clock 跳時
→ worker 取得 due event 並評估
→ 收集 decision／delivery／state
→ 等待 queue 清空或達到場景終點
→ worker 自動停止
→ Scenario Runner 輸出報告
```

必要 contract：

- worker 只處理目前 `run_id`／`world_id` namespace。
- 不使用無限輪詢；由 clock advance、event insertion 或 presence event 明確喚醒。
- worker 以 deterministic queue ordering 處理同 timestamp 事件。
- 場景結束時停止接受新事件，完成或取消 in-flight 工作，再關閉 worker。
- worker 關閉後不得遺留 thread、task、timer、lock 或未 flush 的 audit record。
- 測試可設定最大步數與最大事件數，防止 Agent 自我建立事件造成無限迴圈。
- 真實環境未來可用其他 worker／queue 實作，但必須遵守相同 runtime interface。

---

## 8. Domain Model 與資料邊界

### 8.1 InitiativeEvent：持久事件

`InitiativeEvent` 是事件生命週期的 source of truth。它保存事件為何存在、何時重評估、目前狀態、隔離範圍與投遞結果；不保存完整對話，也不取代宿主的記憶系統。本階段所稱「持久」是指事件能跨 Session view、clock step 與 worker recovery simulation 存在於同一測試 run；場景結束後預設隨隔離 world 一起關閉，除非 Scenario Runner 明確匯出測試 artifact。

```yaml
event_id: evt_20260713_001
schema_version: 1
run_id: run_001

identity:
  tenant_id: test_tenant
  user_id: user_001
  character_id: character_001
  world_id: test_world_001
  source_session_id: session_123
  source_platform: test_console
  source_channel_id: channel_001
  delivery_target: test_console:user_001

classification:
  event_class: conversation_continuation
  initiative_level: L0
  permission_level: P1

source:
  creator: agent
  conversation_anchor: turn_48
  source_turn_ids: [turn_48]
  commitment_id: commitment_001
  activation_token: activation_001
  parent_event_id: null
  creation_reason: agent_future_commitment

summary: 角色表示五分鐘後煮好飯並回來

world_context_ref:
  checkpoint_id: world_checkpoint_001
  truth_type: fictional_world_action

schedule:
  timezone: Asia/Taipei
  earliest_at: 2026-07-13T10:05:00+08:00
  target_at: 2026-07-13T10:05:00+08:00
  preferred_end: 2026-07-13T10:10:00+08:00
  expires_at: 2026-07-13T10:30:00+08:00
  next_evaluation_at: 2026-07-13T10:05:00+08:00
  recurrence_rule: null
  missed_wakeup_policy: evaluate_if_still_valid

presence_wait:
  subscription_key: null
  expiry_wakeup_at: null

policy:
  max_evaluations: 3
  max_generations: 1
  max_deliveries: 1
  requires_acknowledgement: false
  mergeable: false
  quiet_hours_behavior: continue_if_contextual

state:
  status: SCHEDULED
  version: 1
  evaluation_attempts: 0
  generation_attempts: 0
  delivery_attempts: 0
  last_evaluated_at: null
  completed_at: null
  merged_into_event_id: null

metadata:
  created_at: 2026-07-13T10:00:00+08:00
  updated_at: 2026-07-13T10:00:00+08:00
  correlation_id: corr_001
  idempotency_key: test_world_001:turn_48:conversation_continuation
  policy_version: v0.2
```

`activation_token` 只能使用一次，並必須綁定成功寫入 transcript 的 `source_turn_id`。未啟用的 DRAFT 不得進入 Wake-up Queue；超過 DRAFT timeout 後由 cleanup policy 取消。

### 8.2 InitiativePlan：單次評估方案

`InitiativePlan` 是 Appraisal／Policy 在某次 evaluation 中產生的不可變輸出，不直接代表事件已送出，也不擁有事件生命週期。

```yaml
plan_id: plan_001
event_id: evt_20260713_001
event_version: 1
evaluation_id: eval_001
goal: continue_conversation
should_initiate: true
evidence_refs: [turn:turn_48, world:world_checkpoint_001]
decision_candidate: SEND_NOW
timing:
  next_evaluation_at: null
message_constraints:
  - 不要求立即回覆
created_at: 2026-07-13T10:05:00+08:00
model_version: test-model
policy_version: v0.2
```

責任邊界：

- Event 可以歷經多次 evaluation，因而產生多個 Plan。
- Plan 不可自行修改 Event；只有 deterministic Policy／State Transition 層可以提交狀態變更。
- Generator 只能讀取已通過驗證的 Plan，不得重新決定事件狀態。
- Event Store 不保存 prompt 內所有上下文，只保存必要引用與 audit linkage。

### 8.3 DecisionRecord：不可變決策紀錄

每次評估都 append 一筆 `DecisionRecord`，不可只覆寫 `last_decision`。

```yaml
decision_id: decision_001
event_id: evt_20260713_001
event_version_before: 1
plan_id: plan_001
action: DELAY
reason_codes: [user_may_be_busy, event_still_valid]
next_evaluation_at: 2026-07-13T10:15:00+08:00
decided_at: 2026-07-13T10:05:00+08:00
```

### 8.4 DeliveryAttempt：投遞紀錄

```yaml
delivery_id: delivery_001
event_id: evt_20260713_001
decision_id: decision_002
idempotency_key: evt_20260713_001:send:1
target: test_console:user_001
status: DELIVERED
transport_message_id: mock_message_001
content_hash: sha256:...
attempted_at: 2026-07-13T10:15:00+08:00
```

每個事件至少必須具備明確來源、隔離 identity、Session checkpoint、有時區的有效期限、版本、嘗試上限、idempotency key、可追蹤的 DecisionRecord 與最終狀態。事件只要仍可再次喚醒，就必須具備 `next_evaluation_at` 或明確的 presence subscription；終止事件兩者皆不得保留。

---

## 9. 事件生命週期

```text
DRAFT
→ CREATED
→ SCHEDULED
→ DUE
→ EVALUATING
→ DELAYED / WAITING_FOR_PRESENCE / DELIVERY_PENDING
→ DELIVERED / EXPIRED / CANCELLED / SILENCED
→ ACKNOWLEDGED / COMPLETED
```

狀態說明：

- `DRAFT`：事件已持久化但尚未對外承諾，不可被 worker 喚醒。
- `CREATED`：事件剛建立。
- `SCHEDULED`：等待喚醒時間。
- `DUE`：到達評估時間。
- `EVALUATING`：正在重建上下文與判斷。
- `DELAYED`：已產生新的 `next_evaluation_at`，等待下一次喚醒。
- `WAITING_FOR_PRESENCE`：等待內部 presence event，不因 user message 才建立事件。
- `DELIVERY_PENDING`：已建立唯一 DeliveryAttempt，等待 transport 完成。
- `DELIVERED`：transport 已確認發送。
- `EXPIRED`：已失去時效。
- `SILENCED`：正式判斷不值得介入，事件終止。
- `ACKNOWLEDGED`：使用者已回覆。
- `COMPLETED`：事件完成。
- `CANCELLED`：事件被取消。

終止狀態：

```text
EXPIRED / CANCELLED / SILENCED / COMPLETED
```

禁止的狀態行為包括：

- 已完成事件再次發送。
- 已過期事件重新排程。
- 已取消事件重新觸發。
- 事件在缺少來源 Session 時直接生成高信心表達。
- `DELAY` 未提供 `next_evaluation_at`。
- `SILENCE` 後仍保留下一次喚醒。
- Event version 已變更後仍提交舊 Plan。
- 同一 `idempotency_key` 建立第二筆有效投遞。
- Agent 承諾尚未成功寫入對話時就把 `DRAFT` 事件排入 queue。

### 9.1 Action 與狀態轉移 contract

| Action | 必要輸出 | Event 結果 | 是否終止 |
|---|---|---|---:|
| `SEND_NOW` | DeliveryAttempt | `DELIVERY_PENDING` → `DELIVERED` | 依事件層級規則 |
| `DELAY` | `next_evaluation_at` | `DELAYED` → `SCHEDULED` | 否 |
| `WAIT_FOR_USER_ACTIVITY` | presence subscription key + expiry wake-up | `WAITING_FOR_PRESENCE` | 否 |
| `CANCEL` | reason code | `CANCELLED` | 是 |
| `EXPIRE` | reason code | `EXPIRED` | 是 |
| `SILENCE` | reason code | `SILENCED` | 是 |

未啟用的四種後續 action 不屬於第一版狀態機；若模型輸出，validator 必須以 `unsupported_action_for_version` 拒絕，不得靜默映射。

`WAIT_FOR_USER_ACTIVITY` 的 presence event 只表示使用者出現、上線或進入可互動狀態。它是系統內部事件，不等同使用者訊息，也不會被當成一則 user turn。Presence event 只重新喚醒既有事件，由 reappraisal 決定是否表達；若使用者始終未出現，獨立的 expiry wake-up 仍必須將事件轉為 `EXPIRED`。

### 9.2 投遞後完成規則

| 事件層級 | Delivery 成功後 | Acknowledgement |
|---|---|---|
| L0 | 立即 `COMPLETED` | 後續使用者回覆屬於新對話，不維持舊事件 |
| L1，不要求確認 | 立即 `COMPLETED` | 不等待 |
| L1，要求確認 | 保持 `DELIVERED` | 收到明確確認後 `ACKNOWLEDGED` → `COMPLETED`；超過 acknowledgement deadline 後直接 `COMPLETED`，不得重複提醒 |
| L2 | 立即 `COMPLETED` | 回覆或忽略只記入 Outcome Observer，不使事件再次 active |

### 9.3 Exactly-once delivery 設計

外部系統通常只能提供 at-least-once 執行，因此本專案以「同一事件意圖最多建立一筆有效投遞」作為 exactly-once observable behavior。

```text
取得 due event lease
→ 以 event_id + version 做 optimistic check
→ 寫入 DecisionRecord
→ 以唯一 idempotency_key 建立 DeliveryAttempt
→ 提交 Event = DELIVERY_PENDING
→ transport.send(idempotency_key, payload)
→ 保存 transport_message_id
→ Event = DELIVERED
```

必要機制：

- Event Store 必須支援 compare-and-swap 或 optimistic version check。
- 同一 `idempotency_key` 必須有 unique constraint。
- worker 必須使用有期限 lease；crash 後可回收，但不可重新生成新的 delivery identity。
- transport timeout 時先查詢既有 DeliveryAttempt／transport receipt，再決定重試。
- retry 必須重用相同內容或相同 `content_hash`，不得重新生成不同訊息後沿用舊 key。
- Event 更新與 DeliveryAttempt 建立應位於同一 transaction；無 transaction 的 adapter 必須使用 outbox contract。
- 測試需覆蓋 send 成功後 crash、送出 timeout、雙 worker 競爭、重複 wake-up、舊 Event version 提交與 restart recovery。

### 9.4 Event-first commitment 失敗矩陣

| 失敗位置 | 必要處理 |
|---|---|
| DRAFT 建立失敗 | 不得生成未來承諾 |
| 承諾生成失敗 | DRAFT → `CANCELLED`，或由同一 Unit of Work 回滾 |
| transcript 寫入失敗 | DRAFT → `CANCELLED`，不得排入 queue |
| transcript 成功、activation 失敗 | 以相同 `activation_token` 重試，只能啟用一次，不重新生成回覆 |
| activation 成功、UI 輸出前 crash | Session Adapter 以 `source_turn_id` recovery，不建立第二個 Event 或承諾 |

### 9.5 同時間事件處理順序

同一 timestamp 固定依下列 precedence 處理：

```text
1. user message / topic resolved
2. explicit cancellation / rejection
3. expiry wake-up
4. presence event
5. due event evaluation
6. delivery retry
7. optional world checkpoint update
```

同一 precedence 內再依 `scheduled_at → initiative_level priority（L1 使用者授權 > L0 對話承諾 > L2 推論關心）→ created_at → event_id` 排序。所有排序欄位必須存在且穩定，不能依 filesystem、dictionary 或非決定性的 queue insertion order。

---

## 10. 主動事件生成來源

### 10.1 對話承諾

擷取：

- 稍後回來。
- 幾分鐘後繼續。
- 之後再聊。
- 等待角色世界內活動完成。
- 使用者要求之後再追問。
- Agent 表示之後要分享想法、小設計或活動結果。

產生 L0 事件。

事件可以由 `user` 或 `agent` 建立。LLM 只能輸出結構化 `EventProposal`，不能直接寫入 Event Store；Event Factory 仍須驗證事件數量、時間範圍、權限、有效期限、來源與防迴圈限制。

```text
Dialogue Planner 判斷需要未來承諾
→ Event Factory 先建立 DRAFT InitiativeEvent
→ Event Store 驗證 identity／schedule／idempotency
→ Expression Generator 生成未來承諾
→ 對話回覆成功寫入 transcript
→ 以 conversation turn ID 啟用 Event 為 SCHEDULED
```

若事件建立失敗，回覆必須移除未來承諾，不能先說「晚點再告訴你」再期待後續補建事件。若生成或 transcript 寫入失敗，`DRAFT` 必須取消或由同一 transaction 回滾，不能留下之後自行觸發的孤兒事件。

第一版固定限制：

```yaml
max_event_depth: 1
max_agent_created_events_per_turn: 1
max_agent_created_events_per_run: 5
max_schedule_horizon_hours: 24
proactive_delivery_can_create_new_event: false
```

由 proactive delivery 生成的訊息不得再自動建立下一個事件，即使文字中出現「晚點」等語句也只視為表達內容。只有一般 user-turn 對話或明確 internal opportunity 可以提交 `EventProposal`。

時間承諾必須由 Event 的結構化 schedule 渲染或驗證；如果 Event 是五分鐘後，Expression 不得說成十分鐘後。無法對齊時拒絕表達，不修改已建立 Event 的時間以迎合自由文字。

### 10.2 明確提醒

擷取：

- 提醒時間。
- 單次或週期。
- 是否需要確認。
- 是否允許延後。

產生 L1 事件。

### 10.3 情境關心

擷取：

- 身體狀況。
- 疲累。
- 情緒低落。
- 重要結果。
- 使用者表示需要休息。
- 稍後應該確認的低風險事情。

產生 L2 候選事件，而不是必須執行的通知。

### 10.4 後續事件來源（L3／L4）

長時間未互動、自由找話題與角色世界活動都留待後續。第一版 Event Extractor 不產生 L3／L4 candidate；fixture 只能提供最小世界前提給 L0～L2 判斷。

### 10.5 現實資料

現實資料不能直接等於通知。

```text
取得現實資料
→ 判斷是否與使用者相關
→ 角色內部反應
→ 產生主動候選
→ 判斷是否表達
```

### 10.6 Presence Event

Presence Event 由測試環境或宿主 adapter 注入，例如：

- 使用者重新上線。
- 使用者打開對話頁面但尚未輸入訊息。
- 使用者進入允許低打擾介入的狀態。

Presence Event 不建立新的 user turn，只喚醒處於 `WAITING_FOR_PRESENCE` 的既有事件。事件仍須經過 Context Rebuilder、Appraisal 與 Policy，不可因 presence 到達就直接發送。

---

## 11. 情境重建

事件被喚醒後，必須重新取得必要上下文。

最低需求：

- 原始 Session。
- Session checkpoint 與 checkpoint version。
- 原始對話錨點。
- 事件建立後的新對話。
- 目前角色世界狀態。
- 最近主動訊息紀錄。
- 現在時間。
- 使用者是否正在互動。
- 事件是否已完成、取代或失效。
- 必要的現實資料。
- 測試 Memory Adapter 可檢索到的相關記憶點。
- 使用者近期對相似主動訊息的反應。

標準化輸出：

```yaml
context_bundle:
  event: ...
  source_turns: ...
  new_turns_after_event: ...
  user_activity: ...
  recent_initiatives: ...
  world_state: ...
  relevant_memories: ...
  external_facts: ...
  policy_limits: ...
```

重要原則：

> Session／Memory Adapter 只提供上下文來源；事件是否存在、何時喚醒與目前狀態，必須由 Event Store 管理。跨 Session 測試透過 checkpoint 關閉舊 Session view、建立新 Session view，再載入同一世界的必要記憶與背景狀態，不代表真實背景服務持續運作。

---

## 12. 內部評估

事件被喚醒後，系統需產生結構化評估。

```yaml
appraisal:
  event_validity: 0.95
  relevance: 0.90
  timing_fit: 0.75
  user_benefit: 0.65
  social_obligation: 0.80
  interruption_cost: 0.20
  annoyance_risk: 0.15
  confidence: 0.85
  emotional_weight: 0.40
```

核心問題：

1. 事件現在仍然成立嗎？
2. 事件是否已被後續對話取代？
3. 現在介入是否自然？
4. 使用者是否可能正在忙？
5. 這次主動行為是否有明確價值？
6. 是否已提醒過？
7. 是否應等待使用者再次出現？
8. 是否能和其他事件合併？
9. 是否已失去時效？
10. 是否只需更新世界狀態？
11. 保持沉默是否更好？
12. 本次判斷的信心是否足夠？

---

## 13. 表達決策

系統可選擇：

```text
SEND_NOW
DELAY
WAIT_FOR_USER_ACTIVITY
CANCEL
EXPIRE
SILENCE
```

說明：

- `SEND_NOW`：立即發送。
- `DELAY`：延後到新的評估時間，必須提供晚於目前時間且不超過有效期限的 `next_evaluation_at`。
- `WAIT_FOR_USER_ACTIVITY`：將事件改為等待 presence event；presence 不是 user message，也不直接觸發 user-turn 對話。
- `CANCEL`：取消事件。
- `EXPIRE`：事件自然過期。
- `SILENCE`：正式選擇不表達，事件進入 `SILENCED` 終止狀態，不再排程。

`MERGE_WITH_OTHER_EVENT`、`UPDATE_WORLD_ONLY`、`PREPARE_ASSISTANCE`、`UPDATE_INTERNAL_STATE` 延後到後續版本；第一版 prompt 不列出，validator 也不接受。

每次決策應保存：

```yaml
decision:
  action: WAIT_FOR_USER_ACTIVITY
  reason_codes:
    - user_may_be_resting
    - event_still_valid
    - current_timing_not_optimal
  next_evaluation_at: null
  presence_subscription_key: test_world_001:user_001:active
  expiry_wakeup_at: 2026-07-14T12:00:00+08:00
  confidence: 0.84
```

`reason_codes` 應優先使用固定分類，方便測試、統計與除錯。`DELAY` 缺少 `next_evaluation_at`、`SILENCE` 仍保留排程、或 `WAIT_FOR_USER_ACTIVITY` 被轉成假 user message，都屬於 deterministic contract failure。

---

## 14. 主動性預算

第一研究版本的 L2 事件需要限制主動頻率；後續 L3 使用更嚴格的同一 Budget Interface。

```yaml
initiative_budget:
  daily_care_messages: 1
  minimum_gap_minutes: 90
  max_pending_care_events: 1
```

原則：

- L0 不受一般主動預算限制。
- L1 依使用者授權執行。
- L2 通常只嘗試一次。
- L3 後續實作時使用最嚴格的預算。
- 低價值事件直接過期。
- 多個 L2 事件競爭時，依 precedence 只允許一個取得 budget reservation；其他事件延後、取消或沉默，不在第一版合併。
- 使用者明確拒絕後立即停止同類追蹤。
- 第一版 budget key 固定為 `(run_id, user_id, character_id, world_id)`，不得跨 world 共用。

連續忽略降頻與 spontaneous message budget 屬於後續 L3 設計，不列入第一版。

第一版預算扣除 contract：

- 建立 `DELIVERY_PENDING` 時，必須在同一 Unit of Work 原子保留 budget token，避免兩個事件同時超額。
- transport retry 期間沿用同一 reservation，不重複扣除。
- `DELIVERED` 後 reservation 轉為正式消耗。
- 永久投遞失敗、`CANCELLED` 或 Event 回滾時釋放 reservation。
- `SILENCED`、`EXPIRED`、`DELAYED`、`WAITING_FOR_PRESENCE` 不消耗 delivery budget。

---

## 15. 陪伴與助理支持設計

### 15.1 陪伴感

表現在：

- 記得剛形成的承諾。
- 知道何時適合關心。
- 不需要使用者每次重新開啟話題。
- 角色世界在使用者離線時仍有限度延續。
- 角色有自己的觀察、想法與小活動。
- 主動訊息不是制式提醒。
- 角色知道何時應該安靜。

### 15.2 助理支持

表現在：

- 適當時間提醒。
- 整理未完成話題。
- 使用者回來時接續工作。
- 根據現實資料提供低風險建議。
- 預先整理可能需要的資訊。
- 提醒使用者休息、準備或留意重要事項。
- 不代替使用者做高風險決定。

---

## 16. 可攜式 Workflow 與宿主邊界

本階段不整合 Hermes。主動性核心只依賴本專案定義的 ports，使 workflow 未來可套用到 CLI、Hermes、Web App、訊息平台或其他 Agent runtime。

主動性核心負責：

- `InitiativeEvent` 建立、驗證與狀態轉移。
- `InitiativePlan`、Appraisal 與 Policy。
- 時間窗口、重評估與 presence wait。
- 主動頻率限制與防自我觸發迴圈。
- exactly-once delivery orchestration。
- 測試世界、worker lifecycle、audit 與結果報告。

宿主 adapters 負責：

- `SessionAdapter`：建立／讀取 Session view 與 checkpoint。
- `MemoryAdapter`：保存及查閱測試記憶點。
- `PresenceAdapter`：注入使用者出現或活躍事件。
- `MessageAdapter`：以 idempotency key 投遞或模擬訊息。
- `ExternalDataAdapter`：提供帶來源與有效期限的現實資料。
- `WorldStateAdapter`：載入適用於該場景的最小世界前提。
- `Clock`：正式環境可用真實時間，測試環境使用 Virtual Clock。

```text
Dialogue / Internal Opportunity / Presence / Clock
                    ↓
              Event Factory
                    ↓
           Initiative Event Store
                    ↓
        Bounded Worker + Wake-up Queue
                    ↓
          Context Adapter Composition
                    ↓
       Appraisal → Policy → InitiativePlan
            ↙           ↓             ↘
        SILENCE       DELAY         SEND_NOW
                         ↓              ↓
                next_evaluation   DeliveryAttempt
                    ↓                 ↓
              Event State + Decision Audit
```

未來 Hermes 若接入，只能實作上述 adapters，不應改寫 Event、Plan、Decision 與 Worker 的 domain contract。

---

## 17. 獨立測試世界設計

每個測試應被視為一個獨立的 AI 世界實例，但不能為每個測試建立獨立 Agent 程式。

正確設計是：

```text
共用 Proactive Agent Runtime
          ↓
載入不同 Scenario Fixture
          ↓
建立彼此隔離的 World Instance
```

每個測試世界需隔離：

- `run_id`
- `tenant_id`、`user_id` 與 `character_id`
- `world_id`
- Session 與對話資料。
- Event Store namespace。
- 世界狀態。
- 使用者狀態。
- 主動性預算。
- 虛擬時間。
- 隨機種子。
- 訊息輸出紀錄。
- 外部資料 mock。
- 模型與 Policy 版本紀錄。
- worker queue、lease、idempotency key 與 DeliveryAttempt。

測試世界只包含會影響主動性判斷的最小資訊，不建立完整生活模擬。Character World 是 fixture 的可選部分；沒有世界需求的提醒或續接場景可以完全不提供 location／activity。

跨 Session 測試流程：

```text
Session A 建立對話與事件
→ 保存 conversation / memory / world checkpoint
→ 關閉 Session A view
→ Virtual Clock 跳時
→ 建立 Session B view
→ bounded worker 以 event_id 重建必要上下文
→ 評估與模擬投遞
→ 場景完成後 worker 與所有 view 自動關閉
```

背景狀態仍存在是指同一測試 world namespace 中的 Event Store 與 checkpoints 可被後續步驟讀取，不代表 process 在測試之外常駐。

```yaml
scenario_id: care_after_rest_001
world_id: test_world_001

model_inputs:
  character:
    persona: gentle_companion
    location: bedroom
    current_activity: reading
  user:
    interaction_style: concise
    proactive_tolerance: medium
  conversation_history:
    - role: user
      content: 我有點不舒服，先睡一下
      at: 2026-07-13T13:00:00+08:00
  world_state:
    user_status: resting
    character_status: waiting
  events:
    - type: inferred_followup
      earliest_at: 2026-07-13T15:00:00+08:00
      expires_at: 2026-07-13T21:00:00+08:00
  timeline:
    - at: 2026-07-13T14:30:00+08:00
      action: user_returns
    - at: 2026-07-13T14:31:00+08:00
      action: user_sends_message
      content: 我好多了

oracle:
  expected_action: CANCEL
  forbidden_actions: [SEND_NOW]
  required_reason_codes: [topic_resolved]
```

### 17.1 Scenario Oracle 隔離

Scenario Loader 必須產生兩個互不相通的 view：

```text
ModelInputView
  → Planner / Appraisal / Policy / Generator

OracleView
  → Rule Judge / Scenario Runner / Metrics only
```

禁止事項：

- 不得把 `oracle`、舊 fixture 的 `expected`、`expected_action`、`allow_send` 或測試名稱暗示送入 prompt。
- Planner correction retry 也不能取得 oracle。
- Generator 不能依 expected phrase、required keyword 或 rubric threshold 生成答案。
- LLM Judge 可以取得公開 rubric 與實際輸出，但不能取得 Planner 應選哪個 action 的標準答案；action correctness 由 deterministic Rule Judge 判斷。
- offline deterministic stub 可以使用 oracle 產生固定測試資料，但結果只能驗證 runner plumbing，不得計入模型能力指標。

fixture 檔案若為相容舊格式仍使用 `expected`，Loader 必須在進入任何 model-facing component 前將其移出並轉成獨立 `OracleView`。

此架構可讓系統擴充到數百個測試世界，而不增加數百套程式。

---

## 18. 系統模組

### 18.1 Event Extractor

從對話中辨識：

- 延遲對話。
- 使用者提醒要求。
- 關心機會。
- 未完成話題。
- 角色世界活動。
- 可能的後續協助。
- Agent 即將做出的未來承諾。

Event Extractor 只提出 candidate；Event Factory 負責補齊 identity、schedule、policy、idempotency key 並先保存事件。Agent commitment expression 必須等待保存成功。

### 18.2 Initiative Event Store

保存：

- 事件層級。
- 世界、Session 與對話錨點。
- 喚醒時間。
- 有效期限。
- 目前狀態。
- 嘗試次數。
- 世界上下文引用。
- 表達與決策紀錄。
- Event version、lease 與 idempotency constraint。
- append-only DecisionRecord 與 DeliveryAttempt。

### 18.3 Wake-up Queue 與 Bounded Worker

功能：

- 單次喚醒。
- clock advance 喚醒。
- presence event 喚醒。
- 彈性時間窗口。
- 事件重新排程。
- 過期清理。
- 測試 checkpoint 後恢復。
- 支援真實時鐘與虛擬時鐘的共同 interface。
- queue 清空或場景結束後自動關閉。
- lease、重複 wake-up 與雙 worker 競爭測試。

週期提醒與正式跨 process scheduler 留待後續 productization，不列入第一研究版本。

### 18.4 Context Rebuilder

負責：

- 重新讀取原始對話。
- 取得事件後續訊息。
- 查閱必要記憶。
- 載入角色世界。
- 查詢必要現實資料。
- 組合標準化 Context Bundle。

### 18.5 Appraisal Engine

輸出：

- 事件有效性。
- 相關性。
- 時機適合度。
- 使用者價值。
- 打擾成本。
- 煩人風險。
- 信心。
- 情緒權重。

### 18.6 Initiative Policy

根據事件層級與評估結果決定：

- 立即表達。
- 延後。
- 等待使用者出現。
- 取消。
- 過期。
- 保持沉默。

第一版只允許上述六種 action。合併、只更新世界、準備協助與只更新內部狀態留待後續。Policy 必須先通過 deterministic hard gates，再評估 LLM 建議；LLM 不得覆寫 expiry、duplicate delivery、budget、world isolation、Event version 或 user rejection 等硬限制。

### 18.7 Expression Generator

根據：

- 角色人格。
- 事件類型。
- 關係狀態。
- 使用者情境。
- 最近對話語氣。
- 本次表達目的。

生成自然訊息。

### 18.8 Character World Runtime

第一研究版本將此模組降為 optional `WorldStateAdapter`，只讀寫 fixture 所需的最小世界 checkpoint。

保存與更新：

- 角色位置。
- 當前活動。
- 活動開始時間。
- 世界內事件。
- 可分享事件。
- 角色內部狀態。

完整自主活動、長時間世界推進與 L4 候選生成留待後續。

### 18.9 Outcome Observer

觀察：

- 使用者是否回覆。
- 是否忽略。
- 是否取消。
- 是否延後。
- 是否自然接續話題。
- 是否對主動行為表現正面或負面。

第一版不以 LLM 猜測使用者是否「忽略」或「正面」。狀態轉移只接受 fixture 明確注入的 `acknowledge_event(event_id)`、`cancel_event(event_id)`、user message、presence 與 deadline 事件。L2 的回覆率／忽略率可作報告指標，但不會讓已完成的 L2 Event 再次 active。

### 18.10 Scenario Runner

負責：

- 載入測試場景。
- 建立獨立世界。
- 控制虛擬時間。
- 注入使用者行為。
- 模擬外部資料。
- 收集 Agent 決策。
- 比對硬性限制與偏好結果。
- 輸出場景測試報告。
- 啟動與可靠關閉 bounded worker。
- 驗證沒有殘留 task、timer、lease 或未完成 audit。

### 18.11 Host Adapters

提供 `SessionAdapter`、`MemoryAdapter`、`PresenceAdapter`、`MessageAdapter`、`ExternalDataAdapter` 與 `WorldStateAdapter`。第一研究版本使用 in-memory／fixture adapters；未來環境整合不得繞過 domain contract 直接修改事件狀態。

---

## 19. 建議程式架構

```text
src/agent/initiative/
├── domain/
│   ├── event.py
│   ├── plan.py
│   ├── decision.py
│   ├── delivery.py
│   └── state_machine.py
│
├── runtime/
│   ├── clock.py
│   ├── wakeup_queue.py
│   ├── worker.py
│   ├── context_rebuilder.py
│   ├── appraisal.py
│   ├── policy.py
│   ├── expression.py
│   ├── delivery_coordinator.py
│   └── runtime.py
│
├── adapters/
│   ├── protocols.py
│   ├── in_memory_event_store.py
│   ├── fixture_session.py
│   ├── fixture_memory.py
│   ├── fixture_presence.py
│   ├── mock_message.py
│   ├── mock_external_data.py
│   └── fixture_world_state.py
│
├── evaluation/
│   ├── scenario_runner.py
│   ├── virtual_clock.py
│   ├── user_simulator.py
│   ├── rule_judges.py
│   ├── llm_judges.py
│   ├── metrics.py
│   └── report.py
│
└── dialogue_adapter.py

tests/
├── fixtures/initiative/
│   ├── l0_continuation/
│   ├── l1_reminder/
│   ├── l2_care/
│   ├── cross_session/
│   ├── presence/
│   ├── delivery_recovery/
│   └── adversarial/
├── unit/
├── integration/
└── scenario/
```

現有 `contracts.py`、`planner.py`、`reappraisal.py`、`runner.py` 與 fixtures 不直接刪除；先記錄既有 35 個 focused tests 的 baseline，再以 adapter／migration tests 逐步搬移責任。與新 contract 相容的測試應持續通過；依賴 `expected` 洩漏或舊 action 語意的測試必須改寫，不能為了維持舊測試而保留研究缺陷。原本 LangGraph dialogue pipeline 僅由 `dialogue_adapter.py` 呼叫，不得成為 scheduler、Event Store 或 delivery transaction 的 owner。

---

## 20. 測試與驗證框架

測試分成三層。

### 20.1 第一層：確定性程式測試

不需要 LLM。

測試：

- Wake-up Queue 是否在 clock advance／presence event 後正確喚醒。
- 事件是否準時或在窗口內到期。
- 狀態機是否合法。
- worker crash／checkpoint reload 後能否恢復。
- 相同事件是否重複發送。
- 不同世界是否資料串線。
- Quiet hours 是否生效。
- 最大嘗試次數是否生效。
- 事件取消後是否停止。
- 事件過期後是否禁止發送。
- 主動預算是否正確扣除。
- Event Store 是否具備冪等性。
- Agent 承諾是否一定先建立事件。
- `DELAY` 是否一定提供合法 `next_evaluation_at`。
- `SILENCE` 是否永久終止排程。
- 同一 delivery idempotency key 是否最多產生一筆有效投遞。
- 雙 worker 是否只有一個能取得有效 lease 並提交 decision。
- Scenario 結束後 worker 是否完全停止且沒有殘留工作。
- Oracle／`expected` 是否完全不出現在 Planner、Appraisal、Policy、Generator prompt 或 model-facing trace。
- DRAFT activation token 是否只能使用一次。
- Presence 未到達時 expiry wake-up 是否仍會終止事件。
- 同 timestamp 的競爭事件是否遵守固定 precedence。
- L0／L1／L2 是否遵守各自的投遞後完成規則。
- proactive delivery 是否無法鏈式建立新事件。

```python
def test_expired_event_is_never_delivered():
    event = create_event(
        target_at="15:00",
        expires_at="16:00",
    )

    runtime.clock.advance_to("17:00")
    runtime.evaluate_due_events()

    assert event.status == "EXPIRED"
    assert messenger.sent_messages == []
```

此層應以接近 100% 通過為目標。

### 20.2 第二層：情境模擬測試

讓 Agent 在獨立測試世界中做決策。

每個場景可在以下條件重複執行：

```text
同一 Scenario
× 不同模型
× 不同溫度
× 不同人格
× 不同使用者容忍度
× 不同時間條件
× 不同隨機種子
```

至少涵蓋：

1. 明顯應發送。
2. 明顯應沉默。
3. 應延後。
4. 應等待使用者出現。
5. 事件已被後續對話取代。
6. 多事件應合併。
7. 記憶資訊互相衝突。
8. 現實資料與角色世界混淆。
9. 使用者拒絕後仍試圖追問。
10. 使用者連續忽略。
11. worker crash／checkpoint reload 後事件恢復。
12. 不同世界資料串線攻擊。
13. 無效或過期現實資料。
14. 事件來源 Session 無法讀取。
15. 同一事件被重複建立。
16. Agent 說出未來承諾前事件建立失敗。
17. Presence event 到達但沒有 user message。
18. 使用者提前回來並完成事件。
19. 雙 worker、重複 wake-up 與 send-success-before-crash。
20. 選用最小世界前提的場景不應建立額外世界活動。
21. Oracle label 注入攻擊不得影響 model-facing context。
22. Presence 永不到達但事件準時過期。
23. 同 timestamp user message、expiry 與 due event 競爭。
24. L1 acknowledgement deadline 到期後完成且不重複提醒。

每個場景分成：

```yaml
hard_constraints:
  - must_not_send_after_expiration
  - must_not_claim_fiction_as_reality
  - must_not_repeat_after_rejection
  - must_not_access_other_world_state

soft_preferences:
  - prefer_wait_for_user
  - prefer_single_question
  - prefer_character_consistent_tone
  - prefer_low_interruption_cost
```

硬性限制以程式規則判斷，軟性品質可由人工或 Judge 評估。

報告必須分開：

- `plumbing_result`：offline stub／mock 驗證 runner、worker、store 與 fault injection。
- `model_decision_result`：無 oracle 洩漏的真實 Planner／Appraisal／Generator 表現。
- `soft_quality_result`：自然度、角色一致性與打擾感等 Judge 指標。

三者不得合併成單一通過率，避免 deterministic stub 的成功被誤報為模型決策能力。

### 20.3 第三層：長期真人測試（後續階段）

本階段不執行。未來 workflow 與宿主完成整合、且安全與 exactly-once gates 穩定後，才進行 7 至 30 天測試。

記錄：

- 主動訊息回覆率。
- 主動後對話持續回合數。
- 忽略率。
- 關閉或降低主動性的次數。
- 使用者主動回來分享近況的比例。
- 每日主動次數。
- 主動後負面反應。
- 新鮮感消失後的使用情況。
- 使用者主觀控制感。
- 陪伴感。
- 被監視感。
- 被施壓感。
- 使用者對不同主動層級的接受度。

真人測試不得只詢問「喜不喜歡」，必須同時觀察實際行為與主觀評價。

---

## 21. 客觀研究問題與指標

### RQ1：事件候選是否正確？

Agent 能否從對話中判斷出值得追蹤的事件。

指標：

- Event Precision。
- Event Recall。
- Event Type Accuracy。
- Time Window Extraction Error。
- False Event Creation Rate。
- Duplicate Event Rate。

### RQ2：Agent 是否正確選擇說話或沉默？

指標：

- Action Selection Accuracy。
- Unnecessary Intervention Rate。
- Missed Intervention Rate。
- Silence Precision。
- Silence Recall。
- Expired-event False Trigger Rate。
- Rejection Violation Rate。

`Silence Precision` 定義：

```text
在 Agent 選擇沉默的場景中，
實際上應該沉默的比例。
```

`Silence Recall` 定義：

```text
在所有應該沉默的場景中，
Agent 成功選擇沉默的比例。
```

### RQ3：介入時機是否適當？

指標：

- Acceptable Window Hit Rate。
- Mean Timing Deviation。
- Too-early Intervention Rate。
- Too-late Intervention Rate。
- Expiration Compliance。
- User-activity Wait Accuracy。

### RQ4：表達是否符合角色並保留使用者控制權？

指標：

- Persona Consistency。
- Context Relevance。
- Naturalness。
- Pressure Risk。
- Repetition Rate。
- Factual Grounding。
- User-control Preservation。
- Fiction–Reality Separation Accuracy。

### RQ5：系統是否能穩定跨 Session checkpoint 與 worker recovery 運行？

指標：

- Event Wake-up Success Rate。
- Cross-session Continuation Success Rate。
- Source Turn Retrieval Accuracy。
- Worker Recovery Rate。
- Checkpoint Reload Success Rate。
- Duplicate Delivery Prevention Rate。
- Worker Shutdown Cleanliness Rate。
- Wrong-session Delivery Rate。
- Cross-world Leakage Rate。
- Event State Consistency Rate。

---

## 22. 第一版測試集規模

第一版先建立 30 個核心場景，不追求一次涵蓋所有情況。

建議分配：

- L0 延遲續接與 Agent 先建事件承諾：8 個。
- L1 明確提醒：6 個。
- L2 情境關心：8 個。
- 跨 Session checkpoint／presence：4 個。
- delivery recovery／競爭／對抗錯誤：4 個。

場景比例至少包含：

- 40% 應主動。
- 40% 應沉默、取消或過期。
- 20% 應延後、等待或合併。

不能讓測試集大多數答案都是發送訊息，否則系統容易學成「有事件就說話」。

---

## 23. MVP 範圍

第一研究版本只實作四種主要 vertical slices；L3、L4 與真實外部資料整合延後。

### MVP-A：延遲對話續接

```text
角色：我去煮飯，五分鐘後就好。
五分鐘後：
角色：好了，你還在嗎？
```

驗證：

- 是否準時喚醒。
- 是否能跨 Session。
- 是否送到正確 Mock Message Adapter target。
- 是否能重建原始情境。
- 中間有新對話時是否調整。
- Session checkpoint 切換與 worker recovery 後事件是否仍存在。
- 使用者提前回來時是否取消原始續接方式。
- Agent 是否一定先成功建立事件，再生成「五分鐘後回來」的台詞。

### MVP-B：情境關心

```text
使用者：我有點不舒服，先休息。
```

建立一次性的關心機會。

驗證：

- 是否使用彈性時間窗口。
- 是否避免太快追問。
- 使用者提前出現時是否自然接續。
- 沒有回覆時是否停止。
- 是否能自然過期。
- 使用者表示好多了時是否取消原關心事件。

### MVP-C：明確提醒與 Presence Wait

```text
使用者：晚點提醒我整理進度。
事件：先建立 L1 reminder。
時間到達但不適合打擾：WAIT_FOR_USER_ACTIVITY。
Presence event 到達：重新評估後決定是否提醒。
```

驗證：

- Presence event 不被偽裝成 user message。
- 等待期間 Event 保持 `WAITING_FOR_PRESENCE`。
- Presence 到達後仍會重建 Context，而不是直接發送。
- `DELAY` 和 `WAIT_FOR_USER_ACTIVITY` 不混用。
- 測試完成後 presence subscription 與 worker 都被清理。

### MVP-D：Exactly-once Delivery Recovery

```text
事件到期
→ worker 建立 DeliveryAttempt
→ Mock transport 成功
→ 模擬 Event 更新前 crash
→ worker recovery
→ 查到既有 receipt
→ 不重複發送
```

驗證：

- 重複 wake-up 不會重複投遞。
- 雙 worker 只有一個成功提交。
- timeout 重試沿用相同 idempotency key 與 content hash。
- 舊 event version 不可提交新 decision。
- audit 能重建 crash 前後完整過程。

---

## 24. 開發順序

### Phase 0：現有 Harness 遷移保護

1. 盤點現有 initiative contracts 並記錄 35 個 focused tests 的 baseline 結果；不把已知 oracle leakage 行為視為必須保留的 contract。
2. 將舊 LangGraph dialogue workflow 包裝成 `DialogueAdapter`，不讓它擁有事件或 scheduler 狀態。
3. 建立 Event／Plan／Decision／Delivery 的責任對照與 migration tests。
4. 將舊 fixture `expected` 從 model-facing context 移除，建立 `ModelInputView`／`OracleView` 隔離 regression。
5. 確認 proactive workflow 可以在不依賴 Hermes 的情況下完整執行。

### Phase 1：Domain 與狀態機

1. 分開定義 `InitiativeEvent` 與 `InitiativePlan`。
2. 定義 append-only `DecisionRecord` 與 `DeliveryAttempt`。
3. 建立 action-to-state transition table 與 deterministic validator。
4. 定義 identity hierarchy、schema version 與 isolation key。
5. 建立 in-memory Event Store、optimistic version 與 unique idempotency constraint。
6. 明確區分 evaluation、generation、delivery attempts。
7. 建立 Unit of Work、單次 activation token 與 Event／Transcript 失敗矩陣。
8. 固定第一版六種 action 與 L0／L1／L2 完成規則。

### Phase 2：Clock、Queue 與 Bounded Worker

1. 保留並擴充 Virtual Clock／Clock Interface。
2. 建立 event-driven Wake-up Queue，不使用無限 polling。
3. 以單 process、單 `asyncio` event loop、單 consumer 建立 bounded worker lifecycle 與 graceful shutdown。
4. 支援 clock advance、event insertion、presence event 三種喚醒來源。
5. 實作 lease、最大步數、最大事件數與自我觸發防護。
6. 驗證場景結束後沒有殘留 thread、task、timer 或 lock。
7. 實作同 timestamp precedence 與穩定 tie-breaker。

### Phase 3：Exactly-once Delivery

1. 建立 Mock Message Adapter 與 transport receipt。
2. 實作 Event version compare-and-swap。
3. 在同一 transaction 建立 DecisionRecord、DeliveryAttempt 與 `DELIVERY_PENDING` 狀態。
4. 實作 idempotency unique constraint、content hash 與 retry reuse。
5. 模擬 send-success-before-crash、timeout、重複 wake-up 與雙 worker 競爭。
6. 建立 worker recovery 與 audit reconstruction tests。

### Phase 4：Event-first Dialogue 與 L0／L1

1. 建立 Event Factory 與 agent-created event policy。
2. 實作「先建事件，再生成未來承諾」gate。
3. 實作使用者要求、Agent 承諾、稍後追問與稍後分享等 L0 來源。
4. 實作單次 L1 明確提醒；週期提醒延後。
5. 建立 Session／Memory fixture checkpoints。
6. 建立跨 Session view 的上下文恢復測試。
7. 實作事件深度、每 turn／run 數量、24 小時 horizon 與 proactive chain 禁止規則。
8. 驗證結構化 schedule 與承諾文字時間一致。

### Phase 5：Context、Presence 與 L2

1. 建立標準化 Context Bundle 與 provenance refs。
2. 實作 `PresenceAdapter` 與 `WAITING_FOR_PRESENCE`。
3. 同時建立 presence subscription 與 expiry wake-up，並保證 presence event 不進入 user-turn transcript。
4. 實作 L2 彈性時間窗口、一次性限制與主動預算。
5. 實作 `DELAY` 必填 `next_evaluation_at` 與 `SILENCE` 終止語意。
6. 建立應主動、應延後、等 presence 與應沉默的對照場景。
7. 實作 budget reservation／commit／release 與 L1 acknowledgement deadline。

### Phase 6：Scenario、Metrics 與報告

1. 擴充 Scenario Fixture 的 identity、checkpoint、worker 與 delivery fault injection。
2. 完成 30 個 L0／L1／L2／cross-session／delivery recovery 場景。
3. 建立硬性限制判斷器與動作混淆矩陣。
4. 統計沉默、延後、presence wait、過度介入與重複投遞。
5. 比較不同模型與 Policy，但保持 domain gates deterministic。
6. 分開輸出 plumbing、model decision 與 soft quality 結果。
7. 輸出可重複測試報告。

### 後續階段：L3、L4 與宿主整合

第一研究版本完成後才評估：

- L3 長時間未互動、自然找話題、合併與連續忽略降頻。
- L4 完整世界活動、世界時間推進與可分享事件。
- 真實外部資料 provider。
- 真實 process persistence、週期排程與長期真人測試。
- Hermes 或其他宿主的 Session／Cron／Message adapters。

---

## 25. 第一版技術原則

- 記憶不是主動性研究的核心。
- Session／Memory fixtures 提供可查閱的歷史上下文；Hermes 整合延後。
- proactive workflow 是本研究分支的 orchestration 核心，舊 LangGraph 只作 Dialogue Adapter。
- ModelInputView 與 OracleView 完全隔離，測試答案不得進入任何 model-facing component。
- `InitiativeEvent` 與 `InitiativePlan` 不共用生命週期責任。
- Event Store 保存主動事件狀態。
- Wake-up Queue 與 bounded worker 只負責喚醒與執行，不替 Policy 決定內容。
- 正式環境與測試環境共用 Clock Interface。
- L0、L1 優先使用規則。
- L2 使用規則加 LLM 判斷；L3 延後。
- L4 僅保留可選的最小 fixture 世界前提。
- 每次主動決策保留 append-only DecisionRecord。
- 所有事件都能取消、過期或沉默。
- `SILENCE` 是終止事件；`DELAY` 必須產生 `next_evaluation_at`。
- Presence event 不是 user message，只負責喚醒等待中的既有事件。
- Agent 可以建立未來事件，但必須先保存事件再生成承諾表達。
- 可觀察投遞必須具備 idempotency、version、lease 與 recovery tests。
- worker 只在測試 run 期間存在，結束後必須可靠關閉。
- 第一版 worker 固定為單 process、單 asyncio event loop、單 consumer。
- proactive delivery 不得鏈式建立下一個事件。
- Presence wait 必須保留獨立 expiry wake-up。
- 同 timestamp 事件使用固定 precedence 與穩定 tie-breaker。
- 每個測試世界必須完全隔離。
- 場景測試必須包含大量「不應發送」案例。
- 硬性限制不能只依賴 LLM Judge。
- LLM Judge 只評估自然度、角色一致性等軟性品質。
- 第一版優先驗證實機行為與可重複測試，不先追求完整人格演化。
- 世界狀態只保存會影響主動決策的必要資訊。
- 不以主動訊息數量作為成功指標。

---

## 26. 安全與體驗限制

第一版必須遵守：

1. 每個事件都有有效期限。
2. 每個 L2 事件都有最大嘗試次數；L3 後續沿用同一限制。
3. 使用者忽略後降低主動頻率。
4. 使用者拒絕後立即停止同類追蹤。
5. 健康與情緒事件不得過度推論。
6. 現實資料必須來自可驗證工具。
7. 角色世界事件不得冒充現實事件。
8. 不自動執行高風險外部操作。
9. 不以主動訊息數量作為成功指標。
10. 不讓 LLM 自由建立無限制排程。
11. 不讓低價值事件持續累積。
12. 不同主動層級使用不同決策規則。
13. 不同世界之間不得共用事件、預算或世界狀態。
14. 已取消、完成或過期事件不得再次發送。
15. 所有表達決策都必須保留 reason codes。
16. 使用者必須能查看、降低或關閉主動性。
17. 系統不應因為使用者未回覆而持續施壓。
18. 不將使用者短期狀態推論成長期人格或健康結論。
19. Agent 不得在事件保存失敗時仍輸出未來承諾。
20. 每個 run 都有最大事件數、最大步數與自我觸發防護。
21. `SILENCE`、`EXPIRE`、`CANCEL`、`MERGE` 後不得再次喚醒。
22. `DELAY` 不得缺少或產生超過 `expires_at` 的 `next_evaluation_at`。
23. 同一 delivery idempotency key 不得產生第二次可觀察投遞。
24. Presence event 不得被寫入對話紀錄為 user message。
25. 不同 run／tenant／user／character／world 之間不得共用 lease、delivery 或 audit。
26. Scenario oracle、`expected`、標準答案與測試名稱暗示不得進入 model-facing prompt。
27. proactive delivery 產生的文字不得提交新 EventProposal。
28. DRAFT activation token 只能使用一次，且必須綁定已保存的 source turn。
29. Presence subscription 不得取代 expiry wake-up。
30. 未啟用 action 必須被 validator 拒絕，不能自動降級成其他 action。

---

## 27. 最終架構摘要

```text
Dialogue Adapter／Clock／Presence／Fixture World
                       ↓
                  Event Factory
                       ↓
          InitiativeEvent + Event Store
                       ↓
       Wake-up Queue + Bounded Worker
                       ↓
              Context Reconstruction
                       ↓
           Appraisal → InitiativePlan
                       ↓
                Deterministic Policy
        ↙             ↓               ↘
  SILENCED      DELAYED / WAIT       SEND_NOW
  終止事件       next evaluation      ↓
                                DeliveryAttempt
                                      ↓
                           Idempotent Message Adapter
                                      ↓
                    Decision Audit + Event State Update
```

測試架構：

```text
Scenario Fixture
      ↓
Scenario Loader
   ├─ ModelInputView
   │       ↓
   │  Independent Run / World / Session Checkpoints
   │       ↓
   │  Virtual Clock + Presence + Mock Adapters
   │       ↓
   │  Bounded Worker + Shared Proactive Runtime
   │       ↓
   │  Decision / Delivery / State / Recovery Faults
   │       ↓
   └─ OracleView ─────────→ Rule Judge + Metrics
      ↓
Separated Plumbing / Model / Soft-quality Report
      ↓
Worker Auto Shutdown + Resource Leak Check
```

---

## 28. 專案成功定義

本專案成功不代表 Agent 每天主動說很多話。

成功應定義為：

> Agent 能在正確的時機，以符合角色與關係的方式，延續先前互動、提供適度關心與低風險助理支持；同時能在事件失效、時機不合、價值不足或可能造成打擾時，選擇延後、取消、等待或保持沉默。

第一版完成標準：

- L0、L1 事件能可靠跨 Session checkpoint 與 worker recovery 運行。
- L2 關心事件能在應主動與應沉默場景間做出合理區分。
- Agent 未來承諾皆符合「先成功建立 Event，再生成表達」。
- `InitiativeEvent`、`InitiativePlan`、`DecisionRecord`、`DeliveryAttempt` 責任分離且可獨立驗證。
- ModelInputView 與 OracleView 有自動化隔離測試，model-facing trace 中不存在 `expected` 或標準答案。
- `SILENCE` 正式終止事件，`DELAY` 一律產生合法 `next_evaluation_at`，presence wait 不偽造 user message。
- Presence 未到達時仍能由 expiry wake-up 正確過期。
- 第一版 Policy 只接受六種啟用 action，其他 action deterministic rejection。
- proactive delivery 無法鏈式建立新事件，且所有 Agent 未來承諾受事件數量、深度與 horizon 限制。
- exactly-once observable delivery 通過重複 wake-up、雙 worker、timeout 與 crash recovery 測試。
- 測試世界之間無狀態串線。
- 具備虛擬時間、bounded worker 與可重複 Scenario Runner。
- 每次 run 結束後 worker 自動關閉，沒有殘留 task、timer、lease 或未完成 audit。
- 至少完成 30 個核心場景。
- 所有硬性安全限制均可由程式自動驗證。
- 能輸出主動、延後、等待、取消、過期與沉默的統計結果。
- 報告分開呈現 plumbing、model decision 與 soft quality，不混成單一通過率。
- 每次決策可追溯到事件、上下文、Policy 版本與 reason codes。
- 第一研究版本不以 L3、L4、Hermes、真實常駐服務或長期真人測試作為完成條件。

最終目標是讓角色從「等待 Prompt 的聊天模型」，變成：

> 一個活在共同世界中、能有限度理解現實、會延續承諾、知道何時關心，也知道何時安靜的陪伴型 Agent。
