# 長期記憶結構化紀錄實作計劃書

## 1. 問題理解

目前 `logs/memory.md` 以純文字段落記錄長期記憶摘要，雖然人類可讀，但存在以下問題：

- 資訊混雜，不易快速檢索特定事實（如 AI 偏好、共同約定）。
- AI 讀取時只能拿到連貫敘述，沒有結構化欄位。
- 日誌與 AI 可讀記憶未分離。

使用者希望：

- 將 `memory.md` 改成結構化格式記錄重點。
- 不標註來源輪次。
- 保留摘要原文供人類閱讀。
- AI 讀取記憶時不會讀到「摘要原文」區塊。

## 2. 影響範圍

| 檔案 | 影響內容 |
|------|----------|
| `src/agent/nodes/writeback.py` | 修改摘要 prompt，要求 LLM 輸出結構化 Markdown |
| `src/agent/memory_quality.py` | 新增結構化萃取與驗證邏輯 |
| `src/agent/logger.py` | 修改 `log_memory_summary`，輸出結構化 Markdown |
| `src/agent/llm/prompting.py` | 微調 `long_term_memory` 注入方式 |
| `logs/memory.md` | 輸出格式改變 |

## 3. 建議方案

採用「LLM 直接輸出結構化 Markdown + 程式萃取 AI 可讀區塊」方案。

### 3.1 記憶格式

每筆長期記憶包含以下區塊：

1. **對話總覽**：簡短概述本次對話主題與情緒走向。
2. **使用者相關記憶**：使用者偏好、習慣、行為事件。
3. **AI 人設/偏好記憶**：AI 角色應堅持的設定與偏好。
4. **共同事實 / 任務狀態**：雙方約定、待辦、數值。
5. **待確認/不確定項目**：推論或未證實內容。
6. **標籤**：分類標籤。
7. **摘要原文**：連貫敘述，僅供人類閱讀。

### 3.2 AI 可讀記憶

AI 實際讀取的是 `AgentState.long_term_memory`。該欄位只儲存區塊 1–6，**不包含「摘要原文」**。

### 3.3 日誌輸出

`logs/memory.md` 記錄完整 Markdown（區塊 1–7），供人類除錯與品質稽核。

## 4. 實作步驟

### Step 1: 修改摘要 Prompt（writeback.py）

- 更新 `_build_summary_prompt`，要求 LLM 輸出結構化 Markdown。
- Prompt 中提供範例，說明每個區塊的撰寫方式。
- 要求不標註來源輪次。

### Step 2: 新增結構化萃取（memory_quality.py）

- 新增 `extract_ai_memory(markdown: str) -> str`：從完整 Markdown 中移除「摘要原文」區塊，保留其餘部分。
- 新增 `is_structured_memory(text: str) -> bool`：檢查是否包含必要區塊。
- 調整 `clean_summary_output`：保留 Markdown 列表結構，只移除 prompt leakage 與殘留標記。
- 調整 `validate_summary`：允許結構化 Markdown 通過驗證。

### Step 3: 修改日誌輸出（logger.py）

- 修改 `log_memory_summary`：
  - 接受 `structured_markdown` 與 `ai_memory` 兩個參數。
  - 寫入完整 Markdown 到 `memory.md`。
  - 保留輸入對話與模型資訊。

### Step 4: 修改 writeback.py 的摘要流程

- LLM 產生結構化 Markdown 後，用 `extract_ai_memory` 萃取 AI 可讀部分。
- 將 AI 可讀部分存入 `long_term_memory`。
- 將完整 Markdown 傳給 `log_memory_summary`。

### Step 5: Fallback 機制

- 當 LLM 無法產生有效結構化 Markdown 時，使用 `build_structured_fallback` 產生簡化結構。
- Fallback 版本同樣需包含區塊 1–6，並可用於 AI 讀取。

### Step 6: Prompt 注入微調（prompting.py）

- 確認 `long_term_memory` 注入時加上適當標題，例如「【長期記憶】」。
- 確保格式對 LLM 清楚。

## 5. 驗證方式與結果

1. **單元測試（手動）**：透過 Python 直譯器測試 `extract_ai_memory`、`is_structured_memory`、`clean_summary_output`、`build_structured_fallback`。
   - 結果：結構化 Markdown 能被正確清理與萃取；AI 可讀記憶確實不含「摘要原文」。
2. **Mock 模式驗證**：執行 `LLM_BACKEND=mock python main.py --continuous`。
   - 結果：`memory.md` 正確輸出結構化 fallback；`long_term_memory` 被更新。
3. **Google 後端驗證**：執行 `python main.py --continuous`（使用 `.env` 設定的 Google API）。
   - 結果：LLM 成功產生結構化 Markdown，包含全部七個區塊；AI 可讀記憶只包含區塊 1–6。
4. **Prompt 注入驗證**：使用真實 `memory.md` 中的 AI 可讀記憶測試 `build_prompts`。
   - 結果：`system_prompt` 包含「【長期記憶】」、包含關鍵記憶（青椒/遊戲評分）、不含「摘要原文」。
5. **Pipeline Replay**：執行 `python scripts/replay_pipeline.py --scenario continuous --limit 10`。
   - 結果：judge / emotion / tone 流程正常，無錯誤。

## 6. 風險與假設

| 風險 | 影響 | 對策 |
|------|------|------|
| LLM 無法穩定輸出結構化 Markdown | 摘要失敗或 fallback 頻繁 | 提供詳細 few-shot prompt 與驗證邏輯 |
| `clean_summary_output` 誤刪列表結構 | 結構化格式被破壞 | 調整清理規則，保留 Markdown 列表 |
| AI 可讀記憶過長 | 佔用 prompt token | 設定字數上限，必要時截斷 |
| 舊版 `memory.md` 格式相容 | 歷史日誌無法重新解析 | 只影響新產生的摘要，舊檔案維持原樣 |
| 摘要原文增加 token 成本 | 摘要模型輸出變長 | 控制摘要原文長度，或改為僅在需要時產生 |

## 7. 決策確認

1. **LLM 輸出格式**：讓 LLM 直接輸出完整結構化 Markdown（區塊 1–7），再由 `extract_ai_memory` 萃取 AI 可讀部分。此方案最直接，且能保留高品質摘要原文供人類閱讀。
2. **Fallback 格式**：`build_structured_fallback` 產生結構化 Markdown（區塊 1–7），確保即使 LLM 失敗，日誌與 AI 記憶仍維持一致格式。
3. **完整 Markdown 儲存**：不新增 `AgentState` 欄位。`long_term_memory` 只儲存 AI 可讀部分；完整 Markdown 僅寫入 `logs/memory.md` 供人類檢閱。
