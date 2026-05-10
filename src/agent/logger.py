from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
ERROR_LOG = LOG_DIR / "error.log"
PROMPT_LOG = LOG_DIR / "prompts.log"
PROMPT_MD = LOG_DIR / "prompts.md"


def init_logs() -> None:
    """初始化日誌檔案，每次啟動時清空舊日誌並重新開始記錄"""
    # 確保日誌目錄存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 準備啟動資訊
    startup_info = f"{'=' * 80}\n=== 日誌開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n{'=' * 80}\n\n"
    
    for log_file in [ERROR_LOG, PROMPT_LOG]:
        try:
            # 使用 'w' 模式清空文件並寫入新的啟動資訊
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(startup_info)
                f.flush()
        except Exception as e:
            # 如果無法建立日誌檔案，至少列印錯誤
            print(f"警告：無法初始化日誌檔案 {log_file}: {e}")
    
    # 初始化 Markdown 日誌
    try:
        md_header = f"""# 📝 Prompts 日誌

> 生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

"""
        with open(PROMPT_MD, "w", encoding="utf-8") as f:
            f.write(md_header)
            f.flush()
    except Exception as e:
        print(f"警告：無法初始化 Markdown 日誌檔案: {e}")


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
) -> None:
    """
    記錄輸入輸出的格式化資訊到 prompts.log 和 prompts.md
    
    Args:
        scenario_id: 場景ID
        user_input: 使用者輸入
        system_prompt: 系統提示詞
        response: 模型回應
        strategy: 策略
        emotion: 情緒值
        model: 使用的模型（選用）
        temperature: 溫度參數（選用）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 原始 log 格式（保持向後兼容）
    log_entry = f"""
[{timestamp}] 場景 {scenario_id}
{'=' * 80}
使用者輸入:
{user_input}

系統提示詞:
{system_prompt[:500]}{'...' if len(system_prompt) > 500 else ''}

模型回應:
{response}

元數據:
  - 策略: {strategy}
  - 情緒值: {emotion:.3f}
"""
    
    if tone:
        log_entry += f"  - 語氣: {tone}\n"
    if defect_mode:
        log_entry += f"  - 缺陷模式: {defect_mode}\n"
    if model:
        log_entry += f"  - 模型: {model}\n"
    if temperature is not None:
        log_entry += f"  - 溫度: {temperature}\n"
    
    log_entry += "=" * 80 + "\n"
    
    try:
        with open(PROMPT_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
            f.flush()  # 立即寫入磁碟
    except Exception as e:
        print(f"警告：無法寫入提示詞日誌: {e}")
    
    # Markdown 格式輸出（現代化風格）
    _write_markdown_log(
        scenario_id=scenario_id,
        timestamp=timestamp,
        user_input=user_input,
        system_prompt=system_prompt,
        response=response,
        strategy=strategy,
        emotion=emotion,
        model=model,
        temperature=temperature
    )


def log_raw_io(
    scenario_id: int,
    input_data: dict,
    output_data: dict,
) -> None:
    """
    記錄原始輸入輸出數據（JSON格式）到 prompts.log 和 prompts.md
    
    Args:
        scenario_id: 場景ID
        input_data: 輸入數據字典
        output_data: 輸出數據字典
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    import json
    
    log_entry = f"""
[{timestamp}] 場景 {scenario_id} - 原始數據
輸入:
{json.dumps(input_data, ensure_ascii=False, indent=2)}

輸出:
{json.dumps(output_data, ensure_ascii=False, indent=2)}
{'=' * 80}
"""
    
    try:
        with open(PROMPT_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
            f.flush()  # 立即寫入磁碟
    except Exception as e:
        print(f"警告：無法寫入原始數據日誌: {e}")
    
    # Markdown 格式
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
) -> None:
    """
    將日誌以現代化 Markdown 格式寫入 prompts.md
    
    Args:
        各參數同 log_prompt
    """
    from agent.state import STRATEGY_EMOJI
    
    emotion_bar = _fmt_emotion_bar_md(emotion)
    strategy_emoji = STRATEGY_EMOJI.get(strategy, f"❓ {strategy}")
    
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
    
    md_entry += "\n### ⚙️ 系統提示詞\n<details>\n<summary>點擊展開/收起系統提示詞</summary>\n\n```\n"
    md_entry += system_prompt[:1000]
    if len(system_prompt) > 1000:
        md_entry += f"\n... (已截斷，完整長度: {len(system_prompt)} 字符)"
    md_entry += "\n```\n\n</details>\n\n---\n"
    
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
