# Keyword 依賴、回覆收斂與 Judge 降級路徑修正計劃

日期：2026-07-12  
狀態：分析與實作計劃，尚未修改 runtime  
範圍：`judge → emotion / stance / tone → response → writeback` 對話主鏈

## 1. 結論先行

目前回覆容易產生相似結果，不是單一「隨機性不足」問題，而是多層 deterministic 規則共同形成的收斂漏斗：

1. `classify_input()` 先以 substring keyword 建立 category evidence。
2. 正常 Judge LLM prompt 仍收到完整 keyword evidence，容易形成分類先驗。
3. `fake_praise` 規則可在 Judge 成功後仍硬覆寫 `category/event_type`。
4. `task_status` 用 artifact marker 與 stance 推測是否真的產出成果，事實 contract 不夠可靠。
5. `category` 再決定 `response_goal`，並調整 stance/flow 權重，使前段誤判被放大。
6. `is_on_strategy()` 用固定字詞與長度淘汰候選；非串流路徑 retry temperature 又降到 `0.3`。
7. 串流路徑沒有 response retry，validator 一失敗就直接進入少量固定 fallback 台詞。

因此，即使 stance、flow 或 LLM sampling 有隨機性，候選仍會在後段被壓回少數 category、少數 flow 與少量 fallback template。提高 temperature 或再增加同義 keyword，只會增加表面變化或誤判，不會處理根因。

本計劃建議採用：

> **Keyword 只保留為診斷與 Judge 失敗時的低信心 evidence；正常 Judge 不再以 keyword 作顯式輸入，fake praise 不再硬覆寫成功的 rich appraisal，task status 改成可驗證事實，validator 只硬擋 correctness invariant，parser 只做結構清理；同時完整保留 Judge 兩次嘗試與 deterministic rule fallback。**

Judge fallback 不能刪除。它是 provider timeout、API failure、空回覆、非法 JSON 與 schema validation failure 時的可用性保護。本次修正目標是降低 fallback 的語義權限，不是降低可用性。

---

## 2. 問題與非目標

### 2.1 要解決的問題

- 正常 LLM judge 被 keyword evidence anchoring。
- `fake_praise` keyword 規則凌駕成功的 LLM appraisal。
- task status 把 marker、category、stance 推測當成已確認的對話事實。
- response validator 把人格樣式偏好當成 hard validity condition。
- response retry 與小型 fallback template 壓縮輸出多樣性。
- streaming 與 graph response path 的 retry/fallback contract 不一致。
- output cleaning 存在兩套 `clean_response()`，責任與實際接線不清楚。
- Judge fallback 將 keyword category 直接升格為完整 event appraisal，進而改變 emotion state。

### 2.2 不在本輪計劃內

- 不刪除 Judge retry 或 rule fallback。
- 不把 Judge LLM 變成可任意寫入 `character_state` 的自由 agent。
- 不新增 relationship episode、長期關係模型或大型 memory schema。
- 不用更高 temperature 掩蓋錯誤 routing。
- 不以更多 keyword、regex 或模板擴充作為主要修法。
- 不改變對外 CLI 或 public API；新增欄位若需要，先限制在內部 `event_analysis` / task fact contract。

---

## 3. Current-state 控制流

### 3.1 Judge 正常與降級路徑

目前 `judge_input()` 的真實流程：

```text
classify_input(user_input)
  └─ substring keywords → classifier category / keyword_signals

build_judge_prompts(state + keyword_signals)
  ↓
Judge LLM call #1 → parse_judge_output_v2
  ↓ invalid
Judge LLM call #2 → parse_judge_output_v2
  ↓ invalid
_run_smart_fallback()
  └─ classify_input() again
     └─ category → build_rule_event_analysis(category)
```

正常路徑雖然在 prompt 中寫明「關鍵字只是 evidence」，但 Judge 同時看見：

- `Keyword evidence`
- `Keyword confidence`
- 類別規則與大量類別範例
- 上一個 task status
- 最近四筆對話

這會讓 keyword 從純診斷資料變成模型的顯式分類先驗。

降級路徑則更直接：

```text
fallback category
  → event_type = category
  → intensity = 0.5
  → relationship_signal = neutral
  → state_delta_suggestion = {}
```

這不是 bounded appraisal，而是把 keyword label 包成 appraisal shape。

### 3.2 Fake praise 硬覆寫

`_check_fake_praise()` 先依 `last_task_status`，再依前一輪 user request marker 與 assistant refusal marker 判斷。命中後，不論 Judge LLM 原本輸出什麼，都會改成：

```text
category = questioning
event_type = questioning
fake_praise = true
ambiguous = true
```

這條規則的正確目標是守住「不能承認不存在的成果」，但目前同時做了兩件不同責任的事：

1. 對話事實校正：成果是否存在。
2. 情緒／意圖 appraisal：使用者是否在挖苦或質疑。

第一項可以 deterministic；第二項不能只靠 marker 確定。把兩者綁在一起，會讓真誠稱讚、延遲引用、引用第三方成果或模糊代詞都收斂成 `questioning`。

### 3.3 Task status 與成果引用

目前 task status 有三個脆弱點：

1. artifact type 由 `詩／翻譯／故事／程式／畫／文案` 等 marker 推測。
2. `task_request` 是否 `produced` 主要由 `action_stance` 推測，而不是實際 response artifact。
3. `creative_task` 被直接記為 `rejected`，再由「這首／寫得／成果／剛剛那個」等 marker 推斷 fake praise。

也就是說，task fact 可能先被隨機 stance 決定，再反向影響下一輪 Judge。這會把 persona routing 產生的隨機結果寫成對話事實。

### 3.4 Response validator 與 fallback

非串流 `generate_response()`：

```text
LLM candidate
  → is_on_strategy()
  → fail: retry with temperature=0.3
  → fail again: fallback_response()
```

串流 `interactive_chat` / `continuous_chat_mode`：

```text
streamed candidate
  → is_on_strategy()
  → fail: fallback_response() immediately
```

問題包括：

- fake praise 回覆必須包含少數 denial markers，否則整段判 invalid。
- `authoritative_bluffing` 出現「我不知道／我不確定」反而 invalid，與真實性原則衝突。
- 部分 stance 只用字數判斷 valid，無法驗證是否真的完成 Response Goal。
- retry temperature 從一般 `0.85` 降到 `0.3`，更容易得到固定、安全、相似句型。
- fallback pool 多數 stance 只有 1 至 4 句；相同 category/stance 會頻繁撞句。
- streaming 沒有 corrective retry，實際比 graph path 更容易掉入模板。

### 3.5 Output parser 的實際接線

Repo 內有兩個同名 `clean_response()`：

- `src/agent/llm/providers.py::clean_response()`：目前 provider 與 streaming runtime 實際使用。
- `src/agent/llm/output_parser.py::clean_response()`：包含「找到傲嬌 keyword 後只保留該行與後三行」邏輯，但目前沒有接到回覆主路徑，只在檔案自己的示範程式使用。

因此，傲嬌 keyword 截斷目前不是 runtime 相似輸出的直接主因；它是重複 parser contract 與未來誤接風險。真正 runtime parser 仍有另一類收斂：`providers.clean_response()` 偏好最後一段中文、quote 或最後三行，可能丟失前面的回答內容，但它不是由傲嬌 keyword 觸發。

---

## 4. 為什麼會壓縮回覆隨機性

### 4.1 隨機抽樣之前，候選空間已被 category 固定

`category` 會先決定或強烈影響：

- `response_goal`
- emotion base delta
- stance weight
- flow weight
- prompt 中的 task/fake-praise 強制規則

如果同類 keyword 反覆把輸入送入相同 category，後續抽樣只能在一個很小的合法區間內變化。

### 4.2 隨機抽樣之後，validator 再做 rejection sampling

LLM 即使生成不同候選，只要沒有命中特定 marker 或長度，就會被丟棄。這相當於：

```text
large candidate space
  → keyword/stance validator filter
  → low-temperature retry
  → tiny fallback pool
```

最後使用者看到的不是模型真正的多樣性，而是「通過規則的少數句型」。

### 4.3 固定 fallback 會製造可見撞句

`fallback_response()` 以 category/stance 選固定句或極小 `random.choice()` pool。只要 validator false-positive rate 稍高，相同句子就會高頻出現。

### 4.4 多樣性不能凌駕語義正確性

本計劃不以「每次都不一樣」作單一目標。正確順序應是：

1. 同一語境的核心事實與回應義務一致。
2. fallback 不把低信心 keyword 當成情緒事實。
3. 在正確的 goal/stance 可行集合內保留多種自然表達。
4. validator 不因缺少角色口頭禪而淘汰正確答案。

---

## 5. 方案比較

### 方案 A：直接移除所有 keyword 與 fallback

優點：規則最少，正常模型輸出較自由。  
缺點：Judge provider/JSON failure 時整條 graph 無可用 decision；安全與可用性退化。  
判斷：不採用。

### 方案 B：保留 keyword，但增加更多詞、否定 regex 與優先級

優點：修改局部、短期容易看到部分 case 改善。  
缺點：規則會持續膨脹；無法可靠處理 target、引用、反諷、多意圖與跨輪事實；仍會壓縮輸出。  
判斷：只適合極少數安全／操作性明確的 narrow rule，不作主方案。

### 方案 C：Evidence、fact、appraisal、style 分層（建議）

核心責任：

```text
keyword evidence  → 只供診斷與 rule fallback
task facts        → deterministic、帶 provenance 的對話事實
LLM appraisal     → 正常路徑的 rich proposal
validator         → schema/correctness invariant
reducer/router    → bounded deterministic state transition
style preference  → scoring/prompt hint，不作 hard validity
```

優點：保留 Judge fallback 與可 replay 性；降低正常路徑 anchoring；能分開修正 correctness 與 diversity。  
缺點：需要跨 `judge/task_status/validators/response/parser` 的分期修改，不能用單一 patch 完成。  
判斷：採用。

---

## 6. 目標 contract

### 6.1 Judge contract

正常路徑：

- Judge 只看原始輸入、必要對話歷史、可信 task facts、bounded character context。
- 不把 `keyword_signals` 與 `keyword_confidence` 放入正常 Judge prompt。
- keyword classifier 可繼續先跑，但用途限於 logging、shadow comparison 與 fallback。
- 成功通過 canonical validator 的 Judge 結果，不再被 keyword category 覆寫。

失敗路徑：

- 保留兩次 Judge 嘗試。
- 保留 exception/None/empty/invalid JSON/schema error 的捕捉與 log。
- 第二次仍失敗時一定回 rule result，不讓 graph 因 Judge failure 中止。
- rule result 必須標記 `judge_source=rule`、低信心與 fallback reason。
- keyword category 可維持最低限度 service routing，但不能自動取得完整 emotion appraisal 權限。

### 6.2 Task fact contract

將「是否產出」與「使用者現在如何評價」分開：

```text
last_task_status:
  request_kind
  requested_artifact
  outcome: completed | partial | rejected | unknown
  produced_artifact: true | false | unknown
  evidence_source
  response_turn
```

規則：

- stance 不再單獨決定 `produced_artifact`。
- 只有明確拒絕、LLM/provider failure、deterministic fallback 無 artifact 時才能可靠寫 `false`。
- 只有 response stage 或 artifact validator 確認有產出時才能寫 `true`。
- 無法確認時寫 `unknown`，不能猜成 false。
- artifact keyword 只作 type hint；不可單獨證明目前輸入正在引用上一輪成果。

### 6.3 Premise conflict / fake praise contract

`fake_praise` 應降級成較中性的「前提衝突候選」：

- deterministic fact：上一輪是否確定沒有產出。
- reference evidence：本輪是否明確引用該 artifact。
- appraisal：是挖苦、記錯、真誠稱讚其他內容，仍由 Judge 判斷。

正常 Judge 成功時：

- 不硬改 `category/event_type`。
- 將可信 task fact 放入 prompt，要求不得承認不存在成果。
- 若 Judge 輸出與硬事實衝突，只修正「成果存在性」欄位／prompt guard，不替它決定使用者情緒。

Judge fallback 時：

- 僅在 `produced_artifact=false` 且 current reference 高信心對應同一 artifact 時，啟用 deterministic premise correction。
- category 可用 `questioning` 或 `normal + ambiguous` 的 bounded policy，但不得自動產生 hostile/relationship delta。
- 弱 marker 或 `produced_artifact=unknown` 時只標 ambiguous，不作 hard override。

### 6.4 Response validator contract

Hard fail 僅保留：

- 空回覆／低於最低可讀長度。
- 明確承認 deterministic fact 判定不存在的成果。
- 明顯未回答必須回答的 task goal（需用結構／語義檢查，不能只看口頭禪）。
- 安全或 schema invariant。

Soft score / telemetry：

- 是否符合 stance 語氣。
- 是否出現傲嬌風格。
- 長度是否偏離建議。
- flow 是否表現明顯。
- 是否與最近回覆過度相似。

禁止：

- 因沒有固定 denial keyword 就淘汰事實正確的 fake-praise 回覆。
- 因說「我不知道／我不確定」就淘汰回覆。
- 用單純字數當作完成 goal 的充分條件。

### 6.5 Parser contract

- parser 只移除 think blocks、格式包裝、已知 draft metadata。
- 不依 persona keyword 選擇哪幾行是 final answer。
- 不以「有中文」或「最後三行」作唯一答案判定；若結構不明，保守保留內容。
- 統一 `providers.clean_response()` 與 `output_parser.clean_response()` 的 owner，避免兩套不同 contract。
- `smart_truncate()` 保留句界截斷責任，不混入 persona/style 判定。

---

## 7. 分期實作計劃

## Phase 0：建立基線與觀測，不改行為

### 修改範圍

- `src/agent/nodes/judge.py`
- `src/agent/nodes/response.py`
- `main.py`
- `src/agent/logger.py`
- `scripts/replay_pipeline.py`
- focused test script

### 工作

1. 為 Judge 記錄失敗原因：exception、empty、invalid JSON、invalid schema。
2. 分開記錄：
   - `classifier_category`
   - `judge category`
   - `judge_source`
   - `fake_praise override` 是否發生
   - response validator rejection reason
   - response retry 次數
   - response fallback reason/template id
3. 讓 replay 顯示 rule fallback 是否套用了 emotion event delta。
4. 建立固定 scenario corpus，至少包含：
   - keyword 與語境衝突
   - 多意圖告別＋問題
   - 真／假／不確定成果稱讚
   - task artifact 指代
   - 誠實不確定回答
   - 多行回答含／不含角色口頭禪

### 完成門檻

- 能回答「相似輸出來自相同 routing、validator rejection、低溫 retry，還是 fallback template」。
- 不靠人工翻整份 prompt log 才能定位。

## Phase 1：先解除 response 後段收斂

### 修改範圍

- `src/agent/llm/validators.py`
- `src/agent/nodes/response.py`
- `main.py`

### 工作

1. 將 `is_on_strategy()` 拆成：
   - `validate_response_invariants()`：hard pass/fail + reason。
   - `score_style_alignment()`：只記分，不淘汰。
2. 移除 `authoritative_bluffing` 對誠實不確定語句的 hard rejection。
3. fake-praise validation 改驗「是否錯誤承認成果存在」，不要求固定 denial marker。
4. graph 與 streaming 共用同一 response finalize helper，消除路徑差異。
5. streaming 也允許一次 corrective retry；不可直接因 style mismatch 進模板。
6. retry 使用針對 failure reason 的 corrective instruction；temperature 不固定降到 `0.3`。建議先維持原 temperature 或只小幅調整，實測後再定。
7. fallback 僅在 provider/empty/hard invariant 連續失敗時使用。

### 完成門檻

- streaming 與 graph path 對相同 state 有相同 validation/fallback policy。
- style mismatch 不再導致 fallback。
- fallback rate 明顯下降，但 factual contradiction rate 不上升。

## Phase 2：修正 task status 與 fake praise 責任

### 修改範圍

- `src/agent/task_status.py`
- `src/agent/nodes/judge.py`
- `src/agent/llm/judging.py`
- `src/agent/llm/prompting.py`
- `src/agent/nodes/writeback.py` 或實際 task status owner

### 工作

1. 將 `produced_artifact` 改成可表達 unknown 的 fact。
2. 移除「stance 直接等於是否完成」推論。
3. artifact marker 只決定候選 type，不直接決定成果引用。
4. 把 fake praise 改成 premise-conflict candidate：
   - 正常 Judge：提供事實，不硬覆寫 appraisal。
   - rule fallback：只有強事實＋強引用才 deterministic correction。
5. response prompt 繼續保留「不得捏造不存在成果」的 truth guard。
6. 將 task fact provenance 寫入 log/replay，確認來源是 response observation、explicit rejection 或 unknown。

### 完成門檻

- 真實稱讚不因弱 marker 被改成 questioning。
- 明確不存在的成果仍不會被 AI 承認。
- `unknown` 不會被當成 `false`。
- persona stance 不再反向製造 task fact。

## Phase 3：正常 Judge 移除 keyword anchoring

### 修改範圍

- `src/agent/llm/judging.py`
- `src/agent/nodes/judge.py`
- `src/agent/nodes/classifier.py`

### 工作

1. 從正常 Judge prompt 移除 `Keyword evidence` 與 `Keyword confidence`。
2. classifier 繼續執行，作為：
   - fallback input
   - diagnostic log
   - shadow comparison
3. Judge 成功後不再讓 fake-praise/category keyword 硬改 canonical event；只允許 truth invariant correction。
4. 觀測 `classifier_category != judge category` 的分布，不將差異本身視為錯誤。
5. 保留 prompt 中抽象分類定義，但刪減過度具體、容易形成 lexical shortcut 的例詞；以正反語境例子取代詞表暗示。

### 完成門檻

- 正常 Judge 的結果只由完整語境與可信 facts 決定。
- keyword classifier 改壞或新增詞彙時，不會直接改變正常 Judge prompt。
- Judge latency、schema pass rate與 category correctness 不退化。

## Phase 4：保留但收窄 Judge rule fallback

### 修改範圍

- `src/agent/nodes/classifier.py`
- `src/agent/nodes/judge.py`
- `src/agent/llm/judge_validators.py`
- `src/agent/nodes/emotion.py`
- `src/agent/nodes/tone_goal.py`

### 工作

1. 保留現有兩次 Judge call 與最終 rule fallback。
2. `build_rule_event_analysis()` 顯式輸出低信心／rule provenance。
3. 分開兩種決策：
   - functional routing：task、安全 boundary、明確 farewell 等最低可用行為。
   - emotional appraisal：event intensity、relationship、sarcasm、state delta。
4. keyword 命中可以支援 functional routing，但低信心 rule event 預設：
   - `relationship_signal=neutral`
   - 無 LLM state delta
   - 不推斷 sarcasm/hostility
   - emotion 採 decay-only 或極小 bounded delta
5. `should_apply_emotion_event()` 讀取 `judge_source/appraisal confidence`，不再只看 category 與字數。
6. mixed keyword signals 不以固定優先級假裝已消歧；標 ambiguous，採最保守且可服務使用者的 goal。
7. 不增加第三次 Judge 呼叫；先做本地 parse/canonicalization，再在兩次失敗後可靠 fallback。

### 完成門檻

- Judge provider 完全失敗時 graph 仍可產生可用回覆。
- rule fallback 不會把一般 lexical match 寫成強 emotion/relationship 事實。
- task/safety/farewell 等基本服務能力仍存在。
- fallback 決策可 replay、可辨識、可統計。

## Phase 5：Parser owner 收斂與 dead-path 清理

### 修改範圍

- `src/agent/llm/providers.py`
- `src/agent/llm/output_parser.py`
- provider 與 response callers

### 工作

1. 定義單一 canonical response cleaning helper。
2. provider 只負責 transport／model call；輸出 cleaning 由 parser owner 處理，或明確反向定案，但只能有一套。
3. 移除未接線的傲嬌 keyword 行選擇邏輯。
4. 用結構訊號處理 JSON wrapper、think block、draft metadata。
5. 對無法可靠辨認的多行 plain text 保守保留，不自行挑最後中文段落。

### 完成門檻

- 所有 backend、streaming/non-streaming 使用同一 cleaning contract。
- parser 不依 persona keyword 決定保留內容。
- 多行答案不因包含或缺少「哼／笨蛋」而改變保留範圍。

---

## 8. 驗證計劃

### 8.1 Contract tests

#### Judge

- 正常 Judge prompt 不含 `Keyword evidence`。
- LLM canonical result 不被 keyword category 覆寫。
- call #1 exception、call #2 invalid JSON 後仍取得 rule fallback。
- rule fallback 明確標示 source、reason、low confidence。
- unknown state keys 仍被 canonical validator 丟棄。

#### Fake praise / task facts

- 上輪明確拒絕寫詩，本輪「你剛寫的那首很好」：糾正成果不存在，但不強制 hostile appraisal。
- 上輪有實際詩作，本輪相同稱讚：不可判 fake praise。
- `produced_artifact=unknown`：不可硬判 fake praise。
- 「這首歌很好聽」但上一輪 task 是 code：不可因「這首」誤綁 task。
- 稱讚第三方作品：target 不得被固定成 assistant。

#### Validator

- 正確否認不存在成果但未使用 denial marker：應通過。
- 誠實說「我不確定」：不可因 stance 被判 invalid。
- 有完整答案但缺傲嬌口頭禪：hard validator 應通過。
- 明確承認不存在成果：hard fail 並帶 reason。

#### Parser

- 多行回答含「哼」：不得只保留該行後三行。
- 多行回答不含中文：不得只留下最後三行。
- `<think>`、合法 JSON wrapper、plain text 各有固定結果。
- streaming 與 non-streaming cleaning 結果一致。

### 8.2 Replay scenarios

每個 scenario 同時觀察：

- `classifier_category`
- final `category/event_type`
- `judge_source`
- task fact provenance
- premise conflict confidence
- emotion apply/decay-only
- `response_goal`
- stance / flow
- validator result/reason
- retry/fallback reason

至少加入：

1. 「我要睡了，但先回答最後一題」：主要義務不能只由 farewell keyword 決定。
2. 「你明明寫得很好」：要依真實 task fact 判斷，不由「你明明」固定成 flirt。
3. 「這個 small 改得很好」：fallback 不得把 `small` 直接變成強 negative emotion。
4. 「我不是說你很爛，是在描述那個產品」：target/negation 要被保留。
5. 「真的假的，你確定嗎？」：可 question，但不能自動變 hostile。
6. provider timeout／空 JSON／非法 category：兩次失敗後仍安全回覆。

### 8.3 多樣性與相似度驗證

對同一批 scenario，以固定 state 執行多個 seeds／sampling runs，分開看 correctness 與 diversity。

#### Correctness gate（先通過）

- factual contradiction rate
- response-goal accuracy
- Judge schema pass rate
- rule fallback availability
- unsupported emotion delta rate
- fake-praise false-positive / false-negative rate

#### Diversity gate（correctness 通過後）

- exact duplicate rate
- normalized duplicate rate（移除標點與常見口頭禪）
- pairwise lexical / semantic similarity
- fallback template collision rate
- validator rejection rate by reason
- stance/flow distribution 與 anti-repeat effectiveness
- 相同 goal 下的有效表達數量

建議門檻先以 baseline 相對改善定義，不在未量測前硬訂絕對數字。必要條件：fallback rate、exact duplicate rate 與 validator style rejection rate下降，同時 factual contradiction 不得上升。

### 8.4 路徑一致性

必須分別驗證：

- graph `generate_response()`
- interactive streaming
- continuous chat streaming with history
- mock backend
- 至少一個實際 JSON Judge backend 的 failure injection

不能只驗 graph node，因為目前 streaming 的 retry/fallback 行為不同。

---

## 9. 建議修改順序與切片邊界

建議實作順序：

```text
Phase 0 observability
  ↓
Phase 1 validator + response path parity
  ↓
Phase 2 task fact + fake praise
  ↓
Phase 3 normal Judge keyword isolation
  ↓
Phase 4 bounded rule fallback
  ↓
Phase 5 parser consolidation
```

原因：

- 若先移除 Judge keyword，但 validator 仍高頻把結果打回模板，很難判斷多樣性是否改善。
- 若先改 fake praise，但 task status 仍由 stance 推測，仍會用不可靠事實做判定。
- 若先刪 fallback，會破壞 Judge failure 可用性，與本次目標相反。
- Parser 的傲嬌 keyword 邏輯目前未接線，可後移；runtime parser contract 仍需最終收斂。

每個 Phase 應獨立提交、獨立 replay，避免一次修改所有 routing 後無法定位行為變化。

---

## 10. 風險與防護

### 風險 1：移除 Judge keyword evidence 後分類波動

防護：先 shadow log classifier vs Judge；保留類別定義與 history/task facts；不立即刪 classifier。

### 風險 2：validator 放寬後人格變淡

防護：人格改成 soft score、prompt hint 與 replay metric，不是完全移除；correctness 優先於固定口頭禪。

### 風險 3：fake praise 放寬後模型承認不存在成果

防護：保留 deterministic task fact 與 truth guard；只移除「直接替使用者決定情緒」的硬覆寫。

### 風險 4：fallback emotion 太保守，角色短暫變平

防護：functional routing 保留；低信心時採 decay-only 比寫入錯誤情緒更安全。待有 evidence 再逐步加入 narrow high-confidence delta。

### 風險 5：共用 response finalize helper 影響 streaming 體感

防護：保留 token streaming；只統一 stream 完成後的 clean/validate/retry/fallback contract。若 retry 發生，UI 應明確處理，不把第一候選與第二候選混接。

### 風險 6：只追求低相似度導致角色不一致

防護：多樣性 gate 永遠排在 correctness、fact consistency、goal accuracy 之後；不獎勵無理由的 stance/flow 跳動。

---

## 11. Definition of Done

完成這組修正不能只看測試全綠，必須同時滿足：

1. 正常 Judge prompt 不再接收 keyword evidence。
2. 成功的 LLM appraisal 不再被 fake-praise keyword 硬改 category/event type。
3. task status 不再由 stance 單獨推測是否產出。
4. response hard validator 只守 correctness invariant，style 改為 soft signal。
5. streaming/non-streaming 使用同一 validation/retry/fallback contract。
6. runtime 只有一套 response cleaning contract，且不依 persona keyword 選答案。
7. Judge 兩次失敗後仍一定有 deterministic rule fallback。
8. rule fallback 不會把低信心 keyword 自動寫成強 emotion/relationship 事實。
9. replay 能顯示 Judge source、fallback reason、task fact provenance、validator reason。
10. 相同 scenario 的 template collision 與 normalized duplicate rate 相對 baseline 降低，且 factual contradiction、goal accuracy 不退化。

---

## 12. 最終建議

這次不應以「刪 keyword」或「增加隨機句庫」作為修正名稱。真正要做的是重新切清責任：

- keyword 是 evidence，不是事件真相；
- task status 是可驗證事實，不是 stance 推測；
- fake praise 的事實校正與情緒 appraisal 必須分開；
- validator 守 correctness，不負責要求固定人格口頭禪；
- parser 清結構，不判斷哪句最傲嬌；
- fallback 保證可用性，但以低信心、低狀態權限運作。

這樣才能同時保留 Judge 失敗保護、減少 keyword 誤判、降低固定模板撞句，並讓回覆多樣性來自合理的 goal/stance/flow 可行集合，而不是無約束地提高 temperature。
