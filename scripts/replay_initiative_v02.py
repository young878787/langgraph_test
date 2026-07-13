"""Replay initiative v0.2 E2E scenarios without coupling the CLI to runner internals."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
import importlib
import inspect
from pathlib import Path
import sys
import types
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if "agent" not in sys.modules:
    package = types.ModuleType("agent")
    package.__path__ = [str(SRC_PATH / "agent")]
    sys.modules["agent"] = package

from agent.initiative.scenario import ScenarioError, ScenarioFixture, load_scenarios
from agent.logger import init_logs, log_error, log_initiative_summary, log_initiative_trace


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "initiative_v02" / "core_scenarios.json"
RUNNER_MODULE = "agent.initiative.scenario_runner_v02"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay initiative v0.2 structured E2E scenarios.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--scenario", help="Replay one scenario id.")
    selection.add_argument("--all", action="store_true", help="Replay every fixture scenario.")
    parser.add_argument("--live-api", action="store_true", help="Use the runner's live AI policy.")
    parser.add_argument("--repeat", type=int, default=1, help="Run each scenario N times (default: 1).")
    parser.add_argument("--seed", type=int, default=None, help="Base run seed; repetitions increment it.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def select_fixtures(fixtures: Iterable[ScenarioFixture], scenario_id: str | None) -> tuple[ScenarioFixture, ...]:
    fixtures = tuple(fixtures)
    if scenario_id is None:
        return fixtures
    selected = tuple(item for item in fixtures if item.model.scenario_id == scenario_id)
    if not selected:
        raise ScenarioError(f"unknown initiative v0.2 scenario: {scenario_id}")
    return selected


def to_mapping(value: Any) -> dict[str, Any]:
    """Normalize Mapping/dataclass runner results for logger and CLI rendering."""
    if isinstance(value, Mapping):
        return dict(value)
    for adapter_name in ("to_mapping", "to_dict"):
        adapter = getattr(value, adapter_name, None)
        if callable(adapter):
            result = adapter()
            if not isinstance(result, Mapping):
                raise TypeError(f"runner result {adapter_name}() must return a Mapping")
            return dict(result)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"runner result must be a Mapping or dataclass, got {type(value).__name__}")


async def invoke_runner(
    fixtures: tuple[ScenarioFixture, ...], *, live_api: bool, repeat: int, seed: int | None
) -> list[Any]:
    """Invoke the stable batch hook, or a class-level fixture hook during migration."""
    module = importlib.import_module(RUNNER_MODULE)
    batch = getattr(module, "run_scenarios", None)
    if callable(batch):
        result = batch(fixtures, live_api=live_api, repeat=repeat, seed=seed)
        if inspect.isawaitable(result):
            result = await result
        return list(result)

    runner_type = getattr(module, "ScenarioRunnerV02", None)
    fixture_hook = getattr(runner_type, "run_fixture", None) if runner_type else None
    if callable(fixture_hook):
        results: list[Any] = []
        for fixture in fixtures:
            for repetition in range(repeat):
                run_seed = None if seed is None else seed + repetition
                result = fixture_hook(
                    fixture, live_api=live_api, repetition=repetition + 1, seed=run_seed
                )
                if inspect.isawaitable(result):
                    result = await result
                results.append(result)
        return results

    raise RuntimeError(
        f"{RUNNER_MODULE} 尚未提供 run_scenarios(...) 或 ScenarioRunnerV02.run_fixture(...)；"
        "CLI 不會猜測 runner 建構參數，請在 runner 端提供其中一個 adapter。"
    )


def _result_details(raw: Mapping[str, Any]) -> tuple[list[Any], Any, Any, list[Mapping[str, Any]]]:
    traces = raw.get("traces", raw.get("steps", []))
    if not isinstance(traces, (list, tuple)):
        traces = []
    event = raw.get("event", {})
    final_status = event.get("status") if isinstance(event, Mapping) else None
    final_status = final_status or raw.get("event_status") or raw.get("final_status")
    if hasattr(final_status, "value"):
        final_status = final_status.value
    cleanup = raw.get("cleanup_snapshot", raw.get("cleanup", {}))
    model_decisions = [
        step.get("model_decision")
        for step in traces
        if isinstance(step, Mapping) and isinstance(step.get("model_decision"), Mapping)
    ]
    return list(traces), final_status, cleanup, model_decisions


def _provider_name(
    traces: Iterable[Any],
    model_decisions: Iterable[Mapping[str, Any]],
    *,
    error: Exception | None = None,
) -> str | None:
    for decision in model_decisions:
        if decision.get("provider"):
            return str(decision["provider"])
    for step in traces:
        if not isinstance(step, Mapping):
            continue
        if step.get("provider_name"):
            return str(step["provider_name"])
        attempts = step.get("provider_attempts", ())
        if isinstance(attempts, (list, tuple)):
            for attempt in attempts:
                if isinstance(attempt, Mapping) and attempt.get("provider"):
                    return str(attempt["provider"])
    if error is not None:
        if getattr(error, "provider_name", None):
            return str(error.provider_name)
        for attempt in getattr(error, "attempts", ()):
            name = getattr(attempt, "provider_name", None)
            if name:
                return str(name)
    return None


def _scenario_metadata(
    fixture: ScenarioFixture,
    *,
    repetition: int,
    run_seed: int | None,
    live_api: bool,
    provider: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_id": fixture.model.scenario_id,
        "title": fixture.model.title,
        "category": fixture.model.category,
        "repetition": repetition,
        "run_seed": run_seed,
        "mode": "LIVE_API" if live_api else "DETERMINISTIC",
        "provider_backend": provider or ("unknown" if live_api else "deterministic"),
        "model": model or "unknown",
    }


def result_payload(
    result: Any,
    fixture: ScenarioFixture,
    repetition: int,
    *,
    run_seed: int | None = None,
    live_api: bool = False,
) -> dict[str, Any]:
    raw = to_mapping(result)
    traces, final_status, cleanup, model_decisions = _result_details(raw)
    expected = fixture.oracle.expected_final
    provider = _provider_name(traces, model_decisions)
    prompt_hashes = {
        f"step_{index}": item.get("prompt_hash")
        for index, item in enumerate(model_decisions, start=1)
        if item.get("prompt_hash")
    }
    actuals = {
        "event_status": str(final_status),
        "event_count": raw.get("event_count"),
        "decision_count": raw.get("decision_count"),
        "delivery_count": raw.get("delivery_count"),
        "transport_message_count": raw.get("transport_message_count"),
        "pending_wakeup_count": cleanup.get("pending_wakeup_count") if isinstance(cleanup, Mapping) else None,
        "presence_subscription_count": cleanup.get("presence_subscription_count") if isinstance(cleanup, Mapping) else None,
        "active_lease_count": cleanup.get("active_lease_count") if isinstance(cleanup, Mapping) else None,
        "worker_task_count": cleanup.get("worker_task_count") if isinstance(cleanup, Mapping) else None,
    }
    expected_values = {
        name: getattr(expected, name)
        for name in actuals
    }
    gates = [
        {
            "name": name,
            "ok": actuals[name] == wanted,
            "summary": f"expected={wanted!r}, actual={actuals[name]!r}",
        }
        for name, wanted in expected_values.items()
    ]
    actions = raw.get("actions", [])
    first_action = actions[0] if isinstance(actions, (list, tuple)) and actions else None
    gates.append({
        "name": "first_model_or_primary_action",
        "ok": first_action == fixture.oracle.expected_action,
        "summary": f"expected={fixture.oracle.expected_action!r}, actual={first_action!r}",
    })
    status = "PASS" if all(gate["ok"] for gate in gates) else "FAIL"
    trace = {
        "result": status,
        "scenario": _scenario_metadata(
            fixture,
            repetition=repetition,
            run_seed=run_seed,
            live_api=live_api,
            provider=provider,
        ),
        "steps": traces,
        "final_status": final_status,
        "delivery_count": raw.get("delivery_count"),
        "cleanup_snapshot": cleanup,
        "provider": provider,
        "decision": model_decisions or None,
        "prompt_hashes": prompt_hashes,
        "planner_raw": [item.get("raw_output") for item in model_decisions]
        if model_decisions else None,
        "gates": gates,
    }
    return {
        "scenario_id": fixture.model.scenario_id,
        "status": status,
        "final_status": final_status,
        "delivery_count": raw.get("delivery_count"),
        "trace": trace,
    }


def error_payload(
    error: Exception,
    fixture: ScenarioFixture,
    repetition: int,
    *,
    run_seed: int | None,
    live_api: bool,
) -> dict[str, Any]:
    partial = getattr(error, "partial_result", None)
    raw: dict[str, Any] = {}
    if partial is not None:
        try:
            raw = to_mapping(partial)
        except (TypeError, ValueError):
            raw = {}
    traces, final_status, cleanup, model_decisions = _result_details(raw)
    provider = _provider_name(traces, model_decisions, error=error)
    model = getattr(error, "model_name", None)
    prompt_hashes = {
        f"step_{index}": item.get("prompt_hash")
        for index, item in enumerate(model_decisions, start=1)
        if item.get("prompt_hash")
    }
    message = f"{type(error).__name__}: {error}"
    trace = {
        "result": "ERROR",
        "scenario": _scenario_metadata(
            fixture,
            repetition=repetition,
            run_seed=run_seed,
            live_api=live_api,
            provider=provider,
            model=model,
        ),
        "steps": traces,
        "final_status": final_status,
        "delivery_count": raw.get("delivery_count"),
        "cleanup_snapshot": cleanup,
        "provider": provider,
        "decision": model_decisions or None,
        "prompt_hashes": prompt_hashes,
        "planner_raw": [item.get("raw_output") for item in model_decisions]
        if model_decisions else None,
        "errors": [message],
        "failure": {"primary_reason": "provider_error" if live_api else "runner_error"},
        "gates": [{"name": "scenario_execution", "ok": False, "summary": message}],
    }
    return {
        "scenario_id": fixture.model.scenario_id,
        "status": "ERROR",
        "final_status": final_status,
        "delivery_count": raw.get("delivery_count"),
        "trace": trace,
    }


async def async_main(args: argparse.Namespace) -> int:
    init_logs()
    if args.repeat < 1:
        print("--repeat 必須 >= 1", file=sys.stderr)
        return 2
    fixtures = select_fixtures(load_scenarios(args.fixture), args.scenario)
    if args.live_api:
        print("Replay mode: LIVE_API (real AI provider via AgentConfig / LLM_BACKEND)")
    else:
        print("Replay mode: DETERMINISTIC (fixture baseline policy; no AI API call)")
    payloads: list[dict[str, Any]] = []
    run_index = 0
    for fixture in fixtures:
        for repetition_index in range(args.repeat):
            run_index += 1
            repetition = repetition_index + 1
            run_seed = None if args.seed is None else args.seed + repetition_index
            try:
                results = await invoke_runner(
                    (fixture,), live_api=args.live_api, repeat=1, seed=run_seed
                )
                if len(results) != 1:
                    raise RuntimeError(f"runner 回傳 {len(results)} 筆結果，預期 1 筆")
                payload = result_payload(
                    results[0],
                    fixture,
                    repetition,
                    run_seed=run_seed,
                    live_api=args.live_api,
                )
            except Exception as exc:
                payload = error_payload(
                    exc,
                    fixture,
                    repetition,
                    run_seed=run_seed,
                    live_api=args.live_api,
                )
                log_error(
                    "replay_initiative_v02",
                    "async_main",
                    exc,
                    context={
                        "scenario_id": fixture.model.scenario_id,
                        "repetition": repetition,
                        "run_seed": run_seed,
                        "mode": "LIVE_API" if args.live_api else "DETERMINISTIC",
                    },
                )
            payloads.append(payload)
            log_initiative_trace(
                f"initiative-v02-{run_index}", fixture.model.scenario_id, payload["trace"]
            )
            log_initiative_summary(payloads)
            print(
                f"[{payload['status']}] {fixture.model.scenario_id} "
                f"final={payload['final_status']} delivery={payload['delivery_count']}"
            )

    if any(item["status"] == "ERROR" for item in payloads):
        return 2
    return 0 if all(item["status"] == "PASS" for item in payloads) else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(parse_args(argv)))
    except (ScenarioError, RuntimeError, TypeError) as exc:
        log_error("replay_initiative_v02", "main", exc)
        print(f"Replay ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
