"""Provider execution boundary and auditable logical call ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from time import perf_counter
from typing import Any, Callable, Generic, Iterable, TypeVar


T = TypeVar("T")


class ProviderStage(str, Enum):
    DIALOGUE_RESPONSE = "dialogue_response"
    CANDIDATE_SCAN = "candidate_scan"
    CANDIDATE_CONSOLIDATION = "candidate_consolidation"
    REAPPRAISAL = "reappraisal"
    GENERATOR = "generator"


class ValidationStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True)
class ProviderCallEntry:
    call_id: str
    stage: ProviderStage
    attempt: int
    provider: str
    model: str
    started_at: str
    elapsed_ms: int
    response_received: bool
    validation_status: ValidationStatus
    validation_errors: tuple[str, ...]
    prompt_hash: str | None = None
    raw_response: str | None = None


@dataclass(frozen=True)
class ProviderCallResult(Generic[T]):
    value: T
    raw_response: str
    entry: ProviderCallEntry
    entries: tuple[ProviderCallEntry, ...]


class ProviderCallError(RuntimeError):
    def __init__(self, message: str, entries: Iterable[ProviderCallEntry]) -> None:
        self.entries = tuple(entries)
        super().__init__(message)


def _stage(value: ProviderStage | str) -> ProviderStage:
    try:
        return value if isinstance(value, ProviderStage) else ProviderStage(value)
    except ValueError as exc:
        raise ValueError(f"unsupported provider stage: {value!r}") from exc


def _provider_name(provider: object) -> str:
    return type(provider).__name__


def _provider_model(provider: object) -> str:
    value = getattr(provider, "model", None)
    return str(value) if value else "unknown"


def _errors(exc: Exception) -> tuple[str, ...]:
    values = getattr(exc, "errors", None)
    if isinstance(values, (list, tuple)):
        return tuple(str(item) for item in values)
    return (str(exc),)


class ExternalCallTracker:
    """Context manager for provider calls owned by a higher-level pipeline.

    The adapter wrapping the real execution point must explicitly accept or
    reject the returned value.  Exiting without either is recorded as an error.
    """

    def __init__(
        self,
        ledger: "ProviderCallLedger",
        stage: ProviderStage,
        provider: object,
        call_id: str,
        prompt_hash: str | None,
    ) -> None:
        self._ledger = ledger
        self.stage = stage
        self.provider = provider
        self.call_id = call_id
        self.prompt_hash = prompt_hash
        self.started_at = datetime.now(timezone.utc)
        self._started_perf = 0.0
        self._completed = False

    def __enter__(self) -> "ExternalCallTracker":
        self._started_perf = perf_counter()
        return self

    def _append(
        self,
        status: ValidationStatus,
        *,
        raw_response: str | None,
        validation_errors: Iterable[str] = (),
        response_received: bool | None = None,
    ) -> ProviderCallEntry:
        if self._completed:
            raise RuntimeError("external provider call was already recorded")
        entry = ProviderCallEntry(
            call_id=self.call_id,
            stage=self.stage,
            attempt=1,
            provider=_provider_name(self.provider),
            model=_provider_model(self.provider),
            started_at=self.started_at.isoformat(),
            elapsed_ms=max(0, round((perf_counter() - self._started_perf) * 1000)),
            response_received=(raw_response is not None if response_received is None else response_received),
            validation_status=status,
            validation_errors=tuple(str(item) for item in validation_errors),
            prompt_hash=self.prompt_hash,
            raw_response=raw_response,
        )
        self._ledger._append(entry)
        self._completed = True
        return entry

    def accept(self, raw_response: str) -> ProviderCallEntry:
        if not isinstance(raw_response, str) or not raw_response.strip():
            return self.reject(raw_response, ("response is empty",))
        return self._append(ValidationStatus.ACCEPTED, raw_response=raw_response)

    def reject(self, raw_response: str | None, validation_errors: Iterable[str]) -> ProviderCallEntry:
        return self._append(
            ValidationStatus.REJECTED,
            raw_response=raw_response,
            validation_errors=validation_errors,
        )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._completed:
            return False
        if isinstance(exc, Exception):
            self._append(
                ValidationStatus.ERROR,
                raw_response=None,
                validation_errors=(f"{type(exc).__name__}: {exc}",),
                response_received=False,
            )
        else:
            self._append(
                ValidationStatus.ERROR,
                raw_response=None,
                validation_errors=("external provider call exited without validation",),
                response_received=False,
            )
        return False


class ProviderCallLedger:
    """Records attempts only at actual provider execution boundaries."""

    def __init__(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id is required")
        self.run_id = run_id.strip()
        self._entries: list[ProviderCallEntry] = []
        self._stage_counts: dict[ProviderStage, int] = {}

    @property
    def entries(self) -> tuple[ProviderCallEntry, ...]:
        return tuple(self._entries)

    def _append(self, entry: ProviderCallEntry) -> None:
        self._entries.append(entry)

    def _next_call_id(self, stage: ProviderStage) -> str:
        count = self._stage_counts.get(stage, 0) + 1
        self._stage_counts[stage] = count
        return f"{self.run_id}:{stage.value}:{count}"

    def track(
        self,
        stage: ProviderStage | str,
        provider: object,
        *,
        prompt_hash: str | None = None,
    ) -> ExternalCallTracker:
        selected = _stage(stage)
        return ExternalCallTracker(
            self, selected, provider, self._next_call_id(selected), prompt_hash
        )

    def call_json(
        self,
        stage: ProviderStage | str,
        provider: object,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        validator: Callable[[str], T],
    ) -> ProviderCallResult[T]:
        return self._call(
            stage, provider, system_prompt, user_prompt, temperature,
            max_output_tokens, validator, json_mode=True, allow_correction=True,
        )

    def call_text(
        self,
        stage: ProviderStage | str,
        provider: object,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        validator: Callable[[str], T],
    ) -> ProviderCallResult[T]:
        return self._call(
            stage, provider, system_prompt, user_prompt, temperature,
            max_output_tokens, validator, json_mode=False, allow_correction=False,
        )

    def _call(
        self,
        stage: ProviderStage | str,
        provider: object,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        validator: Callable[[str], T],
        *,
        json_mode: bool,
        allow_correction: bool,
    ) -> ProviderCallResult[T]:
        selected = _stage(stage)
        call_id = self._next_call_id(selected)
        method_name = "generate_json" if json_mode else "generate"
        method = getattr(provider, method_name, None)
        if not callable(method):
            raise ProviderCallError(
                f"provider does not implement {method_name}",
                self._record_missing_method(call_id, selected, provider, method_name),
            )
        active_prompt = user_prompt
        call_entries: list[ProviderCallEntry] = []
        for attempt in range(1, 3 if allow_correction else 2):
            started_at = datetime.now(timezone.utc)
            started_perf = perf_counter()
            prompt_hash = "sha256:" + hashlib.sha256(
                f"{system_prompt}\n{active_prompt}".encode("utf-8")
            ).hexdigest()
            raw: str | None = None
            try:
                raw = method(system_prompt, active_prompt, temperature, max_output_tokens)
            except Exception as exc:
                entry = self._entry(
                    call_id, selected, attempt, provider, started_at, started_perf,
                    ValidationStatus.ERROR, False, (f"{type(exc).__name__}: {exc}",),
                    prompt_hash, None,
                )
                call_entries.append(entry)
                raise ProviderCallError("provider call failed", call_entries) from exc
            try:
                if not isinstance(raw, str) or not raw.strip():
                    raise ValueError("provider returned an empty response")
                value = validator(raw)
            except Exception as exc:
                validation_errors = _errors(exc)
                entry = self._entry(
                    call_id, selected, attempt, provider, started_at, started_perf,
                    ValidationStatus.REJECTED, isinstance(raw, str), validation_errors,
                    prompt_hash, raw if isinstance(raw, str) else None,
                )
                call_entries.append(entry)
                if not allow_correction or attempt == 2:
                    raise ProviderCallError("provider output failed validation", call_entries) from exc
                active_prompt = json.dumps(
                    {
                        "original_request": user_prompt,
                        "previous_output": raw,
                        "validation_errors": list(validation_errors),
                        "instruction": "Correct every error and return one complete JSON object only.",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                continue
            entry = self._entry(
                call_id, selected, attempt, provider, started_at, started_perf,
                ValidationStatus.ACCEPTED, True, (), prompt_hash, raw,
            )
            call_entries.append(entry)
            return ProviderCallResult(value, raw, entry, tuple(call_entries))
        raise AssertionError("provider call loop exhausted unexpectedly")

    def _entry(
        self,
        call_id: str,
        stage: ProviderStage,
        attempt: int,
        provider: object,
        started_at: datetime,
        started_perf: float,
        status: ValidationStatus,
        response_received: bool,
        validation_errors: tuple[str, ...],
        prompt_hash: str | None,
        raw_response: str | None,
    ) -> ProviderCallEntry:
        entry = ProviderCallEntry(
            call_id, stage, attempt, _provider_name(provider), _provider_model(provider),
            started_at.isoformat(), max(0, round((perf_counter() - started_perf) * 1000)),
            response_received, status, validation_errors, prompt_hash, raw_response,
        )
        self._append(entry)
        return entry

    def _record_missing_method(
        self, call_id: str, stage: ProviderStage, provider: object, method_name: str
    ) -> tuple[ProviderCallEntry, ...]:
        now = datetime.now(timezone.utc)
        entry = ProviderCallEntry(
            call_id, stage, 1, _provider_name(provider), _provider_model(provider),
            now.isoformat(), 0, False, ValidationStatus.ERROR,
            (f"provider does not implement {method_name}",),
        )
        self._append(entry)
        return (entry,)


__all__ = [
    "ExternalCallTracker", "ProviderCallEntry", "ProviderCallError", "ProviderCallLedger",
    "ProviderCallResult", "ProviderStage", "ValidationStatus",
]
