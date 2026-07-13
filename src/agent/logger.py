from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
ERROR_LOG = LOG_DIR / "error.log"
PROMPT_MD = LOG_DIR / "prompts.md"
MEMORY_MD = LOG_DIR / "memory.md"
INITIATIVE_SUMMARY_START = "<!-- initiative-summary:start -->"
INITIATIVE_SUMMARY_END = "<!-- initiative-summary:end -->"


def init_logs() -> None:
    """初始化日誌檔案，每次啟動時清空舊日誌並重新開始記錄"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    startup_info = f"{'=' * 80}\n=== 日誌開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n{'=' * 80}\n\n"

    try:
        with open(ERROR_LOG, "w", encoding="utf-8") as f:
            f.write(startup_info)
            f.flush()
    except Exception as e:
        print(f"警告：無法初始化錯誤日誌 {ERROR_LOG}: {e}")

    try:
        md_header = f"""# 📝 Prompts 日誌

> 生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{INITIATIVE_SUMMARY_START}
{INITIATIVE_SUMMARY_END}

---

"""
        with open(PROMPT_MD, "w", encoding="utf-8") as f:
            f.write(md_header)
            f.flush()
    except Exception as e:
        print(f"警告：無法初始化 Markdown 日誌 {PROMPT_MD}: {e}")

    try:
        mem_header = f"""# 🧠 記憶摘要日誌

> 生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 記錄每次異步摘要的輸入對話與輸出結果，供回推記憶品質

---

"""
        with open(MEMORY_MD, "w", encoding="utf-8") as f:
            f.write(mem_header)
            f.flush()
    except Exception as e:
        print(f"警告：無法初始化記憶日誌 {MEMORY_MD}: {e}")


def log_error(
    module: str,
    function: str,
    error: Exception,
    context: Optional[dict] = None
) -> None:
    """
    記錄錯誤資訊到 error.log
    
    Args:
        module: 模組名稱
        function: 函數名稱
        error: 例外物件
        context: 額外的上下文資訊（選用）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    log_entry = f"""
[{timestamp}] 錯誤
模組: {module}
函數: {function}
錯誤類型: {type(error).__name__}
錯誤資訊: {str(error)}
"""
    
    if context:
        log_entry += f"上下文: {context}\n"
    
    log_entry += "-" * 80 + "\n"
    
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
            f.flush()  # 立即寫入磁碟
    except Exception as e:
        print(f"警告：無法寫入錯誤日誌: {e}")


def log_prompt(
    scenario_id: int,
    user_input: str,
    system_prompt: str,
    response: str,
    action_stance: str,
    emotion: float,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tone: Optional[str] = None,
    defect_mode: Optional[str] = None,
    ttfb_ms: Optional[float] = None,
    total_ms: Optional[float] = None,
    max_tokens: Optional[int] = None,
    trigger: str = "",
    judge_source: str = "",
    judge_raw_response: str = "",
    classifier_category: str = "",
    judge_error: str = "",
    provider_history_count: Optional[int] = None,
    provider_history_preview: str = "",
    stance_reason: str = "",
    response_flow: str = "",
    response_goal: str = "",
    flow_reason: str = "",
    raw_llm_response: str = "",
) -> None:
    """
    記錄輸入輸出資訊到 prompts.md
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _write_markdown_log(
        scenario_id=scenario_id,
        timestamp=timestamp,
        user_input=user_input,
        system_prompt=system_prompt,
        response=response,
        action_stance=action_stance,
        emotion=emotion,
        model=model,
        temperature=temperature,
        tone=tone,
        defect_mode=defect_mode,
        ttfb_ms=ttfb_ms,
        total_ms=total_ms,
        max_tokens=max_tokens,
        trigger=trigger,
        judge_source=judge_source,
        judge_raw_response=judge_raw_response,
        classifier_category=classifier_category,
        judge_error=judge_error,
        provider_history_count=provider_history_count,
        provider_history_preview=provider_history_preview,
        stance_reason=stance_reason or flow_reason,
        response_flow=response_flow,
        response_goal=response_goal,
        raw_llm_response=raw_llm_response,
    )


def log_raw_io(
    scenario_id: int,
    input_data: dict,
    output_data: dict,
) -> None:
    """
    記錄原始輸入輸出數據（JSON格式）到 prompts.md
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    import json

    md_entry = f"""
## 📊 場景 {scenario_id} - 原始數據

> 🕐 **時間**: {timestamp}

### 📥 輸入數據
```json
{json.dumps(input_data, ensure_ascii=False, indent=2)}
```

### 📤 輸出數據
```json
{json.dumps(output_data, ensure_ascii=False, indent=2)}
```

---
"""

    try:
        with open(PROMPT_MD, "a", encoding="utf-8") as f:
            f.write(md_entry)
            f.flush()
    except Exception as e:
        print(f"警告：無法寫入 Markdown 原始數據日誌: {e}")


def _write_markdown_log(
    scenario_id: int,
    timestamp: str,
    user_input: str,
    system_prompt: str,
    response: str,
    action_stance: str,
    emotion: float,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tone: Optional[str] = None,
    defect_mode: Optional[str] = None,
    ttfb_ms: Optional[float] = None,
    total_ms: Optional[float] = None,
    max_tokens: Optional[int] = None,
    trigger: str = "",
    judge_source: str = "",
    judge_raw_response: str = "",
    classifier_category: str = "",
    judge_error: str = "",
    provider_history_count: Optional[int] = None,
    provider_history_preview: str = "",
    stance_reason: str = "",
    response_flow: str = "",
    response_goal: str = "",
    raw_llm_response: str = "",
) -> None:
    """
    將日誌以現代化 Markdown 格式寫入 prompts.md
    
    Args:
        各參數同 log_prompt
    """
    from agent.state import STANCE_EMOJI
    
    emotion_bar = _fmt_emotion_bar_md(emotion)
    emotion_zone = _fmt_emotion_zone_md(emotion)
    stance_emoji = STANCE_EMOJI.get(action_stance, f"❓ {action_stance}")
    tone_label = _fmt_tone_label(tone) if tone else "未設定"
    
    md_entry = f"""
## 📌 場景 {scenario_id}

> 🕐 **時間**: {timestamp}

### 🧑 使用者輸入
```
{user_input}
```

### 🤖 模型回應
```
{response}
```

### 📊 元數據
| 項目 | 值 |
|------|-----|
| 🔀 行為 | {stance_emoji} |
| 😊 情緒值 | {emotion_bar} |
| 🌗 情緒區間 | {emotion_zone} |
"""
    
    if model:
        md_entry += f"| 🤖 模型 | `{model}` |\n"
    if temperature is not None:
        md_entry += f"| 🌡️ 溫度 | {temperature} |\n"
    if max_tokens is not None:
        md_entry += f"| 📏 MAX_TOKENS | {max_tokens} |\n"
    if tone:
        md_entry += f"| 🗣️ 語氣 | {tone_label} |\n"
    else:
        md_entry += "| 🗣️ 語氣 | 未設定 |\n"
    if defect_mode:
        md_entry += f"| 🎭 缺陷模式 | {defect_mode} |\n"
    if response_goal:
        md_entry += f"| 🎯 回應目的 | `{response_goal}` |\n"
    if response_flow:
        md_entry += f"| 🧭 回答節奏 | `{response_flow}` |\n"
    if stance_reason:
        md_entry += f"| 🧩 行為原因 | `{stance_reason}` |\n"
    if ttfb_ms is not None:
        md_entry += f"| ⏱️ 首字延遲 | {ttfb_ms:.0f}ms |\n"
    else:
        md_entry += "| ⏱️ 首字延遲 | N/A (非串流) |\n"
    if total_ms is not None:
        md_entry += f"| ⏱️ 總耗時 | {total_ms:.0f}ms |\n"

    md_entry += "\n### ⚙️ 系統提示詞\n<details>\n<summary>點擊展開/收起系統提示詞</summary>\n\n```\n"
    md_entry += system_prompt[:1000]
    if len(system_prompt) > 1000:
        md_entry += f"\n... (已截斷，完整長度: {len(system_prompt)} 字符)"
    md_entry += "\n```\n\n</details>\n"

    if provider_history_count is not None:
        md_entry += f"""

### 🧠 Provider 短期記憶
| 項目 | 值 |
|------|-----|
| 實際傳入 `conversation_history` | {provider_history_count} 筆 |

<details>
<summary>實際傳入片段（太多會截短省略）</summary>

```text
{provider_history_preview or "無短期原文歷史傳入 provider。"}
```

</details>
"""

    _judge_triggers = ("在意我", "幫我")
    if trigger and any(t in trigger for t in _judge_triggers):
        judge_emoji = "🤖" if judge_source == "llm" else "📏"
        fallback_label = " （規則回退）" if judge_source == "rule" else ""
        md_entry += f"""
### 🔍 Judge 判斷
| 項目 | 值 |
|------|-----|
| 🔑 觸發詞 | `{trigger}` |
| 📋 關鍵字分類 | `{classifier_category}` |
| {judge_emoji} Judge 來源 | `{judge_source}`{fallback_label} |
"""
        if judge_raw_response:
            trimmed = judge_raw_response.strip()[:160]
            md_entry += f"| 📝 Judge 原始回應 | `{trimmed}` |\n"
        if judge_error:
            err_trimmed = judge_error.strip()[:200]
            md_entry += f"| ⚠️ Judge 錯誤 | `{err_trimmed}` |\n"

    if raw_llm_response:
        md_entry += "\n### 📦 原始模型輸出 (Raw Output)\n<details>\n<summary>點擊展開/收起模型原始輸出</summary>\n\n```text\n"
        md_entry += raw_llm_response.strip()
        md_entry += "\n```\n\n</details>\n"

    md_entry += "\n---\n"
    
    try:
        with open(PROMPT_MD, "a", encoding="utf-8") as f:
            f.write(md_entry)
            f.flush()
    except Exception as e:
        print(f"警告：無法寫入 Markdown 日誌: {e}")


def _fmt_emotion_bar_md(value: float) -> str:
    """格式化情緒條（Markdown 版本）"""
    num_fill = max(0, min(10, int((value + 1.0) / 2.0 * 10)))
    bar = "█" * num_fill + "░" * (10 - num_fill)
    if value > 0.3:
        label = "🔥 激動"
    elif value > -0.3:
        label = "😊 溫和"
    else:
        label = "😌 冷靜"
    return f"[{bar}] {label} `{value:+.3f}`"


def _fmt_emotion_zone_md(value: float) -> str:
    """格式化情緒區間，對照 response_flow 的加權選擇。"""
    if value < -0.3:
        return "`cold` 冷淡"
    if value < 0.3:
        return "`normal` 穩定"
    if value < 0.7:
        return "`warm` 動搖"
    return "`hot` 炸毛"


def _fmt_tone_label(tone_hints: str) -> str:
    """從多行語氣提示中提取首行標題"""
    if not tone_hints:
        return "未設定"
    first_line = tone_hints.split("\n")[0].strip()
    if first_line.startswith("【") and "】" in first_line:
        return first_line
    if len(first_line) > 40:
        return first_line[:37] + "..."
    return first_line


def log_memory_summary(
    turn: int,
    input_text: str,
    output_text: str,
    model: str = "default",
    existing_memory: str = "",
    source: str = "llm",
    rejected_output: str = "",
    ai_memory: str = "",
) -> None:
    """
    記錄異步記憶摘要到 memory.md

    Args:
        turn: 觸發摘要時的回合數
        input_text: 摘要前的對話內容
        output_text: 完整結構化 Markdown（含摘要原文）
        model: 使用的模型名稱
        existing_memory: 合併前的現有長期記憶
        source: 摘要來源，如 llm / structured_fallback / failed
        rejected_output: 被品質閘門拒絕的原始輸出
        ai_memory: AI 實際可讀的結構化重點（不含摘要原文）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"""
## 🔄 Turn {turn} → 長期記憶更新

> 🕐 **時間**: {timestamp}
> 🤖 **模型**: `{model}`
> 🧪 **來源**: `{source}`
> 📝 **摘要對話數**: {input_text.count(chr(10)) + 1} 行

### 📥 輸入（待摘要的對話）
```
{input_text}
```
"""
    if existing_memory:
        entry += f"""
### 📋 合併前的現有記憶
```
{existing_memory}
```
"""

    if rejected_output:
        entry += f"""
### 🚫 被拒絕的原始摘要輸出
```text
{rejected_output[:1000]}
```
"""

    if ai_memory:
        entry += f"""
### 🤖 AI 可讀記憶
```
{ai_memory}
```
"""

    entry += f"""
### 📤 輸出（完整結構化摘要）
```
{output_text}
```

---
"""

    try:
        with open(MEMORY_MD, "a", encoding="utf-8") as f:
            f.write(entry)
            f.flush()
    except Exception as e:
        print(f"警告：無法寫入記憶日誌: {e}")


def log_initiative_trace(
    run_id: str,
    scenario_id: str,
    trace: Mapping[str, Any],
    *,
    timestamp: Optional[str] = None,
) -> None:
    """將 initiative scenario 的人類可讀診斷摘要追加到 prompts.md。

    initiative trace 使用獨立的 Markdown section，讓同一個 run 的多個
    scenario 可以依序保存；此函式只 append，不負責初始化或清空既有日誌。
    """
    logged_at = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = dict(trace)
    scenario = data.get("scenario", {}) if isinstance(data.get("scenario"), Mapping) else {}
    test_title = str(scenario.get("description") or scenario_id)
    result = str(data.get("result", "UNKNOWN"))
    gates = data.get("gates", []) if isinstance(data.get("gates"), list) else []
    errors = [str(error) for error in data.get("errors", []) if error]
    failed_gates = [gate for gate in gates if isinstance(gate, Mapping) and not gate.get("ok")]

    failure = data.get("failure") if isinstance(data.get("failure"), Mapping) else {}
    primary_reason = str(
        failure.get("primary_reason")
        or data.get("primary_reason")
        or ""
    ).strip()

    def json_block(value: Any) -> str:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"

    gate_rows = []
    for gate in gates:
        if not isinstance(gate, Mapping):
            continue
        status = "PASS" if gate.get("ok") else "FAIL"
        name = str(gate.get("name", "unknown")).replace("|", "\\|")
        summary = str(gate.get("summary", "")).replace("|", "\\|").replace("\n", " ")
        gate_rows.append(f"| {status} | {name} | {summary} |")
    gate_table = "\n".join(gate_rows) or "| - | 尚無 gate | - |"

    if errors or failed_gates:
        issue_lines = []
        if primary_reason:
            issue_lines.append(f"- **主要原因**：`{primary_reason}`")
        issue_lines.extend(f"- `{error}`" for error in errors)
        issue_lines.extend(
            f"- `{gate.get('name', 'unknown')}`：{gate.get('summary', '')}"
            for gate in failed_gates
        )
        issue_summary = "\n".join(issue_lines)
    elif primary_reason:
        issue_summary = f"- **主要原因**：`{primary_reason}`"
    else:
        issue_summary = "- 未發現錯誤或失敗 gate。"

    provider = scenario.get("provider_backend", "unknown")
    model = scenario.get("model", "unknown")
    elapsed_ms = data.get("scenario_elapsed_ms")
    elapsed_text = f"{float(elapsed_ms) / 1000:.2f} 秒" if isinstance(elapsed_ms, (int, float)) else "未知"
    plan = data.get("plan")
    decision = data.get("reappraisal")
    planner_raw = data.get("planner_raw")
    generator_raw = data.get("generator_raw")
    evaluator_raw = data.get("evaluator_raw")
    prompt_hashes = data.get("prompt_hashes", {})

    key_outputs = []
    if plan is not None:
        key_outputs.append("#### Plan\n\n" + json_block(plan))
    if decision is not None:
        key_outputs.append("#### Reappraisal\n\n" + json_block(decision))
    if generator_raw is not None:
        key_outputs.append(f"#### AI 主動訊息\n\n> {str(generator_raw).strip()}")
    if evaluator_raw is not None:
        key_outputs.append("#### Evaluator\n\n" + json_block(evaluator_raw))
    key_output_text = "\n\n".join(key_outputs) or "尚無輸出。"

    prompt_sections = []
    for label, key in (("Planner", "planner_prompt"), ("Generator", "generator_prompt"), ("Evaluator", "evaluator_prompt")):
        if data.get(key) is not None:
            prompt_sections.append(f"#### {label} Prompt\n\n{json_block(data[key])}")
    prompts_text = "\n\n".join(prompt_sections) or "尚無 prompt。"
    entry = f"""
## [{result}] 測試：{test_title} — `{scenario_id}`

> **Run**: `{run_id}`
> **時間**: {logged_at}
> **Provider / Model**: `{provider}` / `{model}`
> **單情境完整耗時**: {elapsed_text}

### 問題摘要

{issue_summary}

### Gate 結果

| 狀態 | 階段 | 摘要 |
|---|---|---|
{gate_table}

### 關鍵輸出

{key_output_text}

### Prompt 指紋

{json_block(prompt_hashes)}

<details>
<summary>展開完整 AI Prompts 與 Planner raw output</summary>

{prompts_text}

#### Planner Raw Output

{json_block(planner_raw) if planner_raw is not None else "尚無輸出。"}

</details>


---
"""

    try:
        with open(PROMPT_MD, "a", encoding="utf-8") as f:
            f.write(entry)
            f.flush()
    except Exception as e:
        print(f"警告：無法追加 initiative trace 日誌: {e}")


def log_initiative_summary(results: Iterable[Mapping[str, Any]]) -> None:
    """將整批 initiative 結果寫到 prompts.md 頂端的可重寫摘要區塊。"""
    payloads = [dict(result) for result in results]
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}
    status_icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}
    rows: list[str] = []

    for index, payload in enumerate(payloads, start=1):
        status = str(payload.get("status") or payload.get("result") or "ERROR").upper()
        if status not in counts:
            status = "ERROR"
        counts[status] += 1
        trace = payload.get("trace") if isinstance(payload.get("trace"), Mapping) else {}
        scenario = trace.get("scenario") if isinstance(trace.get("scenario"), Mapping) else {}
        scenario_id = str(payload.get("scenario_id") or scenario.get("scenario_id") or f"scenario-{index}")
        title = str(scenario.get("description") or scenario_id).replace("|", "\\|").replace("\n", " ")
        gates = payload.get("gates") if isinstance(payload.get("gates"), list) else trace.get("gates", [])
        failed_gate = next(
            (gate for gate in gates if isinstance(gate, Mapping) and not gate.get("ok")),
            None,
        )
        errors = trace.get("errors", []) if isinstance(trace.get("errors"), list) else []
        failure = trace.get("failure") if isinstance(trace.get("failure"), Mapping) else {}
        primary_reason = str(
            failure.get("primary_reason")
            or trace.get("primary_reason")
            or ""
        ).strip()
        if primary_reason:
            detail = primary_reason
        elif failed_gate:
            detail = f"{failed_gate.get('name', 'unknown')}：{failed_gate.get('summary', '')}"
        elif errors:
            detail = str(errors[0])
        else:
            detail = "所有 gate 通過"
        detail = detail.replace("|", "\\|").replace("\n", " ")
        rows.append(
            f"| {index} | {status_icon[status]} **{status}** | {title} | `{scenario_id}` | {detail} |"
        )

    total = len(payloads)
    all_passed = total > 0 and counts["PASS"] == total
    overall = "✅ **全數通過**" if all_passed else "❌ **發現失敗或錯誤，請優先查看紅色項目**"
    summary = f"""{INITIATIVE_SUMMARY_START}
## Initiative 測試總覽

{overall}

> 共 **{total}** 個測試　✅ PASS **{counts['PASS']}**　❌ FAIL **{counts['FAIL']}**　💥 ERROR **{counts['ERROR']}**

| # | 結果 | 測試標題 | Scenario ID | 問題摘要 |
|---:|---|---|---|---|
{chr(10).join(rows) if rows else '| - | - | 尚無測試結果 | - | - |'}
{INITIATIVE_SUMMARY_END}"""

    try:
        content = PROMPT_MD.read_text(encoding="utf-8")
        start = content.find(INITIATIVE_SUMMARY_START)
        end = content.find(INITIATIVE_SUMMARY_END)
        if start < 0 or end < start:
            raise ValueError("initiative summary markers are missing")
        end += len(INITIATIVE_SUMMARY_END)
        PROMPT_MD.write_text(content[:start] + summary + content[end:], encoding="utf-8")
    except Exception as e:
        print(f"警告：無法更新 initiative 測試總覽: {e}")
