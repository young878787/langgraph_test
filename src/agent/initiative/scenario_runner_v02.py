"""Deterministic v0.2 scenario orchestration over the initiative ports.

This runner intentionally owns no transition or delivery rules.  It wires the
domain, store, virtual clock, presence and exactly-once delivery components into
one bounded test world.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, TYPE_CHECKING

from .adapters import GraphDialogueAdapter, MockPresenceAdapter, PresenceSubscription
from .clock import FakeClock
from .delivery import (
    DeliveryAttempt as RuntimeDeliveryAttempt,
    DeliveryStatus,
    DeliveryStore,
    ExactlyOnceDelivery,
    MockMessageAdapter,
    content_hash,
)
from .domain import (
    DecisionRecord,
    EventSchedule,
    EventStatus,
    InitiativeAction,
    InitiativeEvent,
    IsolationIdentity,
    apply_action,
    complete_delivery,
)
from .runtime import LeaseRegistry, WakeItem, WakeKind, WakeUpQueue
from .store import InMemoryInitiativeStore, event_first_commitment
from .decision_contracts import (
    DecisionContractError,
    parse_candidate_consolidation,
    parse_candidate_scan,
    parse_wake_up_reappraisal,
)
from .event_gate import EventGateContext, gate_candidate_events, persist_accepted_events
from .generator import build_generator_prompt, validate_generated_text
from .provider_calls import ProviderCallLedger, ProviderStage
from .scenario import RuntimeModelView

if TYPE_CHECKING:
    from .scenario import ScenarioFixture


@dataclass(frozen=True)
class ProviderAttemptTrace:
    attempt: int
    provider_name: str
    prompt_hash: str
    raw_output: str | None = None
    validation_error: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    action: InitiativeAction
    reason_code: str
    delay_until: datetime | None = None
    prompt_hash: str | None = None
    raw_output: str | None = None
    provider_name: str | None = None
    provider_attempts: tuple[ProviderAttemptTrace, ...] = ()


class LivePolicyError(RuntimeError):
    """A live provider call or its structured decision contract failed."""

    def __init__(
        self,
        message: str,
        *,
        attempts: Iterable[ProviderAttemptTrace] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = tuple(attempts)
        self.partial_result: ScenarioRunResult | None = None


class LiveAIPolicy:
    """Model-owned decision policy with an oracle-free prompt boundary."""

    SYSTEM_PROMPT = """You are the decision policy for a proactive message event.
Choose exactly one action from SEND_NOW, DELAY, WAIT_FOR_USER_ACTIVITY, CANCEL,
EXPIRE, SILENCE. Return one JSON object with keys action, reason_code, and
optionally delay_until (an ISO-8601 timestamp) when action is DELAY. Base the
decision only on the supplied scenario input and current runtime state."""

    def __init__(
        self,
        model_payload: dict[str, Any],
        provider: object,
        *,
        temperature: float = 0.1,
        max_output_tokens: int = 180,
    ) -> None:
        # ModelInputView.to_payload() already enforces the physical fixture
        # boundary.  Keep a serialized copy so later fixture mutations cannot
        # alter what is sent to the provider.
        self._model_payload = json.loads(json.dumps(model_payload, ensure_ascii=False))
        self._provider = provider
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    def __call__(self, event: InitiativeEvent, wake: WakeItem) -> PolicyDecision:
        runtime = {
            "logical_time": wake.scheduled_at.isoformat(),
            "trigger": wake.kind.name,
            "event": {
                "event_id": event.event_id,
                "version": event.version,
                "status": event.status.value,
                "initiative_level": event.initiative_level,
                "summary": event.summary,
                "earliest_at": event.schedule.earliest_at.isoformat(),
                "expires_at": event.schedule.expires_at.isoformat(),
                "next_evaluation_at": (
                    event.schedule.next_evaluation_at.isoformat()
                    if event.schedule.next_evaluation_at else None
                ),
                "requires_acknowledgement": event.requires_acknowledgement,
            },
        }
        user_prompt = json.dumps(
            {"scenario_input": self._model_payload, "runtime": runtime},
            ensure_ascii=False,
            sort_keys=True,
        )
        generate_json = getattr(self._provider, "generate_json", None)
        provider_name = type(self._provider).__name__
        if not callable(generate_json):
            prompt_hash = "sha256:" + hashlib.sha256(
                f"{self.SYSTEM_PROMPT}\n{user_prompt}".encode("utf-8")
            ).hexdigest()
            raise LivePolicyError(
                "live provider does not implement generate_json",
                attempts=(ProviderAttemptTrace(
                    attempt=1,
                    provider_name=provider_name,
                    prompt_hash=prompt_hash,
                    validation_error="provider_error: generate_json is not callable",
                ),),
            )
        raw: object = ""
        active_prompt = user_prompt
        decision: PolicyDecision | None = None
        attempts: list[ProviderAttemptTrace] = []
        for attempt in range(2):
            prompt_hash = "sha256:" + hashlib.sha256(
                f"{self.SYSTEM_PROMPT}\n{active_prompt}".encode("utf-8")
            ).hexdigest()
            try:
                raw = generate_json(
                    self.SYSTEM_PROMPT,
                    active_prompt,
                    self._temperature,
                    self._max_output_tokens,
                )
            except Exception as exc:
                attempts.append(ProviderAttemptTrace(
                    attempt=attempt + 1,
                    provider_name=provider_name,
                    prompt_hash=prompt_hash,
                    validation_error=f"provider_error: {exc}",
                ))
                raise LivePolicyError(
                    f"live provider call failed: {exc}", attempts=attempts
                ) from exc
            try:
                decision = self._parse_decision(raw, event, wake)
                attempts.append(ProviderAttemptTrace(
                    attempt=attempt + 1,
                    provider_name=provider_name,
                    prompt_hash=prompt_hash,
                    raw_output=str(raw),
                ))
                break
            except LivePolicyError as exc:
                attempts.append(ProviderAttemptTrace(
                    attempt=attempt + 1,
                    provider_name=provider_name,
                    prompt_hash=prompt_hash,
                    raw_output=str(raw),
                    validation_error=str(exc),
                ))
                if attempt:
                    preview = str(raw).replace("\n", " ")[:500]
                    raise LivePolicyError(
                        f"{exc}; raw={preview}", attempts=attempts
                    ) from exc
                active_prompt = json.dumps(
                    {
                        "original_request": json.loads(user_prompt),
                        "previous_output": str(raw),
                        "validation_error": str(exc),
                        "instruction": "Return corrected JSON using exactly one allowed action.",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
        if decision is None:
            raise LivePolicyError(
                "live provider did not produce a decision", attempts=attempts
            )
        final_attempt = attempts[-1]
        return replace(
            decision,
            prompt_hash=final_attempt.prompt_hash,
            raw_output=str(raw),
            provider_name=provider_name,
            provider_attempts=tuple(attempts),
        )

    @staticmethod
    def _parse_decision(raw: object, event: InitiativeEvent, wake: WakeItem) -> PolicyDecision:
        if not isinstance(raw, str) or not raw.strip():
            raise LivePolicyError("live provider returned an empty decision")
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].strip().casefold() in {"```", "```json"}:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LivePolicyError("live provider returned invalid decision JSON") from exc
        if not isinstance(data, dict):
            raise LivePolicyError("live provider decision must be a JSON object")
        try:
            action = InitiativeAction(str(data["action"]).strip().upper())
        except (KeyError, ValueError) as exc:
            value = data.get("action", "<missing>")
            raise LivePolicyError(
                f"live provider returned an unsupported action: {value!r}"
            ) from exc
        reason_code = data.get("reason_code")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise LivePolicyError("live provider decision requires reason_code")
        delay_until = None
        if action is InitiativeAction.DELAY:
            value = data.get("delay_until")
            if not isinstance(value, str):
                raise LivePolicyError("DELAY decision requires delay_until")
            try:
                delay_until = datetime.fromisoformat(value)
            except ValueError as exc:
                raise LivePolicyError("delay_until must be an ISO-8601 timestamp") from exc
            if delay_until.tzinfo is None or delay_until.utcoffset() is None:
                raise LivePolicyError("delay_until must include a timezone")
            if not (wake.scheduled_at < delay_until <= event.schedule.expires_at):
                raise LivePolicyError("delay_until must be after now and within the event window")
        return PolicyDecision(action, reason_code.strip(), delay_until)


def _json_default(value: object) -> object:
    if hasattr(value, "value"):
        return getattr(value, "value")
    raise TypeError(f"cannot encode {type(value).__name__}")


def _decision_prompts(stage: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    contracts = {
        "candidate_scan": (
            "Return one JSON object only, with exactly these top-level fields: "
            "schema_version='initiative.world_event_proposal.v1', "
            "decision_type='candidate_scan', events, no_event_reason. events has 0..3 objects; "
            "each object has exactly candidate_id, event_type, summary, evidence_refs, "
            "followup_value, interruption_risk, trigger, confidence, short_rationale. "
            "event_type is reminder|care_followup|commitment|topic_continuation; "
            "interruption_risk is low|medium|high; confidence is 0..1. trigger has exactly "
            "kind, earliest_offset_minutes, preferred_offset_minutes, expires_offset_minutes; "
            "kind is time|presence|user_activity|world_signal and offsets are non-negative "
            "integers with earliest <= preferred < expires. Use only supplied evidence refs. "
            "When events is empty, no_event_reason must be a non-empty string; otherwise null."
        ),
        "candidate_consolidation": (
            "Return one JSON object only, with exactly: "
            "schema_version='initiative.world_event_consolidation.v1', "
            "decision_type='candidate_consolidation', accepted_candidate_ids, "
            "merged_candidates, rejected_candidates, short_rationale. IDs must come from the "
            "supplied candidates and be mutually exclusive. Each merged item has exactly "
            "target_candidate_id and source_candidate_ids. Each rejected item has exactly "
            "candidate_id and reason_code. Empty arrays are valid."
        ),
        "reappraisal": (
            "Return one JSON object only, with exactly: "
            "schema_version='initiative.reappraisal.v1', "
            "decision_type='wake_up_reappraisal', event_id, event_version, action, reason_code, "
            "evidence_refs, next_evaluation_offset_minutes, short_rationale. action is "
            "SEND_NOW|DELAY|WAIT_FOR_USER_ACTIVITY|CANCEL|EXPIRE|SILENCE. Copy the supplied "
            "event id/version exactly and use only supplied evidence refs. DELAY requires a "
            "positive integer offset; every other action requires null."
        ),
    }
    return contracts[stage], json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)


class LedgerReappraisalPolicy:
    """Live reappraisal policy whose every attempt is recorded by the shared ledger."""

    def __init__(
        self,
        *,
        provider: object,
        ledger: ProviderCallLedger,
        runtime_payload: Callable[[InitiativeEvent, WakeItem], Mapping[str, Any]],
        available_evidence_refs: Callable[[], tuple[str, ...]],
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self.provider = provider
        self.ledger = ledger
        self.runtime_payload = runtime_payload
        self.available_evidence_refs = available_evidence_refs
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    def __call__(self, event: InitiativeEvent, wake: WakeItem) -> PolicyDecision:
        system_prompt, user_prompt = _decision_prompts(
            "reappraisal", self.runtime_payload(event, wake)
        )
        result = self.ledger.call_json(
            ProviderStage.REAPPRAISAL,
            self.provider,
            system_prompt,
            user_prompt,
            self.temperature,
            self.max_output_tokens,
            lambda raw: parse_wake_up_reappraisal(
                raw,
                expected_event_id=event.event_id,
                expected_event_version=event.version,
                available_evidence_refs=self.available_evidence_refs(),
                logical_now=wake.scheduled_at,
                expires_at=event.schedule.expires_at,
            ),
        )
        parsed = result.value
        attempts = tuple(
            ProviderAttemptTrace(
                attempt=item.attempt,
                provider_name=item.provider,
                prompt_hash=item.prompt_hash or "",
                raw_output=item.raw_response,
                validation_error=("; ".join(item.validation_errors) or None),
            )
            for item in result.entries
        )
        return PolicyDecision(
            parsed.action,
            parsed.reason_code,
            parsed.next_evaluation_at,
            result.entry.prompt_hash,
            result.raw_response,
            result.entry.provider,
            attempts,
        )


class SequencePolicy:
    """Small deterministic policy used by plumbing baselines."""

    def __init__(self, decisions: Iterable[PolicyDecision]) -> None:
        self._decisions = iter(decisions)

    def __call__(self, event: InitiativeEvent, wake: WakeItem) -> PolicyDecision:
        del event, wake
        try:
            return next(self._decisions)
        except StopIteration as exc:
            raise RuntimeError("deterministic policy has no decision for wake-up") from exc


@dataclass(frozen=True)
class StepTrace:
    step_id: str
    logical_time: datetime
    trigger: str
    event_version_before: int
    status_before: EventStatus
    action: InitiativeAction | None
    event_version_after: int
    status_after: EventStatus
    reason_codes: tuple[str, ...] = ()
    delivery_status: str | None = None
    transport_message_id: str | None = None
    model_prompt_hash: str | None = None
    model_raw_output: str | None = None
    provider_name: str | None = None
    provider_attempts: tuple[ProviderAttemptTrace, ...] = ()
    error_message: str | None = None
    decision_id: str | None = None
    decision_plan_id: str | None = None
    decision_decided_at: datetime | None = None
    delivery_event_version: int | None = None
    delivery_idempotency_key: str | None = None
    delivery_content_hash: str | None = None


@dataclass(frozen=True)
class CleanupSnapshot:
    pending_wakeup_count: int
    presence_subscription_count: int
    active_lease_count: int
    worker_task_count: int


@dataclass(frozen=True)
class ScenarioRunResult:
    event: InitiativeEvent
    traces: tuple[StepTrace, ...]
    decision_count: int
    delivery_count: int
    transport_message_count: int
    cleanup: CleanupSnapshot

    def to_mapping(self) -> dict[str, Any]:
        return {
            "scenario_id": self.event.run_id.removeprefix("run-"),
            "event_status": self.event.status.value,
            "event_count": 1,
            "decision_count": self.decision_count,
            "delivery_count": self.delivery_count,
            "transport_message_count": self.transport_message_count,
            "actions": [trace.action.value for trace in self.traces if trace.action],
            "traces": [
                {
                    "step_id": trace.step_id,
                    "logical_time": trace.logical_time.isoformat(),
                    "trigger": trace.trigger,
                    "event_version_before": trace.event_version_before,
                    "status_before": trace.status_before.value,
                    "action": trace.action.value if trace.action else None,
                    "event_version_after": trace.event_version_after,
                    "status_after": trace.status_after.value,
                    "reason_codes": list(trace.reason_codes),
                    "delivery_status": trace.delivery_status,
                    "transport_message_id": trace.transport_message_id,
                    "model_prompt_hash": trace.model_prompt_hash,
                    "model_raw_output": trace.model_raw_output,
                    "provider_name": trace.provider_name,
                    "provider_attempts": [
                        {
                            "attempt": item.attempt,
                            "provider": item.provider_name,
                            "prompt_hash": item.prompt_hash,
                            "raw_output": item.raw_output,
                            "validation_error": item.validation_error,
                        }
                        for item in trace.provider_attempts
                    ],
                    "error_message": trace.error_message,
                    "model_decision": (
                        {
                            "provider": trace.provider_name,
                            "prompt_hash": trace.model_prompt_hash,
                            "raw_output": trace.model_raw_output,
                            "parsed_action": trace.action.value if trace.action else None,
                            "validation_errors": [
                                item.validation_error for item in trace.provider_attempts
                                if item.validation_error is not None
                            ],
                            "attempts": [
                                {
                                    "attempt": item.attempt,
                                    "provider": item.provider_name,
                                    "prompt_hash": item.prompt_hash,
                                    "raw_output": item.raw_output,
                                    "validation_error": item.validation_error,
                                }
                                for item in trace.provider_attempts
                            ],
                        }
                        if trace.provider_attempts else None
                    ),
                    "decision_record": (
                        {
                            "decision_id": trace.decision_id,
                            "plan_id": trace.decision_plan_id,
                            "event_version_before": trace.event_version_before,
                            "event_version_after": trace.event_version_after,
                            "decided_at": (
                                trace.decision_decided_at.isoformat()
                                if trace.decision_decided_at else None
                            ),
                        }
                        if trace.decision_id is not None else None
                    ),
                    "delivery_audit": (
                        {
                            "event_version": trace.delivery_event_version,
                            "idempotency_key": trace.delivery_idempotency_key,
                            "content_hash": trace.delivery_content_hash,
                            "status": trace.delivery_status,
                            "transport_message_id": trace.transport_message_id,
                        }
                        if trace.delivery_idempotency_key is not None else None
                    ),
                    "system_decision": {
                        "accepted_action": trace.action.value if trace.action else None,
                        "reason_codes": list(trace.reason_codes),
                    },
                }
                for trace in self.traces
            ],
            "cleanup_snapshot": {
                "pending_wakeup_count": self.cleanup.pending_wakeup_count,
                "presence_subscription_count": self.cleanup.presence_subscription_count,
                "active_lease_count": self.cleanup.active_lease_count,
                "worker_task_count": self.cleanup.worker_task_count,
            },
        }


@dataclass(frozen=True)
class ScenarioE2ERunResult:
    """Result of the oracle-free live model decision loop."""

    scenario_id: str
    events: tuple[InitiativeEvent, ...]
    traces: tuple[StepTrace, ...]
    transcript: tuple[Mapping[str, Any], ...]
    candidate_scans: tuple[object, ...]
    consolidation: object
    gate_result: object
    call_entries: tuple[object, ...]
    cleanup: CleanupSnapshot
    delivery_count: int
    transport_messages: tuple[tuple[str, str, str], ...]
    flow_result: str = "PASS"
    human_review: str = "PENDING"

    @property
    def event(self) -> InitiativeEvent | None:
        return self.events[0] if self.events else None

    def to_mapping(self) -> dict[str, Any]:
        event = self.event
        return {
            "scenario_id": self.scenario_id,
            "event_status": event.status.value if event else "NO_EVENT",
            "event_count": len(self.events),
            "decision_count": len(self.traces),
            "delivery_count": self.delivery_count,
            "transport_message_count": len(self.transport_messages),
            "actions": [trace.action.value for trace in self.traces if trace.action],
            "traces": ScenarioRunResult(
                event=event,
                traces=self.traces,
                decision_count=len(self.traces),
                delivery_count=self.delivery_count,
                transport_message_count=len(self.transport_messages),
                cleanup=self.cleanup,
            ).to_mapping()["traces"] if event is not None else [],
            "transcript": [dict(item) for item in self.transcript],
            "candidate_scans": [asdict(item) for item in self.candidate_scans],
            "candidate_consolidation": asdict(self.consolidation),
            "event_gate": asdict(self.gate_result),
            "call_ledger": [
                {
                    **asdict(item),
                    "stage": item.stage.value,
                    "validation_status": item.validation_status.value,
                }
                for item in self.call_entries
            ],
            "cleanup_snapshot": {
                "pending_wakeup_count": self.cleanup.pending_wakeup_count,
                "presence_subscription_count": self.cleanup.presence_subscription_count,
                "active_lease_count": self.cleanup.active_lease_count,
                "worker_task_count": self.cleanup.worker_task_count,
            },
            "initiative_message": self.transport_messages[-1][1] if self.transport_messages else None,
            "flow_result": self.flow_result,
            "human_review": self.human_review,
        }


def _live_flow_result(
    *,
    call_entries: Iterable[object],
    transcript: Iterable[Mapping[str, Any]],
    event_count: int,
    traces: Iterable[StepTrace],
    cleanup: CleanupSnapshot,
    transport_messages: Iterable[object],
) -> str:
    entries = tuple(call_entries)
    stages = [
        getattr(item, "stage", None).value
        for item in entries
        if getattr(getattr(item, "validation_status", None), "value", None) == "accepted"
    ]
    turns = sum(1 for item in transcript if item.get("role") == "user")
    actions = tuple(item.action for item in traces if item.action is not None)
    deterministic_only = bool(actions) and all(
        action in {InitiativeAction.EXPIRE, InitiativeAction.CANCEL}
        for action in actions
    )
    messages = tuple(transport_messages)
    checks = (
        cleanup.pending_wakeup_count == 0,
        cleanup.presence_subscription_count == 0,
        cleanup.active_lease_count == 0,
        cleanup.worker_task_count == 0,
        stages.count("dialogue_response") == turns,
        stages.count("candidate_scan") == turns,
        stages.count("candidate_consolidation") == 1,
        event_count == 0 or stages.count("reappraisal") >= 1 or deterministic_only,
        (InitiativeAction.SEND_NOW not in actions and not messages)
        or (stages.count("generator") >= 1 and bool(messages)),
    )
    return "PASS" if all(checks) else "FAIL"


@dataclass
class ScenarioRunnerV02:
    clock: FakeClock
    policy: Callable[[InitiativeEvent, WakeItem], PolicyDecision]
    message_generator: Callable[[InitiativeEvent, PolicyDecision], str] | None = None
    store: InMemoryInitiativeStore = field(default_factory=InMemoryInitiativeStore)
    presence: MockPresenceAdapter = field(default_factory=MockPresenceAdapter)
    delivery_store: DeliveryStore = field(default_factory=DeliveryStore)
    transport: MockMessageAdapter = field(default_factory=MockMessageAdapter)

    def __post_init__(self) -> None:
        self.queue = WakeUpQueue(self.clock)
        self.leases = LeaseRegistry(self.clock)
        self.delivery = ExactlyOnceDelivery(self.delivery_store, self.transport)
        self._event: InitiativeEvent | None = None
        self._traces: list[StepTrace] = []
        self._step = 0
        self._pending_delivery: RuntimeDeliveryAttempt | None = None

    @classmethod
    async def run_fixture(
        cls,
        fixture: "ScenarioFixture",
        *,
        live_api: bool = False,
        repetition: int = 1,
        seed: int | None = None,
        provider: object | None = None,
        config: object | None = None,
        dialogue_adapter: object | None = None,
    ) -> ScenarioE2ERunResult:
        """Execute one oracle-free live E2E decision loop.

        Deterministic transition tests should instantiate ``ScenarioRunnerV02``
        directly with ``SequencePolicy``.  Fixture execution intentionally has
        no oracle-shaped fallback path.
        """
        del repetition, seed
        if not live_api:
            raise ValueError(
                "fixture replay is live-model-only; use ScenarioRunnerV02 + "
                "SequencePolicy for deterministic transition tests"
            )
        from agent.config import AgentConfig
        from agent.llm.providers import get_provider

        resolved_config = config if isinstance(config, AgentConfig) else AgentConfig()
        if provider is None:
            if (resolved_config.backend or "mock").casefold() == "mock":
                raise LivePolicyError(
                    "live model E2E requires LLM_BACKEND to select a non-mock provider"
                )
            provider = get_provider(resolved_config)
        adapter = dialogue_adapter or GraphDialogueAdapter(
            config=resolved_config,
            initial_state={
                "conversation_history": [],
                "long_term_memory": "\n".join(
                    json.dumps(item, ensure_ascii=False)
                    for item in fixture.model.context.memories
                ),
            },
        )
        return await cls._run_live_e2e_fixture(
            fixture,
            provider=provider,
            config=resolved_config,
            dialogue_adapter=adapter,
        )

    @classmethod
    async def _run_live_e2e_fixture(
        cls,
        fixture: "ScenarioFixture",
        *,
        provider: object,
        config: object,
        dialogue_adapter: object,
    ) -> ScenarioE2ERunResult:
        clock = FakeClock(datetime.fromisoformat(fixture.driver.clock_start))
        identity_data = fixture.driver.identity
        identity = IsolationIdentity(
            tenant_id="fixture",
            user_id=identity_data["user_id"],
            character_id=identity_data["character_id"],
            world_id=identity_data["world_id"],
            source_session_id=identity_data["session_id"],
            source_platform="test",
            source_channel_id="fixture",
            delivery_target=f"test:{identity_data['user_id']}",
        )
        run_id = identity_data["run_id"]
        ledger = ProviderCallLedger(run_id)
        transcript: list[dict[str, Any]] = []
        scans: list[object] = []
        evidence_refs: list[str] = []
        user_inputs = [
            (item.step_id, item.data.get("input"))
            for item in fixture.driver.prelude
            if item.type in {"dialogue_turn", "request_reminder"}
            and isinstance(item.data.get("input"), str)
        ]
        if not user_inputs:
            user_inputs = [
                (str(item.get("turn_id") or f"u{index}"), item.get("content"))
                for index, item in enumerate(fixture.model.context.conversation, start=1)
                if item.get("role") == "user" and isinstance(item.get("content"), str)
            ]

        def process_dialogue_turn(source_id: str, user_input: str) -> None:
            index = 1 + sum(1 for item in transcript if item.get("role") == "user")
            user_ref = str(source_id) if str(source_id).startswith("turn:") else f"turn:u{index}"
            assistant_ref = f"turn:a{index}"
            with ledger.track(ProviderStage.DIALOGUE_RESPONSE, provider) as tracked:
                response = dialogue_adapter.respond({
                    "user_input": str(user_input),
                    "turn_id": user_ref,
                    "logical_now": clock.now().isoformat(),
                })
                tracked.accept(response)
            transcript.extend((
                {"turn_id": user_ref, "role": "user", "content": str(user_input)},
                {"turn_id": assistant_ref, "role": "assistant", "content": response},
            ))
            evidence_refs.extend((user_ref, assistant_ref))
            runtime_view = RuntimeModelView.from_context(
                logical_now=clock.now().isoformat(),
                context=fixture.model.context,
                transcript=transcript,
            )
            system_prompt, user_prompt = _decision_prompts(
                "candidate_scan", {"runtime": runtime_view.to_payload()}
            )
            scan_result = ledger.call_json(
                ProviderStage.CANDIDATE_SCAN,
                provider,
                system_prompt,
                user_prompt,
                float(getattr(config, "judge_temperature", 0.1)),
                max(512, int(getattr(config, "judge_max_output_tokens", 256))),
                lambda raw, refs=tuple(evidence_refs): parse_candidate_scan(
                    raw, available_evidence_refs=refs
                ),
            )
            scans.append(scan_result.value)

        for source_id, user_input in user_inputs:
            process_dialogue_turn(str(source_id), str(user_input))

        candidates = {
            candidate.candidate_id: candidate
            for scan in scans
            for candidate in scan.events
        }
        runtime_view = RuntimeModelView.from_context(
            logical_now=clock.now().isoformat(),
            context=fixture.model.context,
            transcript=transcript,
        )
        system_prompt, user_prompt = _decision_prompts(
            "candidate_consolidation",
            {
                "runtime": runtime_view.to_payload(),
                "candidate_revisions": [asdict(item) for item in candidates.values()],
            },
        )
        consolidation_result = ledger.call_json(
            ProviderStage.CANDIDATE_CONSOLIDATION,
            provider,
            system_prompt,
            user_prompt,
            float(getattr(config, "judge_temperature", 0.1)),
            max(512, int(getattr(config, "judge_max_output_tokens", 256))),
            lambda raw: parse_candidate_consolidation(
                raw, known_candidate_ids=tuple(candidates)
            ),
        )
        consolidated_scan = type(scans[-1])(
            scans[-1].schema_version,
            scans[-1].decision_type,
            tuple(candidates.values()),
            scans[-1].no_event_reason if not candidates else None,
        ) if scans else parse_candidate_scan(
            {
                "schema_version": "initiative.world_event_proposal.v1",
                "decision_type": "candidate_scan",
                "events": [],
                "no_event_reason": "no completed dialogue turn",
            },
            available_evidence_refs=(),
        )
        store = InMemoryInitiativeStore()
        gate_result = gate_candidate_events(
            consolidated_scan,
            consolidation_result.value,
            EventGateContext(
                logical_now=clock.now(),
                identity=identity,
                run_id=run_id,
                available_evidence_refs=tuple(evidence_refs),
                active_events=(),
            ),
        )
        persisted = persist_accepted_events(gate_result, store)
        empty_cleanup = CleanupSnapshot(0, 0, 0, 0)
        if not persisted:
            flow_result = _live_flow_result(
                call_entries=ledger.entries,
                transcript=transcript,
                event_count=0,
                traces=(),
                cleanup=empty_cleanup,
                transport_messages=(),
            )
            return ScenarioE2ERunResult(
                fixture.model.scenario_id, (), (), tuple(transcript), tuple(scans),
                consolidation_result.value, gate_result, ledger.entries,
                empty_cleanup, 0, (), flow_result,
            )

        def runtime_payload(event: InitiativeEvent, wake: WakeItem) -> Mapping[str, Any]:
            view = RuntimeModelView.from_context(
                logical_now=wake.scheduled_at.isoformat(),
                context=fixture.model.context,
                transcript=transcript,
                active_events=({
                    "event_id": event.event_id,
                    "event_version": event.version,
                    "status": event.status.value,
                    "summary": event.summary,
                    "expires_at": event.schedule.expires_at.isoformat(),
                },),
            )
            return {
                "runtime": view.to_payload(),
                "wake": {"kind": wake.kind.name, "logical_now": wake.scheduled_at.isoformat()},
            }

        reappraisal_policy = LedgerReappraisalPolicy(
            provider=provider,
            ledger=ledger,
            runtime_payload=runtime_payload,
            available_evidence_refs=lambda: tuple(evidence_refs),
            temperature=float(getattr(config, "judge_temperature", 0.1)),
            max_output_tokens=max(512, int(getattr(config, "judge_max_output_tokens", 256))),
        )

        def generate_message(event: InitiativeEvent, decision: PolicyDecision) -> str:
            plan = {
                "event_id": event.event_id,
                "summary": event.summary,
                "source_turn_ids": list(event.source_turn_ids),
                "message_constraints": [],
            }
            context = RuntimeModelView.from_context(
                logical_now=clock.now().isoformat(),
                context=fixture.model.context,
                transcript=transcript,
            ).to_payload()
            generator_system, generator_user = build_generator_prompt(plan, context)

            def validate(raw: str) -> str:
                errors = validate_generated_text(raw, plan=plan)
                if errors:
                    raise DecisionContractError(errors)
                return raw.strip()

            generated = ledger.call_text(
                ProviderStage.GENERATOR,
                provider,
                generator_system,
                generator_user,
                float(getattr(config, "temperature", 0.7)),
                int(getattr(config, "short_max_tokens", 160)),
                validate,
            )
            return generated.value

        runner = cls(
            clock,
            reappraisal_policy,
            message_generator=generate_message,
            store=store,
        )
        runner._event = persisted[0]
        await runner._execute_driver_lifecycle(
            fixture, process_dialogue_turn=process_dialogue_turn
        )
        finished = await runner.finish()
        events = (finished.event, *persisted[1:])
        flow_result = _live_flow_result(
            call_entries=ledger.entries,
            transcript=transcript,
            event_count=len(events),
            traces=finished.traces,
            cleanup=finished.cleanup,
            transport_messages=runner.transport.messages,
        )
        return ScenarioE2ERunResult(
            fixture.model.scenario_id,
            events,
            finished.traces,
            tuple(transcript),
            tuple(scans),
            consolidation_result.value,
            gate_result,
            ledger.entries,
            finished.cleanup,
            finished.delivery_count,
            tuple(runner.transport.messages),
            flow_result,
        )

    async def _execute_driver_lifecycle(
        self,
        fixture: "ScenarioFixture",
        *,
        process_dialogue_turn: Callable[[str, str], None] | None = None,
    ) -> None:
        """Consume driver/harness steps without consulting the post-run oracle."""
        terminal = {
            EventStatus.CANCELLED, EventStatus.EXPIRED,
            EventStatus.SILENCED, EventStatus.COMPLETED,
        }
        steps = tuple(sorted(
            (*fixture.driver.timeline, *fixture.harness.timeline),
            key=lambda item: (
                datetime.fromisoformat(item.at) if item.at is not None else datetime.max.replace(tzinfo=self.clock.now().tzinfo)
            ),
        ))

        async def drain_due_until(target: datetime) -> None:
            while self.event.status not in terminal:
                due_at = self.event.schedule.next_evaluation_at
                expiry_at = self.event.schedule.expires_at
                wake_at = min(
                    item for item in (due_at, expiry_at) if item is not None
                )
                if wake_at > target:
                    return
                if wake_at > self.clock.now():
                    self.clock.advance_to(wake_at)
                kind = WakeKind.EXPIRY if self.clock.now() >= expiry_at else WakeKind.DUE_EVALUATION
                await self.wake(kind)

        for step in steps:
            if self.event.status in terminal:
                break
            target: datetime | None = None
            if step.at is not None:
                target = datetime.fromisoformat(step.at)
            elif step.type == "advance_clock":
                minutes = step.data.get("minutes")
                if isinstance(minutes, int) and minutes > 0:
                    target = self.clock.now() + timedelta(minutes=minutes)
                else:
                    target = self.event.schedule.next_evaluation_at or self.event.schedule.expires_at
            if target is not None and target > self.clock.now():
                await drain_due_until(target)
                if self.event.status in terminal:
                    break
                if target > self.clock.now():
                    self.clock.advance_to(target)
            if step.type == "advance_clock":
                continue
            if step.type == "presence_signal":
                if self.event.status is EventStatus.WAITING_FOR_PRESENCE:
                    await self.signal_presence()
                else:
                    target = self.event.schedule.next_evaluation_at
                    if target is not None and target > self.clock.now():
                        self.clock.advance_to(target)
                    await self.wake(WakeKind.DUE_EVALUATION)
            elif step.type in {"user_message", "resolve_topic"}:
                user_input = step.data.get("input")
                if process_dialogue_turn is not None and isinstance(user_input, str):
                    process_dialogue_turn(step.step_id, user_input)
                await self.wake(WakeKind.USER_MESSAGE)
            elif step.type == "cancel_event":
                await self.wake(
                    WakeKind.CANCELLATION,
                    decision_override=PolicyDecision(
                        InitiativeAction.CANCEL, "explicit_user_cancel"
                    ),
                )
            elif step.type == "inject_fault":
                target = self.event.schedule.next_evaluation_at or self.clock.now()
                if target > self.clock.now():
                    self.clock.advance_to(target)
                try:
                    await self.wake(WakeKind.DUE_EVALUATION, crash_after_send=True)
                except RuntimeError as exc:
                    if "crash after send" not in str(exc):
                        raise
                    await self.recover_delivery()
            elif step.type == "duplicate_wakeup":
                await self.wake(WakeKind.DUE_EVALUATION)
            elif step.type in {
                "checkpoint_session", "open_session", "set_world_state",
                "set_external_observation", "set_do_not_disturb",
            }:
                target = self.event.schedule.next_evaluation_at
                if target is not None and target > self.clock.now():
                    self.clock.advance_to(target)
                await self.wake(WakeKind.DUE_EVALUATION)
            elif step.type in {"acknowledge_event", "shutdown_world", "start_competing_worker"}:
                continue

    @property
    def event(self) -> InitiativeEvent:
        if self._event is None:
            raise RuntimeError("scenario event has not been created")
        return self._event

    def create_committed_event(
        self,
        *,
        event_id: str,
        run_id: str,
        identity: IsolationIdentity,
        level: str,
        source_turn_id: str,
        summary: str,
        earliest_at: datetime,
        expires_at: datetime,
        requires_acknowledgement: bool = False,
    ) -> InitiativeEvent:
        event = InitiativeEvent(
            event_id=event_id,
            run_id=run_id,
            identity=identity,
            initiative_level=level,
            source_turn_ids=(source_turn_id,),
            summary=summary,
            schedule=EventSchedule(earliest_at, expires_at, earliest_at),
            idempotency_key=f"{run_id}:{event_id}:create",
            activation_token=f"{run_id}:{event_id}:activate",
            requires_acknowledgement=requires_acknowledgement,
        )
        activated, _ = event_first_commitment(
            self.store, event, lambda: summary, lambda _: source_turn_id
        )
        self._event = activated
        return activated

    async def advance_to_next_evaluation(self) -> StepTrace:
        target = self.event.schedule.next_evaluation_at
        if target is None:
            raise RuntimeError("event has no scheduled evaluation")
        self.clock.advance_to(target)
        return await self.wake(WakeKind.DUE_EVALUATION)

    async def wake(
        self,
        kind: WakeKind,
        *,
        crash_after_send: bool = False,
        decision_override: PolicyDecision | None = None,
    ) -> StepTrace:
        event = self.event
        item = WakeItem(
            self.clock.now(), kind, event.event_id, event.run_id,
            event.identity.world_id, event.initiative_level, self.clock.now(),
            payload={"event_version": event.version},
        )
        self.queue.put_nowait(item)
        due = await self.queue.get_due()
        if due is None:
            raise RuntimeError("wake queue closed before dispatch")
        return await self._evaluate(
            due, crash_after_send=crash_after_send,
            decision_override=decision_override,
        )

    async def signal_presence(
        self, *, decision_override: PolicyDecision | None = None
    ) -> StepTrace:
        event = self.event
        matched = self.presence.signal(
            event.identity.world_id, event.identity.user_id, self.clock.now()
        )
        if event.event_id not in matched:
            raise RuntimeError("presence signal did not match the scenario event")
        return await self.wake(WakeKind.PRESENCE, decision_override=decision_override)

    async def recover_delivery(self) -> StepTrace:
        if self._pending_delivery is None:
            raise RuntimeError("there is no interrupted delivery to recover")
        before = self.event
        delivered = await self.delivery.deliver(self._pending_delivery)
        after = complete_delivery(before)
        self.store.save_event(after, expected_version=before.version)
        self._event = after
        self._pending_delivery = None
        return self._record(
            "DELIVERY_RETRY", before, after, InitiativeAction.SEND_NOW,
            ("receipt_recovery",), delivered,
        )

    async def _evaluate(
        self,
        wake: WakeItem,
        *,
        crash_after_send: bool,
        decision_override: PolicyDecision | None = None,
    ) -> StepTrace:
        before = self.event
        if self.clock.now() >= before.schedule.expires_at and wake.kind is not WakeKind.PRESENCE:
            decision = PolicyDecision(InitiativeAction.EXPIRE, "expiry_precedence")
        else:
            try:
                decision = decision_override or self.policy(before, wake)
            except LivePolicyError as exc:
                self._record(
                    wake.kind.name,
                    before,
                    before,
                    None,
                    (),
                    None,
                    provider_attempts=exc.attempts,
                    error_message=str(exc),
                )
                raise
        kwargs: dict[str, object] = {}
        if decision.action is InitiativeAction.DELAY:
            kwargs["next_evaluation_at"] = decision.delay_until
        elif decision.action is InitiativeAction.WAIT_FOR_USER_ACTIVITY:
            key = f"presence:{before.run_id}:{before.event_id}"
            kwargs.update(
                presence_subscription_key=key,
                expiry_wakeup_at=before.schedule.expires_at,
            )
        after = apply_action(before, decision.action, **kwargs)
        record = DecisionRecord(
            decision_id=f"decision-{len(self.store.decisions_for(before.event_id)) + 1}",
            event_id=before.event_id,
            event_version_before=before.version,
            plan_id=f"plan-{before.version}",
            action=decision.action,
            reason_codes=(decision.reason_code,),
            decided_at=self.clock.now(),
            next_evaluation_at=decision.delay_until,
        )
        self.store.append_decision(record)
        self.store.save_event(after, expected_version=before.version)
        self._event = after
        if decision.action is InitiativeAction.WAIT_FOR_USER_ACTIVITY:
            self.presence.subscribe(PresenceSubscription(
                after.presence_subscription_key or "", after.identity.world_id,
                after.identity.user_id, after.event_id, after.schedule.expires_at,
            ))
        elif before.presence_subscription_key:
            self.presence.unsubscribe(before.presence_subscription_key)

        delivered = None
        if decision.action is InitiativeAction.SEND_NOW:
            generated_content = (
                self.message_generator(after, decision)
                if self.message_generator is not None else after.summary
            )
            if not isinstance(generated_content, str) or not generated_content.strip():
                raise RuntimeError("initiative generator returned an empty message")
            generated_content = generated_content.strip()
            attempt = RuntimeDeliveryAttempt(
                event_id=after.event_id,
                event_version=after.version,
                idempotency_key=f"{after.event_id}:send:{after.version}",
                target=after.identity.delivery_target,
                content=generated_content,
                content_hash=content_hash(generated_content),
                attempted_at=self.clock.now(),
            )
            self._pending_delivery = attempt
            try:
                delivered = await self.delivery.deliver(
                    attempt, crash_after_send=crash_after_send
                )
            except RuntimeError:
                recorded_attempt = self.delivery_store.attempts.get(
                    attempt.idempotency_key, attempt
                )
                self._record(wake.kind.name, before, after, decision.action,
                             (decision.reason_code,), recorded_attempt, decision,
                             decision_record=record)
                raise
            completed = complete_delivery(after)
            self.store.save_event(completed, expected_version=after.version)
            self._event = completed
            self._pending_delivery = None
            after = completed
        return self._record(
            wake.kind.name, before, after, decision.action,
            (decision.reason_code,), delivered, decision, decision_record=record,
        )

    def _record(self, trigger: str, before: InitiativeEvent, after: InitiativeEvent,
                action: InitiativeAction | None, reason_codes: tuple[str, ...],
                delivery: RuntimeDeliveryAttempt | None,
                policy_decision: PolicyDecision | None = None,
                *,
                decision_record: DecisionRecord | None = None,
                provider_attempts: tuple[ProviderAttemptTrace, ...] = (),
                error_message: str | None = None) -> StepTrace:
        self._step += 1
        trace = StepTrace(
            step_id=f"step-{self._step}", logical_time=self.clock.now(), trigger=trigger,
            event_version_before=before.version, status_before=before.status,
            action=action, event_version_after=after.version, status_after=after.status,
            reason_codes=reason_codes,
            delivery_status=delivery.status.value if delivery else None,
            transport_message_id=delivery.transport_message_id if delivery else None,
            model_prompt_hash=policy_decision.prompt_hash if policy_decision else None,
            model_raw_output=policy_decision.raw_output if policy_decision else None,
            provider_name=policy_decision.provider_name if policy_decision else None,
            provider_attempts=(
                policy_decision.provider_attempts if policy_decision else provider_attempts
            ),
            error_message=error_message,
            decision_id=decision_record.decision_id if decision_record else None,
            decision_plan_id=decision_record.plan_id if decision_record else None,
            decision_decided_at=decision_record.decided_at if decision_record else None,
            delivery_event_version=delivery.event_version if delivery else None,
            delivery_idempotency_key=delivery.idempotency_key if delivery else None,
            delivery_content_hash=delivery.content_hash if delivery else None,
        )
        self._traces.append(trace)
        return trace

    async def finish(self) -> ScenarioRunResult:
        event = self.event
        if event.presence_subscription_key:
            self.presence.unsubscribe(event.presence_subscription_key)
        self.queue.close()
        cleanup = CleanupSnapshot(
            pending_wakeup_count=0 if self.queue.empty else 1,
            presence_subscription_count=len(self.presence.subscriptions),
            active_lease_count=0,
            worker_task_count=0,
        )
        return ScenarioRunResult(
            event=event,
            traces=tuple(self._traces),
            decision_count=len(self.store.decisions_for(event.event_id)),
            delivery_count=len(self.delivery_store.attempts),
            transport_message_count=len(self.transport.messages),
            cleanup=cleanup,
        )


async def run_scenarios(
    fixtures: Iterable["ScenarioFixture"],
    *,
    live_api: bool = False,
    repeat: int = 1,
    seed: int | None = None,
    provider: object | None = None,
    config: object | None = None,
) -> tuple[ScenarioE2ERunResult, ...]:
    """Run an oracle-free live fixture batch in isolated worlds."""
    if repeat <= 0:
        raise ValueError("repeat must be positive")
    results = []
    for fixture in fixtures:
        for repetition in range(repeat):
            run_seed = None if seed is None else seed + repetition
            results.append(await ScenarioRunnerV02.run_fixture(
                fixture,
                live_api=live_api,
                repetition=repetition + 1,
                seed=run_seed,
                provider=provider,
                config=config,
            ))
    return tuple(results)


ScenarioRunner = ScenarioRunnerV02


__all__ = [
    "CleanupSnapshot", "LedgerReappraisalPolicy", "LiveAIPolicy", "LivePolicyError",
    "PolicyDecision", "ScenarioE2ERunResult", "ScenarioRunResult", "ScenarioRunner",
    "ScenarioRunnerV02", "SequencePolicy", "StepTrace", "run_scenarios",
]
