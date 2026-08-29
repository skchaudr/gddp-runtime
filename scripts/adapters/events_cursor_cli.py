"""cursor-agent stream-json -> canonical ExecutorEvent translation.

The only place cursor's provider event names appear. Pure: no clock, no IO,
no envelope — the driver's EventWriter owns ts/seq/session_id/turn_id, so
this module emits ``TranslatedEvent`` (type + raw_type + type-specific
fields) and the driver hands each one straight to ``EventWriter.emit``. That
keeps the translator testable against recorded fixtures with no live binary
and no filesystem.

Ground truth, and the only ground truth (AGENTS.md: never design around an
unmeasured behavior):
  scripts/runtime/spike/cursor_cli_spike_results.json      — 7 turns
  scripts/runtime/spike/cursor_tool_probe_results.json     — write/edit/grep/
                                                             shell/read +
                                                             a failing read

Mapping table: docs/proposals/executor-event-vocabulary.md §5.2.

Not this module's job: the no-events/non-zero-exit case and the SIGTERM/
SIGKILL case. Both produce NO terminal cursor event at all
(cursor_cli_spike_results.json: `invalid_model` has zero stream events,
`sigterm_mid_turn`/`sigkill_mid_turn` have `result_event: null`), so the
turn_ended for them is synthesized by the driver from the return code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from adapters.executor_events import EventType, ExecutorEvent, TurnUsage

# Canonical tool names are the pi spellings already load-bearing in coverage
# and in 72 existing spools; cursor's spellings map onto them.
#
# Probe-verified (cursor_tool_probe_results.json derived_facts):
#   readToolCall  -> read     grepToolCall  -> grep    shellToolCall -> bash
#   editToolCall  -> write when the call_id starts "Write_" (file creation)
#                 -> edit  when it starts "StrReplace_" (in-place edit)
# Both write and edit arrive as editToolCall; the call_id prefix is the only
# observed discriminator. An editToolCall with neither prefix stays "edit" —
# the tool key's own claim — rather than being guessed into "write".
_TOOL_KEY_NAMES = {
    "readtoolcall": "read",
    "greptoolcall": "grep",
    "shelltoolcall": "bash",
    "lstoolcall": "ls",
    "findtoolcall": "find",
}
_EDIT_CALL_ID_PREFIXES = (("write_", "write"), ("strreplace_", "edit"))


def canonical_tool_name(tool_key: str, call_id: str) -> str:
    """Canonical tool name for one cursor ``<name>ToolCall`` key.

    Unknown keys pass through as their lowercased stem (``fooToolCall`` ->
    ``foo``) rather than being dropped: an unmapped tool must still be
    visible in the spool, and only read/grep are load-bearing for coverage.
    """
    stem = tool_key[: -len("ToolCall")] if tool_key.endswith("ToolCall") else tool_key
    lowered = stem.lower()
    if lowered == "edit":
        lowered_call_id = (call_id or "").lower()
        for prefix, name in _EDIT_CALL_ID_PREFIXES:
            if lowered_call_id.startswith(prefix):
                return name
        return "edit"
    return _TOOL_KEY_NAMES.get(f"{lowered}toolcall", lowered)


@dataclass(frozen=True)
class TranslatedEvent:
    """One canonical event minus the envelope the writer stamps."""

    type: EventType
    raw_type: str
    fields: Mapping[str, object] = field(default_factory=dict)


def _tool_body(raw: Mapping[str, object]) -> tuple[str, Mapping[str, object]]:
    """Return (tool_key, body) for a tool_call event, or ("", {})."""
    call = raw.get("tool_call")
    if not isinstance(call, Mapping):
        return "", {}
    for key, value in call.items():
        if key.endswith("ToolCall") and isinstance(value, Mapping):
            return key, value
    return "", {}


def _paths_from_args(args: Mapping[str, object] | None) -> tuple[str, ...]:
    """Paths a tool call names, as the harness reported them.

    Observed arg shapes carry at most one ``path`` (read/grep/edit); shell
    carries ``command`` and no path. Resolution against a base is the
    consumer's job, so nothing is normalized here.
    """
    if not isinstance(args, Mapping):
        return ()
    path = args.get("path")
    if isinstance(path, str) and path:
        return (path,)
    return ()


def _command_from_args(args: Mapping[str, object] | None) -> str | None:
    if not isinstance(args, Mapping):
        return None
    command = args.get("command")
    return command if isinstance(command, str) and command else None


def _duration_ms(raw_call: Mapping[str, object]) -> int | None:
    started = raw_call.get("startedAtMs")
    completed = raw_call.get("completedAtMs")
    try:
        return int(completed) - int(started)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _outcome(result: object) -> tuple[bool, str | None]:
    """(ok, error) from a cursor tool result.

    Probe-verified: a success body sits under the ``success`` key, a failure
    under ``error`` carrying ``errorMessage``. A completed call with neither
    key (never observed) counts as success, which is the same default pi's
    extraction takes for an end event with no ``isError`` — coverage must
    rate identically on both transports.
    """
    if not isinstance(result, Mapping):
        return True, None
    error = result.get("error")
    if error is not None:
        message = None
        if isinstance(error, Mapping):
            raw_message = error.get("errorMessage")
            message = raw_message if isinstance(raw_message, str) else None
        elif isinstance(error, str):
            message = error
        return False, message or "tool call failed"
    return True, None


def _assistant_text(raw: Mapping[str, object]) -> str:
    message = raw.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(
        part.get("text", "")
        for part in content
        if isinstance(part, Mapping) and isinstance(part.get("text"), str)
    )


class CursorStreamTranslator:
    """Incremental cursor stream-json -> canonical events.

    Holds two pieces of per-turn state:

    1. ``call_id -> (tool, paths, command)`` captured from ``tool_call``
       ``started``. The probe proved a FAILED call's ``completed`` event
       carries no args at all (``cursor_tool_probe_results.json``
       derived_facts.failing_completed_drops_args), so without this buffer a
       failed read would emit a ``tool_completed`` with no path and the
       self-contained-completion contract would break exactly where it
       matters most.
    2. The assistant text buffer. ``--stream-partial-output`` streams partial
       and final content on the same ``assistant`` type with no observed
       discriminator field, and naive concatenation doubles the output
       ("SPIKE7-COLDSPIKE7-COLD", cursor_cli_spike_results.json:13). Measured
       across every spike turn, the partials are DELTAS and the final event
       repeats the whole message, so an event whose text equals the buffer so
       far is a re-emission and is dropped. One ``assistant_message`` is
       emitted per message: flushed when the model stops talking to act (a
       tool call) and again at the turn boundary — never per delta.
    """

    def __init__(self) -> None:
        self._calls: dict[str, tuple[str, tuple[str, ...], str | None]] = {}
        self._text = ""
        self.session_id: str | None = None
        self.model: str | None = None
        self.saw_turn_end = False

    def translate(self, raw: object) -> list[TranslatedEvent]:
        """Translate one decoded stream-json line. Unknown types yield []."""
        if not isinstance(raw, Mapping):
            return []
        raw_type = str(raw.get("type") or "")
        subtype = raw.get("subtype")
        label = f"{raw_type}/{subtype}" if subtype else raw_type

        if raw_type == "system" and subtype == "init":
            return self._session_started(raw, label)
        if raw_type == "assistant":
            self._absorb_text(_assistant_text(raw))
            return []
        if raw_type == "tool_call":
            return self._tool_call(raw, str(subtype or ""), label)
        if raw_type == "result":
            return self._result(raw, label)
        # user echo, thinking deltas: dropped from the canonical spool, kept
        # verbatim in raw.jsonl.
        return []

    def flush_text(self, raw_type: str = "") -> list[TranslatedEvent]:
        """Emit the buffered assistant message, if any, and clear it."""
        text = self._text
        self._text = ""
        if not text:
            return []
        return [
            TranslatedEvent(
                type="assistant_message",
                raw_type=raw_type or "assistant",
                fields={"text": text, "role": "assistant"},
            )
        ]

    def _absorb_text(self, text: str) -> None:
        if not text:
            return
        if text == self._text:
            # Final re-emission of the whole message; appending doubles it.
            return
        self._text += text

    def _session_started(
        self, raw: Mapping[str, object], label: str
    ) -> list[TranslatedEvent]:
        session_id = raw.get("session_id")
        model = raw.get("model")
        self.session_id = session_id if isinstance(session_id, str) else None
        self.model = model if isinstance(model, str) else None
        return [
            TranslatedEvent(
                type="session_started",
                raw_type=label,
                fields={
                    # The same value serves --resume; cursor has no separate
                    # resume handle (cursor_cli_spike.py:77).
                    "model": self.model,
                    "resume_token": self.session_id,
                },
            )
        ]

    def _tool_call(
        self, raw: Mapping[str, object], subtype: str, label: str
    ) -> list[TranslatedEvent]:
        call_id = raw.get("call_id")
        call_id = call_id if isinstance(call_id, str) else ""
        tool_key, body = _tool_body(raw)
        if not tool_key:
            return []
        tool = canonical_tool_name(tool_key, call_id)
        args = body.get("args")
        paths = _paths_from_args(args if isinstance(args, Mapping) else None)
        command = _command_from_args(args if isinstance(args, Mapping) else None)

        if subtype == "started":
            self._calls[call_id] = (tool, paths, command)
            events = self.flush_text()
            events.append(
                TranslatedEvent(
                    type="tool_started",
                    raw_type=label,
                    fields={
                        "call_id": call_id,
                        "tool": tool,
                        "paths": paths,
                        "command": command,
                    },
                )
            )
            return events

        if subtype != "completed":
            return []

        buffered = self._calls.pop(call_id, None)
        if buffered is not None:
            buffered_tool, buffered_paths, buffered_command = buffered
            # The failed-read probe shows args can vanish from completed;
            # the started event is the durable source for tool and paths.
            paths = paths or buffered_paths
            command = command or buffered_command
            if not args:
                tool = buffered_tool
        ok, error = _outcome(body.get("result"))
        raw_call = raw.get("tool_call")
        duration = (
            _duration_ms(raw_call) if isinstance(raw_call, Mapping) else None
        )
        return [
            TranslatedEvent(
                type="tool_completed",
                raw_type=label,
                fields={
                    "call_id": call_id,
                    "tool": tool,
                    "paths": paths,
                    "command": command,
                    "ok": ok,
                    "error": error,
                    "duration_ms": duration,
                },
            )
        ]

    def _result(
        self, raw: Mapping[str, object], label: str
    ) -> list[TranslatedEvent]:
        self.saw_turn_end = True
        session_id = raw.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
        is_error = bool(raw.get("is_error"))
        result_text = raw.get("result")
        if not self._text and isinstance(result_text, str) and result_text:
            # Some turns emit no assistant events at all; the terminal event
            # still carries the turn's final text.
            self._text = result_text
        events = self.flush_text(label)

        usage = raw.get("usage")
        if isinstance(usage, Mapping):
            events.append(
                TranslatedEvent(
                    type="usage",
                    raw_type=label,
                    fields={
                        "usage": TurnUsage(
                            input_tokens=_int_or_none(usage.get("inputTokens")),
                            output_tokens=_int_or_none(usage.get("outputTokens")),
                            # Lane 1 finding 5: cacheReadTokens is absent from
                            # prompt_topology's provider key list, so an
                            # un-normalized cursor stream silently reports no
                            # cache at all. Normalizing here is the fix.
                            cached_input_tokens=_int_or_none(
                                usage.get("cacheReadTokens")
                            ),
                            cache_write_tokens=_int_or_none(
                                usage.get("cacheWriteTokens")
                            ),
                            # Cursor reports usage once, terminally. Never
                            # summed with pi's per-message records.
                            scope="turn",
                        )
                    },
                )
            )

        events.append(
            TranslatedEvent(
                type="turn_ended",
                raw_type=label,
                fields={
                    "status": "failed" if is_error else "completed",
                    "error": (
                        str(result_text)
                        if is_error and result_text is not None
                        else None
                    ),
                    "stop_reason": str(raw.get("subtype") or "") or None,
                    "duration_ms": _int_or_none(raw.get("duration_ms")),
                },
            )
        )
        return events


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def translate_stream(
    lines: Sequence[object],
    *,
    executor: str = "cursor_cli",
    session_id: str = "",
    turn_id: str = "turn",
    ts: str = "1970-01-01T00:00:00.000Z",
) -> list[ExecutorEvent]:
    """Translate a whole recorded stream into stamped canonical events.

    Fixture/replay convenience: the live driver stamps the envelope through
    EventWriter (which owns the real clock and the seq counter), so this
    applies a fixed one to keep the result comparable.
    """
    translator = CursorStreamTranslator()
    translated: list[TranslatedEvent] = []
    for raw in lines:
        translated.extend(translator.translate(raw))
    translated.extend(translator.flush_text())
    return [
        ExecutorEvent(
            type=item.type,
            executor=executor,
            session_id=session_id or (translator.session_id or ""),
            turn_id=turn_id,
            seq=seq,
            ts=ts,
            raw_type=item.raw_type,
            **item.fields,  # type: ignore[arg-type]
        )
        for seq, item in enumerate(translated, start=1)
    ]


__all__ = [
    "CursorStreamTranslator",
    "TranslatedEvent",
    "canonical_tool_name",
    "translate_stream",
]
