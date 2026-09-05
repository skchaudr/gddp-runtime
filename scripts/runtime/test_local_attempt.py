"""Executor-neutral local-attempt runtime contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.executor_protocol import NodePacket
from runtime import local_attempt


def _packet(base: str = "abc123") -> NodePacket:
    return NodePacket(
        job_id="job/one",
        execution_attempt_id="job/one:attempt:3",
        node_id="node one",
        title="T",
        goal="G",
        why="W",
        constraints=(),
        acceptance_criteria=(),
        required_artifacts=(),
        attempt_index=3,
        expected_base_commit_sha=base,
    )


def _write_supervisor_inputs(attempt_dir: Path, worktree: Path, repo: Path) -> None:
    attempt_dir.mkdir()
    (attempt_dir / "packet.json").write_text(_packet().to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps({"worktree": str(worktree), "repo": str(repo)})
    )


def test_attempt_dir_path_validation():
    attempt_id = "job-one-attempt-3-deadbeef"
    assert local_attempt.attempt_dir_for(Path("/spool"), attempt_id) == (
        Path("/spool") / attempt_id
    )
    assert local_attempt.attempt_dir_for(Path("/spool"), "../escape") is None
    assert local_attempt.attempt_dir_for(Path("/spool"), "") is None


def test_resolve_attempt_spool_root_precedence(monkeypatch, tmp_path):
    canonical = tmp_path / "canonical"
    legacy = tmp_path / "legacy"
    family = tmp_path / "family"
    monkeypatch.setenv("GDDP_ATTEMPT_SPOOL_DIR", str(canonical))
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(legacy))
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(family))

    assert local_attempt.resolve_attempt_spool_root(
        legacy_env="GDDP_CURSOR_CLI_SPOOL_DIR"
    ) == canonical.resolve()
    assert local_attempt.resolve_attempt_spool_root(
        tmp_path / "explicit", legacy_env="GDDP_CURSOR_CLI_SPOOL_DIR"
    ) == (tmp_path / "explicit").resolve()


def test_resolve_attempt_spool_root_legacy_then_family(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy"
    family = tmp_path / "family"
    monkeypatch.delenv("GDDP_ATTEMPT_SPOOL_DIR", raising=False)
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(legacy))
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(family))

    assert local_attempt.resolve_attempt_spool_root(
        legacy_env="GDDP_CURSOR_CLI_SPOOL_DIR"
    ) == legacy.resolve()
    monkeypatch.delenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", raising=False)
    assert local_attempt.resolve_attempt_spool_root(
        legacy_env="GDDP_CURSOR_CLI_SPOOL_DIR"
    ) == family.resolve()


def test_locate_attempt_dir_prefers_recorded_then_historical(tmp_path):
    recorded = tmp_path / "recorded" / "att-1"
    recorded.mkdir(parents=True)
    historical = tmp_path / "jobs" / "cursor-cli-spool" / "att-1"
    historical.mkdir(parents=True)
    canonical = tmp_path / "jobs" / "local-subprocess-spool"
    canonical.mkdir(parents=True)

    assert local_attempt.locate_attempt_dir(
        "att-1",
        spool_root=canonical,
        recorded_dir=recorded,
        runtime_root=tmp_path,
    ) == recorded.resolve()
    assert local_attempt.locate_attempt_dir(
        "att-1",
        spool_root=canonical,
        runtime_root=tmp_path,
    ) == historical.resolve()


def test_exit_state_drives_structured_plumbing_without_error_prose(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    local_attempt.write_exit_state(
        attempt_dir,
        local_attempt.ExitState(
            returncode=17,
            cancelled=False,
            plumbing=True,
            error="provider initialization failed",
        ),
    )

    status = local_attempt.read_attempt_status(
        tmp_path, "attempt", executor="neutral_test"
    )

    assert status.state == "failed"
    assert status.error == "provider initialization failed"
    assert status.plumbing is True


def test_invalid_exit_state_is_structured_plumbing(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    (attempt_dir / "exit.json").write_text("{")

    status = local_attempt.read_attempt_status(
        tmp_path, "attempt", executor="neutral_test"
    )

    assert status.state == "failed"
    assert status.plumbing is True


def test_result_handoff_decoder_has_success_and_recovery_shapes(tmp_path):
    success = local_attempt.decode_result_handoff(
        {
            "result_commit_sha": "deadbeef",
            "result_ref": "gddp/attempt-1",
            "worktree_path": None,
        },
        patch_path=tmp_path / "handoff.json",
        executor="neutral_test",
    )
    failure = local_attempt.decode_result_handoff(
        {
            "result_commit_sha": None,
            "worktree_path": "/tmp/recover-me",
            "error": "persist broke",
        },
        patch_path=tmp_path / "handoff.json",
        executor="neutral_test",
    )

    assert success.success is True
    assert success.result_commit_sha == "deadbeef"
    assert failure.success is False
    assert failure.worktree_path == "/tmp/recover-me"
    assert failure.error == "persist broke"


def test_persisted_result_licenses_worktree_removal(
    tmp_path, monkeypatch
):
    from local_agent_executor import persist_result, remove_worktree

    attempt_dir = tmp_path / "attempt"
    worktree = tmp_path / "worktree"
    repo = tmp_path / "repo"
    worktree.mkdir()
    repo.mkdir()
    _write_supervisor_inputs(attempt_dir, worktree, repo)
    removed: list[tuple[Path, Path]] = []

    monkeypatch.setattr(
        "local_agent_executor.persist_result",
        lambda selected_worktree, packet: {
            "schema": "gddp.local_result.v1",
            "result_commit_sha": "deadbeef",
            "result_ref": "gddp/attempt-1",
            "worktree_path": None,
        },
    )
    monkeypatch.setattr(
        "local_agent_executor.remove_worktree",
        lambda selected_repo, selected_worktree: removed.append(
            (selected_repo, selected_worktree)
        ),
    )

    result = local_attempt.run_attempt_supervisor(
        attempt_dir,
        run_turn=lambda *_args: local_attempt.TurnOutcome(returncode=0),
    )

    assert result == 0
    assert removed == [(repo, worktree)]
    assert json.loads((attempt_dir / "exit.json").read_text())["returncode"] == 0
    assert json.loads((attempt_dir / "result.json").read_text())[
        "result_commit_sha"
    ] == "deadbeef"

    monkeypatch.setattr("local_agent_executor.persist_result", persist_result)
    monkeypatch.setattr("local_agent_executor.remove_worktree", remove_worktree)


def test_persist_failure_keeps_worktree(tmp_path, monkeypatch):
    attempt_dir = tmp_path / "attempt"
    worktree = tmp_path / "worktree"
    repo = tmp_path / "repo"
    worktree.mkdir()
    repo.mkdir()
    _write_supervisor_inputs(attempt_dir, worktree, repo)
    removed: list[Path] = []

    monkeypatch.setattr(
        "local_agent_executor.persist_result",
        lambda selected_worktree, packet: {
            "schema": "gddp.local_result.v1",
            "result_commit_sha": None,
            "result_ref": None,
            "worktree_path": str(selected_worktree),
            "error": "persist broke",
        },
    )
    monkeypatch.setattr(
        "local_agent_executor.remove_worktree",
        lambda _repo, selected_worktree: removed.append(selected_worktree),
    )

    local_attempt.run_attempt_supervisor(
        attempt_dir,
        run_turn=lambda *_args: local_attempt.TurnOutcome(returncode=0),
    )

    assert removed == []
    exit_state = json.loads((attempt_dir / "exit.json").read_text())
    assert exit_state["returncode"] == 1
    assert exit_state["plumbing"] is False
    assert str(worktree) in exit_state["error"]


def test_canonical_failed_terminal_overrides_zero_turn_outcome(
    tmp_path, monkeypatch
):
    """Executor-neutral backstop: last turn_ended status=failed is attempt
    failure even when TurnOutcome.returncode is 0."""
    attempt_dir = tmp_path / "attempt"
    worktree = tmp_path / "worktree"
    repo = tmp_path / "repo"
    worktree.mkdir()
    repo.mkdir()
    _write_supervisor_inputs(attempt_dir, worktree, repo)
    (attempt_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "v": 1,
                "ts": "1970-01-01T00:00:00.000Z",
                "executor": "neutral_test",
                "session_id": "s",
                "turn_id": "t",
                "seq": 1,
                "type": "turn_ended",
                "raw_type": "",
                "status": "failed",
                "error": "provider exploded",
            }
        )
        + "\n"
    )
    persisted: list[Path] = []
    removed: list[Path] = []

    monkeypatch.setattr(
        "local_agent_executor.persist_result",
        lambda selected_worktree, packet: persisted.append(selected_worktree)
        or {
            "schema": "gddp.local_result.v1",
            "result_commit_sha": "deadbeef",
            "result_ref": "gddp/attempt-1",
            "worktree_path": None,
        },
    )
    monkeypatch.setattr(
        "local_agent_executor.remove_worktree",
        lambda _repo, selected_worktree: removed.append(selected_worktree),
    )

    result = local_attempt.run_attempt_supervisor(
        attempt_dir,
        run_turn=lambda *_args: local_attempt.TurnOutcome(returncode=0),
    )

    assert result == 0
    assert persisted == []
    assert removed == []
    exit_state = json.loads((attempt_dir / "exit.json").read_text())
    assert exit_state["returncode"] == 1
    assert exit_state["plumbing"] is False
    assert "provider exploded" in exit_state["error"]
    assert not (attempt_dir / "result.json").exists()
    assert worktree.exists()
