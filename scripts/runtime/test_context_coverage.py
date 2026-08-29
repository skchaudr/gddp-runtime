"""Context coverage over canonical events must rate identically to the pi
implementation it was ported from.

The hard constraint on a second transport is that the MEASUREMENT does not
change when the event shape does: same ratings, same "None when nothing was
offered" rule. These tests assert both halves — the rating table directly, and
equivalence across matched pi/cursor streams of the same work.

The pi-shaped copy of this rating this file used to compare against is gone;
pi now reaches the same implementation through events_pi_rpc, so the
equivalence case below runs both native shapes through their translators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from adapters.events_cursor_cli import translate_stream
from adapters.events_pi_rpc import translate_stream as translate_pi_stream
from adapters.executor_events import ExecutorEvent
from runtime.context_coverage import (
    compute_turn_context_coverage,
    extract_read_paths,
)

SPIKE_DIR = ROOT / "scripts" / "runtime" / "spike"
PROBE_EVENTS = json.loads(
    (SPIKE_DIR / "cursor_tool_probe_results.json").read_text()
)["events"]


def _completed(
    tool: str, paths: tuple[str, ...], ok: bool = True, call_id: str = "c1"
) -> ExecutorEvent:
    return ExecutorEvent(
        type="tool_completed",
        executor="cursor_cli",
        session_id="s",
        turn_id="t",
        seq=1,
        ts="1970-01-01T00:00:00.000Z",
        call_id=call_id,
        tool=tool,
        paths=paths,
        ok=ok,
    )


def _started(tool: str, paths: tuple[str, ...]) -> ExecutorEvent:
    return ExecutorEvent(
        type="tool_started",
        executor="cursor_cli",
        session_id="s",
        turn_id="t",
        seq=1,
        ts="1970-01-01T00:00:00.000Z",
        tool=tool,
        paths=paths,
    )


def test_only_successful_content_tools_count_as_a_read():
    events = [
        _completed("read", ("/repo/a.md",)),
        _completed("grep", ("/repo/b.md",)),
        # Failed: an ENOENT read is not coverage.
        _completed("read", ("/repo/missing.md",), ok=False),
        # ls/find prove a path exists, not that it was consumed.
        _completed("ls", ("/repo/dir",)),
        _completed("find", ("/repo/dir",)),
        _completed("write", ("/repo/out.md",)),
        _completed("bash", ()),
        # A start with no completion never counts.
        _started("read", ("/repo/never-finished.md",)),
    ]

    assert extract_read_paths(events) == {"/repo/a.md", "/repo/b.md"}


def test_relative_paths_resolve_against_the_base_the_harness_used(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n")
    events = [_completed("read", ("README.md",))]

    assert extract_read_paths(events, base=tmp_path) == {
        str((tmp_path / "README.md").resolve())
    }
    # No base: reported as-is rather than resolved against a guess.
    assert extract_read_paths(events) == {str(Path("README.md").resolve())}


@pytest.mark.parametrize(
    ("read", "expected"),
    (
        ((), "none"),
        # Something offered was read, but no canonical doc.
        (("/repo/nodes/up.yaml",), "low"),
        # A doc, but no neighbor while neighbors were offered.
        (("/repo/README.md",), "medium"),
        (("/repo/README.md", "/repo/nodes/up.yaml"), "high"),
    ),
)
def test_rating_table(read, expected):
    pointers = {
        "readme": "/repo/README.md",
        "neighbor:node-up": "/repo/nodes/up.yaml",
    }
    events = [
        _completed("read", (path,), call_id=f"c{index}")
        for index, path in enumerate(read)
    ]

    coverage = compute_turn_context_coverage(pointers=pointers, events=events)

    assert coverage is not None
    assert coverage["rating"] == expected


def test_a_doc_read_rates_high_when_no_neighbors_were_offered():
    coverage = compute_turn_context_coverage(
        pointers={"readme": "/repo/README.md"},
        events=[_completed("read", ("/repo/README.md",))],
    )

    assert coverage is not None
    assert coverage["rating"] == "high"


def test_nothing_offered_produces_no_artifact_rather_than_a_misleading_none():
    """A packet with no pointers must not render as 'none' coverage — absent
    evidence, never a fabricated zero."""
    assert compute_turn_context_coverage(pointers={}, events=[]) is None
    assert (
        compute_turn_context_coverage(
            pointers={"invariants": "/repo/INVARIANTS.md"}, events=[]
        )
        is None
    )
    assert (
        compute_turn_context_coverage(
            pointers={"readme": "UNAVAILABLE: /repo/README.md does not exist"},
            events=[_completed("read", ("/repo/README.md",))],
        )
        is None
    )


def test_unread_and_unoffered_paths_are_both_reported():
    coverage = compute_turn_context_coverage(
        pointers={
            "readme": "/repo/README.md",
            "project_brief": "/repo/BRIEF.md",
            "foundational_node": "/repo/nodes/00.yaml",
            "invariants": "UNAVAILABLE: none configured",
        },
        events=[
            _completed("read", ("/repo/README.md",), call_id="c1"),
            _completed("grep", ("/repo/somewhere/else.py",), call_id="c2"),
        ],
    )

    assert coverage is not None
    assert coverage["offered"] == 3
    assert coverage["content_accessed"] == 1
    assert coverage["not_observed_paths"] == ["/repo/BRIEF.md", "/repo/nodes/00.yaml"]
    # Research drift: read paths that were never offered.
    assert coverage["outside_pointers"] == ["/repo/somewhere/else.py"]
    assert coverage["unavailable_pointer_keys"] == ["invariants"]
    assert coverage["groups"]["docs"]["content_accessed"] == 1
    assert coverage["groups"]["neighbors"]["content_accessed"] == 0


def test_cursor_and_pi_streams_of_the_same_work_produce_the_same_record():
    """The measurement must not change because the transport did. Same reads,
    same failures, same record — one stream in pi's native shape, one in
    cursor's, both through their translators into the one implementation."""
    pointers = {
        "readme": "/repo/README.md",
        "neighbor:node-up": "/repo/nodes/up.yaml",
        "foundational_node": "/repo/nodes/00.yaml",
    }
    pi_events = [
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "read",
            "args": {"path": "/repo/README.md"},
        },
        {"type": "tool_execution_end", "toolCallId": "call-1", "isError": False},
        {
            "type": "tool_execution_start",
            "toolCallId": "call-2",
            "toolName": "grep",
            "args": {"path": "/repo/nodes/up.yaml"},
        },
        {"type": "tool_execution_end", "toolCallId": "call-2", "isError": False},
        {
            "type": "tool_execution_start",
            "toolCallId": "call-3",
            "toolName": "read",
            "args": {"path": "/repo/nodes/00.yaml"},
        },
        {"type": "tool_execution_end", "toolCallId": "call-3", "isError": True},
    ]
    cursor_events = translate_stream(
        [
            *_cursor_tool("Read_0_a", "readToolCall", "/repo/README.md", ok=True),
            *_cursor_tool("Grep_1_b", "grepToolCall", "/repo/nodes/up.yaml", ok=True),
            *_cursor_tool("Read_2_c", "readToolCall", "/repo/nodes/00.yaml", ok=False),
        ]
    )

    pi_coverage = compute_turn_context_coverage(
        pointers=pointers, events=translate_pi_stream(pi_events)
    )
    cursor_coverage = compute_turn_context_coverage(
        pointers=pointers, events=cursor_events
    )

    assert pi_coverage == cursor_coverage
    assert cursor_coverage is not None
    assert cursor_coverage["rating"] == "high"
    assert "/repo/nodes/00.yaml" in cursor_coverage["not_observed_paths"]


def _cursor_tool(call_id: str, tool_key: str, path: str, *, ok: bool) -> list[dict]:
    started = {
        "type": "tool_call",
        "subtype": "started",
        "call_id": call_id,
        "tool_call": {tool_key: {"args": {"path": path}}},
    }
    completed = {
        "type": "tool_call",
        "subtype": "completed",
        "call_id": call_id,
        "tool_call": {
            tool_key: {
                "args": {"path": path},
                "result": {"success": {}} if ok else {"error": {"errorMessage": "no"}},
            }
        },
    }
    return [started, completed]


def test_probe_stream_coverage_uses_the_failing_read_correctly():
    """The probe's failing read must not count, and its path must still be
    visible as drift — which only works because tool_completed is
    self-contained."""
    coverage = compute_turn_context_coverage(
        pointers={
            "readme": "/private/tmp/cursor-tool-probe",
            "neighbor:x": "/nonexistent/definitely-missing.txt",
        },
        events=translate_stream(PROBE_EVENTS),
    )

    assert coverage is not None
    # grep succeeded on the probe dir; the read of the missing file failed.
    assert coverage["rating"] == "medium"
    assert coverage["not_observed_paths"] == ["/nonexistent/definitely-missing.txt"]
