"""Continuity policy: cold is the structural default, resume is a hint.

The failure this guards against is a receipt that claims continuity the turn
never had. Every negative path here must return FRESH — never raise, never
fail the attempt — because the cursor chat store is host-local and
cwd-namespaced and GDDP runs every attempt in a fresh worktree path.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from adapters.executor_protocol import ExecutorCapabilities
from runtime.heartbeat.continuity_policy import (
    DEFAULT_SESSION_POLICY,
    OPERATOR_REQUESTED,
    RESUME_MARKER,
    SessionPolicy,
    choose_continuity,
    parse_session_policy,
    read_resume_request,
)

CURSOR = ExecutorCapabilities(executor="cursor_cli", resume="token")
PI = ExecutorCapabilities(executor="pi_rpc", resume="session_file")
NO_RESUME = ExecutorCapabilities(executor="jules_api")


def test_default_is_cold_with_no_marker(tmp_path):
    decision = choose_continuity(attempt_dir=tmp_path, capabilities=CURSOR)

    assert decision.mode == "fresh"
    assert decision.token is None
    assert decision.reason == "no operator resume request"


def test_operator_marker_holding_a_session_id_requests_resume(tmp_path):
    (tmp_path / RESUME_MARKER).write_text("e130cd81-dcf7-4de8-bd50-58c80d951107\n")

    decision = choose_continuity(attempt_dir=tmp_path, capabilities=CURSOR)

    assert decision.mode == "resume"
    assert decision.token == "e130cd81-dcf7-4de8-bd50-58c80d951107"
    assert decision.reason == OPERATOR_REQUESTED


def test_an_executor_that_cannot_resume_is_never_asked_to(tmp_path):
    """The runtime is responsible for not asking: CapabilityUnsupported is a
    bug-catcher, not a control-flow path."""
    (tmp_path / RESUME_MARKER).write_text("some-session")

    decision = choose_continuity(attempt_dir=tmp_path, capabilities=NO_RESUME)

    assert decision.mode == "fresh"
    assert "does not support resume" in decision.reason


@pytest.mark.parametrize("body", ("", "   \n", "{not json", '{"cwd": "/tmp"}'))
def test_an_unusable_marker_falls_back_to_cold_silently(tmp_path, body):
    (tmp_path / RESUME_MARKER).write_text(body)

    decision = choose_continuity(attempt_dir=tmp_path, capabilities=CURSOR)

    assert decision.mode == "fresh"


def test_marker_can_carry_the_cwd_and_host_the_session_was_recorded_against(tmp_path):
    (tmp_path / RESUME_MARKER).write_text(
        json.dumps(
            {
                "session_id": "sess-1",
                "cwd": str(tmp_path),
                "host": socket.gethostname(),
            }
        )
    )

    request = read_resume_request(tmp_path)
    assert request is not None
    assert request.token == "sess-1"

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, cwd=tmp_path
    )
    assert decision.mode == "resume"


def test_a_token_from_another_cwd_falls_back_to_cold(tmp_path):
    """The cursor chat store is cwd-namespaced and GDDP executes in a
    tempfile.mkdtemp worktree — a different absolute path every attempt. That
    boundary was never proven crossable."""
    (tmp_path / RESUME_MARKER).write_text(
        json.dumps({"session_id": "sess-1", "cwd": "/some/other/worktree"})
    )

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, cwd=tmp_path
    )

    assert decision.mode == "fresh"
    assert "different cwd" in decision.reason


def test_a_token_from_another_host_falls_back_to_cold(tmp_path):
    (tmp_path / RESUME_MARKER).write_text(
        json.dumps({"session_id": "sess-1", "host": "pi-big"})
    )

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, host="sab-mini"
    )

    assert decision.mode == "fresh"
    assert "pi-big" in decision.reason


def test_guards_can_be_relaxed_by_policy(tmp_path):
    (tmp_path / RESUME_MARKER).write_text(
        json.dumps({"session_id": "sess-1", "host": "pi-big", "cwd": "/elsewhere"})
    )
    policy = SessionPolicy(
        resume_when=(OPERATOR_REQUESTED,),
        require_same_cwd=False,
        require_same_host=False,
    )

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, policy=policy, host="sab-mini"
    )

    assert decision.mode == "resume"


def test_a_project_can_refuse_operator_resume_entirely(tmp_path):
    (tmp_path / RESUME_MARKER).write_text("sess-1")

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, policy=DEFAULT_SESSION_POLICY
    )

    assert decision.mode == "fresh"
    assert "project policy" in decision.reason


def test_resume_scope_never_refuses_even_a_named_trigger(tmp_path):
    (tmp_path / RESUME_MARKER).write_text("sess-1")
    policy = SessionPolicy(resume_when=(OPERATOR_REQUESTED,), resume_scope="never")

    decision = choose_continuity(
        attempt_dir=tmp_path, capabilities=CURSOR, policy=policy
    )

    assert decision.mode == "fresh"


def test_pi_resume_is_reachable_through_the_same_policy(tmp_path):
    """pi has had --session wired end to end since it was written and the
    runtime has never set it. The policy is the caller that finally can."""
    (tmp_path / RESUME_MARKER).write_text("/spool/pi-session/abc.jsonl")

    decision = choose_continuity(attempt_dir=tmp_path, capabilities=PI)

    assert decision.mode == "resume"
    assert decision.token == "/spool/pi-session/abc.jsonl"


# ---------------------------------------------------------------------------
# project.yaml session_policy parsing (defined and tested; not yet wired)
# ---------------------------------------------------------------------------


def test_absent_session_policy_takes_the_documented_defaults():
    policy = parse_session_policy(None)

    assert policy == SessionPolicy(
        default="cold",
        resume_when=(),
        resume_scope="attempt",
        require_same_cwd=True,
        require_same_host=True,
    )


def test_operator_requested_is_the_only_accepted_trigger():
    policy = parse_session_policy({"resume_when": ["operator_requested"]})

    assert policy.resume_when == ("operator_requested",)


def test_an_unknown_trigger_is_a_configuration_error_not_a_silent_cold_turn():
    with pytest.raises(ValueError) as excinfo:
        parse_session_policy({"resume_when": ["cache_economics"]})

    assert "cache_economics" in str(excinfo.value)


def test_resume_is_rejected_as_a_project_default_at_v1():
    """Resume portability is unproven: cross-cwd resume was never tested, the
    store is host-local, and retention is unknown. A project-wide default
    would assume all three."""
    with pytest.raises(ValueError) as excinfo:
        parse_session_policy({"default": "resume"})

    assert "not accepted at v1" in str(excinfo.value)


@pytest.mark.parametrize(
    "block",
    (
        {"default": "warm"},
        {"resume_when": "operator_requested"},
        {"resume_scope": "session"},
        {"require_same_cwd": "yes"},
        {"require_same_host": 1},
        ["not", "a", "mapping"],
    ),
)
def test_malformed_session_policy_blocks_raise(block):
    with pytest.raises(ValueError):
        parse_session_policy(block)
