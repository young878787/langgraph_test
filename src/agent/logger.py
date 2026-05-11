from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
ERROR_LOG = LOG_DIR / "error.log"
PROMPT_MD = LOG_DIR / "prompts.md"


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

---

"""
        with open(PROMPT_MD, "w", encoding="utf-8") as f:
            f.write(md_header)
            f.flush()
    except Exception as e:
        print(f"警告：無法初始化 Markdown 日誌 {PROMPT_MD}: {e}")


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
    strategy: str,
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
        strategy=strategy,
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
    strategy: str,
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
) -> None:
    """
    將日誌以現代化 Markdown 格式寫入 prompts.md
    
    Args:
        各參數同 log_prompt
    """
    from agent.state import STRATEGY_EMOJI
    
    emotion_bar = _fmt_emotion_bar_md(emotion)
    strategy_emoji = STRATEGY_EMOJI.get(strategy, f"❓ {strategy}")
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
| 🔀 行為 | {strategy_emoji} |
| 😊 情緒值 | {emotion_bar} |
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
