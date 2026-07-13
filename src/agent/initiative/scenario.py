"""v0.2 scenario boundary: validated fixtures and oracle-safe model inputs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class ScenarioError(ValueError):
    pass


_CATEGORIES = {"L0", "L1", "L2", "cross_session_presence", "delivery_recovery"}
_ACTIONS = {"SEND_NOW", "CANCEL", "EXPIRE", "SILENCE", "DELAY", "WAIT_FOR_USER_ACTIVITY"}
_STATUSES = {"DRAFT", "ACTIVE", "DUE", "DELAYED", "WAITING_FOR_PRESENCE", "DELIVERY_PENDING", "DELIVERED", "COMPLETED", "CANCELLED", "EXPIRED", "SILENCED"}
_OWNERS = {"model", "system", "user"}
_PRELUDE_TYPES = {"dialogue_turn", "internal_opportunity", "request_reminder", "seed_via_factory", "activate_event", "deliver_once"}
_TIMELINE_TYPES = {"advance_clock", "user_message", "presence_signal", "acknowledge_event", "cancel_event", "resolve_topic", "checkpoint_session", "open_session", "set_do_not_disturb", "set_world_state", "set_external_observation", "inject_fault", "duplicate_wakeup", "start_competing_worker", "shutdown_world"}
_TRIGGERS = {"DUE_EVALUATION", "EXPIRY", "PRESENCE", "USER_MESSAGE", "USER_CANCEL", "ACK_DEADLINE", "RECOVERY", "DUPLICATE_WAKEUP", "STALE_COMMIT", "INTERNAL_OPPORTUNITY"}
_TERMINAL_STATUSES = {"COMPLETED", "CANCELLED", "EXPIRED", "SILENCED"}


def _nonempty(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ScenarioError(f"{label} must be non-empty")
    return text


def _timestamp(value: Any, label: str) -> str:
    text = _nonempty(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ScenarioError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScenarioError(f"{label} must include a timezone")
    return text


@dataclass(frozen=True)
class ProvenanceRef:
    ref: str
    source_type: str
    observed_at: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.ref, "provenance.ref")
        _nonempty(self.source_type, "provenance.source_type")
        if self.observed_at is not None:
            _timestamp(self.observed_at, "provenance.observed_at")


@dataclass(frozen=True)
class ContextBundle:
    identity: Mapping[str, str]
    conversation: tuple[Mapping[str, Any], ...] = ()
    session_checkpoint: Mapping[str, Any] = field(default_factory=dict)
    memories: tuple[Mapping[str, Any], ...] = ()
    presence: Mapping[str, Any] = field(default_factory=dict)
    world: Mapping[str, Any] = field(default_factory=dict)
    external_data: tuple[Mapping[str, Any], ...] = ()
    provenance: tuple[ProvenanceRef, ...] = ()

    def __post_init__(self) -> None:
        required = {"run_id", "world_id", "user_id", "character_id", "session_id"}
        if missing := required - set(self.identity):
            raise ScenarioError(f"context identity missing: {sorted(missing)}")
        if any(not str(self.identity[key]).strip() for key in required):
            raise ScenarioError("context identity values must be non-empty")
        refs = [item.ref for item in self.provenance]
        if len(refs) != len(set(refs)):
            raise ScenarioError("provenance refs must be unique")

    def to_model_payload(self) -> dict[str, Any]:
        return {"identity": deepcopy(dict(self.identity)), "conversation": deepcopy(list(self.conversation)), "session_checkpoint": deepcopy(dict(self.session_checkpoint)), "memories": deepcopy(list(self.memories)), "presence": deepcopy(dict(self.presence)), "world": deepcopy(dict(self.world)), "external_data": deepcopy(list(self.external_data)), "provenance": [asdict(item) for item in self.provenance]}


@dataclass(frozen=True)
class PreludeStep:
    step_id: str
    type: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TimelineStep:
    step_id: str
    type: str
    at: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedStep:
    step_id: str
    trigger: str
    decision_owner: str
    expected_action: str
    expected_status_before: str
    expected_status_after: str
    allowed_reason_codes: tuple[str, ...] = ()
    expected_delivery_delta: int = 0
    required_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedFinal:
    event_status: str
    event_count: int
    decision_count: int
    delivery_count: int
    transport_message_count: int
    pending_wakeup_count: int
    presence_subscription_count: int
    active_lease_count: int
    worker_task_count: int


@dataclass(frozen=True)
class LogAssertion:
    field: str
    operator: str = "present"
    value: Any = None


@dataclass(frozen=True)
class ModelInputView:
    scenario_id: str
    category: str
    title: str
    purpose: str
    clock_start: str
    context: ContextBundle
    prelude: tuple[PreludeStep, ...]
    timeline: tuple[TimelineStep, ...]

    def to_payload(self) -> dict[str, Any]:
        payload = {"schema_version": 2, "scenario_id": self.scenario_id, "category": self.category, "title": self.title, "purpose": self.purpose, "clock_start": self.clock_start, "context": self.context.to_model_payload(), "prelude": [_step_payload(item) for item in self.prelude], "timeline": [_step_payload(item) for item in self.timeline]}
        encoded = json.dumps(payload, ensure_ascii=False).casefold()
        if any(token in encoded for token in ('"expected_', '"oracle"', '"hard_constraints"', '"soft_preferences"', '"log_assertions"')):
            raise ScenarioError("oracle data leaked into model input")
        return payload


@dataclass(frozen=True)
class OracleView:
    scenario_id: str
    expected_event_count: int
    expected_action: str
    expected_steps: tuple[ExpectedStep, ...]
    expected_final: ExpectedFinal
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]
    log_assertions: tuple[LogAssertion, ...]


@dataclass(frozen=True)
class ScenarioFixture:
    model: ModelInputView
    oracle: OracleView


def _step_payload(step: PreludeStep | TimelineStep) -> dict[str, Any]:
    payload = {"step_id": step.step_id, "type": step.type, **deepcopy(dict(step.data))}
    if isinstance(step, TimelineStep) and step.at is not None:
        payload["at"] = step.at
    return payload


def _context(raw: Mapping[str, Any]) -> ContextBundle:
    try:
        provenance = tuple(ProvenanceRef(**item) for item in raw.get("provenance", []))
        return ContextBundle(identity=MappingProxyType(deepcopy(dict(raw["identity"]))), conversation=tuple(deepcopy(raw.get("conversation", []))), session_checkpoint=MappingProxyType(deepcopy(dict(raw.get("session_checkpoint", {})))), memories=tuple(deepcopy(raw.get("memories", []))), presence=MappingProxyType(deepcopy(dict(raw.get("presence", {})))), world=MappingProxyType(deepcopy(dict(raw.get("world", {})))), external_data=tuple(deepcopy(raw.get("external_data", []))), provenance=provenance)
    except (KeyError, TypeError) as exc:
        raise ScenarioError(f"invalid context: {exc}") from exc


def _steps(raw_steps: Any, *, prelude: bool) -> tuple[PreludeStep | TimelineStep, ...]:
    if not isinstance(raw_steps, list):
        raise ScenarioError("prelude and timeline must be lists")
    result: list[PreludeStep | TimelineStep] = []
    allowed = _PRELUDE_TYPES if prelude else _TIMELINE_TYPES
    previous_at: datetime | None = None
    for raw in raw_steps:
        if not isinstance(raw, Mapping):
            raise ScenarioError("scenario steps must be objects")
        step_id = _nonempty(raw.get("step_id", ""), "step_id")
        step_type = str(raw.get("type", ""))
        if step_type not in allowed:
            raise ScenarioError(f"unsupported {'prelude' if prelude else 'timeline'} step type: {step_type}")
        at = raw.get("at")
        if at is not None:
            at = _timestamp(at, f"step {step_id}.at")
            parsed_at = datetime.fromisoformat(at)
            if previous_at is not None and parsed_at < previous_at:
                raise ScenarioError("timeline timestamps must be ordered")
            previous_at = parsed_at
        data = MappingProxyType(deepcopy({key: value for key, value in raw.items() if key not in {"step_id", "type", "at"}}))
        result.append(PreludeStep(step_id, step_type, data) if prelude else TimelineStep(step_id, step_type, at, data))
    return tuple(result)


def _expected_step(raw: Mapping[str, Any]) -> ExpectedStep:
    action, before, after = str(raw.get("expected_action", "")), str(raw.get("expected_status_before", "")), str(raw.get("expected_status_after", ""))
    trigger, owner = str(raw.get("trigger", "")), str(raw.get("decision_owner", ""))
    if action not in _ACTIONS or before not in _STATUSES or after not in _STATUSES or trigger not in _TRIGGERS or owner not in _OWNERS:
        raise ScenarioError("expected step contains unsupported action, status, trigger, or decision owner")
    delta = raw.get("expected_delivery_delta", 0)
    if not isinstance(delta, int) or delta < 0:
        raise ScenarioError("expected_delivery_delta must be a non-negative integer")
    return ExpectedStep(_nonempty(raw.get("step_id", ""), "oracle step_id"), trigger, owner, action, before, after, tuple(raw.get("allowed_reason_codes", [])), delta, tuple(raw.get("required_evidence_refs", [])))


def _expected_final(raw: Mapping[str, Any]) -> ExpectedFinal:
    required = ("event_status", "event_count", "decision_count", "delivery_count", "transport_message_count", "pending_wakeup_count", "presence_subscription_count", "active_lease_count", "worker_task_count")
    if missing := set(required) - set(raw):
        raise ScenarioError(f"expected_final missing: {sorted(missing)}")
    status = str(raw["event_status"])
    if status not in _TERMINAL_STATUSES:
        raise ScenarioError("expected_final.event_status must be terminal")
    values = [raw[key] for key in required[1:]]
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ScenarioError("expected_final counts must be non-negative integers")
    return ExpectedFinal(status, *values)


def fixture_from_mapping(raw: Mapping[str, Any]) -> ScenarioFixture:
    try:
        if raw.get("schema_version") != 2:
            raise ScenarioError("schema_version must be 2")
        scenario_id, category = _nonempty(raw["scenario_id"], "scenario_id"), str(raw["category"])
        if category not in _CATEGORIES:
            raise ScenarioError(f"unsupported scenario category: {category}")
        prelude = _steps(raw["prelude"], prelude=True)
        timeline = _steps(raw["timeline"], prelude=False)
        step_ids = [item.step_id for item in (*prelude, *timeline)]
        if len(step_ids) != len(set(step_ids)):
            raise ScenarioError("step ids must be unique within a scenario")
        oracle_raw = raw["oracle"]
        expected_steps = tuple(_expected_step(item) for item in oracle_raw["expected_steps"])
        if not expected_steps:
            raise ScenarioError("oracle.expected_steps must not be empty")
        final = _expected_final(oracle_raw["expected_final"])
        expected_event_count = oracle_raw["expected_event_count"]
        if not isinstance(expected_event_count, int) or expected_event_count < 0 or final.event_count != expected_event_count:
            raise ScenarioError("expected_event_count must match expected_final.event_count")
        expected_action = str(oracle_raw.get("expected_action", expected_steps[0].expected_action))
        if expected_action != expected_steps[0].expected_action:
            raise ScenarioError("expected_action must match the first expected step")
        model = ModelInputView(scenario_id, category, _nonempty(raw["title"], "title"), _nonempty(raw["purpose"], "purpose"), _timestamp(raw["clock_start"], "clock_start"), _context(raw["context"]), prelude, timeline)
        oracle = OracleView(scenario_id, expected_event_count, expected_action, expected_steps, final, tuple(oracle_raw.get("hard_constraints", [])), tuple(oracle_raw.get("soft_preferences", [])), tuple(LogAssertion(**item) for item in oracle_raw.get("log_assertions", [])))
    except ScenarioError:
        raise
    except (KeyError, TypeError) as exc:
        raise ScenarioError(f"invalid scenario fixture: {exc}") from exc
    model.to_payload()
    return ScenarioFixture(model, oracle)


def load_scenarios(path: str | Path) -> tuple[ScenarioFixture, ...]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioError(f"cannot load scenarios: {exc}") from exc
    if not isinstance(raw, list):
        raise ScenarioError("scenario collection must be a JSON list")
    fixtures = tuple(fixture_from_mapping(item) for item in raw)
    ids = [item.model.scenario_id for item in fixtures]
    if len(ids) != len(set(ids)):
        raise ScenarioError("scenario ids must be unique")
    return fixtures


@dataclass(frozen=True)
class ScenarioObservation:
    scenario_id: str
    action: str
    deliveries: int = 0
    hard_violations: tuple[str, ...] = ()
    soft_scores: Mapping[str, float] = field(default_factory=dict)
    plumbing_ok: bool = True


def action_confusion(fixtures: Iterable[ScenarioFixture], observations: Iterable[ScenarioObservation]) -> dict[str, dict[str, int]]:
    expected = {item.oracle.scenario_id: item.oracle.expected_action for item in fixtures}
    matrix: dict[str, dict[str, int]] = {}
    for item in observations:
        wanted = expected[item.scenario_id]
        matrix.setdefault(wanted, {})[item.action] = matrix.setdefault(wanted, {}).get(item.action, 0) + 1
    return matrix


def build_report(fixtures: Iterable[ScenarioFixture], observations: Iterable[ScenarioObservation]) -> dict[str, Any]:
    fixtures, observations = tuple(fixtures), tuple(observations)
    expected = {item.oracle.scenario_id: item.oracle.expected_action for item in fixtures}
    return {"plumbing_result": {"total": len(observations), "passed": sum(item.plumbing_ok and not item.hard_violations for item in observations), "hard_violations": sum(len(item.hard_violations) for item in observations), "duplicate_deliveries": sum(max(0, item.deliveries - 1) for item in observations)}, "model_decision_result": {"total": len(observations), "correct": sum(expected.get(item.scenario_id) == item.action for item in observations), "action_confusion": action_confusion(fixtures, observations)}, "soft_quality_result": {"judged": sum(bool(item.soft_scores) for item in observations), "averages": _averages(observations)}}


def _averages(observations: Iterable[ScenarioObservation]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for item in observations:
        for key, value in item.soft_scores.items():
            buckets.setdefault(key, []).append(float(value))
    return {key: sum(values) / len(values) for key, values in buckets.items()}


__all__ = ["ContextBundle", "ExpectedFinal", "ExpectedStep", "LogAssertion", "ModelInputView", "OracleView", "PreludeStep", "ProvenanceRef", "ScenarioError", "ScenarioFixture", "ScenarioObservation", "TimelineStep", "action_confusion", "build_report", "fixture_from_mapping", "load_scenarios"]
