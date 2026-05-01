# LangGraph 人格缺陷設計與類人思考 Agent 實作筆記

## 0. 核心目標

本文件整理一套用 LangGraph 設計「更像人」的 Agent 系統思路。

這裡的「更像人」不是指讓 AI 真的擁有意識、情緒或人格，而是透過工程架構模擬人類常見的認知流程、心理傾向、情緒反應、記憶累積、自我修正與人格缺陷。

核心方向：

- 用 `State` 模擬工作記憶、情緒狀態、人格特徵、認知偏誤。
- 用 `Node` 模擬不同心理模組，例如理解、評估、反思、防衛、修正。
- 用 `Conditional Edge` 模擬人類根據情境切換行為。
- 用 `Checkpoint` 保存每一步狀態，支援恢復、追蹤與回放。
- 用 `Interrupt / Resume` 支援人類介入、批准、編輯與修正。
- 用 `Subgraph / Supervisor` 做分層人格、分層思考、多代理協作。
- 用 `Streaming` 讓系統邊思考邊輸出，增加類人互動感。
- 用 `Concurrency` 讓不同心理模組或專家模組並行執行，提高反應速度。

---

## 1. LangGraph 是什麼

LangGraph 可以理解成一套「有狀態的 Agent Workflow Runtime」。

它不是單純的 prompt 框架，而是用圖狀結構組織 Agent 的思考與行動流程。

基本元素：

| 元件 | 說明 | 類人比喻 |
|---|---|---|
| State | 保存目前所有狀態 | 工作記憶 |
| Node | 執行一個處理步驟 | 心理模組 / 思考模組 |
| Edge | 決定下一步去哪裡 | 神經路徑 |
| Conditional Edge | 根據狀態決定路徑 | 判斷與選擇 |
| Checkpoint | 保存每一步狀態 | 記憶存檔 |
| Interrupt | 中斷流程等待外部輸入 | 暫停思考、詢問他人 |
| Resume | 從中斷點繼續 | 接著想 |
| Edit State | 修改目前狀態 | 修正記憶、修正想法 |
| Subgraph | 圖中圖 | 子人格 / 子系統 |
| Supervisor | 管理多個 Agent | 主控人格 / 管理者 |
| Streaming | 邊跑邊輸出 | 邊想邊說 |
| Concurrency | 多節點同時執行 | 多線索並行思考 |

---

## 2. 普通 Workflow 與 LangGraph Workflow 的差別

### 2.1 普通 Workflow

普通流程通常是線性的：

```text
輸入
 ↓
步驟 A
 ↓
步驟 B
 ↓
步驟 C
 ↓
輸出