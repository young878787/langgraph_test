"""Replay event-driven initiative fixtures from the terminal."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.config import AgentConfig
from agent.initiative.fixtures import FixtureError, InitiativeFixture, load_fixture, load_fixtures
from agent.initiative.runner import InitiativeRunResult, InitiativeRunner
from agent.logger import init_logs, log_initiative_summary


FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "initiative"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay post-dialogue character initiative fixtures with the configured live AI provider."
    )
    parser.add_argument(
        "--scenario",
        default="",
        help="Scenario id or JSON path. Omit to replay every initiative fixture.",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Run each scenario N times (default: 1).")
    parser.add_argument("--seed", type=int, default=None, help="Override fixture seed; repetitions increment it.")
    return parser.parse_args(argv)


def _select_fixtures(scenario: str, config: AgentConfig) -> list[InitiativeFixture]:
    if not scenario:
        return load_fixtures(FIXTURE_DIR, config=config)
    candidate = Path(scenario)
    if candidate.suffix.lower() == ".json" or candidate.exists():
        return [load_fixture(candidate if candidate.is_absolute() else PROJECT_ROOT / candidate, config=config)]
    fixtures = load_fixtures(FIXTURE_DIR, config=config)
    selected = [fixture for fixture in fixtures if fixture.scenario_id == scenario]
    if not selected:
        raise FixtureError(f"unknown initiative scenario: {scenario}")
    return selected


def render_terminal(result: InitiativeRunResult) -> str:
    lines = [
        "Initiative Live Test",
        f"Scenario: {result.scenario_id}",
        f"Repetition: {result.repetition}",
        "",
    ]
    for gate in result.gates or []:
        lines.append(f"[{ 'PASS' if gate.ok else 'FAIL' }] {gate.name}: {gate.summary}")
    if result.initiative_message:
        lines.extend(["", f"AI 主動訊息：{result.initiative_message}"])
    elapsed_ms = (result.trace or {}).get("scenario_elapsed_ms")
    if isinstance(elapsed_ms, (int, float)):
        lines.append(f"完整耗時：{elapsed_ms / 1000:.2f} 秒")
    lines.extend([f"Result: {result.status}", f"Log: {result.log_path}"])
    return "\n".join(lines)


def render_progress(completed: int, total: int, scenario_id: str, status: str = "處理中") -> str:
    width = 20
    filled = width if total == 0 else int(width * completed / total)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {completed}/{total} {status}：{scenario_id}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repeat < 1:
        print("--repeat 必須 >= 1", file=sys.stderr)
        return 2

    config = AgentConfig()
    if (config.backend or "mock").lower() == "mock":
        print(
            "CLI 僅支援真實 AI；請在 .env 設定 LLM_BACKEND=google 或 openrouter。",
            file=sys.stderr,
        )
        return 2
    try:
        fixtures = _select_fixtures(args.scenario, config)
    except FixtureError as exc:
        print(f"Fixture ERROR: {exc}", file=sys.stderr)
        return 2

    # One process-level log refresh; runner only appends detailed traces.
    init_logs()
    runner = InitiativeRunner(config, live_api=True)
    total = len(fixtures) * args.repeat
    results: list[InitiativeRunResult] = []
    completed = 0
    for fixture in fixtures:
        for repetition in range(1, args.repeat + 1):
            print(render_progress(completed, total, fixture.scenario_id), end="\r", flush=True)
            run_seed = None if args.seed is None else args.seed + repetition - 1
            result = runner.run_fixture(fixture, repetition=repetition, seed=run_seed)
            results.append(result)
            completed += 1
            print(render_progress(completed, total, fixture.scenario_id, result.status))

    log_initiative_summary(result.to_dict() for result in results)

    print()
    for index, result in enumerate(results):
        if index:
            print("\n" + "=" * 60 + "\n")
        print(render_terminal(result))
    return 0 if all(result.status == "PASS" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
