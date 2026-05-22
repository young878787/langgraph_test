import os

def rep(p, o, n):
    with open(p, 'r', encoding='utf-8') as f:
        c = f.read()
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c.replace(o, n))

log_p = 'src/agent/logger.py'
rep(log_p, 'strategy: str,', 'action_stance: str,')
rep(log_p, 'strategy=strategy,', 'action_stance=action_stance,')
rep(log_p, 'response_flow: str = "",\n    flow_reason: str = "",', 'stance_reason: str = "",')
rep(log_p, 'response_flow=response_flow,\n        flow_reason=flow_reason,', 'stance_reason=stance_reason,')
rep(log_p, 'from agent.state import STRATEGY_EMOJI', 'from agent.state import STANCE_EMOJI')
rep(log_p, 'strategy_emoji = STRATEGY_EMOJI.get(strategy, f"❓ {strategy}")', 'stance_emoji = STANCE_EMOJI.get(action_stance, f"❓ {action_stance}")')
rep(log_p, '| 🔀 行為 | {strategy_emoji} |', '| 🔀 行為 | {stance_emoji} |')
rep(log_p, '    if response_flow:\n        md_entry += f"| 🧭 回答流程 | `{response_flow}` |\\n"\n    if flow_reason:\n        md_entry += f"| 🧩 流程原因 | `{flow_reason}` |\\n"', '    if stance_reason:\n        md_entry += f"| 🧩 行為原因 | `{stance_reason}` |\\n"')

sr_p = 'src/agent/scenario_runner.py'
rep(sr_p, 'from agent.state import STRATEGY_EMOJI', 'from agent.state import STANCE_EMOJI')
rep(sr_p, 'strategy = state.get("strategy", "unknown")', 'stance = state.get("action_stance", "unknown")')
rep(sr_p, 'strategy_emoji = STRATEGY_EMOJI.get(strategy, f"❓ {strategy}")', 'stance_emoji = STANCE_EMOJI.get(stance, f"❓ {stance}")')
rep(sr_p, 'print(f"│ 【步驟 {index}】 {strategy_emoji:<35}{\'策略: \' + strategy:<20}│")', 'print(f"│ 【步驟 {index}】 {stance_emoji:<35}{\'姿態: \' + stance:<20}│")')
rep(sr_p, 'state["strategy"] = "error"', 'state["action_stance"] = "deadpan"')
rep(sr_p, '策略: {strategy}', '姿態: {stance}')

main_p = 'main.py'
rep(main_p, 'strategy_history: list[str] = []', 'stance_history: list[str] = []')
rep(main_p, 'state["strategy"] = strategy', 'state["action_stance"] = "deadpan"')
rep(main_p, 'strategy = state.get("strategy", "error")', 'stance = state.get("action_stance", "deadpan")')
rep(main_p, 'response_flow = state.get("response_flow", "")\n        ', '')
rep(main_p, '│ 策略:{strategy} │ 流程:{response_flow or \'未設定\'}', '│ 姿態:{stance} │')
rep(main_p, 'response=response, strategy=strategy, tone=tone,\n                defect_mode=strategy,', 'response=response, action_stance=stance, tone=tone,\n                defect_mode=stance,')
rep(main_p, 'response_flow=state.get("response_flow", ""),\n                flow_reason=state.get("flow_reason", ""),', 'stance_reason=state.get("flow_reason", ""),')
rep(main_p, 'strategy_history.append(strategy)', 'stance_history.append(stance)')
rep(main_p, 'strat_counts = Counter(strategy_history)', 'strat_counts = Counter(stance_history)')
rep(main_p, 'strategy=state.get("strategy", "unknown"),', 'action_stance=state.get("action_stance", "unknown"),')
rep(main_p, 'defect_mode=state.get("strategy", "unknown"),', 'defect_mode=state.get("action_stance", "unknown"),')
rep(main_p, 'strategy = state.get("strategy", "unknown")', 'stance = state.get("action_stance", "unknown")')
rep(main_p, 'strategy=strategy,', 'action_stance=stance,')
rep(main_p, 'defect_mode=strategy,', 'defect_mode=stance,')
rep(main_p, '{_fmt_defect_emoji(strategy)} |\n                  f"🧭 {state.get(\'response_flow\', \'未設定\')} | "', '{_fmt_defect_emoji(stance)} | "')

old_func = """def _fmt_defect_emoji(defect_mode: str) -> str:
    emoji_map = {
        "excuse": "🙅 找藉口",
        "gaslight": "🎭 說謊",
        "rambling": "💬 廢話",
        "random_ramble": "🌀 跑題",
        "tsundere": "😤 傲嬌",
        "angry_denial": "🔥 否認",
        "avoidance": "🫣 迴避",
        "defend": "🛡️ 防禦",
        "cooperative_for_once": "😇 配合",
        "honest_defense": "🤷 誠實",
        "yandere_protect": "💘 病嬌",
        "self_contradict": "🔄 矛盾",
        "over_associate": "🦋 聯想",
        "incorrect_correct": "🤓 糾錯",
        "sudden_competence": "✨ 正常",
        "burst": "💥 噴泉",
        "none": "😐 一般",
        "normal": "😐 一般",
        "emotion_burst": "💥 噴泉",
        "error": "⚠️ 故障",
        "tsundere_retort": "😤 傲嬌",
    }
    return emoji_map.get(defect_mode, f"❓ {defect_mode}")"""

new_func = """def _fmt_defect_emoji(defect_mode: str) -> str:
    from agent.state import STANCE_EMOJI
    return STANCE_EMOJI.get(defect_mode, f"❓ {defect_mode}")"""
rep(main_p, old_func, new_func)

print("Refactor complete")
