"""cursor_cli transport: translator against recorded fixtures, then the
adapter lifecycle against a fake cursor-agent.

No test here requires the real binary. The translator runs on the two spike
fixtures verbatim, and the adapter runs against a recorded stream replayed by
an executable stub, so the suite stays honest on a host with no cursor login.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from adapters import cursor_cli_adapter
from adapters.cursor_cli_adapter import (
    CursorCliAdapter,
    build_argv,
    build_cursor_turn_prompt,
    read_cursor_cli_status,
)
from adapters.events_cursor_cli import (
    CursorStreamTranslator,
    canonical_tool_name,
    translate_stream,
)
from adapters.executor_events import read_events, turn_usage
from adapters.executor_protocol import (
    AttemptContext,
    FRESH,
    CapabilityUnsupported,
    Continuity,
    ExecutorCapabilities,
    NodePacket,
    SessionRef,
)
from adapters.pi_rpc_adapter import PiRpcAdapter

SPIKE_DIR = ROOT / "scripts" / "runtime" / "spike"
PROBE_RESULTS = json.loads((SPIKE_DIR / "cursor_tool_probe_results.json").read_text())
SPIKE_RESULTS = json.loads((SPIKE_DIR / "cursor_cli_spike_results.json").read_text())
PROBE_EVENTS = PROBE_RESULTS["events"]


# ---------------------------------------------------------------------------
# translator — fixtures are the only ground truth
# ---------------------------------------------------------------------------


def _by_type(events, kind):
    return [event for event in events if event.type == kind]


def test_probe_stream_translates_to_the_canonical_vocabulary():
    events = translate_stream(PROBE_EVENTS)

    assert [event.type for event in events] == [
        "session_started",
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_started",
        "tool_started",
        "tool_completed",
        "tool_completed",
        "tool_completed",
        "assistant_message",
        "usage",
        "turn_ended",
    ]
    started = _by_type(events, "session_started")[0]
    assert started.model == "Kimi K3 Max"
    # Same value serves --resume; there is no separate resume handle.
    assert started.resume_token == "b9074518-21fc-49ed-a839-738d08fbb8c9"


def test_cursor_tool_names_map_onto_the_pi_spellings():
    """Coverage gates on tool names. If a transport invents its own
    spelling the gate silently stops matching and a session that read
    everything reports 'none' — a silent zero, not a loud failure."""
    completed = {
        event.call_id: event for event in _by_type(translate_stream(PROBE_EVENTS), "tool_completed")
    }

    assert completed["Write_0_25c30736-af0a1"].tool == "write"
    assert completed["StrReplace_0_80e029ed-af0a2"].tool == "edit"
    assert completed["Grep_0_70a20c0e-af0a3"].tool == "grep"
    assert completed["Shell_1_8d06cebb-af0a3"].tool == "bash"
    assert completed["Read_2_a2b0f77d-af0a3"].tool == "read"


@pytest.mark.parametrize(
    ("tool_key", "call_id", "expected"),
    (
        ("readToolCall", "Read_0_x", "read"),
        ("grepToolCall", "Grep_0_x", "grep"),
        ("shellToolCall", "Shell_0_x", "bash"),
        ("editToolCall", "Write_0_x", "write"),
        ("editToolCall", "StrReplace_0_x", "edit"),
        # Neither observed prefix: keep the tool key's own claim rather than
        # guessing a create.
        ("editToolCall", "Mystery_0_x", "edit"),
        # Unmapped tools stay visible instead of vanishing from the spool.
        ("somethingNewToolCall", "New_0_x", "somethingnew"),
    ),
)
def test_canonical_tool_name_cases(tool_key, call_id, expected):
    assert canonical_tool_name(tool_key, call_id) == expected


def test_failed_tool_call_keeps_its_path_from_the_buffered_start():
    """The probe proved a FAILED call's completed event carries no args at
    all. Without the call_id -> args buffer, tool_completed would lose the
    path exactly where a failure needs explaining."""
    completed = {
        event.call_id: event
        for event in _by_type(translate_stream(PROBE_EVENTS), "tool_completed")
    }
    failed = completed["Read_2_a2b0f77d-af0a3"]

    raw_completed = next(
        event
        for event in PROBE_EVENTS
        if event.get("call_id") == "Read_2_a2b0f77d-af0a3"
        and event.get("subtype") == "completed"
    )
    assert "args" not in raw_completed["tool_call"]["readToolCall"]

    assert failed.ok is False
    assert failed.error == "File not found"
    assert failed.paths == ("/nonexistent/definitely-missing.txt",)
    assert failed.tool == "read"


def test_ok_derivation_matches_the_probed_result_shapes():
    completed = {
        event.call_id: event
        for event in _by_type(translate_stream(PROBE_EVENTS), "tool_completed")
    }
    assert completed["Grep_0_70a20c0e-af0a3"].ok is True
    assert completed["Read_2_a2b0f77d-af0a3"].ok is False


def test_tool_completed_is_self_contained():
    """Coverage must be a one-pass filter: tool and paths ride the
    completion, so no consumer re-implements the start/end join."""
    for event in _by_type(translate_stream(PROBE_EVENTS), "tool_completed"):
        assert event.tool
        assert event.ok is not None
        if event.tool in {"read", "grep", "write", "edit"}:
            assert event.paths


def test_shell_calls_carry_command_and_no_path():
    started = {
        event.call_id: event
        for event in _by_type(translate_stream(PROBE_EVENTS), "tool_started")
    }
    shell = started["Shell_1_8d06cebb-af0a3"]
    assert shell.command == "echo probe-done"
    assert shell.paths == ()


def test_terminal_result_becomes_turn_scoped_usage_and_a_turn_boundary():
    events = translate_stream(PROBE_EVENTS)
    usage_event = _by_type(events, "usage")[0]
    assert usage_event.usage is not None
    assert usage_event.usage.scope == "turn"
    assert usage_event.usage.input_tokens == 27420
    assert usage_event.usage.output_tokens == 768
    # Lane 1 finding 5: cacheReadTokens is not in prompt_topology's provider
    # key list, so an un-normalized cursor stream reports no cache at all.
    assert usage_event.usage.cached_input_tokens == 59408
    assert usage_event.usage.cache_write_tokens == 0

    ended = _by_type(events, "turn_ended")[0]
    assert ended.status == "completed"
    assert ended.error is None


@pytest.mark.parametrize(
    "label",
    [
        name
        for name, turn in SPIKE_RESULTS["turns"].items()
        if turn.get("result_event")
    ],
)
def test_every_recorded_result_event_yields_usage_and_a_boundary(label):
    turn = SPIKE_RESULTS["turns"][label]
    events = translate_stream([turn["result_event"]])

    usage_event = _by_type(events, "usage")[0]
    recorded = turn["result_event"]["usage"]
    assert usage_event.usage is not None
    assert usage_event.usage.cached_input_tokens == recorded["cacheReadTokens"]
    assert usage_event.usage.input_tokens == recorded["inputTokens"]
    assert _by_type(events, "turn_ended")[0].status == "completed"


def test_result_is_error_ends_the_turn_failed():
    events = translate_stream(
        [{"type": "result", "subtype": "error", "is_error": True, "result": "boom"}]
    )
    ended = _by_type(events, "turn_ended")[0]
    assert ended.status == "failed"
    assert ended.error == "boom"


def test_success_subtype_with_is_error_stays_completed_and_records_warning():
    """Not blunt is_error→failed. Spike-recorded completed turns are
    result/success (cursor_cli_spike_results.json cold_turn); is_error on
    that subtype is a termination-boundary crash, not undone work."""
    events = translate_stream(
        [
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "result": "died after",
            }
        ]
    )
    ended = _by_type(events, "turn_ended")[0]
    assert ended.status == "completed"
    assert ended.warning == "died after"
    assert ended.error is None


def test_error_result_after_completed_success_does_not_flip_status():
    stream = [
        SPIKE_RESULTS["turns"]["cold_turn"]["result_event"],
        {"type": "result", "subtype": "error", "is_error": True, "result": "crash"},
    ]
    ended = _by_type(translate_stream(stream), "turn_ended")
    assert ended[0].status == "completed"
    assert ended[-1].status == "completed"
    assert ended[-1].warning == "crash"


def test_assistant_partial_and_final_are_emitted_once():
    """Measured: naive concatenation doubles the output
    (assistant_text 'SPIKE7-COLDSPIKE7-COLD' for a turn whose result was
    'SPIKE7-COLD'). Partials are deltas; the final event repeats the whole
    message."""
    cold = SPIKE_RESULTS["turns"]["cold_turn"]
    assert cold["assistant_text"] == "SPIKE7-COLDSPIKE7-COLD"
    assert cold["event_types"]["assistant"] == 3

    stream = [
        _assistant("SPIKE7"),
        _assistant("-COLD"),
        _assistant("SPIKE7-COLD"),
        cold["result_event"],
    ]
    messages = _by_type(translate_stream(stream), "assistant_message")

    assert [message.text for message in messages] == ["SPIKE7-COLD"]


def test_repeated_delta_text_is_not_mistaken_for_a_final_reemission():
    """The kill turn streamed 41 counted lines with no final event. A dedupe
    rule that dropped any repeated-looking chunk would eat real output."""
    stream = [_assistant("1\n"), _assistant("2\n"), _assistant("1\n")]
    messages = _by_type(translate_stream(stream), "assistant_message")

    assert [message.text for message in messages] == ["1\n2\n1\n"]


def test_assistant_text_is_flushed_when_the_model_stops_talking_to_act():
    events = translate_stream(
        [
            _assistant("I'll run these steps in order."),
            PROBE_EVENTS[1],
            PROBE_EVENTS[2],
            _assistant("done"),
        ]
    )
    assert [event.type for event in events] == [
        "assistant_message",
        "tool_started",
        "tool_completed",
        "assistant_message",
    ]
    assert _by_type(events, "assistant_message")[0].text == (
        "I'll run these steps in order."
    )


def test_thinking_and_user_echo_are_dropped_from_the_canonical_spool():
    translator = CursorStreamTranslator()
    assert translator.translate({"type": "thinking", "subtype": "delta"}) == []
    assert translator.translate({"type": "user", "message": {}}) == []
    assert translator.translate("not a mapping") == []


def test_killed_turn_produces_no_terminal_event_for_the_translator():
    """cursor emits nothing terminal after a kill; synthesizing the boundary
    is the driver's job, not the translator's."""
    translator = CursorStreamTranslator()
    translator.translate(
        {
            "type": "system",
            "subtype": "init",
            "session_id": "s-1",
            "model": "Kimi K3 Max",
        }
    )
    translator.translate(_assistant("partial work"))

    assert translator.saw_turn_end is False
    assert translator.completed_work is False
    assert [event.type for event in translator.flush_text()] == ["assistant_message"]


def _assistant(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


# ---------------------------------------------------------------------------
# capability declarations
# ---------------------------------------------------------------------------


def test_cursor_capability_declaration(tmp_path):
    caps = CursorCliAdapter(repo="owner/repo", spool_root=tmp_path).capabilities()

    assert caps.executor == "cursor_cli"
    assert caps.streaming_events is True
    assert caps.partial_text is True
    assert caps.cancellation == "preemptive"
    assert caps.resume == "token"
    assert caps.usage_reporting is True
    assert caps.structured_tool_calls is True
    # A per-turn subprocess has no in-flight input channel, and nothing in
    # the spike exercised a subagent tool.
    assert caps.midturn_steering is False
    assert caps.native_subagents is False
    assert caps.engagement is False
    assert caps.reply is False
    assert caps.supports("cancellation") is True
    assert caps.supports("midturn_steering") is False


def test_pi_capability_declaration_and_engagement_shim(tmp_path):
    adapter = PiRpcAdapter(repo="owner/repo", spool_root=tmp_path, model="m")
    caps = adapter.capabilities()

    assert caps.executor == "pi_rpc"
    # Marker file only, honored at the packet boundary — never a signal.
    assert caps.cancellation == "cooperative"
    assert caps.resume == "session_file"
    assert caps.midturn_steering is True
    assert caps.native_subagents is True
    assert caps.engagement is False
    assert adapter.supports_engagement() is caps.engagement


def test_pi_dispatch_maps_a_resume_continuity_onto_its_session_file(tmp_path):
    """Resume has been implemented and unreachable since pi_rpc was written:
    no caller ever passed resume_session_file. The continuity kwarg is the
    reachable path."""
    adapter = PiRpcAdapter(repo="", spool_root=tmp_path, model="m")
    packet = _packet()

    result = _dispatch(
        adapter,
        packet,
        continuity=Continuity(mode="resume", token="/tmp/pi-session.jsonl"),
    )

    assert result.success is True
    assert result.session_ref is not None
    command = json.loads(
        (tmp_path / result.session_ref.session_id / "command.json").read_text()
    )
    assert command["resume_session_file"] == "/tmp/pi-session.jsonl"
    _kill_orchestrator(tmp_path, result.session_ref.session_id)


def test_pi_fresh_dispatch_leaves_resume_unset(tmp_path):
    adapter = PiRpcAdapter(repo="", spool_root=tmp_path, model="m")

    result = _dispatch(adapter, _packet(), continuity=FRESH)

    assert result.session_ref is not None
    command = json.loads(
        (tmp_path / result.session_ref.session_id / "command.json").read_text()
    )
    assert command["resume_session_file"] is None
    _kill_orchestrator(tmp_path, result.session_ref.session_id)


def test_resume_against_an_adapter_that_cannot_resume_is_a_hard_error(tmp_path):
    """A silent resume -> fresh substitution produces a receipt claiming
    continuity the turn never had."""
    adapter = CursorCliAdapter(repo="owner/repo", spool_root=tmp_path)
    adapter.capabilities = lambda: ExecutorCapabilities(
        executor="cursor_cli", resume="none"
    )

    with pytest.raises(CapabilityUnsupported) as excinfo:
        _dispatch(
            adapter,
            _packet(),
            continuity=Continuity(mode="resume", token="x"),
        )

    assert excinfo.value.capability == "resume"


# ---------------------------------------------------------------------------
# pi prompt byte stability (the preamble is now a parameter)
# ---------------------------------------------------------------------------


def test_pi_turn_prompt_bytes_are_unchanged_by_the_shared_builder():
    """Parameterizing the protocol zone must not move a single byte of pi's
    prompt: prefix caching discounts a byte-identical prefix, and pi's
    spools are live."""
    from adapters.pi_rpc_adapter import (
        _PACKET_PREAMBLE,
        build_executor_turn_prompt,
        build_project_zone,
    )
    from adapters.session_prompt import split_packet_zones
    from prompt_topology import TurnPrompt

    packets = [_packet().to_json_value(), _packet(attempt=3).to_json_value()]
    packets[0]["context_pointers"] = {"readme": "/repo/README.md"}
    worktree = Path("/tmp/wt-stability")

    # The pre-refactor implementation, inline.
    node_blocks = []
    envelopes = []
    for idx, packet in enumerate(packets, start=1):
        stable_zone, volatile_zone = split_packet_zones(packet)
        node_blocks.append(
            f"### NODE {idx} (authoritative GDDP NodePacket)\n{stable_zone}"
        )
        envelopes.append(
            f"### ATTEMPT ENVELOPE {idx}\n{volatile_zone}\nworktree_path: {worktree}"
        )
    turn_note = (
        f"### TURN — {len(packets)} packet(s) on the session worktree {worktree}. "
        "Worker-subagent count is the step-2 cap, not one per packet."
    )
    expected = TurnPrompt(
        protocol=_PACKET_PREAMBLE,
        project=build_project_zone(packets),
        node="\n\n".join(node_blocks),
        attempt="\n\n".join(envelopes) + f"\n\n{turn_note}\n",
    )

    actual = build_executor_turn_prompt(worktree=worktree, packets=packets)

    assert actual == expected
    assert actual.assemble() == expected.assemble()


def test_cursor_protocol_zone_never_instructs_subagent_fanout():
    """cursor_cli declares native_subagents=False. Telling an executor to use
    a capability it does not have is how a capability contract becomes
    decoration."""
    from adapters.pi_rpc_adapter import _PACKET_PREAMBLE

    prompt = build_cursor_turn_prompt(
        worktree=Path("/tmp/wt"), packets=[_packet().to_json_value()]
    )

    assert prompt.protocol != _PACKET_PREAMBLE
    lowered = prompt.assemble().lower()
    assert "subagent" not in lowered
    assert "worker" not in lowered
    assert "do not commit" in lowered


def test_cursor_prompt_keeps_the_four_zone_topology():
    packet = _packet().to_json_value()
    packet["context_pointers"] = {"readme": "/repo/README.md"}

    prompt = build_cursor_turn_prompt(worktree=Path("/tmp/wt"), packets=[packet])
    offsets = prompt.zone_offsets()

    assert prompt.assemble().startswith(prompt.protocol)
    assert offsets["protocol"][1] <= offsets["project"][0]
    assert offsets["project"][1] <= offsets["node"][0]
    assert offsets["node"][1] <= offsets["attempt"][0]
    assert "/repo/README.md" in prompt.project
    # Retry-volatile identifiers stay in the attempt zone.
    assert "job-123:attempt:2" not in prompt.protocol + prompt.project + prompt.node


# ---------------------------------------------------------------------------
# invocation shape
# ---------------------------------------------------------------------------


def test_argv_matches_the_spike_invocation():
    assert build_argv(binary="cursor-agent", prompt="P") == [
        "cursor-agent",
        "-p",
        "--trust",
        "--output-format",
        "stream-json",
        "--stream-partial-output",
        "P",
    ]
    assert build_argv(
        binary="cursor-agent", prompt="P", model="kimi-k3-max", resume_token="s-1"
    )[-5:] == ["--model", "kimi-k3-max", "--resume", "s-1", "P"]


# ---------------------------------------------------------------------------
# lifecycle against a fake cursor-agent
# ---------------------------------------------------------------------------


_FAKE_CURSOR = '''#!/usr/bin/env python3
"""Replay a recorded cursor-agent stream. Never talks to a network."""
import json
import os
import sys
import time

argv = sys.argv[1:]
record = os.environ.get("FAKE_CURSOR_ARGV")
if record:
    with open(record, "w") as handle:
        json.dump(argv, handle)

write_target = os.environ.get("FAKE_CURSOR_WRITE")
if write_target:
    with open(write_target, "w") as handle:
        handle.write("work produced by the fake executor\\n")

stderr_text = os.environ.get("FAKE_CURSOR_STDERR", "")
if stderr_text:
    sys.stderr.write(stderr_text)
    sys.stderr.flush()

lines_path = os.environ.get("FAKE_CURSOR_LINES")
if lines_path:
    with open(lines_path) as handle:
        for line in handle:
            if line.strip():
                sys.stdout.write(line if line.endswith("\\n") else line + "\\n")
                sys.stdout.flush()

sleep_s = float(os.environ.get("FAKE_CURSOR_SLEEP", "0"))
if sleep_s:
    time.sleep(sleep_s)
sys.exit(int(os.environ.get("FAKE_CURSOR_EXIT", "0")))
'''


@pytest.fixture
def fake_cursor(tmp_path, monkeypatch):
    binary = tmp_path / "fake-cursor-agent"
    binary.write_text(_FAKE_CURSOR)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    argv_record = tmp_path / "fake-argv.json"
    monkeypatch.setenv("FAKE_CURSOR_ARGV", str(argv_record))
    monkeypatch.setenv("GDDP_WORKTREE_MAP_PATH", str(tmp_path / "worktree-map.ndjson"))
    return binary, argv_record


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "checkout"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@localhost")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("# repo\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _stream_file(tmp_path: Path, events: list[dict], name="stream.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


def _successful_stream(session_id="sess-cold-1") -> list[dict]:
    return [
        {
            "type": "system",
            "subtype": "init",
            "session_id": session_id,
            "model": "Kimi K3 Max",
        },
        {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "Read_0_a",
            "tool_call": {
                "readToolCall": {"args": {"path": "README.md"}},
                "startedAtMs": "1000",
            },
        },
        {
            "type": "tool_call",
            "subtype": "completed",
            "call_id": "Read_0_a",
            "tool_call": {
                "readToolCall": {
                    "args": {"path": "README.md"},
                    "result": {"success": {"content": "# repo"}},
                },
                "startedAtMs": "1000",
                "completedAtMs": "1400",
            },
        },
        _assistant("did the work"),
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "did the work",
            "session_id": session_id,
            "duration_ms": 1200,
            "usage": {
                "inputTokens": 500,
                "outputTokens": 40,
                "cacheReadTokens": 8188,
                "cacheWriteTokens": 0,
            },
        },
    ]


def _packet(attempt: int = 2, base: str | None = None) -> NodePacket:
    return NodePacket(
        job_id="job-123",
        execution_attempt_id=f"job-123:attempt:{attempt}",
        node_id="node-456",
        title="Repair transport",
        goal="Preserve semantic intent",
        why="Executors must receive equivalent work",
        constraints=("No shell",),
        acceptance_criteria=("Packet is immutable",),
        required_artifacts=("decision.md",),
        attempt_index=attempt,
        expected_base_commit_sha=base or "abc123",
        project_id="proj",
    )


def _dispatch(adapter, packet: NodePacket, *, continuity=FRESH):
    attempt_id = f"test-{packet.execution_attempt_id.replace(':', '-')}-{time.time_ns()}"
    attempt_dir = adapter.attempt_root() / attempt_id
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "packet.json").write_text(packet.to_json())
    return adapter.dispatch(
        packet,
        attempt=AttemptContext(attempt_id=attempt_id, attempt_dir=attempt_dir),
        continuity=continuity,
    )


def _wait_for_terminal(adapter, session_ref, timeout=25.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = adapter.status(session_ref)
        if status.state in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    pytest.fail(f"cursor_cli attempt never terminalized: {adapter.status(session_ref)}")


def _kill_orchestrator(spool_root: Path, session_id: str) -> None:
    """pi dispatch spawns a real orchestrator; stop it so the test host is
    left clean."""
    for name in ("supervisor.pid", "pid"):
        try:
            pid = int((spool_root / session_id / name).read_text().strip())
        except (OSError, ValueError):
            continue
        try:
            os.killpg(pid, 15)
        except OSError:
            pass


def test_dispatch_runs_a_turn_and_hands_back_a_commit_ref(
    tmp_path, monkeypatch, repo, fake_cursor
):
    binary, argv_record = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES", str(_stream_file(tmp_path, _successful_stream()))
    )
    monkeypatch.setenv("FAKE_CURSOR_WRITE", "produced.txt")
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))

    assert result.success is True
    assert result.session_ref is not None
    assert "attempt-2" in result.session_ref.session_id
    status = _wait_for_terminal(adapter, result.session_ref)
    assert status.state == "completed"

    # R4: the handoff is a commit ref the reconciler can verify against git.
    collected = adapter.collect(result.session_ref, tmp_path / "handoff.json")
    assert collected.success is True
    assert collected.result_commit_sha
    assert collected.result_ref == "gddp/attempt-job-123-attempt-2"
    assert _git(repo, "cat-file", "-t", collected.result_commit_sha) == "commit"
    produced = _git(
        repo, "show", "--name-only", "--format=", collected.result_commit_sha
    )
    assert "produced.txt" in produced

    # Persist succeeded, so the worktree is gone.
    attempt_dir = spool / result.session_ref.session_id
    worktree = Path((attempt_dir / "worktree_path").read_text())
    assert not worktree.exists()

    argv = json.loads(argv_record.read_text())
    assert argv[:5] == ["-p", "--trust", "--output-format", "stream-json", "--stream-partial-output"]
    assert "--resume" not in argv


def test_turn_writes_canonical_events_beside_the_verbatim_stream(
    tmp_path, monkeypatch, repo, fake_cursor
):
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    raw_events = _successful_stream()
    monkeypatch.setenv("FAKE_CURSOR_LINES", str(_stream_file(tmp_path, raw_events)))
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))
    _wait_for_terminal(adapter, result.session_ref)
    attempt_dir = spool / result.session_ref.session_id

    raw_lines = [
        json.loads(line)
        for line in (attempt_dir / "raw.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert raw_lines == raw_events

    events = read_events(attempt_dir / "events.jsonl")
    assert [event.type for event in events] == [
        "turn_started",
        "session_started",
        "tool_started",
        "tool_completed",
        "assistant_message",
        "usage",
        "turn_ended",
    ]
    assert [event.seq for event in events] == [1, 2, 3, 4, 5, 6, 7]
    assert {event.session_id for event in events} == {"sess-cold-1"}
    assert len({event.turn_id for event in events}) == 1
    assert events[-1].status == "completed"

    # D14: the session id is persisted on EVERY dispatch, cold included — it
    # is the operator's only handle for a later operator_requested resume.
    assert (attempt_dir / "session_id").read_text() == "sess-cold-1"


def test_usage_and_coverage_land_in_the_attempt_dir(
    tmp_path, monkeypatch, repo, fake_cursor
):
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    readme = repo / "README.md"
    events = _successful_stream()
    events[1]["tool_call"]["readToolCall"]["args"]["path"] = str(readme)
    events[2]["tool_call"]["readToolCall"]["args"]["path"] = str(readme)
    monkeypatch.setenv("FAKE_CURSOR_LINES", str(_stream_file(tmp_path, events)))
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )
    packet = NodePacket(
        **{
            **{
                field: getattr(_packet(base=_head(repo)), field)
                for field in (
                    "job_id",
                    "execution_attempt_id",
                    "node_id",
                    "title",
                    "goal",
                    "why",
                    "constraints",
                    "acceptance_criteria",
                    "required_artifacts",
                    "attempt_index",
                    "expected_base_commit_sha",
                    "project_id",
                )
            },
            "context_pointers": {
                "readme": str(readme),
                "neighbor:node-up": "UNAVAILABLE: /cfg/node-up.yaml does not exist",
            },
        }
    )

    result = _dispatch(adapter, packet)
    _wait_for_terminal(adapter, result.session_ref)
    attempt_dir = spool / result.session_ref.session_id

    # D7: cursor's cacheReadTokens must not be silently dropped.
    report = json.loads((attempt_dir / "prompt_cache_report.json").read_text())
    assert report["actual_cached_tokens"] == 8188
    assert report["potential_reuse_tokens"] > 0

    coverage = json.loads((attempt_dir / "context_coverage.json").read_text())
    assert coverage["rating"] == "high"
    assert coverage["accessed_paths"] == [str(readme.resolve())]
    assert coverage["unavailable_pointer_keys"] == ["neighbor:node-up"]


def test_a_turn_that_never_reported_a_boundary_is_a_plumbing_failure(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """`invalid_model` produced zero events; structured status routes its retry."""
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.delenv("FAKE_CURSOR_LINES", raising=False)
    monkeypatch.setenv("FAKE_CURSOR_EXIT", "1")
    monkeypatch.setenv("FAKE_CURSOR_STDERR", "Error: model not found\n")
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))
    status = _wait_for_terminal(adapter, result.session_ref)

    assert status.state == "failed"
    assert status.plumbing is True
    assert "model not found" in (status.error or "")
    assert adapter.collect(result.session_ref, tmp_path / "nope.json").success is False

    # Even with zero harness events, the canonical spool carries a boundary.
    events = read_events(spool / result.session_ref.session_id / "events.jsonl")
    assert [event.type for event in events] == ["turn_ended"]
    assert events[0].status == "failed"

    # Nothing persisted -> the worktree survives for recovery.
    worktree = Path(
        (spool / result.session_ref.session_id / "worktree_path").read_text()
    )
    assert worktree.exists()


def test_missing_terminal_record_fails_closed_with_structured_plumbing(tmp_path):
    """A dead supervisor leaves no exit.json. status() must never report that
    as still running."""
    spool = tmp_path / "spool"
    (spool / "orphan").mkdir(parents=True)

    status = read_cursor_cli_status(spool, "orphan")

    assert status.state == "failed"
    assert status.error == "cursor_cli attempt terminal record is missing"
    assert status.plumbing is True


@pytest.mark.parametrize("session_id", ("", ".", "..", "a/b"))
def test_status_rejects_traversal_session_ids(tmp_path, session_id):
    assert read_cursor_cli_status(tmp_path, session_id).state == "failed"
    adapter = CursorCliAdapter(repo="", spool_root=tmp_path)
    assert adapter.cancel(SessionRef("cursor_cli", session_id)) is False


def test_cancel_is_preemptive_and_refuses_a_terminal_session(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """Spike: SIGTERM killed a turn in 1.16s. cancel() returning False must
    mean 'nothing left to cancel', so the operator surface stops rendering an
    exited session as 'remote may continue'."""
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES",
        str(
            _stream_file(
                tmp_path,
                [
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "sess-slow",
                        "model": "Kimi K3 Max",
                    }
                ],
            )
        ),
    )
    monkeypatch.setenv("FAKE_CURSOR_SLEEP", "60")
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if adapter.status(result.session_ref).state == "running":
            break
        time.sleep(0.05)
    else:
        pytest.fail("fake cursor-agent never reached running")

    assert adapter.cancel(result.session_ref) is True
    status = _wait_for_terminal(adapter, result.session_ref)
    assert status.state == "failed"
    assert "cancel" in (status.error or "").lower()

    events = read_events(spool / result.session_ref.session_id / "events.jsonl")
    assert events[-1].type == "turn_ended"
    assert events[-1].status == "cancelled"

    # Already terminal: nothing left to cancel.
    assert adapter.cancel(result.session_ref) is False


def test_cancel_before_launch_never_starts_the_binary(
    tmp_path, monkeypatch, repo, fake_cursor
):
    binary, argv_record = fake_cursor
    spool = tmp_path / "spool"
    attempt_dir = spool / "pending"
    attempt_dir.mkdir(parents=True)
    worktree_marker = tmp_path / "wt"
    worktree_marker.mkdir()
    (attempt_dir / "packet.json").write_text(_packet(base=_head(repo)).to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps(
            {
                "binary": str(binary),
                "model": None,
                "repo": str(repo),
                "worktree": str(worktree_marker),
                "turn_timeout_s": 30.0,
                "resume_token": None,
            }
        )
    )
    adapter = CursorCliAdapter(repo="", spool_root=spool)

    assert adapter.cancel(SessionRef("cursor_cli", "pending")) is True
    assert cursor_cli_adapter._run_attempt(attempt_dir) == 0

    assert not argv_record.exists()
    exit_state = json.loads((attempt_dir / "exit.json").read_text())
    assert exit_state["cancelled"] is True
    assert exit_state["plumbing"] is False
    assert adapter.status(SessionRef("cursor_cli", "pending")).state == "failed"


def test_resume_token_is_plumbed_only_when_continuity_says_so(
    tmp_path, monkeypatch, repo, fake_cursor
):
    binary, argv_record = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES",
        str(_stream_file(tmp_path, _successful_stream("sess-resumed"))),
    )
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(
        adapter,
        _packet(base=_head(repo)),
        continuity=Continuity(
            mode="resume", token="prior-session-uuid", reason="operator_requested"
        ),
    )
    _wait_for_terminal(adapter, result.session_ref)

    argv = json.loads(argv_record.read_text())
    assert argv[argv.index("--resume") + 1] == "prior-session-uuid"
    command = json.loads(
        (spool / result.session_ref.session_id / "command.json").read_text()
    )
    assert command["continuity_mode"] == "resume"
    assert command["continuity_reason"] == "operator_requested"


def test_unusable_resume_token_falls_back_to_a_cold_turn(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """Resume is a HINT. The cursor chat store is host-local and
    cwd-namespaced, GDDP runs every attempt in a fresh worktree path, and
    cross-cwd resume was never proven — a missing token must never fail the
    attempt."""
    binary, argv_record = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES", str(_stream_file(tmp_path, _successful_stream()))
    )
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(
        adapter,
        _packet(base=_head(repo)),
        continuity=Continuity(mode="resume", token=None, reason="token unusable"),
    )
    status = _wait_for_terminal(adapter, result.session_ref)

    assert status.state == "completed"
    argv = json.loads(argv_record.read_text())
    assert "--resume" not in argv
    command = json.loads(
        (spool / result.session_ref.session_id / "command.json").read_text()
    )
    assert command["continuity_mode"] == "fresh"


def test_dispatch_fails_cleanly_on_an_unreachable_base_commit(
    tmp_path, repo, fake_cursor
):
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base="0" * 40))

    assert result.success is False
    assert result.session_ref is None
    assert "cursor_cli dispatch failed" in (result.error or "")


def test_status_and_cancel_are_constructible_from_the_repo_alone(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """Lane 1 finding 3: the reconciler rebuilds adapters with
    adapter_cls(repo=...) only. pi_rpc raises without a model env; cursor_cli
    must not."""
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(spool))
    monkeypatch.delenv("GDDP_CURSOR_CLI_MODEL", raising=False)
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES", str(_stream_file(tmp_path, _successful_stream()))
    )
    dispatching = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )
    result = _dispatch(dispatching, _packet(base=_head(repo)))
    _wait_for_terminal(dispatching, result.session_ref)

    reconstructed = CursorCliAdapter(repo="owner/repo")

    assert reconstructed.model is None
    assert reconstructed.status(result.session_ref).state == "completed"
    assert reconstructed.collect(result.session_ref, tmp_path / "h.json").success


def test_dispatcher_routes_cursor_cli_without_a_new_env_knob(
    tmp_path, monkeypatch, repo, fake_cursor
):
    from runtime.heartbeat import dispatcher
    from runtime.heartbeat.graph_reader import EXECUTION_MODE_ADAPTERS

    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(spool))
    monkeypatch.setenv("GDDP_CURSOR_CLI_BINARY", str(binary))
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES", str(_stream_file(tmp_path, _successful_stream()))
    )
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)

    assert "cursor_cli" in EXECUTION_MODE_ADAPTERS
    assert dispatcher.executor_preflight_error("cursor_cli", "owner/repo") is None
    assert dispatcher.executor_supports_engagement("cursor_cli", "owner/repo") is False

    job = {
        "job_id": "job-123",
        "node_id": "node-456",
        "title": "T",
        "goal": "G",
        "why": "W",
        "constraints": json.dumps([]),
        "acceptance_criteria": json.dumps([]),
        "attempt": 0,
        "executor": "cursor_cli",
        "expected_base_commit_sha": _head(repo),
    }
    result = dispatcher.dispatch(job, "owner/repo", repo_path=str(repo))

    assert result.success is True
    adapter = CursorCliAdapter(repo="owner/repo", spool_root=spool)
    assert _wait_for_terminal(adapter, result.session_ref).state == "completed"


def _provider_failure_stream(session_id="sess-fail-1") -> list[dict]:
    """Unobserved live shape (spike open_risks). Uses the translator's
    recorded failure fixture: subtype != success, is_error true."""
    return [
        {
            "type": "system",
            "subtype": "init",
            "session_id": session_id,
            "model": "Kimi K3 Max",
        },
        {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "Provider error: boom",
            "session_id": session_id,
        },
    ]


def test_provider_failure_mid_turn_is_attempt_failure(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """cursor-agent exits 0 on a model/provider result that is not
    result/success. Work was not done — attempt failure, no success exit."""
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES",
        str(_stream_file(tmp_path, _provider_failure_stream())),
    )
    monkeypatch.setenv("FAKE_CURSOR_EXIT", "0")
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))
    status = _wait_for_terminal(adapter, result.session_ref)

    assert status.state == "failed"
    attempt_dir = spool / result.session_ref.session_id
    exit_state = json.loads((attempt_dir / "exit.json").read_text())
    assert exit_state["returncode"] != 0
    assert not (attempt_dir / "result.json").exists()
    ended = [event for event in read_events(attempt_dir / "events.jsonl") if event.type == "turn_ended"]
    assert ended[-1].status == "failed"
    worktree = Path((attempt_dir / "worktree_path").read_text())
    assert worktree.exists()


def test_termination_crash_after_completed_result_is_success(
    tmp_path, monkeypatch, repo, fake_cursor
):
    """Spike result/success (cold_turn) then process death: work was done.
    Success TurnOutcome; crash rides turn_ended.warning."""
    binary, _ = fake_cursor
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv(
        "FAKE_CURSOR_LINES", str(_stream_file(tmp_path, _successful_stream()))
    )
    monkeypatch.setenv("FAKE_CURSOR_WRITE", "produced.txt")
    monkeypatch.setenv("FAKE_CURSOR_EXIT", "143")
    adapter = CursorCliAdapter(
        repo="owner/repo", spool_root=spool, cwd=repo, binary=str(binary)
    )

    result = _dispatch(adapter, _packet(base=_head(repo)))
    status = _wait_for_terminal(adapter, result.session_ref)

    assert status.state == "completed"
    attempt_dir = spool / result.session_ref.session_id
    exit_state = json.loads((attempt_dir / "exit.json").read_text())
    assert exit_state["returncode"] == 0
    ended = [
        event
        for event in read_events(attempt_dir / "events.jsonl")
        if event.type == "turn_ended"
    ]
    assert len(ended) == 1
    assert ended[0].status == "completed"
    assert ended[0].warning
    assert "143" in ended[0].warning
    collected = adapter.collect(result.session_ref, tmp_path / "handoff.json")
    assert collected.success is True


def test_turn_usage_reads_the_single_terminal_record():
    """pi reports per-message usage, cursor reports exactly one terminal
    record. The scope field is what keeps them from being summed together."""
    events = translate_stream(PROBE_EVENTS)

    assert len(_by_type(events, "usage")) == 1
    usage = turn_usage(events)
    assert usage is not None
    assert usage.scope == "turn"
    assert usage.cached_input_tokens == 59408
