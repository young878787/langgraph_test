"""Offline/live orchestration for event-driven character initiative fixtures."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import importlib
import hashlib
import json
import random
import re
import time
from typing import Any, Callable, Iterable, Mapping

from agent.config import AgentConfig
from agent.graph import build_graph
from agent.llm.providers import get_provider
from agent.state import AgentState

from .clock import FakeClock
from .contracts import (
    InitiativePlan,
    PlanGoal,
    PlanTiming,
    PostDialogueOpportunity,
    check_plan,
)
from .fixtures import InitiativeFixture, parse_event_at
from .reappraisal import ReappraisalContext, ReappraisalDecision, reappraise


class InitiativeRunnerError(RuntimeError):
    """Raised for orchestration failures that should become an ERROR result."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        raw_output: Any = None,
        validation_errors: Iterable[str] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.raw_output = raw_output
        self.validation_errors = tuple(str(error) for error in validation_errors if error)


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    summary: str


@dataclass
class InitiativeRunResult:
    scenario_id: str
    repetition: int
    status: str
    fixture_hash: str
    initiative_message: str = ""
    plan: InitiativePlan | None = None
    decision: ReappraisalDecision | None = None
    gates: list[GateResult] | None = None
    log_path: str = ""
    trace: dict[str, Any] | None = None

    @property
    def result(self) -> str:
        return self.status

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["plan"] = _jsonable(self.plan)
        payload["decision"] = _jsonable(self.decision)
        payload["gates"] = [_jsonable(gate) for gate in (self.gates or [])]
        return payload


class _OfflineProvider:
    """Small graph-compatible provider used only when no provider is injected."""

    def generate(self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens: int | None = None) -> str:
        return "哼，知道了啦。先把眼前的事處理好，別逞強。"

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens: int | None = None) -> str:
        return "{}"

    def generate_with_history(self, system_prompt: str, user_prompt: str, temperature: float, conversation_history: list[dict] | None = None, max_output_tokens: int | None = None) -> str:
        return self.generate(system_prompt, user_prompt, temperature, max_output_tokens)

    def summarize(self, prompt: str, max_tokens: int = 1000) -> str | None:
        return None


class _GraphProviderAdapter:
    """Adapt a minimal fake provider to the existing dialogue graph contract."""

    def __init__(self, provider: Any):
        self.provider = provider

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.provider, name, None)
        if method is None:
            if name in {"generate_json", "generate_with_history"}:
                method = getattr(self.provider, "generate", None)
            if method is None:
                raise InitiativeRunnerError(f"provider has no {name} method")
        try:
            return method(*args, **kwargs)
        except TypeError:
            # Contract fakes commonly expose a shorter signature.
            if name == "generate_with_history":
                return method(args[0], args[1], args[2])
            return method(*args[:3])

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("generate", *args, **kwargs)

    def generate_json(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("generate_json", *args, **kwargs)

    def generate_with_history(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("generate_with_history", *args, **kwargs)

    def summarize(self, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.provider, "summarize", None)
        return method(*args, **kwargs) if method else None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and value.__class__.__module__.startswith("agent."):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _call_variants(callable_obj: Callable[..., Any], variants: Iterable[tuple[Any, ...]]) -> Any:
    last_error: Exception | None = None
    for args in variants:
        try:
            return callable_obj(*args)
        except TypeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise InitiativeRunnerError("no callable variants supplied")


def _parse_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return deepcopy(dict(raw))
    if not isinstance(raw, str) or not raw.strip():
        raise InitiativeRunnerError("provider returned empty JSON output")
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InitiativeRunnerError(f"provider returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise InitiativeRunnerError("provider JSON output must be an object")
    return deepcopy(dict(parsed))


def _component_method(component: Any, names: tuple[str, ...]) -> Callable[..., Any] | None:
    if callable(component):
        return component
    for name in names:
        method = getattr(component, name, None)
        if callable(method):
            return method
    return None


@contextmanager
def _patched_graph_provider(provider: Any):
    """Scope provider injection to dialogue graph execution only."""

    graph_provider = _GraphProviderAdapter(provider)
    modules = [
        importlib.import_module("agent.llm.providers"),
        importlib.import_module("agent.nodes.judge"),
        importlib.import_module("agent.nodes.response"),
    ]
    original = {module: getattr(module, "get_provider", None) for module in modules}
    try:
        for module in modules:
            setattr(module, "get_provider", lambda _config: graph_provider)
        yield
    finally:
        for module, function in original.items():
            if function is not None:
                setattr(module, "get_provider", function)


class InitiativeRunner:
    """Run one or more self-contained initiative fixtures without background work."""

    def __init__(
        self,
        config: AgentConfig | None = None,
        *,
        provider: Any | None = None,
        planner: Any | None = None,
        generator: Any | None = None,
        evaluator: Any | None = None,
        graph_builder: Callable[..., Any] = build_graph,
        live_api: bool = False,
        log_writer: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.provider = provider
        self.planner = planner
        self.generator = generator
        self.evaluator = evaluator
        self.graph_builder = graph_builder
        self.live_api = live_api
        self.log_writer = log_writer

    def run_fixture(self, fixture: InitiativeFixture, *, repetition: int = 1, seed: int | None = None) -> InitiativeRunResult:
        started_at = time.perf_counter()
        random.seed(fixture.seed if seed is None else seed)
        trace: dict[str, Any] = {
            "_scenario_started_at": started_at,
            "scenario": {
                "scenario_id": fixture.scenario_id,
                "description": fixture.description,
                "fixture_hash": fixture.fixture_hash,
                "clock_start": fixture.clock_start.isoformat(),
                "timezone": fixture.timezone,
                "seed": fixture.seed if seed is None else seed,
                "provider_backend": self.config.backend,
                "model": _config_model(self.config),
                "temperature": self.config.temperature,
                "judge_temperature": self.config.judge_temperature,
            },
            "initial_state": _jsonable(fixture.initial_state),
            "dialogue": deepcopy(list(fixture.dialogue)),
            "post_dialogue_events": deepcopy(list(fixture.post_dialogue_events)),
            "expected": deepcopy(fixture.expected),
            "gates": [],
            "errors": [],
        }
        gates: list[GateResult] = []
        state = fixture.fresh_state()
        provider = self._resolve_provider(trace)
        if provider is None:
            provider_errors = trace.get("errors") or ["live API provider unavailable"]
            provider_error = provider_errors[-1]
            return self._finish(
                fixture, repetition, "ERROR", gates, trace, error=provider_error
            )

        try:
            state = self._run_dialogue(fixture, state, provider, trace)
            gates.append(GateResult("dialogue", True, "fixture dialogue replayed and assistant turns written back"))
            opportunity = PostDialogueOpportunity(
                observed_at=fixture.clock_start
                if not fixture.dialogue
                else parse_event_at(fixture.dialogue[-1]["at"], fixture.clock_start, field="dialogue:last.at"),
                last_dialogue_at=None
                if not fixture.dialogue
                else parse_event_at(fixture.dialogue[-1]["at"], fixture.clock_start, field="dialogue:last.at"),
            )
            trace["post_dialogue_opportunity"] = _jsonable(opportunity)
            context = self._build_context(fixture, state)
            trace["context"] = context
            trace["planner_prompt"] = _planner_prompt(fixture, context)
            trace.setdefault("prompt_hashes", {})["planner"] = _prompt_hash(trace["planner_prompt"])

            plan, raw_plan = self._make_plan(fixture, context, provider, opportunity)
            trace["planner_raw"] = _jsonable(raw_plan)
            trace["plan"] = _jsonable(plan)
            evidence_refs = context.get("evidence_refs", [])
            validation = check_plan(plan, available_evidence_refs=evidence_refs)
            expected_goals = fixture.expected.get("allowed_goals", [])
            goal_value = plan.goal.value if hasattr(plan.goal, "value") else str(plan.goal)
            goal_ok = not expected_goals or goal_value in expected_goals
            forbidden = set(fixture.expected.get("forbidden_goals", []))
            goal_ok = goal_ok and goal_value not in forbidden
            required_evidence = set(fixture.expected.get("required_evidence_refs", []))
            evidence_ok = required_evidence.issubset(set(plan.evidence_refs))
            planner_ok = validation.valid and goal_ok and evidence_ok
            gates.append(GateResult("planner contract", planner_ok, "valid plan, goal and evidence bounds" if planner_ok else "plan rejected by deterministic validation, goal or evidence bounds"))
            if not planner_ok:
                return self._finish(fixture, repetition, "FAIL", gates, trace, plan=plan)

            clock = FakeClock(fixture.clock_start)
            decision, event_context = self._replay_post_dialogue_events(
                fixture, state, plan, clock, provider, trace
            )
            trace["fake_clock_now"] = clock.now().isoformat()
            trace["reappraisal"] = _jsonable(decision)
            expected_action = fixture.expected.get("reappraisal_action")
            action_ok = expected_action is None or decision.action == expected_action
            if fixture.expected.get("allow_send") is False:
                action_ok = action_ok and decision.action != "send"
            if fixture.expected.get("allow_send") is True:
                action_ok = action_ok and decision.action == "send"
            gates.append(GateResult("reappraisal", action_ok, decision.reason if action_ok else f"unexpected action: {decision.action}"))
            if not action_ok:
                return self._finish(fixture, repetition, "FAIL", gates, trace, plan=plan, decision=decision)

            if decision.action != "send":
                gates.append(GateResult("generator contract", True, "generator not called by hard reappraisal gate"))
                gates.append(GateResult("evaluator", True, "evaluator not required for non-send result"))
                return self._finish(fixture, repetition, "PASS", gates, trace, plan=plan, decision=decision)

            trace["generator_prompt"] = _generator_prompt(fixture, context, plan)
            trace.setdefault("prompt_hashes", {})["generator"] = _prompt_hash(trace["generator_prompt"])
            message, raw_message = self._make_message(fixture, context, plan, provider)
            trace["generator_raw"] = _jsonable(raw_message)
            message_ok, message_reason = self._validate_message(message, fixture.expected)
            gates.append(GateResult("generator contract", message_ok, message_reason))
            if not message_ok:
                return self._finish(fixture, repetition, "FAIL", gates, trace, plan=plan, decision=decision, message=message)

            trace["evaluator_prompt"] = _evaluator_prompt(fixture, context, plan, message)
            trace.setdefault("prompt_hashes", {})["evaluator"] = _prompt_hash(trace["evaluator_prompt"])
            rubric, raw_rubric = self._evaluate(fixture, context, plan, message, provider)
            trace["evaluator_raw"] = _jsonable(raw_rubric)
            eval_ok, eval_reason = self._validate_rubric(rubric, fixture.expected)
            gates.append(GateResult("evaluator", eval_ok, eval_reason))
            return self._finish(
                fixture,
                repetition,
                "PASS" if eval_ok else "FAIL",
                gates,
                trace,
                plan=plan,
                decision=decision,
                message=message,
            )
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, InitiativeRunnerError):
                validation_errors = list(exc.validation_errors)
                stage = exc.stage or "runner"
                if exc.raw_output is not None and stage == "planner":
                    trace["planner_raw"] = _jsonable(exc.raw_output)
                if validation_errors and stage == "planner":
                    trace["planner_validation_errors"] = validation_errors
                if validation_errors:
                    primary_reason = (
                        f"{stage} contract validation failed: "
                        + "; ".join(validation_errors)
                    )
                else:
                    primary_reason = f"{stage} failed: {exc}"
                trace["failure"] = {
                    "stage": stage,
                    "kind": "validation" if validation_errors else "exception",
                    "primary_reason": primary_reason,
                    "validation_errors": validation_errors,
                }
                trace["primary_reason"] = primary_reason
            trace["errors"].append(error_text)
            gates.append(GateResult("runner", False, str(exc)))
            return self._finish(fixture, repetition, "ERROR", gates, trace)

    def run_many(self, fixtures: Iterable[InitiativeFixture], *, repeat: int = 1, seed: int | None = None) -> list[InitiativeRunResult]:
        if repeat < 1:
            raise ValueError("repeat must be >= 1")
        results: list[InitiativeRunResult] = []
        for fixture in fixtures:
            for repetition in range(1, repeat + 1):
                run_seed = None if seed is None else seed + repetition - 1
                results.append(self.run_fixture(fixture, repetition=repetition, seed=run_seed))
        return results

    def _resolve_provider(self, trace: dict[str, Any]) -> Any | None:
        if self.live_api:
            if (self.config.backend or "mock").lower() == "mock":
                trace["errors"].append("--live-api requires a non-mock backend")
                return None
            try:
                provider = get_provider(self.config)
            except Exception as exc:
                trace["errors"].append(
                    f"live API provider initialization failed: {type(exc).__name__}: {exc}"
                )
                return None
            trace["provider"] = type(provider).__name__
            return provider
        provider = self.provider or _OfflineProvider()
        trace["provider"] = type(provider).__name__
        return provider

    def _run_dialogue(self, fixture: InitiativeFixture, state: AgentState, provider: Any, trace: dict[str, Any]) -> AgentState:
        graph = _call_variants(self.graph_builder, ((self.config,), tuple()))
        pending_assistant_index: int | None = None
        with _patched_graph_provider(provider):
            for entry in fixture.dialogue:
                if entry["role"] == "user":
                    prior_history = deepcopy(state.get("conversation_history", []))
                    state = deepcopy(graph.invoke({**state, "user_input": entry["content"]}))
                    # The production graph currently returns only its generated
                    # assistant turn.  The replay harness owns the fixture
                    # transcript, so preserve the user evidence explicitly.
                    history = prior_history + [{"role": "user", "content": entry["content"]}]
                    generated_response = state.get("response")
                    if generated_response:
                        history.append({"role": "assistant", "content": generated_response})
                        pending_assistant_index = len(history) - 1
                    else:
                        pending_assistant_index = None
                    state["conversation_history"] = history
                    continue
                history = list(state.get("conversation_history", []))
                if pending_assistant_index is not None and 0 <= pending_assistant_index < len(history) and history[pending_assistant_index].get("role") == "assistant":
                    history[pending_assistant_index] = {"role": "assistant", "content": entry["content"]}
                else:
                    history.append({"role": "assistant", "content": entry["content"]})
                state["conversation_history"] = history
                state["response"] = entry["content"]
                pending_assistant_index = None
        trace["state_after_dialogue"] = _jsonable(state)
        return state

    def _build_context(self, fixture: InitiativeFixture, state: AgentState) -> dict[str, Any]:
        # Context construction owns the bounded selection and provenance
        # rules.  Keep this adapter keyword-only so runner/debug data cannot
        # leak through a positional call.
        try:
            module = importlib.import_module("agent.initiative.context")
        except ModuleNotFoundError:
            module = None
        if module is not None:
            builder = _component_method(module, ("build_context", "create_context"))
            if builder:
                try:
                    value = builder(
                        state=state,
                        conversation_history=state.get("conversation_history", []),
                        long_term_memory=state.get("long_term_memory", ""),
                        relationship_context=state.get("relationship_state", {}),
                        character_state_summary=state.get("character_state", {}),
                        candidate_goal_context=fixture.expected,
                    )
                    if isinstance(value, Mapping):
                        return deepcopy(dict(value))
                except Exception as exc:
                    raise InitiativeRunnerError(
                        f"context builder failed: {type(exc).__name__}: {exc}"
                    ) from exc
        history = deepcopy(state.get("conversation_history", []))
        last_user = next((item for item in reversed(history) if item.get("role") == "user"), None)
        evidence_refs = [f"dialogue:{index}" for index in range(len(history))]
        if last_user:
            evidence_refs.append("dialogue:last_user")
        if state.get("long_term_memory"):
            evidence_refs.append("memory:long_term")
        open_thread = deepcopy(state.get("open_thread", {}))
        if open_thread:
            evidence_refs.append("open_thread:current")
        return {
            "mode": "topic_discovery" if not history else "conversation_followup",
            "conversation_excerpt": history[-20:],
            "memory_summary": state.get("long_term_memory", ""),
            "open_thread": open_thread,
            "relationship_context": deepcopy(state.get("relationship_state", {})),
            "character_state_summary": deepcopy(state.get("character_state", {})),
            "candidate_goal_context": deepcopy(fixture.expected),
            "evidence_refs": evidence_refs,
        }

    def _make_plan(self, fixture: InitiativeFixture, context: Mapping[str, Any], provider: Any, opportunity: PostDialogueOpportunity) -> tuple[InitiativePlan, Any]:
        method = _component_method(self.planner, ("plan", "create_plan", "generate_plan"))
        if method:
            try:
                result = method(context, expected=fixture.expected)
            except TypeError:
                result = _call_variants(method, ((context,), (fixture, context), (context, opportunity)))
            if hasattr(result, "ok") and hasattr(result, "plan"):
                if not result.ok:
                    validation_errors = list(getattr(result, "validation_errors", []) or [])
                    details = "; ".join(validation_errors)
                    raise InitiativeRunnerError(
                        details or getattr(result, "error", None) or "planner returned an invalid result",
                        stage="planner",
                        raw_output=getattr(result, "raw_output", None),
                        validation_errors=validation_errors,
                    )
                raw = getattr(result, "raw_output", None) or result.plan
                payload = result.plan or {}
            else:
                raw = result
                payload = None
        elif self.provider is not None or self.live_api:
            from .planner import Planner

            result = Planner(provider, config=self.config).plan(context, expected=fixture.expected)
            if not result.ok:
                validation_errors = list(result.validation_errors)
                details = "; ".join(validation_errors)
                raise InitiativeRunnerError(
                    details or result.error or "planner returned an invalid result",
                    stage="planner",
                    raw_output=result.raw_output,
                    validation_errors=validation_errors,
                )
            raw = result.raw_output or result.plan
            payload = result.plan or {}
        else:
            raw = _offline_plan(fixture, context)
            payload = None
        if isinstance(raw, InitiativePlan):
            return raw, raw
        if payload is None:
            payload = _parse_json(raw)
        if "plan" in payload and isinstance(payload["plan"], Mapping):
            payload = dict(payload["plan"])
        return _plan_from_payload(fixture, payload, opportunity.observed_at), raw

    def _replay_post_dialogue_events(self, fixture: InitiativeFixture, state: AgentState, plan: InitiativePlan, clock: FakeClock, provider: Any, trace: dict[str, Any]) -> tuple[ReappraisalDecision, ReappraisalContext]:
        context = ReappraisalContext()
        decision: ReappraisalDecision | None = None
        for event in fixture.post_dialogue_events:
            target = parse_event_at(event["at"], fixture.clock_start, field="post_dialogue_events.at")
            # An explicit expired event represents the expiry boundary itself;
            # do not auto-send at preferred before advancing to that boundary.
            if event["event_type"] != "expired" and plan.timing and target > plan.timing.preferred_at and clock.now() < plan.timing.preferred_at:
                clock.advance_to(plan.timing.preferred_at)
                decision = reappraise(plan, clock.now(), context)
                if decision.action == "send":
                    return decision, context
            clock.advance_to(target)
            event_type = event["event_type"]
            if event_type == "user_message":
                context = ReappraisalContext(has_new_user_message=True)
                decision = reappraise(plan, clock.now(), context)
                trace["cancelled_by_user_message"] = True
                # Complete the inserted conversation, but never create a new
                # initiative plan in this run.
                self._run_inserted_user_message(state, event, provider, trace)
                return decision, context
            if event_type == "topic_resolved":
                context = ReappraisalContext(valid_context=False)
            elif event_type == "do_not_disturb":
                context = ReappraisalContext(do_not_disturb=True)
            elif event_type == "duplicate_send":
                context = ReappraisalContext(duplicate=True)
            decision = reappraise(plan, clock.now(), context)
            trace.setdefault("event_decisions", []).append({"event": deepcopy(event), "decision": _jsonable(decision)})
            if decision.action in {"expire", "suppress"} and event_type != "advance":
                return decision, context
            if decision.action == "send":
                return decision, context
        if plan.timing and clock.now() < plan.timing.preferred_at:
            clock.advance_to(plan.timing.preferred_at)
        decision = reappraise(plan, clock.now(), context)
        return decision, context

    def _run_inserted_user_message(self, state: AgentState, event: Mapping[str, Any], provider: Any, trace: dict[str, Any]) -> None:
        content = event.get("content", event.get("message", ""))
        if not isinstance(content, str) or not content.strip():
            return
        graph = _call_variants(self.graph_builder, ((self.config,), tuple()))
        with _patched_graph_provider(provider):
            updated = graph.invoke({**state, "user_input": content})
        state.clear()
        state.update(deepcopy(updated))
        trace["state_after_competing_user_message"] = _jsonable(state)

    def _make_message(self, fixture: InitiativeFixture, context: Mapping[str, Any], plan: InitiativePlan, provider: Any) -> tuple[str, Any]:
        method = _component_method(self.generator, ("generate", "generate_message", "create_message"))
        prompt = _generator_prompt(fixture, context, plan)
        if method:
            try:
                result = method(
                    _plan_mapping(plan),
                    context,
                    decision="send",
                    expected=fixture.expected,
                )
            except TypeError:
                result = _call_variants(
                    method,
                    ((_plan_mapping(plan), context), (context, plan), (prompt,)),
                )
            if hasattr(result, "ok") and hasattr(result, "message"):
                if not result.ok:
                    details = "; ".join(getattr(result, "validation_errors", []) or [])
                    raise InitiativeRunnerError(
                        getattr(result, "error", None) or details or "generator returned an invalid result"
                    )
                raw = getattr(result, "raw_output", None) or result.message
            else:
                raw = result
        elif self.provider is not None or self.live_api:
            from .generator import Generator

            result = Generator(provider, config=self.config).generate(
                _plan_mapping(plan),
                context,
                decision="send",
                expected=fixture.expected,
            )
            if not result.ok:
                details = "; ".join(result.validation_errors or [])
                raise InitiativeRunnerError(
                    result.error or details or "generator returned an invalid result"
                )
            raw = result.raw_output or result.message
        else:
            raw = _offline_message(plan, context)
        if isinstance(raw, Mapping):
            raw = raw.get("message", raw.get("text", raw.get("line", "")))
        return (raw.strip() if isinstance(raw, str) else ""), raw

    def _evaluate(self, fixture: InitiativeFixture, context: Mapping[str, Any], plan: InitiativePlan, message: str, provider: Any) -> tuple[dict[str, Any], Any]:
        method = _component_method(self.evaluator, ("evaluate", "grade", "score"))
        prompt = _evaluator_prompt(fixture, context, plan, message)
        if method:
            try:
                result = method(
                    message,
                    _plan_mapping(plan),
                    context,
                    expected=fixture.expected,
                )
            except TypeError:
                result = _call_variants(
                    method,
                    ((context, plan, message), (plan, message), (message,)),
                )
            if hasattr(result, "rubric") and hasattr(result, "status"):
                if result.status == "error":
                    raise InitiativeRunnerError(
                        getattr(result, "error", None) or "evaluator returned an error"
                    )
                rubric = result.rubric
                if not isinstance(rubric, Mapping):
                    raise InitiativeRunnerError("evaluator returned no rubric")
                return dict(rubric), getattr(result, "raw_output", None) or rubric
            raw = result
        elif self.provider is not None or self.live_api:
            from .evaluator import Evaluator

            result = Evaluator(provider, config=self.config).evaluate(
                message,
                _plan_mapping(plan),
                context,
                expected=fixture.expected,
            )
            if result.status == "error":
                raise InitiativeRunnerError(result.error or "evaluator returned an error")
            if not isinstance(result.rubric, Mapping):
                raise InitiativeRunnerError("evaluator returned no rubric")
            return dict(result.rubric), result.raw_output or result.rubric
        else:
            raw = {"goal_alignment": 1.0, "context_grounding": 1.0, "character_consistency": 1.0, "timing_reasonableness": 1.0, "intrusiveness": 1.0, "unsupported_claims": [], "violations": [], "pass": True, "reason": "offline deterministic rubric"}
        return _parse_json(raw), raw

    def _validate_message(self, message: str, expected: Mapping[str, Any]) -> tuple[bool, str]:
        from .generator import validate_generated_text

        errors = validate_generated_text(
            message,
            plan={"message_constraints": []},
            expected=expected,
        )
        return (
            not errors,
            "non-empty plain initiative message" if not errors else "; ".join(errors),
        )

    def _validate_rubric(self, rubric: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[bool, str]:
        from .evaluator import validate_rubric

        validation_config: dict[str, float] | None = None
        if isinstance(expected.get("evaluator_min_score"), (int, float)):
            score = float(expected["evaluator_min_score"])
            validation_config = {
                key: score
                for key in (
                    "goal_alignment",
                    "context_grounding",
                    "character_consistency",
                    "timing_reasonableness",
                    "intrusiveness",
                )
            }
        errors, passed = validate_rubric(
            rubric,
            expected=expected,
            config=validation_config,
        )
        if errors:
            return False, "; ".join(errors)
        return passed, str(rubric.get("reason", "evaluator pass"))

    def _finish(self, fixture: InitiativeFixture, repetition: int, status: str, gates: list[GateResult], trace: dict[str, Any], *, plan: InitiativePlan | None = None, decision: ReappraisalDecision | None = None, message: str = "", error: str | None = None) -> InitiativeRunResult:
        started_at = trace.pop("_scenario_started_at", None)
        if isinstance(started_at, (int, float)):
            trace["scenario_elapsed_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
        if error:
            trace.setdefault("errors", []).append(error)
        trace["gates"] = [_jsonable(gate) for gate in gates]
        trace["result"] = status
        result = InitiativeRunResult(fixture.scenario_id, repetition, status, fixture.fixture_hash, message, plan, decision, gates, _log_path(), trace)
        if status == "ERROR":
            try:
                logger = importlib.import_module("agent.logger")
                logger.log_error(
                    "initiative",
                    "run_fixture",
                    RuntimeError(error or "; ".join(trace.get("errors", [])) or "initiative run failed"),
                    {"scenario_id": fixture.scenario_id, "repetition": repetition},
                )
            except Exception:
                pass
        self._write_log(result)
        return result

    def _write_log(self, result: InitiativeRunResult) -> None:
        if self.log_writer:
            self.log_writer(result.to_dict())
            return
        try:
            logger = importlib.import_module("agent.logger")
            trace = result.trace or {}
            writer = getattr(logger, "log_initiative_trace", None)
            if writer:
                writer(
                    f"{result.scenario_id}:repeat-{result.repetition}",
                    result.scenario_id,
                    trace,
                )
                return
            raw_writer = getattr(logger, "log_raw_io", None)
            if raw_writer:
                raw_writer(result.scenario_id, trace, {"result": result.status, "message": result.initiative_message, "gates": [_jsonable(gate) for gate in (result.gates or [])]})
        except Exception:
            # Logging must not change the scenario result; logger itself owns
            # the detailed error path when available.
            return


def _log_path() -> str:
    try:
        return str(importlib.import_module("agent.logger").PROMPT_MD)
    except Exception:
        return "logs/prompts.md"


def _config_model(config: AgentConfig) -> str:
    """Return the active model label without exposing credentials."""

    backend = (config.backend or "mock").lower()
    if backend == "openrouter":
        return config.openrouter_model
    if backend in {"google", "google_ai_studio", "gemini"}:
        return config.google_model
    return "mock"


def _prompt_hash(prompt: Any) -> str:
    """Hash a prompt payload for replay comparison without logging secrets."""

    canonical = json.dumps(prompt, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _call_provider_json(provider: Any, system: str, prompt: str, config: AgentConfig) -> Any:
    method = getattr(provider, "generate_json", None) or getattr(provider, "generate", None)
    if method is None:
        raise InitiativeRunnerError("provider has no JSON generation method")
    return _call_variants(method, ((system, prompt, config.temperature, 1200), (system, prompt, config.temperature), (prompt,)))


def _call_provider_text(provider: Any, system: str, prompt: str, config: AgentConfig) -> Any:
    method = getattr(provider, "generate", None)
    if method is None:
        raise InitiativeRunnerError("provider has no text generation method")
    return _call_variants(method, ((system, prompt, config.temperature, 300), (system, prompt, config.temperature), (prompt,)))


def _plan_from_payload(fixture: InitiativeFixture, payload: Mapping[str, Any], observed_at: datetime) -> InitiativePlan:
    expected = fixture.expected
    should_initiate = payload.get("should_initiate", True)
    goal = payload.get("goal")
    if not goal:
        allowed = expected.get("allowed_goals", ["silent"])
        goal = next((item for item in allowed if item != "silent"), "silent")
    try:
        goal_value = PlanGoal(goal)
    except ValueError:
        goal_value = goal  # Let deterministic contract validation report it.
    timing_data = payload.get("timing")
    timing = None
    if should_initiate and goal != "silent":
        timing_data = timing_data or {"earliest_offset_minutes": 20, "preferred_offset_minutes": 45, "expires_offset_minutes": 180}
        timing = PlanTiming(observed_at, int(timing_data.get("earliest_offset_minutes", timing_data.get("earliest", 20))), int(timing_data.get("preferred_offset_minutes", timing_data.get("preferred", 45))), int(timing_data.get("expires_offset_minutes", timing_data.get("expires", 180))))
    evidence = tuple(payload.get("evidence_refs", ["dialogue:last_user"] if fixture.dialogue else (["memory:long_term"] if fixture.initial_state.get("long_term_memory") else [])))
    topic_ref = payload.get("topic_ref") or (evidence[0] if evidence else None)
    return InitiativePlan(
        plan_id=str(payload.get("plan_id", f"{fixture.scenario_id}:{fixture.fixture_hash[:12]}")),
        scenario_id=fixture.scenario_id,
        goal=goal_value,
        topic_ref=topic_ref,
        evidence_refs=evidence,
        timing=timing,
        motive=str(payload.get("motive", "care")),
        timing_reason=str(payload.get("timing_reason", "保持低壓力並尊重對話脈絡")),
        message_constraints=tuple(payload.get("message_constraints", [])),
        should_initiate=bool(should_initiate),
        suppressed_reason=payload.get("suppressed_reason"),
    )


def _plan_mapping(plan: InitiativePlan) -> dict[str, Any]:
    """Convert the domain plan into the JSON-shaped prompt contract."""

    timing = None
    if plan.timing is not None:
        timing = {
            "observed_at": plan.timing.observed_at.isoformat(),
            "earliest_offset_minutes": plan.timing.earliest_offset_minutes,
            "preferred_offset_minutes": plan.timing.preferred_offset_minutes,
            "expires_offset_minutes": plan.timing.expires_offset_minutes,
        }
    return {
        "plan_id": plan.plan_id,
        "scenario_id": plan.scenario_id,
        "should_initiate": plan.should_initiate,
        "goal": plan.goal.value if hasattr(plan.goal, "value") else plan.goal,
        "motive": plan.motive,
        "topic_ref": plan.topic_ref,
        "evidence_refs": list(plan.evidence_refs),
        "timing": timing,
        "timing_reason": plan.timing_reason,
        "message_constraints": list(plan.message_constraints),
        "suppressed_reason": plan.suppressed_reason,
    }


def _offline_plan(fixture: InitiativeFixture, context: Mapping[str, Any]) -> dict[str, Any]:
    expected = fixture.expected
    allowed = list(expected.get("allowed_goals", ["silent"]))
    goal = next((item for item in allowed if item != "silent"), "silent")
    needs_active_plan = expected.get("reappraisal_action") in {
        "expire",
        "cancel",
        "suppress",
    }
    if not context.get("evidence_refs") or (
        expected.get("allow_send") is False and not needs_active_plan
    ):
        goal = "silent"
    if goal == "silent":
        return {"should_initiate": False, "goal": "silent", "suppressed_reason": "offline fixture silence"}
    return {"should_initiate": True, "goal": goal, "topic_ref": "dialogue:last_user" if "dialogue:last_user" in context.get("evidence_refs", []) else context["evidence_refs"][0], "evidence_refs": ["dialogue:last_user"] if "dialogue:last_user" in context.get("evidence_refs", []) else [context["evidence_refs"][0]], "timing": {"earliest_offset_minutes": 20, "preferred_offset_minutes": 45, "expires_offset_minutes": 180}}


def _offline_message(plan: InitiativePlan, context: Mapping[str, Any]) -> str:
    if plan.goal == PlanGoal.FOLLOW_UP_TOPIC:
        return "剛剛提到的事，後來有比較順利嗎？不用急著回，想到再說就好。"
    if plan.goal == PlanGoal.TOPIC_DISCOVERY:
        return "突然想到一件事，今天過得還好嗎？有空再跟我說就好。"
    return "剛剛不是說累了嗎，現在有好一點沒？不用勉強自己。"


def _planner_prompt(fixture: InitiativeFixture, context: Mapping[str, Any]) -> dict[str, str]:
    from .planner import build_planner_prompt

    system, user = build_planner_prompt(context, expected=fixture.expected)
    return {"system": system, "user": user}


def _generator_prompt(fixture: InitiativeFixture, context: Mapping[str, Any], plan: InitiativePlan) -> dict[str, str]:
    from .generator import build_generator_prompt

    system, user = build_generator_prompt(
        _plan_mapping(plan), context, expected=fixture.expected
    )
    return {"system": system, "user": user}


def _evaluator_prompt(fixture: InitiativeFixture, context: Mapping[str, Any], plan: InitiativePlan, message: str) -> dict[str, str]:
    from .evaluator import build_evaluator_prompt

    system, user = build_evaluator_prompt(
        message,
        _plan_mapping(plan),
        context,
        expected=fixture.expected,
    )
    return {"system": system, "user": user}


__all__ = ["GateResult", "InitiativeRunResult", "InitiativeRunner", "InitiativeRunnerError"]
