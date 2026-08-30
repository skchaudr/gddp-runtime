"""Canonical executor event vocabulary (v1).

One observable execution world regardless of transport: each thin driver
translates its harness's native stream into these records, and GDDP-owned
code (context coverage, usage extraction, watch surfaces) consumes only this
vocabulary — never provider event names.

Design doc: docs/proposals/executor-event-vocabulary.md.

Spool layout per attempt dir:
  events.jsonl — canonical events, one JSON object per line, append-only
  raw.jsonl    — verbatim harness output for forensics and tail -F

Every event carries the envelope: v, ts (ISO-8601 UTC, driver-stamped),
executor, session_id, turn_id, seq (monotonic within one turn), type,
raw_type (harness type, forensics only).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

EXECUTOR_EVENT_VERSION = 1

EventType = Literal[
    "session_started",
    "turn_started",
    "assistant_message",
    "tool_started",
    "tool_completed",
    "usage",
    "turn_ended",
]

TurnStatus = Literal["completed", "failed", "cancelled"]

# Canonical tool names use the pi spellings already load-bearing in the
# existing spools and in coverage. Drivers map harness spellings onto these
# (cursor: readToolCall -> read, shellToolCall -> bash, editToolCall ->
# write|edit disambiguated by call_id prefix — see events_cursor_cli.py).
# Unknown tools pass through as their lowercased raw stem; raw_type keeps
# the original for forensics.
CONTENT_TOOLS = frozenset({"read", "grep"})
WRITE_TOOLS = frozenset({"write", "edit"})
KNOWN_TOOLS = CONTENT_TOOLS | WRITE_TOOLS | frozenset(
    {"bash", "ls", "find", "subagent"}
)


@dataclass(frozen=True)
class TurnUsage:
    """Normalized usage, whatever the provider called it.

    scope="message" for per-model-call usage (pi message_end), scope="turn"
    for one terminal usage per turn (cursor result event). Never sum across
    scopes.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost: float | None = None
    scope: Literal["message", "turn"] = "turn"


@dataclass(frozen=True)
class ExecutorEvent:
    """One canonical event. Which optional fields are set depends on type:

    session_started:  model, resume_token
    turn_started:     (envelope only)
    assistant_message: text, role — final text only, never deltas
    tool_started:     call_id, tool, paths, command
    tool_completed:   call_id, tool, paths, ok, error, duration_ms
                      (self-contained: carries tool/paths again so coverage
                      is a one-pass filter with no start/end join)
    usage:            usage (TurnUsage)
    turn_ended:       status, error, stop_reason, warning — driver-synthesized
                      when the harness emits no terminal event (kill, bad
                      args). warning records a termination-boundary crash
                      after completed work; it does not flip status.
    """

    type: EventType
    executor: str
    session_id: str
    turn_id: str
    seq: int
    ts: str
    raw_type: str = ""
    v: int = EXECUTOR_EVENT_VERSION
    model: str | None = None
    resume_token: str | None = None
    text: str | None = None
    role: str | None = None
    call_id: str | None = None
    tool: str | None = None
    paths: tuple[str, ...] = ()
    command: str | None = None
    ok: bool | None = None
    duration_ms: int | None = None
    usage: TurnUsage | None = None
    status: TurnStatus | None = None
    error: str | None = None
    stop_reason: str | None = None
    warning: str | None = None

    def to_json_value(self) -> dict[str, object]:
        """Envelope-first dict; unset optional fields are omitted."""
        out: dict[str, object] = {
            "v": self.v,
            "ts": self.ts,
            "executor": self.executor,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "seq": self.seq,
            "type": self.type,
            "raw_type": self.raw_type,
        }
        for key in (
            "model",
            "resume_token",
            "text",
            "role",
            "call_id",
            "tool",
            "command",
            "ok",
            "duration_ms",
            "status",
            "error",
            "stop_reason",
            "warning",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.paths:
            out["paths"] = list(self.paths)
        if self.usage is not None:
            out["usage"] = {
                k: v
                for k, v in {
                    "input": self.usage.input_tokens,
                    "output": self.usage.output_tokens,
                    "cache_read": self.usage.cached_input_tokens,
                    "cache_write": self.usage.cache_write_tokens,
                    "cost": self.usage.cost,
                    "scope": self.usage.scope,
                }.items()
                if v is not None
            }
        return out

    @classmethod
    def from_json_value(cls, data: dict[str, object]) -> ExecutorEvent:
        """Parse one canonical line. Tolerant of unknown fields (forward
        compat); missing fields take defaults."""
        known = {
            "v",
            "ts",
            "executor",
            "session_id",
            "turn_id",
            "seq",
            "type",
            "raw_type",
            "model",
            "resume_token",
            "text",
            "role",
            "call_id",
            "tool",
            "paths",
            "command",
            "ok",
            "duration_ms",
            "usage",
            "status",
            "error",
            "stop_reason",
            "warning",
        }
        kwargs: dict[str, object] = {
            key: value for key, value in data.items() if key in known
        }
        if "paths" in kwargs:
            kwargs["paths"] = tuple(str(p) for p in kwargs["paths"])  # type: ignore[union-attr]
        usage = kwargs.get("usage")
        if isinstance(usage, dict):
            kwargs["usage"] = TurnUsage(
                input_tokens=usage.get("input"),  # type: ignore[arg-type]
                output_tokens=usage.get("output"),  # type: ignore[arg-type]
                cached_input_tokens=usage.get("cache_read"),  # type: ignore[arg-type]
                cache_write_tokens=usage.get("cache_write"),  # type: ignore[arg-type]
                cost=usage.get("cost"),  # type: ignore[arg-type]
                scope=usage.get("scope", "turn"),  # type: ignore[arg-type]
            )
        return cls(**kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True)
class TranslatedEvent:
    """One canonical event minus the envelope the writer stamps.

    What every per-transport translator returns. Keeping it here rather than
    in one driver means a second driver does not import the first one just to
    borrow its return type.
    """

    type: EventType
    raw_type: str
    fields: Mapping[str, object] = field(default_factory=dict)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class EventWriter:
    """Appends canonical events to an attempt dir's events.jsonl.

    Owns the per-turn seq counter. raw() appends a verbatim harness line to
    the sibling raw.jsonl. Both files are append-only.
    """

    def __init__(
        self,
        attempt_dir: Path,
        *,
        executor: str,
        session_id: str,
        turn_id: str,
    ) -> None:
        self._events_path = attempt_dir / "events.jsonl"
        self._raw_path = attempt_dir / "raw.jsonl"
        self._executor = executor
        self._session_id = session_id
        self._turn_id = turn_id
        self._seq = 0

    @property
    def events_path(self) -> Path:
        return self._events_path

    def emit(self, type: EventType, *, raw_type: str = "", **fields: object) -> ExecutorEvent:
        self._seq += 1
        event = ExecutorEvent(
            type=type,
            executor=self._executor,
            session_id=self._session_id,
            turn_id=self._turn_id,
            seq=self._seq,
            ts=_utc_now_iso(),
            raw_type=raw_type,
            **fields,  # type: ignore[arg-type]
        )
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(event.to_json_value(), separators=(",", ":")) + "\n"
            )
        return event

    def raw(self, line: str) -> None:
        with self._raw_path.open("a", encoding="utf-8") as handle:
            handle.write(line if line.endswith("\n") else line + "\n")


def read_events(events_path: Path) -> list[ExecutorEvent]:
    """Read a canonical events.jsonl. Missing file reads as zero events."""
    if not events_path.exists():
        return []
    events: list[ExecutorEvent] = []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(ExecutorEvent.from_json_value(json.loads(line)))
    return events


def turn_usage(events: list[ExecutorEvent]) -> TurnUsage | None:
    """One TurnUsage for a turn from canonical events.

    Prefers a scope="turn" record (cursor's shape); otherwise sums
    scope="message" records (pi's shape). None when no usage was reported —
    absent evidence, never a fabricated zero.
    """
    turn_scoped = [
        e.usage
        for e in events
        if e.type == "usage" and e.usage is not None and e.usage.scope == "turn"
    ]
    if turn_scoped:
        return turn_scoped[-1]
    message_scoped = [
        e.usage
        for e in events
        if e.type == "usage" and e.usage is not None and e.usage.scope == "message"
    ]
    if not message_scoped:
        return None

    def _sum(attr: str) -> int | float | None:
        values = [getattr(u, attr) for u in message_scoped]
        present = [v for v in values if v is not None]
        if not present:
            return None
        return sum(present)

    return TurnUsage(
        input_tokens=_sum("input_tokens"),  # type: ignore[arg-type]
        output_tokens=_sum("output_tokens"),  # type: ignore[arg-type]
        cached_input_tokens=_sum("cached_input_tokens"),  # type: ignore[arg-type]
        cache_write_tokens=_sum("cache_write_tokens"),  # type: ignore[arg-type]
        cost=_sum("cost"),  # type: ignore[arg-type]
        scope="message",
    )
