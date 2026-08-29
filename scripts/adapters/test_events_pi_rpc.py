"""pi RPC -> canonical translation, against a recorded production stream.

The fixture (scripts/runtime/spike/pi_rpc_stream_sample.json) is lifted
verbatim from the 72 real orchestrator spools, so these tests fail if pi's
real shapes stop matching what the translator claims about them. Nothing here
spawns a process or touches the filesystem — the translator is pure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.events_pi_rpc import PiStreamTranslator, translate_stream  # noqa: E402
from adapters.executor_events import turn_usage  # noqa: E402

SAMPLE = json.loads(
    (ROOT / "scripts" / "runtime" / "spike" / "pi_rpc_stream_sample.json").read_text()
)
SAMPLE_EVENTS = SAMPLE["events"]


def _of_type(events, type_):
    return [e for e in events if e.type == type_]


def test_recorded_stream_translates_to_the_seven_canonical_types_only():
    events = translate_stream(SAMPLE_EVENTS)

    assert [e.type for e in events] == [
        "session_started",
        "turn_started",
        "tool_started",
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_completed",
        "tool_completed",
        "assistant_message",
        "usage",
        "turn_ended",
    ]
    assert all(e.executor == "pi_rpc" for e in events)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


def test_every_dropped_type_is_dropped_for_a_reason_and_none_survive():
    """message_update alone is 91.6% of a real spool and no consumer parses
    its content; the canonical spool must not carry it (or the other five
    zero-consumer types) at all."""
    dropped_raw = {
        "agent_start",
        "agent_settled",
        "message_start",
        "message_update",
        "tool_execution_update",
        "entry_appended",
        "extension_ui_request",
    }
    present = {e.get("type") for e in SAMPLE_EVENTS}
    assert dropped_raw <= present, "fixture must exercise every dropped type"

    events = translate_stream(SAMPLE_EVENTS)

    assert not (dropped_raw & {e.raw_type for e in events})


def test_session_identity_comes_off_the_get_state_response():
    events = translate_stream(SAMPLE_EVENTS)
    started = _of_type(events, "session_started")

    assert len(started) == 1
    # data.model is an object in every observed get_state response.
    assert started[0].model == "grok-4.5"
    # pi resumes from the session FILE, not the id.
    assert started[0].resume_token.endswith(
        "019ffce4-f6ff-7c87-b0c0-6ddde137de3d.jsonl"
    )
    assert started[0].session_id == "019ffce4-f6ff-7c87-b0c0-6ddde137de3d"


def test_session_started_is_announced_once_not_on_every_response():
    """Every RPC send produces a `response`; only the get_state one carries
    session identity, and a second one must not re-announce."""
    translator = PiStreamTranslator()
    state = {
        "type": "response",
        "command": "get_state",
        "success": True,
        "data": {"sessionId": "s-1", "sessionFile": "/tmp/s.jsonl"},
    }
    assert len(translator.translate(state)) == 1
    assert translator.translate(state) == []
    assert (
        translator.translate(
            {"type": "response", "command": "prompt", "success": True}
        )
        == []
    )


def test_tool_completed_carries_the_paths_the_start_reported():
    """pi's end event has no args (measured across all 1,401), so without the
    call_id buffer a completion carries no path and coverage's one-pass
    filter (vocabulary §4) cannot work."""
    events = translate_stream(SAMPLE_EVENTS)
    completed = _of_type(events, "tool_completed")

    read_ok = next(e for e in completed if e.tool == "read" and e.ok)
    assert read_ok.paths == ("reports/pi-harness-execution/node-05-extensions-audit.md",)
    # Relative as pi reported it: resolution against a base is the consumer's.
    assert not Path(read_ok.paths[0]).is_absolute()


def test_both_observed_failure_shapes_mark_the_call_not_ok():
    """Top-level isError (74 observed) and nested result.isError (18) are
    both real; a completion that carries neither is a success."""
    completed = _of_type(translate_stream(SAMPLE_EVENTS), "tool_completed")

    # Top-level isError: an ENOENT read. Its path still rides the event, so
    # it stays visible as research drift while not counting as coverage.
    failing_read = next(e for e in completed if e.tool == "read" and not e.ok)
    assert failing_read.paths == (
        "/Users/sab-mini/repos/MyAPI-rebuild/project-docs/corpus-work-2026-08/"
        "2026-08-08-last2w-decisions.md",
    )
    # Nested result.isError: a timed-out subagent workflow.
    assert next(e for e in completed if e.tool == "subagent").ok is False
    # Neither flag set: a success.
    assert next(e for e in completed if e.tool == "read" and e.ok).ok is True


def test_a_completion_with_no_matching_start_reports_no_paths():
    """The subagent failure in the fixture has no start event in the slice;
    an unpaired completion must not fabricate a path."""
    events = translate_stream(SAMPLE_EVENTS)
    orphan = next(e for e in _of_type(events, "tool_completed") if e.tool == "subagent")

    assert orphan.paths == ()
    assert orphan.call_id.startswith("call_80BRNzHQXWgzwefcaAZcquvG")


def test_bash_carries_its_command_and_no_path():
    events = translate_stream(SAMPLE_EVENTS)
    started = next(e for e in _of_type(events, "tool_started") if e.tool == "bash")

    assert started.paths == ()
    assert started.command.startswith("git rev-parse HEAD")
    # The fixture's bash call never completes, which is the shape a turn that
    # died mid-call leaves behind: no tool_completed, so nothing to mistake
    # for a finished call.
    assert not [e for e in _of_type(events, "tool_completed") if e.tool == "bash"]


def test_only_assistant_message_end_becomes_assistant_text_and_usage():
    """message_end also carries toolResult/custom/user roles, and only the
    assistant ones carry usage. A toolResult in the assistant stream would be
    tool output presented as the model talking."""
    events = translate_stream(SAMPLE_EVENTS)
    messages = _of_type(events, "assistant_message")

    assert len(messages) == 1
    assert messages[0].text == (
        "I'll read the paired audit report and check the worktree state "
        "before implementing anything."
    )
    # The thinking part carries its prose under `thinking`, not `text`.
    assert "The user wants me to implement" not in messages[0].text
    assert messages[0].role == "assistant"


def test_usage_is_message_scoped_with_pi_key_names_normalized():
    events = translate_stream(SAMPLE_EVENTS)
    usage_events = _of_type(events, "usage")

    assert len(usage_events) == 1
    usage = usage_events[0].usage
    assert usage.scope == "message"
    assert usage.input_tokens == 9580
    assert usage.output_tokens == 164
    assert usage.cached_input_tokens == 384
    assert usage.cache_write_tokens == 0
    # pi reports cost as a per-component breakdown, not a scalar.
    assert usage.cost == 0.0202592


def test_turn_end_contributes_no_usage_record():
    """turn_end restates the turn's message usage (765 turn_end against 777
    assistant message_end, identical cacheRead totals in 58 of 69 spools).
    Emitting it as scope="turn" would make turn_usage PREFER it over the
    authoritative per-message sum and silently report a different number."""
    events = translate_stream(SAMPLE_EVENTS)

    assert [e.raw_type for e in _of_type(events, "usage")] == ["message_end"]
    assert turn_usage(events).scope == "message"
    assert turn_usage(events).cached_input_tokens == 384


def test_message_update_usage_never_reaches_the_canonical_stream():
    """The §1.2 over-count: 146,799 message_update events carry a usage dict
    and 2,098 of them a nonzero cacheRead, which the raw-pi extractor sums on
    top of message_end. The fixture's message_update carries cacheRead 512;
    the canonical total is the message_end's 384 alone."""
    events = translate_stream(SAMPLE_EVENTS)

    assert turn_usage(events).cached_input_tokens == 384


def test_turn_ended_takes_its_stop_reason_from_the_preceding_turn_end():
    events = translate_stream(SAMPLE_EVENTS)
    ended = _of_type(events, "turn_ended")

    assert len(ended) == 1
    assert ended[0].status == "completed"
    assert ended[0].stop_reason == "toolUse"
    assert ended[0].raw_type == "agent_end"


def test_saw_turn_end_is_the_drivers_synthesize_or_not_signal():
    """The driver must know whether pi reported a boundary at all, because a
    dead process reports none and its turn_ended has to be synthesized."""
    translator = PiStreamTranslator()
    for raw in SAMPLE_EVENTS:
        translator.translate(raw)
    assert translator.saw_turn_end is True

    translator.begin_turn()
    assert translator.saw_turn_end is False
    # Session identity survives a turn reset; the pi process outlives turns.
    assert translator.session_id == "019ffce4-f6ff-7c87-b0c0-6ddde137de3d"


def test_begin_turn_drops_the_call_buffer_so_turns_cannot_bleed():
    translator = PiStreamTranslator()
    translator.translate(
        {
            "type": "tool_execution_start",
            "toolCallId": "c1",
            "toolName": "read",
            "args": {"path": "/repo/a.md"},
        }
    )
    translator.begin_turn()
    completed = translator.translate(
        {"type": "tool_execution_end", "toolCallId": "c1", "toolName": "read"}
    )

    assert completed[0].fields["paths"] == ()


def test_unknown_and_malformed_lines_are_dropped_not_raised():
    translator = PiStreamTranslator()

    assert translator.translate({"type": "some_future_pi_event"}) == []
    assert translator.translate({"type": "_non_json", "raw": "garbage"}) == []
    assert translator.translate("not a mapping") == []
    assert translator.translate({}) == []
