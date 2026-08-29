"""pi `--mode rpc` stream -> canonical ExecutorEvent translation.

The only place pi's provider event names appear. Pure: no clock, no IO, no
envelope — the driver's EventWriter owns ts/seq/session_id/turn_id, so this
module emits ``TranslatedEvent`` and the driver hands each one straight to
``EventWriter.emit``. That keeps the translator testable against recorded
fixtures with no live pi process.

Ground truth, and the only ground truth (AGENTS.md: never design around an
unmeasured behavior): 72 real orchestrator spools under
``jobs/local-subprocess-spool/*/events.jsonl`` (241,585 events), censused in
docs/proposals/executor-event-vocabulary.md §1 and re-measured for this
module. The fixtures in test_events_pi_rpc.py are lifted from those spools.

Mapping table: docs/proposals/executor-event-vocabulary.md §5.1, with two
measured departures recorded below (turn_end usage, message_end role).

Not this module's job: the process-died and cancel-requested cases. pi emits
no event at all for either, so their ``turn_ended`` is synthesized by the
driver from the outcome it already knows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from adapters.executor_events import ExecutorEvent, TranslatedEvent, TurnUsage

# pi's tool names are already the canonical spellings — CONTENT_TOOLS in
# executor_events.py was defined from this vocabulary — so there is no name
# table here. An unknown tool passes through as pi spelled it.


class PiStreamTranslator:
    """Incremental pi RPC stream -> canonical events.

    Session-scoped (one pi process serves a whole project across turns) with
    a per-turn reset: ``begin_turn`` clears the turn-local state and keeps
    the session identity learned from ``get_state``.

    Per-turn state is the ``call_id -> (tool, paths, command)`` buffer.
    pi's ``tool_execution_end`` carries ``toolCallId``/``toolName``/
    ``result``/``isError`` and NO args (measured over all 1,401 end events),
    so without the buffer a ``tool_completed`` would carry no path and the
    self-contained-completion contract (vocabulary §4) would break — which is
    exactly the contract that lets coverage be a one-pass filter.
    """

    def __init__(self) -> None:
        self._calls: dict[str, tuple[str, tuple[str, ...], str | None]] = {}
        self._stop_reason: str | None = None
        self._session_announced = False
        self.session_id: str | None = None
        self.resume_token: str | None = None
        self.model: str | None = None
        self.saw_turn_end = False

    def begin_turn(self) -> None:
        """Reset turn-local state. Session identity survives; the pi process
        and its session file outlive any single turn."""
        self._calls.clear()
        self._stop_reason = None
        self.saw_turn_end = False

    def translate(self, raw: object) -> list[TranslatedEvent]:
        """Translate one decoded pi RPC line. Unknown types yield []."""
        if not isinstance(raw, Mapping):
            return []
        raw_type = str(raw.get("type") or "")

        if raw_type == "response":
            return self._response(raw, raw_type)
        if raw_type == "turn_start":
            return [TranslatedEvent(type="turn_started", raw_type=raw_type)]
        if raw_type == "message_end":
            return self._message_end(raw, raw_type)
        if raw_type == "tool_execution_start":
            return self._tool_started(raw, raw_type)
        if raw_type == "tool_execution_end":
            return self._tool_completed(raw, raw_type)
        if raw_type == "turn_end":
            # Deliberately emits NO usage. Measured over the 72 spools:
            # turn_end usage is a per-turn restatement of the assistant
            # message_end usage (765 turn_end against 777 assistant
            # message_end; identical cacheRead totals in 58 of 69 spools that
            # report any). §5.1 proposed scope="turn" for it, but
            # executor_events.turn_usage PREFERS a turn-scoped record over
            # summed message-scoped ones, so emitting it would silently
            # replace the authoritative per-message sum with whichever
            # turn_end came last — a different number, with no evidence the
            # two agree. Its stopReason is the one fact worth keeping; it
            # rides the next turn_ended.
            self._stop_reason = _stop_reason(raw)
            return []
        if raw_type == "agent_end":
            self.saw_turn_end = True
            stop_reason = self._stop_reason
            self._stop_reason = None
            return [
                TranslatedEvent(
                    type="turn_ended",
                    raw_type=raw_type,
                    fields={"status": "completed", "stop_reason": stop_reason},
                )
            ]
        # agent_start, agent_settled, message_start (a zero usage stub),
        # message_update (221k deltas, 91.6% of the stream),
        # tool_execution_update, entry_appended, extension_ui_request: no
        # consumer, dropped from the canonical spool and kept verbatim in
        # raw.jsonl.
        return []

    def _response(
        self, raw: Mapping[str, object], raw_type: str
    ) -> list[TranslatedEvent]:
        """Session identity, which pi answers out-of-band rather than
        streaming: the driver's ``get_state`` round-trip comes back as a
        ``response`` carrying sessionId/sessionFile."""
        if self._session_announced or not raw.get("success"):
            return []
        data = raw.get("data")
        if not isinstance(data, Mapping):
            return []
        session_id = data.get("sessionId") or data.get("session_id")
        session_file = data.get("sessionFile") or data.get("session_file")
        if not isinstance(session_id, str) and not isinstance(session_file, str):
            return []
        self._session_announced = True
        self.session_id = session_id if isinstance(session_id, str) else None
        self.resume_token = session_file if isinstance(session_file, str) else None
        self.model = _model_name(data.get("model"))
        return [
            TranslatedEvent(
                type="session_started",
                raw_type=f"{raw_type}/{raw.get('command') or 'get_state'}",
                fields={
                    # pi resumes from the session FILE, not the id
                    # (pi_rpc_adapter: `--session <sessionFile>`).
                    "model": self.model,
                    "resume_token": self.resume_token,
                },
            )
        ]

    def _message_end(
        self, raw: Mapping[str, object], raw_type: str
    ) -> list[TranslatedEvent]:
        """Assistant messages only.

        Measured: message_end carries role toolResult (1,401), assistant
        (777), custom (239) and user (59), and ONLY the assistant ones carry
        usage. Treating every message_end as assistant text would put tool
        output and the echoed prompt into the assistant stream.
        """
        message = raw.get("message")
        if not isinstance(message, Mapping) or message.get("role") != "assistant":
            return []
        events: list[TranslatedEvent] = []
        text = _message_text(message)
        if text:
            events.append(
                TranslatedEvent(
                    type="assistant_message",
                    raw_type=raw_type,
                    fields={"text": text, "role": "assistant"},
                )
            )
        usage = message.get("usage")
        if isinstance(usage, Mapping):
            events.append(
                TranslatedEvent(
                    type="usage",
                    raw_type=raw_type,
                    fields={
                        "usage": TurnUsage(
                            input_tokens=_int_or_none(usage.get("input")),
                            output_tokens=_int_or_none(usage.get("output")),
                            cached_input_tokens=_int_or_none(usage.get("cacheRead")),
                            cache_write_tokens=_int_or_none(usage.get("cacheWrite")),
                            cost=_total_cost(usage.get("cost")),
                            # One record per completed model call. Never
                            # summed with a turn-scoped record.
                            scope="message",
                        )
                    },
                )
            )
        return events

    def _tool_started(
        self, raw: Mapping[str, object], raw_type: str
    ) -> list[TranslatedEvent]:
        call_id = raw.get("toolCallId")
        call_id = call_id if isinstance(call_id, str) else ""
        tool = raw.get("toolName")
        tool = tool if isinstance(tool, str) else ""
        args = raw.get("args")
        paths = _paths_from_args(args)
        command = _command_from_args(args)
        if call_id:
            self._calls[call_id] = (tool, paths, command)
        return [
            TranslatedEvent(
                type="tool_started",
                raw_type=raw_type,
                fields={
                    "call_id": call_id,
                    "tool": tool,
                    "paths": paths,
                    "command": command,
                },
            )
        ]

    def _tool_completed(
        self, raw: Mapping[str, object], raw_type: str
    ) -> list[TranslatedEvent]:
        call_id = raw.get("toolCallId")
        call_id = call_id if isinstance(call_id, str) else ""
        buffered = self._calls.pop(call_id, None)
        tool = raw.get("toolName")
        tool = tool if isinstance(tool, str) else ""
        paths: tuple[str, ...] = ()
        command: str | None = None
        if buffered is not None:
            buffered_tool, paths, command = buffered
            tool = tool or buffered_tool
        result = raw.get("result")
        # Both places the failure flag has been observed. Same two checks the
        # pi implementation this replaces made (pi_rpc_adapter, pre-migration
        # extract_read_paths): an end with neither flag is a success.
        failed = bool(raw.get("isError")) or bool(
            isinstance(result, Mapping) and result.get("isError")
        )
        return [
            TranslatedEvent(
                type="tool_completed",
                raw_type=raw_type,
                fields={
                    "call_id": call_id,
                    "tool": tool,
                    "paths": paths,
                    "command": command,
                    "ok": not failed,
                    "error": _tool_error(result) if failed else None,
                },
            )
        ]


def _message_text(message: Mapping[str, object]) -> str:
    """Text parts only. A thinking part carries its prose under `thinking`
    with no `text` key, so it is excluded by construction."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        part.get("text", "")
        for part in content
        if isinstance(part, Mapping) and isinstance(part.get("text"), str)
    )


def _paths_from_args(args: object) -> tuple[str, ...]:
    """Paths a tool call names, as pi reported them.

    Observed arg shapes carry at most one ``path`` (read/grep/write/edit/ls/
    find); bash carries ``command`` and no path, and 3 of 86 grep calls carry
    no path at all — hence a tuple rather than a scalar with a null
    convention. Resolution against a base is the consumer's job, so nothing
    is normalized here.
    """
    if not isinstance(args, Mapping):
        return ()
    path = args.get("path")
    if isinstance(path, str) and path:
        return (path,)
    return ()


def _command_from_args(args: object) -> str | None:
    if not isinstance(args, Mapping):
        return None
    command = args.get("command")
    return command if isinstance(command, str) and command else None


def _tool_error(result: object) -> str | None:
    """Best available failure text.

    No failing-tool result body was observed carrying a dedicated message
    field, so this reads the one shape that is unambiguous and otherwise
    reports nothing rather than inventing a string. ``ok`` is the field
    coverage reads; this is operator prose.
    """
    if isinstance(result, Mapping):
        error = result.get("error")
        if isinstance(error, str) and error:
            return error
    return None


def _stop_reason(raw: Mapping[str, object]) -> str | None:
    message = raw.get("message")
    if isinstance(message, Mapping):
        reason = message.get("stopReason")
        if isinstance(reason, str) and reason:
            return reason
    return None


def _model_name(model: object) -> str | None:
    """get_state reports the model as an object, not a string."""
    if isinstance(model, str):
        return model or None
    if isinstance(model, Mapping):
        for key in ("id", "name"):
            value = model.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _total_cost(cost: object) -> float | None:
    """pi reports cost as a per-component breakdown with a `total`."""
    if isinstance(cost, Mapping):
        total = cost.get("total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            return float(total)
        return None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        return float(cost)
    return None


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
    executor: str = "pi_rpc",
    session_id: str = "",
    turn_id: str = "turn",
    ts: str = "1970-01-01T00:00:00.000Z",
) -> list[ExecutorEvent]:
    """Translate a whole recorded stream into stamped canonical events.

    Fixture/replay convenience: the live driver stamps the envelope through
    EventWriter (which owns the real clock and the seq counter), so this
    applies a fixed one to keep the result comparable.
    """
    translator = PiStreamTranslator()
    translated: list[TranslatedEvent] = []
    for raw in lines:
        translated.extend(translator.translate(raw))
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
    "PiStreamTranslator",
    "TranslatedEvent",
    "translate_stream",
]
