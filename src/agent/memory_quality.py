from __future__ import annotations

import re


SUMMARY_PREFIXES = (
    "輸出更新後的完整摘要：",
    "輸出更新後的完整摘要:",
    "輸出摘要：",
    "輸出摘要:",
    "摘要內容：",
    "摘要內容:",
    "摘要：",
    "摘要:",
)

META_LINE_PATTERNS = (
    r"^\s*\*\s*(Input|Task|Guidelines?|Constraint|Output|Segment \d+):.*$",
    r"^\s*\d+\.\s*(Input|Task|Guidelines?|Constraint|Output|Segment \d+):.*$",
    r"^\s*[-–—]\s*(Input|Task|Guidelines?|Constraint|Output|Segment \d+):.*$",
    r"^\s*(Input|Task|Guidelines?|Constraint|Output|Segment \d+):.*$",
)

PROMPT_LEAKAGE_KEYWORDS = (
    "Input:",
    "Task:",
    "Guidelines:",
    "Guideline:",
    "Constraint:",
    "Output:",
    "Segment ",
)

USER_FACT_KEYWORDS = ("確認", "確定", "偏好", "喜歡", "討厭", "希望", "要求", "記得")
USER_PROPOSAL_KEYWORDS = ("提議", "建議", "想要", "要不要", "不如", "可以", "試試")
USER_EMOTION_KEYWORDS = (
    "開心",
    "難過",
    "生氣",
    "火大",
    "焦慮",
    "失望",
    "稱讚",
    "誇",
    "罵",
    "攻擊",
    "吐槽",
)
ASSISTANT_STANCE_KEYWORDS = (
    "我拒絕",
    "拒絕",
    "不能",
    "不會",
    "我可以",
    "可以",
    "接受",
    "同意",
    "答應",
)
ASSISTANT_EMOTION_KEYWORDS = (
    "害羞",
    "臉紅",
    "不好意思",
    "心虛",
    "嘴硬",
    "真心",
    "動搖",
    "恢復",
    "稱讚",
    "誇",
)


def clean_summary_output(text: str) -> str:
    """清理摘要 LLM 輸出，保留結構化 Markdown 格式。"""
    cleaned = text.strip()

    changed = True
    while changed:
        changed = False
        cleaned = cleaned.strip()
        for prefix in SUMMARY_PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True

    filtered_lines = []
    for line in cleaned.splitlines():
        stripped_line = line.lstrip()
        if any(re.match(pattern, line, re.IGNORECASE) for pattern in META_LINE_PATTERNS):
            continue
        # 移除 Segment N: 這種結構化標記
        if re.match(r"^\s*Segment\s+\d+:\s*", line, re.IGNORECASE):
            continue
        filtered_lines.append(line)
    cleaned = "\n".join(filtered_lines).strip()

    # 只移除強調標記，不碰 Markdown 列表與標題
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)

    return cleaned.strip()


def extract_ai_memory(markdown: str) -> str:
    """從完整結構化 Markdown 中移除『摘要原文』區塊，保留 AI 可讀的重點。"""
    # 移除 ### 7. 摘要原文 到下一個 ### 或檔案結尾
    pattern = r"\n*###\s*7\.?\s*摘要原文\b.*?(?=\n###|\Z)"
    cleaned = re.sub(pattern, "", markdown, flags=re.DOTALL)
    return cleaned.strip()


def is_structured_memory(text: str) -> bool:
    """檢查文字是否包含結構化長期記憶的必要區塊。"""
    required_sections = (
        "對話總覽",
        "使用者相關記憶",
        "AI 人設/偏好記憶",
        "共同事實 / 任務狀態",
    )
    return all(section in text for section in required_sections)


def validate_summary(text: str) -> bool:
    """驗證摘要是否足夠像可用記憶，而不是 prompt leakage 或低品質 fallback。"""
    stripped = text.strip()
    if len(stripped) < 15:
        return False

    leakage_count = sum(1 for keyword in PROMPT_LEAKAGE_KEYWORDS if keyword in stripped)
    if leakage_count >= 2:
        return False

    compact = stripped.replace(" ", "").replace("\n", "")
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", compact))
    if compact and chinese_chars / len(compact) < 0.3:
        return False

    if _looks_like_mechanical_fallback(stripped):
        return False

    if stripped in {"（摘要失敗，無法提取有效內容）", "摘要失敗，無法提取有效內容"}:
        return False

    return True


def build_structured_fallback(messages: list[dict]) -> str:
    """從交錯訊息保守產生低信心結構化摘要，不把 assistant 表述升格成外部事實。"""
    user_items: list[str] = []
    ai_items: list[str] = []

    for message in messages:
        role = message.get("role")
        content = _normalize_space(str(message.get("content", "")))
        if not content:
            continue

        if role == "user":
            item = _summarize_user_message(content)
            if item and item not in user_items:
                user_items.append(item)
        elif role == "assistant":
            item = _summarize_assistant_message(content)
            if item and item not in ai_items:
                ai_items.append(item)

    if not user_items and not ai_items:
        return (
            "### 1. 對話總覽\n"
            "低信心摘要：本批對話以閒聊/吐槽為主，未萃取到可確認長期事實。\n\n"
            "### 2. 使用者相關記憶\n- 待確認\n\n"
            "### 3. AI 人設/偏好記憶\n- 待確認\n\n"
            "### 4. 共同事實 / 任務狀態\n- 待確認\n\n"
            "### 5. 待確認/不確定項目\n- 本摘要為 fallback 產生，信心度低\n\n"
            "### 6. 標籤\n#fallback\n\n"
            "### 7. 摘要原文\n"
            "低信心摘要，本批對話未萃取出可確認長期事實。"
        )

    user_section = "\n".join(f"- {item}" for item in user_items) if user_items else "- 待確認"
    ai_section = "\n".join(f"- {item}" for item in ai_items) if ai_items else "- 待確認"

    return (
        "### 1. 對話總覽\n"
        "低信心摘要：本批對話以閒聊/吐槽為主，已盡力萃取重點。\n\n"
        f"### 2. 使用者相關記憶\n{user_section}\n\n"
        f"### 3. AI 人設/偏好記憶\n{ai_section}\n\n"
        "### 4. 共同事實 / 任務狀態\n- 待確認\n\n"
        "### 5. 待確認/不確定項目\n- 本摘要為 fallback 產生，信心度低\n\n"
        "### 6. 標籤\n#fallback\n\n"
        "### 7. 摘要原文\n"
        "低信心摘要，僅依本批對話表述整理，尚未外部驗證。"
    )


def _looks_like_mechanical_fallback(text: str) -> bool:
    has_user_topic = "使用者提到：" in text or "使用者提到:" in text
    has_ai_topic = "AI 回應涉及：" in text or "AI 回應涉及:" in text
    return has_user_topic and has_ai_topic


def _summarize_user_message(content: str) -> str:
    snippet = _truncate_text(content, 80)
    if _contains_any(content, USER_FACT_KEYWORDS):
        return f"表達偏好或需求：{snippet}"
    if _contains_any(content, USER_PROPOSAL_KEYWORDS):
        return f"提出互動提議：{snippet}"
    if _contains_any(content, USER_EMOTION_KEYWORDS):
        return f"出現情緒或互動轉折：{snippet}"
    if "？" in content or "?" in content:
        return f"詢問或開啟話題：{snippet}"
    return ""


def _summarize_assistant_message(content: str) -> str:
    snippet = _truncate_text(content, 80)
    if _contains_any(content, ASSISTANT_STANCE_KEYWORDS):
        if "拒絕" in content or "不能" in content or "不會" in content:
            return f"明確拒絕或設下界線：{snippet}"
        return f"明確接受、同意或承諾互動：{snippet}"
    if _contains_any(content, ASSISTANT_EMOTION_KEYWORDS):
        return f"出現情緒或人格轉折：{snippet}"
    return ""


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
