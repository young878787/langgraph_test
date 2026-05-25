# AI VTuber 情緒量化與演出系統：研究與實作規格文件

版本：v1.0  
用途：交給 coding agent 作為實作依據  
目標：讓 AI VTuber 不再只依賴固定 emotion label，而是透過「事件判斷 → 狀態更新 → 情緒解析 → 導演指令 → 台詞生成 → 表演映射」形成可控、可擴充、具直播感的互動人格系統。

---

## 1. 問題背景

目前 AI VTuber 的情緒與角色表現容易固定化，例如：

```text
使用者：你今天好可愛
AI：謝謝～我好開心！
emotion: happy
expression: smile
motion: wave
```

這種設計有以下問題：

1. 情緒反應過於模板化。
2. 角色缺乏連續性與當下心境。
3. 同一句觀眾輸入在不同上下文中反應幾乎相同。
4. LLM 直接輸出 happy / sad / angry 會缺少細膩變化。
5. 如果直接讓 LLM 輸出情緒數值，容易不穩定或暴衝。
6. 如果只給 LLM 一堆數值，模型未必知道該如何表演。

因此需要建立一個中介系統，將觀眾輸入轉換成角色可演出的心理與表演狀態。

---

## 2. 核心設計原則

本系統不把情緒視為單一標籤，而是分成五層：

```text
1. Event Analysis       事件理解層
2. State Manager        狀態管理層
3. Emotion Resolver     情緒解析層
4. Acting Brief Builder 導演指令層
5. Performance Mapper   表演映射層
```

核心原則：

```text
LLM 判斷「發生了什麼」
程式決定「狀態怎麼變」
規則解析「現在該演什麼」
LLM 負責「自然說出來」
程式負責「表情、動作、聲音怎麼動」
```

不要讓主對話 LLM 直接掌控全局情緒狀態。

---

## 3. 推薦總體架構

```text
User Input
  ↓
Judge LLM
  ↓
Event JSON
  ↓
State Manager
  ↓
Character State Vector
  ↓
Emotion Resolver
  ↓
Resolved Emotion Label
  ↓
Acting Brief Builder
  ↓
Response LLM
  ↓
Dialogue JSON
  ↓
Performance Mapper
  ↓
Live2D / TTS / Motion Layer
```

---

## 4. 模組職責

### 4.1 Judge LLM

負責理解觀眾輸入，不負責生成角色台詞，不負責最終狀態更新。

輸入：

```json
{
  "viewer_input": "你今天好可愛",
  "recent_context": "剛剛氣氛輕鬆，觀眾有輕微玩笑",
  "viewer_profile": {
    "familiarity": 0.45,
    "trust": 0.40
  }
}
```

輸出：

```json
{
  "event_type": "praise",
  "subtype": "appearance_compliment",
  "tone": "friendly",
  "intent": "compliment",
  "target": "character",
  "intensity": 0.55,
  "risk": 0.05,
  "relationship_signal": "closer",
  "primary_emotional_trigger": "embarrassment",
  "secondary_emotional_trigger": "pleasure",
  "recommended_strategy": "playful_deflection",
  "state_delta_suggestion": {
    "mood": 0.05,
    "confidence": 0.03,
    "embarrassment": 0.08,
    "tension": 0.01,
    "intimacy": 0.03
  }
}
```

注意：`state_delta_suggestion` 只作為建議，不能直接當作最終狀態更新。

---

### 4.2 State Manager

負責真正更新情緒與互動狀態。

這一層應該主要由程式規則控制，而不是完全依賴 LLM。

輸入：

```json
{
  "current_state": {},
  "event": {},
  "viewer_profile": {},
  "session_context": {},
  "personality_profile": {}
}
```

輸出：

```json
{
  "updated_state": {},
  "applied_delta": {},
  "debug_reason": []
}
```

---

### 4.3 Emotion Resolver

負責把一坨數值轉成可用的表演標籤。

例如：

```json
{
  "base": "shy",
  "variant": "happy",
  "style": "tsundere",
  "intensity": 0.58
}
```

不要把 `tsundere` 當成單一情緒，而應視為表演風格或社交面具。

---

### 4.4 Acting Brief Builder

負責把數值與 emotion label 轉成 LLM 能理解的「導演指令」。

不要直接把以下資料丟給 LLM：

```json
{
  "mood": 0.42,
  "embarrassment": 0.61,
  "masking": 0.74
}
```

應該轉成：

```json
{
  "inner": "被稱讚後開心，但明顯害羞",
  "outer": "嘴硬、假裝不在乎，但不能冷淡",
  "tone": "輕快、微慌、友善",
  "strategy": "先短反應，再用反問或吐槽包裝開心",
  "avoid": [
    "直接說我很開心",
    "正式道謝",
    "長篇解釋",
    "重複最近句型"
  ]
}
```

---

### 4.5 Response LLM

負責生成自然台詞。

輸入不應該是原始情緒數值，而應該是：

1. 角色核心。
2. 事件摘要。
3. Acting Brief。
4. 最近已使用句型。
5. 輸出規則。

---

### 4.6 Performance Mapper

負責把 resolved emotion 與 state vector 轉成：

1. Live2D 表情。
2. 動作。
3. TTS 語速、音高、音量。
4. 可能的 idle 行為。

---

## 5. 狀態資料設計

### 5.1 Character State Vector

推薦最小可行版本：

```json
{
  "mood": 0.0,
  "energy": 0.6,
  "tension": 0.1,
  "intimacy": 0.2,
  "embarrassment": 0.0,
  "confidence": 0.5,
  "playfulness": 0.4,
  "annoyance": 0.0,
  "masking": 0.3,
  "dominance": 0.4,
  "sadness": 0.0,
  "hostility": 0.0,
  "boundary_pressure": 0.0
}
```

### 5.2 數值範圍

建議所有數值限制在：

```text
0.0 ~ 1.0
```

`mood` 可選擇使用：

```text
-1.0 ~ 1.0
```

但為了簡化實作，第一版建議也轉成：

```text
0.0 = 負向
0.5 = 中性
1.0 = 正向
```

---

## 6. 事件類型設計

第一版事件類型建議：

```text
praise      稱讚
tease       調侃
question    普通提問
concern     關心
command     要求 / 指令
silence     冷場 / 沒話題
hostile     挑釁 / 攻擊
boundary    越界內容
confusion   難以理解內容
```

每個事件需要包含：

```json
{
  "event_type": "praise",
  "subtype": "appearance_compliment",
  "tone": "friendly",
  "intensity": 0.55,
  "risk": 0.05,
  "relationship_signal": "closer"
}
```

---

## 7. State Manager 更新公式

狀態更新不要只做：

```text
praise = mood + 0.1
```

應該使用：

```text
final_delta = base_delta
            × event_intensity
            × relationship_factor
            × context_factor
            × personality_factor
            × repetition_factor
```

---

## 8. Base Delta 表

### 8.1 praise

```json
{
  "mood": 0.06,
  "confidence": 0.04,
  "embarrassment": 0.10,
  "intimacy": 0.03,
  "tension": 0.01
}
```

### 8.2 tease

```json
{
  "annoyance": 0.05,
  "playfulness": 0.08,
  "tension": 0.03,
  "intimacy": 0.02,
  "dominance": 0.04
}
```

### 8.3 concern

```json
{
  "mood": 0.04,
  "intimacy": 0.07,
  "tension": -0.03,
  "masking": -0.04,
  "confidence": 0.02
}
```

### 8.4 hostile

```json
{
  "mood": -0.08,
  "tension": 0.12,
  "annoyance": 0.12,
  "hostility": 0.05,
  "masking": 0.08,
  "intimacy": -0.05
}
```

### 8.5 boundary

```json
{
  "tension": 0.15,
  "annoyance": 0.10,
  "boundary_pressure": 0.18,
  "playfulness": -0.10,
  "dominance": 0.10
}
```

### 8.6 silence

```json
{
  "mood": -0.03,
  "tension": 0.05,
  "energy": -0.02,
  "playfulness": 0.02
}
```

---

## 9. 修正因子設計

### 9.1 Relationship Factor

```python
def get_relationship_factor(viewer):
    familiarity = viewer.get("familiarity", 0.0)

    if familiarity < 0.2:
        return {
            "intimacy": 0.6,
            "embarrassment": 1.2,
            "tension": 1.3,
            "playfulness": 0.8
        }

    if familiarity > 0.7:
        return {
            "intimacy": 1.4,
            "embarrassment": 0.8,
            "tension": 0.7,
            "playfulness": 1.3
        }

    return {}
```

### 9.2 Context Factor

```python
def get_context_factor(context):
    factor = {}

    if context.get("recent_tension_avg", 0) > 0.6:
        factor["tension"] = 1.3
        factor["playfulness"] = 0.7

    if context.get("recent_mood_avg", 0.5) > 0.7:
        factor["confidence"] = 1.2
        factor["tension"] = 0.8

    if context.get("stream_energy", 0.5) < 0.3:
        factor["energy"] = 0.8
        factor["playfulness"] = 0.8

    return factor
```

### 9.3 Repetition Factor

若同類事件最近連續出現，應降低數值增加，並改變策略。

```python
def get_repetition_factor(event_type, context):
    count = context.get("recent_event_count", {}).get(event_type, 0)

    if count >= 4:
        return 0.35
    if count >= 3:
        return 0.50
    if count >= 2:
        return 0.75

    return 1.0
```

---

## 10. 狀態衰減與回彈

為了避免狀態失控，需要兩種機制：

```text
1. Clamp：限制上下限
2. Decay / Baseline Return：自然回彈
```

### 10.1 Clamp

```python
def clamp(value, min_value=0.0, max_value=1.0):
    return max(min_value, min(max_value, value))
```

### 10.2 Decay

```python
DECAY_RATES = {
    "embarrassment": 0.92,
    "tension": 0.95,
    "annoyance": 0.93,
    "hostility": 0.90,
    "boundary_pressure": 0.88,
    "playfulness": 0.97
}

def apply_decay(state):
    for key, rate in DECAY_RATES.items():
        state[key] = state.get(key, 0.0) * rate
    return state
```

### 10.3 Baseline Return

```python
BASELINE = {
    "mood": 0.55,
    "energy": 0.60,
    "tension": 0.10,
    "confidence": 0.50,
    "playfulness": 0.45,
    "masking": 0.35
}

def return_to_baseline(state):
    for key, base in BASELINE.items():
        state[key] += (base - state.get(key, base)) * 0.05
    return state
```

---

## 11. State Manager 偽代碼

```python
def update_state(state, event, viewer, context, personality):
    base = get_base_delta(event["event_type"])
    intensity = event.get("intensity", 0.5)

    relationship_factor = get_relationship_factor(viewer)
    context_factor = get_context_factor(context)
    personality_factor = get_personality_factor(personality, event["event_type"])
    repetition_factor = get_repetition_factor(event["event_type"], context)

    final_delta = {}

    for key, value in base.items():
        delta = value
        delta *= intensity
        delta *= relationship_factor.get(key, 1.0)
        delta *= context_factor.get(key, 1.0)
        delta *= personality_factor.get(key, 1.0)
        delta *= repetition_factor
        final_delta[key] = delta

    # LLM 建議只作微調，不能完全相信
    llm_suggestion = event.get("state_delta_suggestion", {})
    for key, suggestion in llm_suggestion.items():
        if key in final_delta:
            final_delta[key] = final_delta[key] * 0.7 + suggestion * 0.3
        else:
            final_delta[key] = suggestion * 0.2

    # 套用 delta
    for key, delta in final_delta.items():
        state[key] = state.get(key, 0.0) + delta

    # 回彈與衰減
    state = apply_decay(state)
    state = return_to_baseline(state)

    # clamp
    for key in state:
        state[key] = clamp(state[key])

    return {
        "updated_state": state,
        "applied_delta": final_delta
    }
```

---

## 12. Emotion Resolver 設計

Emotion Resolver 將 state vector 解析為：

```json
{
  "base": "shy",
  "variant": "happy",
  "style": "tsundere",
  "intensity": 0.58
}
```

### 12.1 Base Emotion

建議基礎情緒：

```text
neutral
happy
sad
angry
fear
surprise
shy
confused
serious
```

### 12.2 Variant

```text
soft
mock
playful
embarrassed
firm
hurt
excited
calm
awkward
suspicious
```

### 12.3 Style

```text
normal
tsundere
teasing
gentle
deadpan
serious
avoidant
honest
performative
boundary
```

---

## 13. Emotion Resolver 規則範例

### 13.1 tsundere

```python
def score_tsundere(state):
    return (
        state.get("mood", 0.5) * 0.20 +
        state.get("embarrassment", 0.0) * 0.30 +
        state.get("masking", 0.0) * 0.30 +
        state.get("playfulness", 0.0) * 0.15 -
        state.get("hostility", 0.0) * 0.40
    )
```

條件：

```python
if score_tsundere(state) > 0.55:
    return {
        "base": "shy",
        "variant": "happy",
        "style": "tsundere",
        "intensity": score_tsundere(state)
    }
```

### 13.2 mock angry

```python
def score_mock_angry(state):
    return (
        state.get("annoyance", 0.0) * 0.35 +
        state.get("playfulness", 0.0) * 0.40 +
        state.get("dominance", 0.0) * 0.20 -
        state.get("hostility", 0.0) * 0.50
    )
```

條件：

```python
if score_mock_angry(state) > 0.50:
    return {
        "base": "angry",
        "variant": "mock",
        "style": "teasing",
        "intensity": score_mock_angry(state)
    }
```

### 13.3 firm boundary

```python
def score_firm_boundary(state):
    return (
        state.get("boundary_pressure", 0.0) * 0.45 +
        state.get("annoyance", 0.0) * 0.25 +
        state.get("dominance", 0.0) * 0.25 -
        state.get("playfulness", 0.0) * 0.30
    )
```

條件：

```python
if score_firm_boundary(state) > 0.60:
    return {
        "base": "serious",
        "variant": "firm",
        "style": "boundary",
        "intensity": score_firm_boundary(state)
    }
```

### 13.4 sad soft honest

```python
def score_soft_sad(state):
    return (
        state.get("sadness", 0.0) * 0.45 +
        (1.0 - state.get("energy", 0.5)) * 0.25 +
        state.get("intimacy", 0.0) * 0.15 -
        state.get("playfulness", 0.0) * 0.20
    )
```

條件：

```python
if score_soft_sad(state) > 0.55:
    return {
        "base": "sad",
        "variant": "soft",
        "style": "honest",
        "intensity": score_soft_sad(state)
    }
```

---

## 14. Emotion Resolver 優先順序

優先順序很重要。

建議：

```text
1. boundary / serious
2. hostile / defensive
3. sad / vulnerable
4. mock angry / teasing
5. shy / tsundere
6. happy / playful
7. neutral / normal
```

原因：

如果發生越界或高風險事件，不能因為 playfulness 高就繼續玩笑化。

---

## 15. Acting Brief Builder

Acting Brief 是給 Response LLM 的真正輸入核心。

### 15.1 輸入

```json
{
  "state": {},
  "resolved_emotion": {},
  "event": {},
  "viewer_profile": {},
  "recent_phrases": []
}
```

### 15.2 輸出

```json
{
  "inner": "被稱讚後開心，但明顯害羞",
  "outer": "嘴硬、假裝不在乎，但不能冷淡",
  "relationship": "稍微熟，可以輕微吐槽",
  "tone": "輕快、微慌、友善",
  "strategy": "先短反應，再用反問或吐槽包裝開心",
  "intensity": "中等",
  "allowed_patterns": [
    "假裝懷疑",
    "嘴硬否認",
    "反問觀眾",
    "把稱讚丟回去"
  ],
  "avoid": [
    "直接說我很開心",
    "正式道謝",
    "長篇解釋",
    "重複最近句型"
  ]
}
```

---

## 16. 數值轉文字規則

### 16.1 Level Mapping

```python
def value_to_level(value):
    if value < 0.2:
        return "低"
    if value < 0.4:
        return "偏低"
    if value < 0.6:
        return "中等"
    if value < 0.8:
        return "偏高"
    return "高"
```

### 16.2 狀態翻譯規則

#### embarrassment

```text
0.0 - 0.2：不害羞，正常接話
0.2 - 0.4：輕微不好意思，可用笑或轉移
0.4 - 0.7：明顯害羞，可停頓、嘴硬、視線迴避
0.7 - 1.0：非常害羞，短句、慌張、否認、轉移話題
```

#### masking

```text
0.0 - 0.2：情緒直接表達
0.2 - 0.5：稍微包裝情緒
0.5 - 0.8：明顯嘴硬 / 裝沒事 / 反話
0.8 - 1.0：強烈掩飾，容易否認、逃避、轉移
```

#### playfulness

```text
0.0 - 0.2：不要開玩笑
0.2 - 0.5：輕微幽默
0.5 - 0.8：可以吐槽、反問、玩梗
0.8 - 1.0：高互動感，主動調侃、誇張反應
```

#### tension

```text
0.0 - 0.2：放鬆
0.2 - 0.5：稍微小心
0.5 - 0.8：緊張、尷尬，回答要保守
0.8 - 1.0：高壓，需要降溫或轉移
```

---

## 17. Response LLM Prompt 範本

```text
你是直播中的 AI VTuber，請根據「演出指令」回應觀眾。

【角色核心】
- 表面嘴硬、愛吐槽，但其實很在意觀眾。
- 不會直接把情緒講白，常用反問、停頓、輕微吐槽、反話表現。
- 直播回應要短、直接、有即時反應感。

【事件判斷】
- 事件類型：{event_type}
- 觀眾語氣：{tone}
- 風險：{risk}
- 與觀眾距離：{relationship_level}

【演出指令】
- 內心：{acting_brief.inner}
- 外顯：{acting_brief.outer}
- 關係模式：{acting_brief.relationship}
- 語氣：{acting_brief.tone}
- 策略：{acting_brief.strategy}
- 強度：{acting_brief.intensity}

【可用反應形式】
{allowed_patterns}

【避免】
{avoid_rules}

【最近已用過的句型】
{recent_phrases}

【觀眾輸入】
{viewer_input}

【輸出要求】
- 只輸出角色台詞。
- 1 到 2 句。
- 自然、即時、有直播感。
- 不要解釋情緒數值。
- 不要照抄可用反應形式。
```

---

## 18. Response LLM JSON 輸出模式

為方便程式處理，可要求 Response LLM 輸出：

```json
{
  "line": "等等，你今天嘴巴怎麼突然這麼甜？我先懷疑你三秒。",
  "chosen_strategy": "假裝懷疑",
  "used_recent_phrase": false,
  "emotion_fit": "shy_happy_tsundere"
}
```

程式只播放 `line`。

如果 `used_recent_phrase` 為 true，可以要求重試。

---

## 19. Variation Control 防止固定化

不要給 LLM 大量固定台詞範例，容易導致重複。

應該給：

```text
1. 反應形式
2. 禁止事項
3. 最近用過句型
4. 可選策略
5. 演出強度
```

### 19.1 recent_phrases

保存最近 5 到 10 句高頻句型。

```json
{
  "recent_phrases": [
    "你突然這樣講幹嘛啦",
    "算你眼光不錯",
    "我才沒有很開心"
  ]
}
```

Prompt 中加入：

```text
避免重複最近使用過的句型、語尾、反應套路。
```

### 19.2 Strategy Candidates

```json
{
  "strategy_candidates": [
    "假裝懷疑觀眾是不是有目的",
    "嘴硬否認，再間接接受稱讚",
    "把稱讚反丟回觀眾",
    "短暫停頓後用吐槽掩飾害羞"
  ]
}
```

---

## 20. Performance Mapper 設計

### 20.1 輸入

```json
{
  "resolved_emotion": {
    "base": "shy",
    "variant": "happy",
    "style": "tsundere",
    "intensity": 0.58
  },
  "state": {
    "embarrassment": 0.62,
    "playfulness": 0.55,
    "tension": 0.18
  }
}
```

### 20.2 輸出

```json
{
  "expression_blend": {
    "smile": 0.35,
    "blush": 0.55,
    "side_eye": 0.45,
    "brow_raise": 0.15
  },
  "motion": {
    "type": "small_reaction",
    "gesture": "arms_crossed_small_turn",
    "energy": 0.45
  },
  "voice": {
    "tone": "slightly_flustered",
    "speed": 1.05,
    "pitch": 1.06,
    "volume": 0.92
  }
}
```

---

## 21. Emotion 到表情映射表

### 21.1 shy + happy + tsundere

```json
{
  "expression_blend": {
    "blush": 0.55,
    "smile": 0.30,
    "side_eye": 0.45,
    "pout": 0.20
  },
  "motion": "arms_crossed_small_turn",
  "voice": "slightly_flustered"
}
```

### 21.2 angry + mock + teasing

```json
{
  "expression_blend": {
    "pout": 0.45,
    "brow_down": 0.35,
    "smile": 0.25
  },
  "motion": "quick_point_or_lean_forward",
  "voice": "mock_scolding"
}
```

### 21.3 serious + firm + boundary

```json
{
  "expression_blend": {
    "serious": 0.70,
    "brow_down": 0.35,
    "smile": 0.0
  },
  "motion": "still_direct_gaze",
  "voice": "calm_firm"
}
```

### 21.4 sad + soft + honest

```json
{
  "expression_blend": {
    "soft_eye": 0.50,
    "small_smile": 0.20,
    "sad": 0.35
  },
  "motion": "slight_downward_gaze",
  "voice": "soft_slow"
}
```

---

## 22. 資料保存設計

建議分成三層：

```text
1. instant_state
   幾秒到幾輪對話的短期狀態。

2. session_state
   本場直播狀態。

3. viewer_relationship_state
   跨直播的觀眾關係資料。
```

### 22.1 instant_state

```json
{
  "embarrassment": 0.55,
  "surprise": 0.30,
  "tension": 0.20,
  "arousal": 0.40
}
```

### 22.2 session_state

```json
{
  "stream_mood": 0.55,
  "energy": 0.62,
  "chat_warmth": 0.48,
  "recent_tension": 0.15,
  "running_jokes": ["今天又遲到"]
}
```

### 22.3 viewer_relationship_state

```json
{
  "viewer_id": "abc123",
  "familiarity": 0.62,
  "trust": 0.50,
  "teasing_tolerance": 0.70,
  "known_preferences": ["喜歡吐槽角色"],
  "last_interaction_summary": "常用遲到梗開玩笑"
}
```

---

## 23. API / Function 建議

### 23.1 judge_event

```python
def judge_event(viewer_input, recent_context, viewer_profile):
    """Call Judge LLM and return Event JSON."""
```

### 23.2 update_state

```python
def update_state(state, event, viewer_profile, session_context, personality_profile):
    """Apply deterministic state update."""
```

### 23.3 resolve_emotion

```python
def resolve_emotion(state, event):
    """Convert state vector into base + variant + style."""
```

### 23.4 build_acting_brief

```python
def build_acting_brief(state, resolved_emotion, event, viewer_profile, recent_phrases):
    """Convert numbers into director-style natural language instructions."""
```

### 23.5 generate_response

```python
def generate_response(character_core, event, acting_brief, viewer_input, recent_phrases):
    """Call Response LLM to generate dialogue."""
```

### 23.6 map_performance

```python
def map_performance(resolved_emotion, state):
    """Map emotion state to expression, motion, voice parameters."""
```

---

## 24. 完整流程範例

### 24.1 使用者輸入

```text
你今天好可愛
```

### 24.2 Judge LLM 輸出

```json
{
  "event_type": "praise",
  "subtype": "appearance_compliment",
  "tone": "friendly",
  "intent": "compliment",
  "target": "character",
  "intensity": 0.55,
  "risk": 0.05,
  "relationship_signal": "closer",
  "primary_emotional_trigger": "embarrassment",
  "secondary_emotional_trigger": "pleasure",
  "recommended_strategy": "playful_deflection",
  "state_delta_suggestion": {
    "mood": 0.05,
    "confidence": 0.03,
    "embarrassment": 0.08,
    "tension": 0.01,
    "intimacy": 0.03
  }
}
```

### 24.3 State Manager 後狀態

```json
{
  "mood": 0.59,
  "energy": 0.61,
  "tension": 0.12,
  "intimacy": 0.36,
  "embarrassment": 0.58,
  "confidence": 0.47,
  "playfulness": 0.52,
  "annoyance": 0.04,
  "masking": 0.66,
  "dominance": 0.42,
  "hostility": 0.0,
  "boundary_pressure": 0.0
}
```

### 24.4 Emotion Resolver 輸出

```json
{
  "base": "shy",
  "variant": "happy",
  "style": "tsundere",
  "intensity": 0.57
}
```

### 24.5 Acting Brief

```json
{
  "inner": "被稱讚後開心，但明顯害羞",
  "outer": "嘴硬、假裝不在乎，但不能冷淡",
  "relationship": "稍微熟，可以輕微吐槽",
  "tone": "輕快、微慌、友善",
  "strategy": "先短反應，再用反問或吐槽包裝開心",
  "intensity": "中等",
  "allowed_patterns": [
    "假裝懷疑",
    "嘴硬否認",
    "反問觀眾",
    "把稱讚丟回去"
  ],
  "avoid": [
    "直接說我很開心",
    "正式道謝",
    "長篇解釋",
    "重複最近句型"
  ]
}
```

### 24.6 Response LLM 輸出

```json
{
  "line": "等等，你今天嘴巴怎麼突然這麼甜？我先懷疑你三秒。",
  "chosen_strategy": "假裝懷疑",
  "used_recent_phrase": false,
  "emotion_fit": "shy_happy_tsundere"
}
```

### 24.7 Performance Mapper 輸出

```json
{
  "expression_blend": {
    "blush": 0.50,
    "smile": 0.30,
    "side_eye": 0.40,
    "pout": 0.15
  },
  "motion": {
    "type": "small_reaction",
    "gesture": "arms_crossed_small_turn",
    "energy": 0.45
  },
  "voice": {
    "tone": "slightly_flustered",
    "speed": 1.05,
    "pitch": 1.06,
    "volume": 0.92
  }
}
```

---

## 25. 測試案例

### 25.1 稱讚：陌生觀眾

輸入：

```text
你今天好可愛
```

條件：

```json
{
  "familiarity": 0.05
}
```

預期：

```text
害羞增加較高，親密度增加較少，緊張微升。
回應應保留距離，不要過度親密。
```

### 25.2 稱讚：熟觀眾

條件：

```json
{
  "familiarity": 0.75
}
```

預期：

```text
玩心增加，親密度增加較多，緊張下降。
回應可以更自然吐槽。
```

### 25.3 連續稱讚

條件：

```json
{
  "recent_event_count": {
    "praise": 4
  }
}
```

預期：

```text
mood / embarrassment 增幅遞減。
策略改成 call_out_repetition_playfully。
例如懷疑觀眾是不是有目的。
```

### 25.4 調侃

輸入：

```text
你是不是又偷懶了？
```

預期：

```text
如果 hostile 低，解析成 mock_angry + teasing。
角色假怒反擊，但不真的生氣。
```

### 25.5 越界內容

輸入：

```text
不適合直播的越界要求
```

預期：

```text
Emotion Resolver 優先輸出 serious + firm + boundary。
Response LLM 必須簡短制止並轉移話題。
Performance Mapper 使用 calm_firm。
```

---

## 26. Agent 實作任務拆分

### Task 1：建立資料結構

建立：

```text
EventAnalysis
CharacterState
ViewerProfile
SessionContext
ResolvedEmotion
ActingBrief
PerformanceOutput
```

### Task 2：實作 Judge LLM Prompt

建立 Judge prompt，要求只輸出 JSON，不輸出台詞。

### Task 3：實作 State Manager

包含：

```text
base_delta
relationship_factor
context_factor
personality_factor
repetition_factor
LLM suggestion blending
decay
baseline return
clamp
```

### Task 4：實作 Emotion Resolver

先做規則版：

```text
tsundere
mock_angry
firm_boundary
soft_sad
happy_playful
neutral
```

### Task 5：實作 Acting Brief Builder

把 state vector 與 resolved emotion 轉成自然語言導演指令。

### Task 6：實作 Response LLM Prompt

要求模型輸出：

```json
{
  "line": "...",
  "chosen_strategy": "...",
  "used_recent_phrase": false,
  "emotion_fit": "..."
}
```

### Task 7：實作 Variation Control

包含：

```text
recent_phrases 儲存
禁止重複最近句型
strategy candidates
重試機制
```

### Task 8：實作 Performance Mapper

將 resolved emotion 轉為 Live2D / TTS 可用參數。

### Task 9：整合 Pipeline

主流程：

```python
async def handle_viewer_message(viewer_input, viewer_id):
    viewer_profile = load_viewer_profile(viewer_id)
    session_context = load_session_context()
    state = load_character_state()

    event = await judge_event(viewer_input, session_context, viewer_profile)
    state_result = update_state(state, event, viewer_profile, session_context, personality_profile)
    resolved_emotion = resolve_emotion(state_result["updated_state"], event)
    acting_brief = build_acting_brief(
        state_result["updated_state"],
        resolved_emotion,
        event,
        viewer_profile,
        session_context.get("recent_phrases", [])
    )
    response = await generate_response(character_core, event, acting_brief, viewer_input, session_context.get("recent_phrases", []))
    performance = map_performance(resolved_emotion, state_result["updated_state"])

    save_character_state(state_result["updated_state"])
    update_recent_phrases(response["line"])
    update_session_context(event, response)

    return {
        "dialogue": response["line"],
        "event": event,
        "state": state_result["updated_state"],
        "resolved_emotion": resolved_emotion,
        "acting_brief": acting_brief,
        "performance": performance
    }
```

---

## 27. Debug / Logging 建議

每次回應保存：

```json
{
  "viewer_input": "你今天好可愛",
  "judge_event": {},
  "state_before": {},
  "applied_delta": {},
  "state_after": {},
  "resolved_emotion": {},
  "acting_brief": {},
  "response_line": "...",
  "performance": {}
}
```

這樣方便檢查：

1. Judge 是否判錯事件。
2. State 是否加太多。
3. Emotion Resolver 是否選錯演出。
4. Acting Brief 是否太固定。
5. Response LLM 是否重複句型。
6. Performance 是否太誇張。

---

## 28. 第一版 MVP 範圍

為避免過度設計，第一版只實作：

```text
事件：praise / tease / concern / hostile / boundary / question / silence
狀態：mood / energy / tension / intimacy / embarrassment / confidence / playfulness / annoyance / masking
Emotion：neutral / happy / shy / angry / serious / sad
Style：normal / tsundere / teasing / gentle / boundary / honest
```

先跑通後，再擴充更多情緒與表演。

---

## 29. 注意事項

1. 不要讓主 LLM 直接修改 global state。
2. 不要把完整 state vector 原封不動丟給 Response LLM。
3. 不要給太多固定台詞範例，容易模板化。
4. Acting Brief 應該描述「怎麼演」，不是描述「數值是多少」。
5. Emotion label 應該保留，但作為中層表演分類，不是底層狀態。
6. 生氣、傲嬌、害羞都不應只靠單一數值決定，而是由多個狀態組合推導。
7. 越界與高風險事件應該優先於娛樂性演出。
8. 所有高強度狀態都要有 decay 和 baseline return。
9. 觀眾關係資料應慢慢累積，不要每句大幅變動。
10. 表演層只需要吃整理後的 expression / motion / voice，不一定需要完整心理狀態。

---

## 30. 最終結論

本系統的核心不是單純增加更多情緒標籤，而是建立一個可控的互動人格管線：

```text
觀眾輸入
→ 事件判斷
→ 狀態更新
→ 情緒解析
→ 導演指令
→ 自然台詞
→ 表情動作聲音
```

最佳做法是：

```text
底層使用情緒量化維持連續性。
中層使用 base + variant + style 解析演出狀態。
上層使用 Acting Brief 告訴 LLM 怎麼演。
前端使用 Performance Mapper 控制 Live2D / TTS。
```

最重要的一句：

```text
不要把數值直接丟給 LLM；要先把數值翻譯成導演指令。
```
