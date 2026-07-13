"""Self-contained fixture loading for the initiative replay harness."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from agent.config import AgentConfig
from agent.state import AgentState, initial_state


class FixtureError(ValueError):
    """Raised when an initiative fixture is incomplete or ambiguous."""


_OFFSET_RE = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$")
_REQUIRED_KEYS = {
    "scenario_id",
    "description",
    "clock_start",
    "timezone",
    "seed",
    "initial_state",
    "dialogue",
    "post_dialogue_events",
    "expected",
}


def _parse_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise FixtureError(f"{field} must be an ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixtureError(f"{field} is not a valid ISO datetime: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixtureError(f"{field} must be timezone-aware")
    return parsed


def parse_event_at(value: Any, clock_start: datetime, *, field: str) -> datetime:
    """Resolve an ISO timestamp or ``+HH:MM`` fixture offset."""

    if isinstance(value, str):
        match = _OFFSET_RE.match(value)
        if match:
            delta = timedelta(
                hours=int(match.group("hours")), minutes=int(match.group("minutes"))
            )
            return clock_start + (delta if match.group("sign") == "+" else -delta)
    return _parse_datetime(value, field=field)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class InitiativeFixture:
    """Validated fixture with a fresh canonical state for every load."""

    scenario_id: str
    description: str
    clock_start: datetime
    timezone: str
    seed: int
    initial_state: AgentState
    dialogue: tuple[dict[str, Any], ...]
    post_dialogue_events: tuple[dict[str, Any], ...]
    expected: dict[str, Any]
    fixture_hash: str
    source_path: Path | None = None

    def fresh_state(self) -> AgentState:
        """Return an isolated state; no mutable object is shared between runs."""

        return deepcopy(self.initial_state)

    @property
    def hash(self) -> str:
        return self.fixture_hash


def _normalize_dialogue(
    entries: Any, clock_start: datetime, *, field: str = "dialogue"
) -> tuple[dict[str, Any], ...]:
    if not isinstance(entries, list):
        raise FixtureError(f"{field} must be a list")
    normalized: list[dict[str, Any]] = []
    previous = clock_start
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping):
            raise FixtureError(f"{field}[{index}] must be an object")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            raise FixtureError(f"{field}[{index}].role must be user or assistant")
        if not isinstance(content, str) or not content.strip():
            raise FixtureError(f"{field}[{index}].content must be non-empty text")
        at = parse_event_at(item.get("at"), clock_start, field=f"{field}[{index}].at")
        if at < previous:
            raise FixtureError(f"{field} must be ordered by at")
        previous = at
        normalized.append({"at": at.isoformat(), "role": role, "content": content})
    return tuple(normalized)


def _normalize_events(entries: Any, clock_start: datetime) -> tuple[dict[str, Any], ...]:
    if not isinstance(entries, list):
        raise FixtureError("post_dialogue_events must be a list")
    normalized: list[dict[str, Any]] = []
    previous = clock_start
    allowed = {
        "user_message",
        "advance",
        "expired",
        "topic_resolved",
        "do_not_disturb",
        "duplicate_send",
    }
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping):
            raise FixtureError(f"post_dialogue_events[{index}] must be an object")
        event_type = item.get("event_type", item.get("type"))
        if event_type not in allowed:
            raise FixtureError(
                f"post_dialogue_events[{index}].event_type must be one of {sorted(allowed)}"
            )
        raw_at = item.get("at")
        if raw_at is None and "minutes" in item:
            raw_at = f"+{int(item['minutes']) // 60:02d}:{int(item['minutes']) % 60:02d}"
        if raw_at is None:
            raise FixtureError(f"post_dialogue_events[{index}] requires at or minutes")
        at = parse_event_at(raw_at, clock_start, field=f"post_dialogue_events[{index}].at")
        if at < previous:
            raise FixtureError("post_dialogue_events must be ordered by at")
        previous = at
        normalized_item = deepcopy(dict(item))
        normalized_item["event_type"] = event_type
        normalized_item["at"] = at.isoformat()
        normalized.append(normalized_item)
    return tuple(normalized)


def _validate_raw(raw: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_KEYS - set(raw))
    if missing:
        raise FixtureError(f"fixture missing required keys: {', '.join(missing)}")
    if not isinstance(raw["scenario_id"], str) or not raw["scenario_id"].strip():
        raise FixtureError("scenario_id must be non-empty text")
    if not isinstance(raw["timezone"], str) or not raw["timezone"].strip():
        raise FixtureError("timezone must be non-empty text")
    if isinstance(raw["seed"], bool) or not isinstance(raw["seed"], int):
        raise FixtureError("seed must be an integer")
    if not isinstance(raw["initial_state"], Mapping):
        raise FixtureError("initial_state must be an object")
    if not isinstance(raw["expected"], Mapping):
        raise FixtureError("expected must be an object")


def fixture_from_mapping(
    raw: Mapping[str, Any], *, config: AgentConfig | None = None, source_path: Path | None = None
) -> InitiativeFixture:
    """Validate and materialize one fixture from JSON-compatible data."""

    _validate_raw(raw)
    config = config or AgentConfig()
    clock_start = _parse_datetime(raw["clock_start"], field="clock_start")

    # Hash the normalized input, before adding canonical state, so the hash is
    # stable across machines while still identifying the complete fixture file.
    raw_copy = deepcopy(dict(raw))
    fixture_hash = hashlib.sha256(_canonical_json(raw_copy).encode("utf-8")).hexdigest()
    canonical = initial_state(config)
    merged_state = _deep_merge(canonical, raw["initial_state"])
    merged_state["conversation_history"] = deepcopy(
        merged_state.get("conversation_history", [])
    )

    return InitiativeFixture(
        scenario_id=raw["scenario_id"].strip(),
        description=str(raw["description"]),
        clock_start=clock_start,
        timezone=raw["timezone"],
        seed=raw["seed"],
        initial_state=merged_state,
        dialogue=_normalize_dialogue(raw["dialogue"], clock_start),
        post_dialogue_events=_normalize_events(raw["post_dialogue_events"], clock_start),
        expected=deepcopy(dict(raw["expected"])),
        fixture_hash=fixture_hash,
        source_path=source_path,
    )


def load_fixture(
    path: str | Path, *, config: AgentConfig | None = None
) -> InitiativeFixture:
    fixture_path = Path(path)
    try:
        with fixture_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureError(f"unable to load fixture {fixture_path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise FixtureError(f"fixture root must be an object: {fixture_path}")
    return fixture_from_mapping(raw, config=config, source_path=fixture_path)


def load_fixtures(
    directory: str | Path, *, config: AgentConfig | None = None
) -> list[InitiativeFixture]:
    directory_path = Path(directory)
    fixtures = [
        load_fixture(path, config=config)
        for path in sorted(directory_path.glob("*.json"))
    ]
    if not fixtures:
        raise FixtureError(f"no initiative fixtures found in {directory_path}")
    return fixtures


__all__ = [
    "FixtureError",
    "InitiativeFixture",
    "fixture_from_mapping",
    "load_fixture",
    "load_fixtures",
    "parse_event_at",
]
