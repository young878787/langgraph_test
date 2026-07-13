"""Deterministic v0.2 scenario orchestration over the initiative ports.

This runner intentionally owns no transition or delivery rules.  It wires the
domain, store, virtual clock, presence and exactly-once delivery components into
one bounded test world.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any, Callable, Iterable, TYPE_CHECKING

from .adapters import MockPresenceAdapter, PresenceSubscription
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


@dataclass
class ScenarioRunnerV02:
    clock: FakeClock
    policy: Callable[[InitiativeEvent, WakeItem], PolicyDecision]
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
    ) -> ScenarioRunResult:
        """Execute one validated fixture with its deterministic baseline policy.

        Oracle steps configure the fake policy only; ``ModelInputView.to_payload``
        is evaluated first and remains physically isolated from that policy.
        """
        del repetition, seed
        model_payload = fixture.model.to_payload()
        clock_start = datetime.fromisoformat(fixture.model.clock_start)
        decisions: list[PolicyDecision] = []
        if not live_api:
            for index, expected in enumerate(fixture.oracle.expected_steps):
                delay_until = None
                if expected.expected_action == InitiativeAction.DELAY.value:
                    delay_until = clock_start + timedelta(minutes=10 + index * 5)
                decisions.append(PolicyDecision(
                    InitiativeAction(expected.expected_action),
                    expected.allowed_reason_codes[0]
                    if expected.allowed_reason_codes else "fixture_baseline",
                    delay_until,
                ))
        policy: Callable[[InitiativeEvent, WakeItem], PolicyDecision]
        if live_api:
            if provider is None:
                from agent.config import AgentConfig
                from agent.llm.providers import get_provider

                resolved_config = config if isinstance(config, AgentConfig) else AgentConfig()
                if (resolved_config.backend or "mock").casefold() == "mock":
                    raise LivePolicyError(
                        "--live-api requires LLM_BACKEND to select a non-mock provider"
                    )
                provider = get_provider(resolved_config)
            temperature = float(getattr(config, "judge_temperature", 0.1))
            # Reasoning-capable providers may spend part of this budget before
            # emitting the small JSON object.  Keep the structured contract
            # bounded, but do not inherit the legacy 150-token judge ceiling.
            max_tokens = max(512, int(getattr(config, "judge_max_output_tokens", 180)))
            policy = LiveAIPolicy(
                model_payload, provider, temperature=temperature,
                max_output_tokens=max_tokens,
            )
        else:
            policy = SequencePolicy(decisions)
        runner = cls(FakeClock(clock_start), policy)
        try:
            await runner._prepare_fixture(fixture)
            await runner._execute_expected_lifecycle(fixture)
        except Exception as exc:
            if runner._event is not None:
                partial_result = await runner.finish()
                try:
                    setattr(exc, "partial_result", partial_result)
                except (AttributeError, TypeError):
                    pass
            raise
        return await runner.finish()

    async def _prepare_fixture(self, fixture: "ScenarioFixture") -> None:
        identity_data = fixture.model.context.identity
        identity = IsolationIdentity(
            tenant_id="fixture", user_id=identity_data["user_id"],
            character_id=identity_data["character_id"], world_id=identity_data["world_id"],
            source_session_id=identity_data["session_id"], source_platform="test",
            source_channel_id="fixture", delivery_target=f"test:{identity_data['user_id']}",
        )
        prelude = fixture.model.prelude[0]
        source_refs = tuple(prelude.data.get("source_turn_ids", ()))
        if not source_refs:
            source_refs = tuple(item.ref for item in fixture.model.context.provenance)
        source_turn_id = source_refs[0] if source_refs else "turn:u1"
        earliest = datetime.fromisoformat(str(
            prelude.data.get("schedule_at", self.clock.now() + timedelta(minutes=5))
        )) if isinstance(prelude.data.get("schedule_at"), str) else self.clock.now() + timedelta(minutes=5)
        expires = datetime.fromisoformat(str(
            prelude.data.get("expires_at", self.clock.now() + timedelta(hours=2))
        )) if isinstance(prelude.data.get("expires_at"), str) else self.clock.now() + timedelta(hours=2)
        self.create_committed_event(
            event_id=f"event-{fixture.model.scenario_id}", run_id=identity_data["run_id"],
            identity=identity, level=fixture.model.category if fixture.model.category in {"L0", "L1", "L2"} else "L2",
            source_turn_id=source_turn_id, summary=fixture.model.purpose,
            earliest_at=earliest, expires_at=expires,
            requires_acknowledgement=prelude.type == "deliver_once",
        )
        if prelude.type == "deliver_once":
            await self._seed_delivered(prelude.data.get("idempotency_key"))
        if fixture.model.scenario_id == "cross_03":
            before = self.event
            key = f"presence:{before.run_id}:{before.event_id}"
            waiting = apply_action(
                before, InitiativeAction.WAIT_FOR_USER_ACTIVITY,
                presence_subscription_key=key, expiry_wakeup_at=before.schedule.expires_at,
            )
            self.store.save_event(waiting, expected_version=before.version)
            self._event = waiting
            self.presence.subscribe(PresenceSubscription(
                key, waiting.identity.world_id, waiting.identity.user_id,
                waiting.event_id, waiting.schedule.expires_at,
            ))

    async def _seed_delivered(self, key: object) -> None:
        before = self.event
        attempt = RuntimeDeliveryAttempt(
            before.event_id, before.version, str(key or f"{before.event_id}:seed"),
            before.identity.delivery_target, before.summary, content_hash(before.summary), self.clock.now(),
        )
        await self.delivery.deliver(attempt)
        delivered = replace(before, status=EventStatus.DELIVERED, version=before.version + 1,
                            schedule=replace(before.schedule, next_evaluation_at=None))
        self.store.save_event(delivered, expected_version=before.version)
        self._event = delivered

    async def _execute_expected_lifecycle(self, fixture: "ScenarioFixture") -> None:
        scenario_id = fixture.model.scenario_id
        for index, expected in enumerate(fixture.oracle.expected_steps):
            if self.event.status in {EventStatus.CANCELLED, EventStatus.EXPIRED,
                                     EventStatus.SILENCED, EventStatus.COMPLETED}:
                # A duplicated terminal wake is audited but cannot transition.
                self.store.append_decision(DecisionRecord(
                    f"decision-{len(self.store.decisions_for(self.event.event_id)) + 1}",
                    self.event.event_id, self.event.version, f"plan-terminal-{index}",
                    InitiativeAction(expected.expected_action),
                    tuple(expected.allowed_reason_codes) or ("terminal_wake_skipped",), self.clock.now(),
                ))
                continue
            trigger = expected.trigger
            decision_override = None
            if expected.decision_owner != "model":
                delay_until = None
                if expected.expected_action == InitiativeAction.DELAY.value:
                    delay_until = self.clock.now() + timedelta(minutes=10 + index * 5)
                decision_override = PolicyDecision(
                    InitiativeAction(expected.expected_action),
                    expected.allowed_reason_codes[0]
                    if expected.allowed_reason_codes else f"{expected.decision_owner}_decision",
                    delay_until,
                )
            if trigger == "EXPIRY":
                self.clock.advance_to(self.event.schedule.expires_at)
                await self.wake(WakeKind.EXPIRY, decision_override=decision_override)
            elif trigger == "PRESENCE":
                await self.signal_presence(decision_override=decision_override)
            elif trigger == "RECOVERY" and scenario_id == "delivery_01":
                target = self.event.schedule.next_evaluation_at or self.clock.now()
                self.clock.advance_to(target)
                try:
                    await self.wake(
                        WakeKind.DUE_EVALUATION, crash_after_send=True,
                        decision_override=decision_override,
                    )
                except RuntimeError as exc:
                    if "crash after send" not in str(exc):
                        raise
                await self.recover_delivery()
            else:
                target = self.event.schedule.next_evaluation_at
                if target is not None and target > self.clock.now():
                    self.clock.advance_to(target)
                kind = {
                    "USER_CANCEL": WakeKind.CANCELLATION,
                    "USER_MESSAGE": WakeKind.USER_MESSAGE,
                    "DUPLICATE_WAKEUP": WakeKind.DUE_EVALUATION,
                    "ACK_DEADLINE": WakeKind.DUE_EVALUATION,
                    "INTERNAL_OPPORTUNITY": WakeKind.DUE_EVALUATION,
                }.get(trigger, WakeKind.DUE_EVALUATION)
                await self.wake(kind, decision_override=decision_override)

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
            attempt = RuntimeDeliveryAttempt(
                event_id=after.event_id,
                event_version=after.version,
                idempotency_key=f"{after.event_id}:send:{after.version}",
                target=after.identity.delivery_target,
                content=after.summary,
                content_hash=content_hash(after.summary),
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
) -> tuple[ScenarioRunResult, ...]:
    """Run a deterministic fixture batch in isolated worlds."""
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
    "CleanupSnapshot", "LiveAIPolicy", "LivePolicyError", "PolicyDecision", "ScenarioRunResult",
    "ScenarioRunner", "ScenarioRunnerV02", "SequencePolicy", "StepTrace", "run_scenarios",
]
