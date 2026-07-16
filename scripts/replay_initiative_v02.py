"""Replay initiative v0.2 E2E scenarios without coupling the CLI to runner internals."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
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
LIVE_MODE = "LIVE_MODEL_E2E_VIRTUAL_IO"
SCENARIO_ALIASES = {
    # Kept for the command documented before the core fixture set was renamed.
    "l0_01": "core_01_commitment_followup",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay initiative v0.2 structured E2E scenarios.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--scenario", help="Replay one scenario id.")
    selection.add_argument("--all", action="store_true", help="Replay every fixture scenario.")
    parser.add_argument(
        "--live-model-e2e", "--live-api", dest="live_api", action="store_true",
        help="Run LIVE_MODEL_E2E_VIRTUAL_IO (the --live-api name is a compatibility alias).",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Run each scenario N times (default: 1).")
    parser.add_argument("--seed", type=int, default=None, help="Base run seed; repetitions increment it.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def select_fixtures(fixtures: Iterable[ScenarioFixture], scenario_id: str | None) -> tuple[ScenarioFixture, ...]:
    fixtures = tuple(fixtures)
    if scenario_id is None:
        return fixtures
    canonical_id = SCENARIO_ALIASES.get(scenario_id, scenario_id)
    selected = tuple(item for item in fixtures if item.model.scenario_id == canonical_id)
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
        for entry in getattr(error, "entries", ()):
            name = getattr(entry, "provider", None)
            if name:
                return str(name)
    return None


def _flow_gates(raw: Mapping[str, Any], fixture: ScenarioFixture) -> list[dict[str, Any]]:
    """Evaluate runtime contracts without treating model semantics as an oracle answer."""
    cleanup = raw.get("cleanup_snapshot", raw.get("cleanup", {}))
    if not isinstance(cleanup, Mapping):
        cleanup = {}
    ledger = raw.get("call_ledger", [])
    if not isinstance(ledger, (list, tuple)):
        ledger = []
    stages = [
        str(item.get("stage"))
        for item in ledger
        if isinstance(item, Mapping)
        and item.get("validation_status") == "accepted"
    ]
    transcript = raw.get("transcript", [])
    user_turns = sum(
        1 for item in transcript
        if isinstance(item, Mapping) and item.get("role") == "user"
    ) if isinstance(transcript, (list, tuple)) else 0
    actions = raw.get("actions", [])
    actions = list(actions) if isinstance(actions, (list, tuple)) else []
    deterministic_only = bool(actions) and all(
        action in {"EXPIRE", "CANCEL"} for action in actions
    )
    event_count = raw.get("event_count", 0)
    transport_count = raw.get("transport_message_count", 0)
    required_stage_checks = [
        ("dialogue_stage_coverage", stages.count("dialogue_response") == user_turns),
        ("candidate_scan_coverage", stages.count("candidate_scan") == user_turns),
        ("consolidation_stage_coverage", stages.count("candidate_consolidation") == 1),
        ("reappraisal_stage_coverage", event_count == 0 or stages.count("reappraisal") >= 1 or deterministic_only),
        ("generator_stage_coverage", ("SEND_NOW" not in actions and transport_count == 0) or stages.count("generator") >= 1),
    ]
    gates = [
        {
            "name": name,
            "ok": cleanup.get(name) == 0,
            "summary": f"expected=0, actual={cleanup.get(name)!r}",
        }
        for name in (
            "pending_wakeup_count", "presence_subscription_count",
            "active_lease_count", "worker_task_count",
        )
    ]
    gates.extend({"name": name, "ok": ok, "summary": f"stages={stages!r}"} for name, ok in required_stage_checks)
    gates.append({
        "name": "generator_delivery_source",
        "ok": transport_count == 0 or (raw.get("initiative_message") not in (None, "")),
        "summary": f"transport_count={transport_count!r}, generated_message={raw.get('initiative_message')!r}",
    })
    first_expected = fixture.oracle.expected_steps[0] if fixture.oracle.expected_steps else None
    if first_expected is not None and first_expected.decision_owner != "model":
        actual = actions[0] if actions else None
        gates.append({
            "name": "system_owned_action",
            "ok": actual == first_expected.expected_action,
            "summary": f"expected={first_expected.expected_action!r}, actual={actual!r}",
        })
    return gates


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
        "mode": LIVE_MODE if live_api else "DETERMINISTIC",
        "provider_backend": provider or ("unknown" if live_api else "deterministic"),
        "model": model or "unknown",
    }


def _plain(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_step_value(step: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = step.get(key)
        if value not in (None, ""):
            return value
    return None


def initiative_flow_payload(
    fixture: ScenarioFixture,
    raw: Mapping[str, Any],
    traces: Iterable[Any],
) -> dict[str, Any]:
    """Project runner internals into the human-facing initiative story."""
    steps = [step for step in traces if isinstance(step, Mapping)]
    first_step = steps[0] if steps else {}
    prelude = fixture.model.prelude[0] if fixture.model.prelude else None
    conversation = list(fixture.model.context.conversation)
    source_turn_id = None
    source_message = None
    if prelude is not None:
        source_refs = prelude.data.get("source_turn_ids")
        if isinstance(source_refs, (list, tuple)) and source_refs:
            source_turn_id = str(source_refs[0])
        source_message = _plain(prelude.data.get("input"))
    if source_turn_id is None and fixture.model.context.provenance:
        source_turn_id = fixture.model.context.provenance[0].ref
    if source_message is None and conversation:
        last_turn = conversation[-1]
        if isinstance(last_turn, Mapping):
            source_message = _plain(last_turn.get("content"))
            source_turn_id = source_turn_id or _plain(last_turn.get("turn_id"))

    scheduled_at = None
    expires_at = None
    if prelude is not None:
        scheduled_at = _plain(prelude.data.get("schedule_at"))
        expires_at = _plain(prelude.data.get("expires_at"))
    if scheduled_at is None:
        scheduled_at = _plain(_first_step_value(first_step, "logical_time"))
    if scheduled_at is None:
        try:
            scheduled_at = (datetime.fromisoformat(fixture.model.clock_start) + timedelta(minutes=5)).isoformat()
        except ValueError:
            scheduled_at = None

    trigger = _first_step_value(first_step, "trigger")
    trigger_text = trigger.get("type") if isinstance(trigger, Mapping) else trigger
    model_decision = first_step.get("model_decision") if isinstance(first_step.get("model_decision"), Mapping) else {}
    system_decision = first_step.get("system_decision") if isinstance(first_step.get("system_decision"), Mapping) else {}
    action = (
        model_decision.get("parsed_action")
        or system_decision.get("accepted_action")
        or first_step.get("action")
        or (raw.get("actions")[0] if isinstance(raw.get("actions"), (list, tuple)) and raw.get("actions") else None)
    )
    reason_codes = system_decision.get("reason_codes") or first_step.get("reason_codes") or []
    if isinstance(reason_codes, str):
        reason_codes = [reason_codes]
    status_before = _first_step_value(first_step, "status_before")
    status_after = _first_step_value(first_step, "status_after")
    final_status = raw.get("event_status") or status_after
    delivery_status = first_step.get("delivery_status")
    event = raw.get("event") if isinstance(raw.get("event"), Mapping) else {}
    proposal = raw.get("accepted_candidate")
    if not isinstance(proposal, Mapping):
        proposal = raw.get("event_proposal")
    if not isinstance(proposal, Mapping):
        proposal = {}
    event_summary = _plain(event.get("summary")) or _plain(proposal.get("summary"))
    proactive_message = (
        _plain(raw.get("initiative_message"))
        or _plain(raw.get("generator_message"))
        or _plain(raw.get("generated_message"))
    )

    runtime_summary = [
        f"來源 turn={source_turn_id or '-'}，預定喚醒={scheduled_at or '-'}",
        f"觸發={trigger_text or '-'}，狀態 {status_before or '-'} -> {status_after or final_status or '-'}",
        f"接受動作={action or '-'}，原因碼={', '.join(str(item) for item in reason_codes) or '-'}",
    ]
    if delivery_status or raw.get("delivery_count"):
        runtime_summary.append(
            f"Delivery={delivery_status or 'recorded'}，訊息來源={'generator' if proactive_message else 'missing'}"
        )

    return {
        "source_turn_id": source_turn_id,
        "source_message": source_message,
        "event_summary": event_summary,
        "scheduled_at": scheduled_at,
        "expires_at": expires_at,
        "trigger": trigger_text,
        "action": action,
        "reason_codes": list(reason_codes) if isinstance(reason_codes, (list, tuple)) else reason_codes,
        "status_before": status_before,
        "status_after": status_after,
        "final_status": final_status,
        "delivery_status": delivery_status,
        "proactive_message": proactive_message,
        "runtime_summary": runtime_summary,
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
    call_ledger = raw.get("call_ledger", [])
    provider = next(
        (
            str(item.get("provider")) for item in call_ledger
            if isinstance(item, Mapping) and item.get("provider")
        ),
        _provider_name(traces, model_decisions),
    ) if isinstance(call_ledger, (list, tuple)) else _provider_name(traces, model_decisions)
    prompt_hashes = {
        f"step_{index}": item.get("prompt_hash")
        for index, item in enumerate(model_decisions, start=1)
        if item.get("prompt_hash")
    }
    gates = _flow_gates(raw, fixture)
    status = "PASS" if all(gate["ok"] for gate in gates) else "FAIL"
    trace = {
        "flow_result": status,
        "human_review": "PENDING",
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
        "call_ledger": call_ledger,
        "prompt_hashes": prompt_hashes,
        "planner_raw": [item.get("raw_output") for item in model_decisions]
        if model_decisions else None,
        "initiative_flow": initiative_flow_payload(fixture, raw, traces),
        "gates": gates,
    }
    return {
        "scenario_id": fixture.model.scenario_id,
        "flow_result": status,
        "human_review": "PENDING",
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
    error_entries = []
    for entry in getattr(error, "entries", ()):
        if is_dataclass(entry):
            item = asdict(entry)
            if hasattr(entry.stage, "value"):
                item["stage"] = entry.stage.value
            if hasattr(entry.validation_status, "value"):
                item["validation_status"] = entry.validation_status.value
            error_entries.append(item)
    provider = _provider_name(traces, model_decisions, error=error)
    model = getattr(error, "model_name", None)
    prompt_hashes = {
        f"step_{index}": item.get("prompt_hash")
        for index, item in enumerate(model_decisions, start=1)
        if item.get("prompt_hash")
    }
    message = f"{type(error).__name__}: {error}"
    trace = {
        "flow_result": "ERROR",
        "human_review": "PENDING",
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
        "call_ledger": raw.get("call_ledger", error_entries),
        "prompt_hashes": prompt_hashes,
        "planner_raw": [item.get("raw_output") for item in model_decisions]
        if model_decisions else None,
        "initiative_flow": initiative_flow_payload(fixture, raw, traces),
        "errors": [message],
        "failure": {"primary_reason": "provider_error" if live_api else "runner_error"},
        "gates": [{"name": "scenario_execution", "ok": False, "summary": message}],
    }
    return {
        "scenario_id": fixture.model.scenario_id,
        "flow_result": "ERROR",
        "human_review": "PENDING",
        "status": "ERROR",
        "final_status": final_status,
        "delivery_count": raw.get("delivery_count"),
        "error_summary": _terminal_error_summary(error, provider),
        "trace": trace,
    }


def _terminal_error_summary(error: Exception, provider: str | None) -> str:
    """Keep the actionable provider failure visible without dumping its full payload."""
    detail = " ".join(str(error).split())
    if len(detail) > 240:
        detail = detail[:237].rstrip() + "..."
    prefix = f"{type(error).__name__}"
    if provider:
        prefix += f" via {provider}"
    return f"{prefix}: {detail}"


def print_flow_summary(payload: Mapping[str, Any]) -> None:
    trace = payload.get("trace") if isinstance(payload.get("trace"), Mapping) else {}
    flow = trace.get("initiative_flow") if isinstance(trace.get("initiative_flow"), Mapping) else {}
    if not flow:
        return
    print(
        f"  觸發：{flow.get('scheduled_at') or '-'} / {flow.get('trigger') or '-'} "
        f"-> {flow.get('action') or '-'}"
    )
    if flow.get("source_message"):
        print(f"  來源訊息：{flow['source_message']}")
    if flow.get("proactive_message") and payload.get("delivery_count"):
        print(f"  AI 主動訊息：{flow['proactive_message']}")
    runtime_summary = flow.get("runtime_summary")
    if isinstance(runtime_summary, (list, tuple)) and runtime_summary:
        print(f"  Runtime：{runtime_summary[-1]}")


async def async_main(args: argparse.Namespace) -> int:
    init_logs()
    if args.repeat < 1:
        print("--repeat 必須 >= 1", file=sys.stderr)
        return 2
    fixtures = select_fixtures(load_scenarios(args.fixture), args.scenario)
    if args.live_api:
        print(
            f"Replay mode: {LIVE_MODE} "
            "(live model; virtual clock/session/presence and mock transport)"
        )
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
                        "mode": LIVE_MODE if args.live_api else "DETERMINISTIC",
                    },
                )
            payloads.append(payload)
            log_initiative_trace(
                f"initiative-v02-{run_index}", fixture.model.scenario_id, payload["trace"]
            )
            log_initiative_summary(payloads)
            print(
                f"[{payload['flow_result']}/{payload['human_review']}] {fixture.model.scenario_id} "
                f"final={payload['final_status']} delivery={payload['delivery_count']}"
            )
            print_flow_summary(payload)
            if payload["flow_result"] == "ERROR":
                print(f"  reason={payload['error_summary']}", file=sys.stderr)

    if any(item["flow_result"] == "ERROR" for item in payloads):
        return 2
    return 0 if all(item["flow_result"] == "PASS" for item in payloads) else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(parse_args(argv)))
    except (ScenarioError, RuntimeError, TypeError) as exc:
        log_error("replay_initiative_v02", "main", exc)
        print(f"Replay ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
