from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
ERROR_LOG = LOG_DIR / "error.log"
PROMPT_LOG = LOG_DIR / "prompts.log"


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
    tone: str,
    defect_mode: str,
    emotion: float,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> None:
    """
    記錄輸入輸出的格式化資訊到 prompts.log
    
    Args:
        scenario_id: 場景ID
        user_input: 使用者輸入
        system_prompt: 系統提示詞
        response: 模型回應
        strategy: 策略
        tone: 語氣
        defect_mode: 缺陷模式
        emotion: 情緒值
        model: 使用的模型（選用）
        temperature: 溫度參數（選用）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
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
  - 語氣: {tone}
  - 缺陷模式: {defect_mode}
  - 情緒值: {emotion:.3f}
"""
    
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


def log_raw_io(
    scenario_id: int,
    input_data: dict,
    output_data: dict,
) -> None:
    """
    記錄原始輸入輸出數據（JSON格式）
    
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
