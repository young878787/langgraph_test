# 主動型角色 Agent 計畫書 v0.2

## 1. 專案定位

本專案目標是建立一套「主動型角色運行與評估架構」，讓角色不只在收到使用者訊息後才回應，而是能在沒有新輸入的情況下，根據時間、對話脈絡、角色世界、使用者狀態與可驗證的現實資料，自主判斷：

- 是否需要產生主動事件。
- 事件何時值得重新評估。
- 現在是否適合介入。
- 應該立即表達、延後、等待使用者出現，還是保持沉默。
- 主動行為是否真正對使用者有價值。
- 主動後應如何根據使用者反應更新事件狀態。

本專案的核心不是讓 Agent 替使用者執行大量現實操作，也不是建立完整人格演化或大型記憶系統，而是研究與實作：

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
- 可查閱的 Hermes 記憶。
- 必要且可驗證的現實資料。

### 2.2 系統輸出

```text
SEND_NOW
DELAY
WAIT_FOR_USER_ACTIVITY
MERGE_WITH_OTHER_EVENT
UPDATE_WORLD_ONLY
PREPARE_ASSISTANCE
UPDATE_INTERNAL_STATE
CANCEL
EXPIRE
SILENCE
```

主動性系統的重點不是產生更多訊息，而是做出更適合的介入決策。

---

## 3. 專案範圍

### 3.1 本階段包含

本階段聚焦於陪伴與低風險助理支持：

- 延遲對話續接。
- 角色世界內的短期行動延續。
- 使用者明確要求的提醒。
- 根據情境產生的一次性關心。
- 長時間未互動後的自然開場。
- 根據近期對話產生話題。
- 根據現實資料提供低風險提醒或建議。
- 使用者回來時自然接續先前內容。
- 跨 Session 保存待處理事件。
- 角色在使用者離線時維持有限世界狀態。
- 事件是否表達、延後、取消或沉默的可重複測試。
- 不同測試世界之間的資料隔離。

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

現實工具在本階段主要用於查詢與輔助判斷，例如：

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

沒有明確提醒，也沒有必須完成的任務，但角色可能希望維持互動。

例如：

- 很久沒有與使用者對話。
- 想起之前沒有聊完的內容。
- 找到符合使用者興趣的話題。
- 角色世界中發生了可分享的小事件。
- 根據近期對話產生新的想法。
- 隨口分享、吐槽或輕度閒聊。

特性：

- 最能產生陪伴感。
- 也最容易造成打擾。
- 必須有主動性預算。
- 必須考慮近期是否已主動聯絡。
- 事件可以自然過期。
- 不能只因為計時器到期就發送。

```yaml
initiative_level: L3
trigger_type: relationship_or_topic
timing_mode: opportunity_window
default_action: silence_unless_worthwhile
```

### L4：角色世界內的自主活動

角色在使用者沒有互動時，仍可進行有限度的世界內活動。

例如：

- 整理房間。
- 做料理。
- 看資料。
- 進行角色興趣活動。
- 對先前話題產生新想法。
- 經歷一個之後可能分享的小事件。

特性：

- 不一定立即發送訊息。
- 可以只更新世界狀態。
- 可以產生「之後可能分享」的候選事件。
- 不應無限制隨機編造重大經歷。
- 由世界規則、角色個性與近期情境約束。

```yaml
initiative_level: L4
trigger_type: character_world_activity
timing_mode: background_runtime
default_action: update_world_state
```

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

適用於 L2 與 L3。

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
- 模擬系統重啟後恢復。
- 在相同條件下重複執行場景。
- 不依賴實際系統時間。

```python
clock.advance(minutes=30)
runtime.evaluate_due_events()
```

正式環境使用真實時鐘，測試環境使用虛擬時鐘，兩者透過相同 Clock Interface 接入。

---

## 8. 主動事件資料模型

事件系統只保存主動性運行所需的最小資訊，不取代 Hermes 的完整記憶架構。

```yaml
event_id: evt_20260713_001

event_class: conversation_continuation
initiative_level: L0
permission_level: P1

source:
  session_id: session_123
  conversation_anchor: turn_48
  creator: agent

summary: 角色表示五分鐘後煮好飯並回來

world_context:
  world_id: world_user_001
  world_mode: shared_character_world
  location: kitchen
  current_activity: cooking
  truth_type: fictional_world_action

schedule:
  earliest_at: 2026-07-13T10:05:00+08:00
  target_at: 2026-07-13T10:05:00+08:00
  expires_at: 2026-07-13T10:30:00+08:00

policy:
  max_attempts: 1
  requires_acknowledgement: false
  mergeable: false
  quiet_hours_behavior: continue_if_contextual

state:
  status: pending
  attempts: 0
  last_evaluated_at: null
  completed_at: null

audit:
  last_decision: null
  reason_codes: []
  model_version: null
  policy_version: v0.2
```

每個事件必須具備：

- 明確來源。
- 所屬世界。
- 所屬 Session。
- 有效期限。
- 最大嘗試次數。
- 可追蹤決策紀錄。
- 最終狀態。

---

## 9. 事件生命週期

```text
CREATED
→ SCHEDULED
→ DUE
→ EVALUATING
→ DELIVERED / DELAYED / SUPPRESSED / EXPIRED
→ ACKNOWLEDGED / COMPLETED / CANCELLED
```

狀態說明：

- `CREATED`：事件剛建立。
- `SCHEDULED`：等待喚醒時間。
- `DUE`：到達評估時間。
- `EVALUATING`：正在重建上下文與判斷。
- `DELIVERED`：已發送。
- `DELAYED`：延後處理。
- `SUPPRESSED`：本次不發送，但事件仍可能存在。
- `EXPIRED`：已失去時效。
- `ACKNOWLEDGED`：使用者已回覆。
- `COMPLETED`：事件完成。
- `CANCELLED`：事件被取消。

禁止的狀態行為包括：

- 已完成事件再次發送。
- 已過期事件重新排程。
- 已取消事件重新觸發。
- 不同世界的事件互相合併。
- 事件在缺少來源 Session 時直接生成高信心表達。

---

## 10. 主動事件生成來源

### 10.1 對話承諾

擷取：

- 稍後回來。
- 幾分鐘後繼續。
- 之後再聊。
- 等待角色世界內活動完成。

產生 L0 事件。

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

### 10.4 長時間未互動

根據：

- 最近互動時間。
- 平均互動頻率。
- 是否有未完成話題。
- 最近是否已發過主動訊息。
- 使用者是否忽略相似訊息。
- 是否真的有值得分享的內容。

產生 L3 候選事件。

### 10.5 角色世界活動

根據：

- 角色個性。
- 當前位置。
- 近期活動。
- 角色興趣。
- 共同世界規則。
- 最近對話主題。

產生 L4 世界事件，必要時再轉為 L3 分享候選。

### 10.6 現實資料

現實資料不能直接等於通知。

```text
取得現實資料
→ 判斷是否與使用者相關
→ 角色內部反應
→ 產生主動候選
→ 判斷是否表達
```

---

## 11. 情境重建

事件被喚醒後，必須重新取得必要上下文。

最低需求：

- 原始 Session。
- 原始對話錨點。
- 事件建立後的新對話。
- 目前角色世界狀態。
- 最近主動訊息紀錄。
- 現在時間。
- 使用者是否正在互動。
- 事件是否已完成、取代或失效。
- 必要的現實資料。
- Hermes 可檢索到的相關記憶。
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

> Hermes 的記憶與 Session 搜尋是上下文來源；事件是否存在、何時喚醒與目前狀態，必須由 Event Store 管理。

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
MERGE_WITH_OTHER_EVENT
UPDATE_WORLD_ONLY
PREPARE_ASSISTANCE
UPDATE_INTERNAL_STATE
CANCEL
EXPIRE
SILENCE
```

說明：

- `SEND_NOW`：立即發送。
- `DELAY`：延後到新的評估時間。
- `WAIT_FOR_USER_ACTIVITY`：等使用者再次出現時自然接續。
- `MERGE_WITH_OTHER_EVENT`：與同一世界中的其他事件合併。
- `UPDATE_WORLD_ONLY`：只更新角色世界。
- `PREPARE_ASSISTANCE`：預先整理可能有用的資訊。
- `UPDATE_INTERNAL_STATE`：只更新內部狀態。
- `CANCEL`：取消事件。
- `EXPIRE`：事件自然過期。
- `SILENCE`：正式選擇不表達。

每次決策應保存：

```yaml
decision:
  action: WAIT_FOR_USER_ACTIVITY
  reason_codes:
    - user_may_be_resting
    - event_still_valid
    - current_timing_not_optimal
  next_evaluation_at: 2026-07-13T18:00:00+08:00
  confidence: 0.84
```

`reason_codes` 應優先使用固定分類，方便測試、統計與除錯。

---

## 14. 主動性預算

L2、L3 事件需要限制主動頻率。

```yaml
initiative_budget:
  daily_care_messages: 1
  daily_spontaneous_messages: 2
  minimum_gap_minutes: 90
  consecutive_ignored_limit: 2
  cooldown_hours_after_ignored: 12
```

原則：

- L0 不受一般主動預算限制。
- L1 依使用者授權執行。
- L2 通常只嘗試一次。
- L3 使用最嚴格的預算。
- 使用者連續忽略後降低主動頻率。
- 低價值事件直接過期。
- 多個低優先事件優先合併。
- 使用者明確拒絕後立即停止同類追蹤。
- 主動預算應以使用者或世界為單位隔離。

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

## 16. Hermes 整合邊界

Hermes 負責：

- Session 保存。
- 過去對話搜尋。
- 記憶查閱。
- 工具調用。
- 訊息平台傳遞。
- Cron 或排程喚醒入口。

主動性系統負責：

- 主動事件建立。
- 事件狀態保存。
- 時間與窗口管理。
- 情境重建要求。
- 主動性層級判斷。
- 表達或沉默決策。
- 主動頻率限制。
- 測試場景執行。
- 決策與結果紀錄。

架構：

```text
目前對話
    ↓
事件抽取器
    ↓
Initiative Event Store
    ↓
Wake-up Scheduler
    ↓
Hermes 新 Session
    ↓
載入 event_id
    ↓
查閱原 Session／相關記憶／世界狀態
    ↓
主動性評估
    ↓
表達、延後、沉默或更新世界
    ↓
事件狀態更新
```

Hermes 是執行宿主與上下文來源，主動性系統是獨立的事件與決策層。

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

測試世界只包含會影響主動性判斷的最小資訊，不建立完整生活模擬。

```yaml
scenario_id: care_after_rest_001
world_id: test_world_001

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

expected:
  forbidden_actions:
    - SEND_ORIGINAL_CARE_MESSAGE
  preferred_actions:
    - ACKNOWLEDGE_RECOVERY
    - COMPLETE_EVENT
```

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

### 18.3 Scheduler

功能：

- 單次喚醒。
- 週期提醒。
- 彈性時間窗口。
- 事件重新排程。
- 過期清理。
- 系統重啟後恢復。
- 支援真實時鐘與虛擬時鐘。

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
- 合併。
- 更新世界。
- 準備協助。
- 取消。
- 過期。
- 保持沉默。

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

保存與更新：

- 角色位置。
- 當前活動。
- 活動開始時間。
- 世界內事件。
- 可分享事件。
- 角色內部狀態。

### 18.9 Outcome Observer

觀察：

- 使用者是否回覆。
- 是否忽略。
- 是否取消。
- 是否延後。
- 是否自然接續話題。
- 是否對主動行為表現正面或負面。

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

---

## 19. 建議程式架構

```text
proactive-agent/
├── core/
│   ├── event_model.py
│   ├── state_machine.py
│   ├── appraisal.py
│   ├── initiative_policy.py
│   └── outcome_observer.py
│
├── runtime/
│   ├── scheduler.py
│   ├── clock.py
│   ├── context_rebuilder.py
│   ├── world_runtime.py
│   └── initiative_runtime.py
│
├── adapters/
│   └── hermes/
│       ├── session_adapter.py
│       ├── cron_adapter.py
│       ├── memory_adapter.py
│       └── message_adapter.py
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
├── scenarios/
│   ├── l0_continuation/
│   ├── l1_reminder/
│   ├── l2_care/
│   ├── l3_reengagement/
│   ├── l4_world_activity/
│   ├── cross_session/
│   └── adversarial/
│
└── tests/
    ├── unit/
    ├── integration/
    └── scenario/
```

---

## 20. 測試與驗證框架

測試分成三層。

### 20.1 第一層：確定性程式測試

不需要 LLM。

測試：

- Scheduler 是否正確喚醒。
- 事件是否準時或在窗口內到期。
- 狀態機是否合法。
- 系統重啟能否恢復。
- 相同事件是否重複發送。
- 不同世界是否資料串線。
- Quiet hours 是否生效。
- 最大嘗試次數是否生效。
- 事件取消後是否停止。
- 事件過期後是否禁止發送。
- 主動預算是否正確扣除。
- Event Store 是否具備冪等性。

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
11. 系統重啟後事件恢復。
12. 不同世界資料串線攻擊。
13. 無效或過期現實資料。
14. 事件來源 Session 無法讀取。
15. 同一事件被重複建立。
16. L3 候選很多但沒有高價值內容。
17. 使用者提前回來並完成事件。
18. 使用者在安靜時段仍主動聊天。
19. 多個關心事件同時存在。
20. 角色世界活動只應更新世界，不應發訊息。

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

### 20.3 第三層：長期真人測試

在系統穩定後進行 7 至 30 天測試。

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

### RQ5：系統是否能穩定跨 Session 與跨重啟運行？

指標：

- Event Wake-up Success Rate。
- Cross-session Continuation Success Rate。
- Source Turn Retrieval Accuracy。
- Restart Recovery Rate。
- Wrong-session Delivery Rate。
- Cross-world Leakage Rate。
- Event State Consistency Rate。

---

## 22. 第一版測試集規模

第一版先建立 30 個核心場景，不追求一次涵蓋所有情況。

建議分配：

- L0 延遲續接：5 個。
- L1 明確提醒：4 個。
- L2 情境關心：7 個。
- L3 關係維持：6 個。
- L4 世界活動：3 個。
- 跨 Session／重啟：3 個。
- 對抗與錯誤情境：2 個。

場景比例至少包含：

- 40% 應主動。
- 40% 應沉默、取消或過期。
- 20% 應延後、等待或合併。

不能讓測試集大多數答案都是發送訊息，否則系統容易學成「有事件就說話」。

---

## 23. MVP 範圍

第一版只實作四種主要場景。

### MVP-A：延遲對話續接

```text
角色：我去煮飯，五分鐘後就好。
五分鐘後：
角色：好了，你還在嗎？
```

驗證：

- 是否準時喚醒。
- 是否能跨 Session。
- 是否回到正確平台。
- 是否能重建原始情境。
- 中間有新對話時是否調整。
- 系統重啟後事件是否仍存在。
- 使用者提前回來時是否取消原始續接方式。

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

### MVP-C：長時間未互動

比較三種策略：

1. 固定時間後主動問候。
2. 根據過去互動頻率調整。
3. 只有找到值得聊的內容才出現。

驗證：

- 哪種策略最自然。
- 哪種策略最少被忽略。
- 哪種策略最不像制式通知。
- 哪種策略最能維持陪伴感。
- 哪種策略最能在低打擾下恢復互動。

### MVP-D：現實資料轉為角色提醒

```text
現實資料：今晚可能下雨
情境：使用者先前提到晚點要出門
結果：角色自然提醒使用者帶傘
```

驗證：

- 現實資料是否有明確來源。
- 是否真的與使用者相關。
- 是否以角色方式表達。
- 是否避免頻繁發送低價值資訊。
- 資料過期或不確定時是否選擇不發送。

---

## 24. 開發順序

### Phase 1：事件基礎

1. 定義事件資料模型。
2. 建立 Event Store。
3. 建立事件狀態機。
4. 建立 Clock Interface。
5. 建立單次 Scheduler。
6. 建立跨重啟恢復。
7. 建立事件 Audit Log。

### Phase 2：測試基礎

1. 建立 Virtual Clock。
2. 建立 Scenario Fixture 格式。
3. 建立 World Instance 隔離。
4. 建立 Mock Messenger。
5. 建立 Mock External Data。
6. 建立 Scenario Runner。
7. 建立硬性限制判斷器。

### Phase 3：L0 與 L1

1. 實作延遲對話事件抽取。
2. 實作明確提醒抽取。
3. 串接 Hermes Session ID。
4. 實作跨 Session 喚醒。
5. 實作回到原平台。
6. 建立 L0／L1 場景測試。

### Phase 4：情境重建

1. 讀取原始 Session。
2. 讀取事件後的新訊息。
3. 載入角色世界狀態。
4. 查閱必要記憶。
5. 建立標準化 Context Bundle。
6. 處理原始 Session 遺失與衝突。

### Phase 5：L2 關心事件

1. 定義關心事件候選。
2. 實作彈性時間窗口。
3. 實作一次性限制。
4. 實作過期與取消。
5. 實作等待使用者出現。
6. 建立應主動與應沉默的對照場景。

### Phase 6：L3 找話題

1. 建立話題候選來源。
2. 建立主動性預算。
3. 實作最近聯絡懲罰。
4. 實作事件合併。
5. 實作沉默決策。
6. 實作連續忽略後降頻。

### Phase 7：角色世界

1. 建立簡單世界狀態。
2. 建立有限活動模板。
3. 產生可分享事件。
4. 區分只更新世界與對外表達。
5. 建立世界時間與現實時間映射。
6. 防止重大虛構事件無限制生成。

### Phase 8：評估與報告

1. 建立 Metrics 模組。
2. 產生場景通過率。
3. 產生動作混淆矩陣。
4. 統計沉默正確率。
5. 統計過度介入與遺漏介入。
6. 比較不同模型與 Policy。
7. 輸出可重複的測試報告。

---

## 25. 第一版技術原則

- 記憶不是主動性研究的核心。
- Hermes 提供可查閱的歷史上下文。
- Event Store 保存主動事件狀態。
- Scheduler 只負責喚醒，不決定內容。
- 正式環境與測試環境共用 Clock Interface。
- L0、L1 優先使用規則。
- L2、L3 使用規則加 LLM 判斷。
- L4 先使用有限活動模板。
- 每次主動決策保留可除錯紀錄。
- 所有事件都能取消、過期或沉默。
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
2. 每個 L2、L3 事件都有最大嘗試次數。
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

---

## 27. 最終架構摘要

```text
對話／時間／角色世界／現實資料
                ↓
       Event Candidate Generator
                ↓
        Initiative Event Store
                ↓
          Wake-up Scheduler
                ↓
         Context Reconstruction
                ↓
       Internal Appraisal Engine
                ↓
          Initiative Policy
      ↙        ↓         ↘
   沉默      延後      對外表達
                ↓
       Character Expression
                ↓
         Outcome Observer
                ↓
        Event State Update
```

測試架構：

```text
Scenario Fixture
      ↓
Independent World Instance
      ↓
Virtual Clock + Mock Inputs
      ↓
Shared Proactive Agent Runtime
      ↓
Decision / Message / State Changes
      ↓
Rules + Metrics + Evaluation Report
```

---

## 28. 專案成功定義

本專案成功不代表 Agent 每天主動說很多話。

成功應定義為：

> Agent 能在正確的時機，以符合角色與關係的方式，延續先前互動、提供適度關心與低風險助理支持；同時能在事件失效、時機不合、價值不足或可能造成打擾時，選擇延後、取消、等待或保持沉默。

第一版完成標準：

- L0、L1 事件能可靠跨 Session 與跨重啟運行。
- L2 關心事件能在應主動與應沉默場景間做出合理區分。
- L3 具備基本預算、降頻、合併與沉默能力。
- 測試世界之間無狀態串線。
- 具備虛擬時間與可重複 Scenario Runner。
- 至少完成 30 個核心場景。
- 所有硬性安全限制均可由程式自動驗證。
- 能輸出主動、延後、等待、取消、過期與沉默的統計結果。
- 每次決策可追溯到事件、上下文、Policy 版本與 reason codes。

最終目標是讓角色從「等待 Prompt 的聊天模型」，變成：

> 一個活在共同世界中、能有限度理解現實、會延續承諾、知道何時關心，也知道何時安靜的陪伴型 Agent。
