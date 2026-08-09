from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from adapters.executor_protocol import (
    EngagementDispatchResult,
    ExecutorAdapter,
    NodePacket,
    SessionRef,
)
from adapters.local_subprocess_adapter import LocalSubprocessAdapter
from adapters.mission_adapter import MissionAdapter
from adapters import mission_adapter
from runtime.heartbeat import dispatcher


def _packet(node_id: str = "node-alpha") -> NodePacket:
    return NodePacket(
        job_id=f"job-{node_id}",
        execution_attempt_id=f"job-{node_id}:attempt:0",
        node_id=node_id,
        title=f"Implement {node_id}",
        goal=f"Complete {node_id}",
        why="Preserve the operator-authored intent.",
        constraints=("Only touch the requested files.",),
        acceptance_criteria=("The requested behavior works.",),
        required_artifacts=("result-summary.md",),
        attempt_index=0,
        expected_base_commit_sha="a" * 40,
    )


class _FakeProcess:
    def __init__(self, pid: int = 43210, returncode: int | None = None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode


def _make_adapter(tmp_path: Path, **kwargs) -> MissionAdapter:
    mission_root = tmp_path / "factory-missions"
    mission_root.mkdir(exist_ok=True)
    return MissionAdapter(
        repo="owner/repo",
        cwd=tmp_path,
        session_root=tmp_path / "sessions",
        mission_root=mission_root,
        mission_dir_timeout=0.1,
        **kwargs,
    )


def _create_factory_mission(adapter: MissionAdapter, name: str = "factory-id") -> Path:
    mission_dir = adapter.mission_root / name
    mission_dir.mkdir()
    return mission_dir


def test_mission_adapter_satisfies_protocol_and_engagement_extension(tmp_path):
    mission = _make_adapter(tmp_path)
    local = LocalSubprocessAdapter(
        repo="owner/repo",
        argv=(sys.executable, "-c", "pass"),
        spool_root=tmp_path / "spool",
    )

    assert isinstance(mission, ExecutorAdapter)
    assert mission.supports_engagement() is True
    assert local.supports_engagement() is False
    with pytest.raises(NotImplementedError):
        local.dispatch_engagement([_packet()])
    with pytest.raises(NotImplementedError):
        local.collect_engagement(SessionRef("local_subprocess", "unused"))


def test_dispatch_launches_exact_headless_command_and_records_identity(
    tmp_path, monkeypatch
):
    adapter = _make_adapter(tmp_path, droid_path="/opt/factory/droid")
    launched = _FakeProcess()
    popen = MagicMock(return_value=launched)

    def launch(*args, **kwargs):
        _create_factory_mission(adapter)
        return popen(*args, **kwargs)

    monkeypatch.setattr(mission_adapter, "_git_head", lambda path: None)
    monkeypatch.setattr(mission_adapter, "_process_identity", lambda pid: None)
    monkeypatch.setattr(mission_adapter.subprocess, "Popen", launch)
    result = adapter.dispatch_engagement([_packet("node-alpha"), _packet("node-beta")])

    assert isinstance(result, EngagementDispatchResult)
    assert result.success is True
    assert result.session_ref is not None
    argv = popen.call_args.args[0]
    assert argv[:3] == ["/opt/factory/droid", "exec", "--mission"]
    assert argv[3] == "-f"
    assert Path(argv[4]).name == "mission.md"
    assert argv[5:9] == ["--auto", "high", "-w", result.engagement_branch]
    assert result.engagement_branch == f"gddp/{result.engagement_id}"
    assert popen.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert Path(popen.call_args.kwargs["stdout"].name).name == "stdout"
    assert Path(popen.call_args.kwargs["stderr"].name).name == "stderr"
    assert popen.call_args.kwargs["start_new_session"] is True
    receipts_path = Path(
        popen.call_args.kwargs["env"]["GDDP_RECEIPTS_PATH"]
    )
    assert receipts_path.parent == adapter.session_root / result.engagement_id
    assert receipts_path.name == "receipts.jsonl"
    push_audit_path = Path(
        popen.call_args.kwargs["env"]["GDDP_PUSH_AUDIT_PATH"]
    )
    git_guard_dir = Path(
        popen.call_args.kwargs["env"]["PATH"].split(os.pathsep)[0]
    )
    assert push_audit_path.parent == adapter.session_root / result.engagement_id
    assert push_audit_path.name == "push-audit.jsonl"
    assert (git_guard_dir / "git").stat().st_mode & 0o111
    assert result.process_pid == launched.pid
    assert result.mission_dir == str(adapter.mission_root / "factory-id")
    assert result.feature_ids == ("node-alpha", "node-beta")

    record = json.loads(
        (adapter.session_root / result.engagement_id / "session.json").read_text()
    )
    assert record["mission_dir"] == result.mission_dir
    assert record["process_pid"] == launched.pid
    assert record["engagement_branch"] == result.engagement_branch
    assert record["feature_ids"] == ["node-alpha", "node-beta"]
    assert record["push_audit_path"] == str(push_audit_path)


def test_single_packet_dispatch_uses_engagement_lifecycle(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "dispatch_engagement",
        MagicMock(
            return_value=EngagementDispatchResult(
                success=True,
                engagement_id="eng-1",
                session_ref=SessionRef("factory_mission", "eng-1"),
                mission_dir="/missions/eng-1",
                process_pid=123,
                engagement_branch="gddp/eng-1",
                feature_ids=("node-alpha",),
            )
        ),
    )

    result = adapter.dispatch(_packet())

    assert result.success is True
    assert result.session_ref == SessionRef("factory_mission", "eng-1")


def test_dispatch_rejects_packets_with_different_expected_bases(tmp_path):
    adapter = _make_adapter(tmp_path)
    packets = [
        _packet("node-alpha"),
        replace(_packet("node-beta"), expected_base_commit_sha="b" * 40),
    ]

    result = adapter.dispatch_engagement(packets)

    assert result.success is False
    assert "one common git base" in (result.error or "")


def test_dispatch_real_git_worktree_keeps_original_branch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repo,
        check=True,
    )
    (repo / "README.md").write_text("base\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)

    mission_root = tmp_path / "factory-missions"
    mission_root.mkdir()
    fake_droid = tmp_path / "fake-droid"
    fake_droid.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "branch=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = '-w' ]; then branch=\"$2\"; shift 2; else shift; fi\n"
        "done\n"
        f"mkdir -p {mission_root}/created\n"
        "git worktree add -b \"$branch\" \"../engagement-worktree\" HEAD\n"
    )
    fake_droid.chmod(0o755)
    adapter = MissionAdapter(
        repo="owner/repo",
        cwd=repo,
        session_root=tmp_path / "sessions",
        mission_root=mission_root,
        droid_path=str(fake_droid),
        mission_dir_timeout=2,
    )

    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    result = adapter.dispatch_engagement(
        [replace(_packet(), expected_base_commit_sha=base_sha)]
    )
    assert result.success is True
    assert result.session_ref is not None
    deadline = time.monotonic() + 5
    while adapter.status(result.session_ref).state == "running":
        assert time.monotonic() < deadline
        time.sleep(0.02)

    worktrees = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert f"branch refs/heads/{result.engagement_branch}" in worktrees
    assert subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip() == "main"


def _write_session(
    adapter: MissionAdapter,
    *,
    pid: int,
    returncode: int | None,
    progress: list[dict] | None = None,
    state: str = "running",
) -> SessionRef:
    engagement_id = "eng-status"
    mission_dir = adapter.mission_root / engagement_id
    mission_dir.mkdir()
    if progress is not None:
        (mission_dir / "progress_log.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in progress)
        )
    (mission_dir / "state.json").write_text(json.dumps({"state": state}))
    session_dir = adapter.session_root / engagement_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "engagement_id": engagement_id,
                "mission_dir": str(mission_dir),
                "process_pid": pid,
                "process_identity": "Sat Aug  8 00:00:00 2026 droid exec --mission",
                "process_returncode": returncode,
                "engagement_branch": f"gddp/{engagement_id}",
                "feature_ids": ["node-alpha"],
            }
        )
    )
    return SessionRef("factory_mission", engagement_id)


def test_status_reports_live_pid_running_without_terminal_event(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=111,
        returncode=None,
        progress=[{"type": "worker_started", "featureId": "node-alpha"}],
    )
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: True)
    monkeypatch.setattr(
        mission_adapter,
        "_process_identity",
        lambda pid: "Sat Aug  8 00:00:00 2026 droid exec --mission",
    )

    assert adapter.status(ref).state == "running"


def test_status_reports_dead_zero_exit_with_terminal_event_completed(
    tmp_path, monkeypatch
):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=112,
        returncode=0,
        progress=[{"type": "mission_completed"}],
        state="running",
    )
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: False)

    assert adapter.status(ref).state == "completed"


@pytest.mark.parametrize("returncode", [None, 0])
def test_status_reports_completed_from_factory_state_without_terminal_event(
    tmp_path, monkeypatch, returncode
):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=115,
        returncode=returncode,
        progress=[{"type": "handoff_items_dismissed"}],
        state="completed",
    )
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: False)

    assert adapter.status(ref).state == "completed"


def test_status_reports_crashed_despite_stale_running_state(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=113,
        returncode=None,
        progress=[{"type": "worker_started"}],
        state="running",
    )
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: False)

    status = adapter.status(ref)
    assert status.state == "crashed"
    assert "mission_completed" in (status.error or "")


def test_status_reports_nonzero_exit_as_failed(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=114,
        returncode=17,
        progress=[{"type": "worker_started", "featureId": "node-alpha"}],
        state="running",
    )
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: False)

    status = adapter.status(ref)

    assert status.state == "failed"
    assert "exit code 17" in (status.error or "")


def test_dispatch_fails_when_process_exits_immediately_nonzero(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path, droid_path="/opt/factory/droid")
    launched = _FakeProcess(pid=55501, returncode=7)

    def launch(*args, **kwargs):
        _create_factory_mission(adapter, "early-exit")
        # Popen is mocked; write the captured streams the real process would.
        kwargs["stderr"].write(b"fatal: missing receipt tool\n")
        kwargs["stderr"].flush()
        return launched

    monkeypatch.setattr(mission_adapter, "_git_head", lambda path: None)
    monkeypatch.setattr(
        mission_adapter, "_process_identity", lambda pid: "start droid exec --mission"
    )
    monkeypatch.setattr(mission_adapter.subprocess, "Popen", launch)

    result = adapter.dispatch_engagement([_packet("node-alpha")])

    assert result.success is False
    assert result.session_ref is not None
    assert "exit code 7" in (result.error or "")
    assert "missing receipt tool" in (result.error or "")
    record = json.loads(
        (adapter.session_root / result.engagement_id / "session.json").read_text()
    )
    assert record["process_returncode"] == 7


def test_status_includes_stderr_on_failed_exit(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=116,
        returncode=9,
        progress=[],
        state="running",
    )
    session_dir = adapter.session_root / ref.session_id
    stderr_path = session_dir / "stderr"
    stderr_path.write_text("Mission initialization is blocked: tool missing\n")
    record_path = session_dir / "session.json"
    record = json.loads(record_path.read_text())
    record["stderr_path"] = str(stderr_path)
    record_path.write_text(json.dumps(record))
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: False)

    status = adapter.status(ref)

    assert status.state == "failed"
    assert "exit code 9" in (status.error or "")
    assert "tool missing" in (status.error or "")


def test_status_rejects_pid_reuse_without_launch_identity(tmp_path, monkeypatch):
    adapter = _make_adapter(tmp_path)
    ref = _write_session(
        adapter,
        pid=117,
        returncode=None,
        progress=[{"type": "worker_started"}],
        state="running",
    )
    record_path = adapter.session_root / ref.session_id / "session.json"
    record = json.loads(record_path.read_text())
    record["process_identity"] = None
    record_path.write_text(json.dumps(record))
    monkeypatch.setattr(mission_adapter, "_pid_is_running", lambda pid: True)
    monkeypatch.setattr(
        mission_adapter, "_process_identity", lambda pid: "other long-lived daemon"
    )

    status = adapter.status(ref)

    assert status.state == "crashed"


def _completed_fixture(adapter: MissionAdapter, ids: list[str]) -> SessionRef:
    ref = _write_session(adapter, pid=120, returncode=0)
    record_path = adapter.session_root / ref.session_id / "session.json"
    record = json.loads(record_path.read_text())
    record["feature_ids"] = ids
    repo = adapter.session_root.parent / "collect-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repo,
        check=True,
    )
    (repo / "tracked.txt").write_text("root\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "root"], cwd=repo, check=True)
    remote = adapter.session_root.parent / "collect-origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "switch", "-c", "gddp/eng-status"], cwd=repo, check=True
    )
    record["repo_path"] = str(repo)
    record["push_audit_path"] = str(
        Path(record["mission_dir"]) / "push-audit.jsonl"
    )
    record_path.write_text(json.dumps(record))
    mission_dir = Path(record["mission_dir"])
    state = json.loads((mission_dir / "state.json").read_text())
    state["missionId"] = "mis_collect_fixture"
    (mission_dir / "state.json").write_text(json.dumps(state))
    (mission_dir / "features.json").write_text(
        json.dumps({"features": [{"id": feature_id} for feature_id in ids]})
    )
    progress = []
    handoff_dir = mission_dir / "handoffs"
    handoff_dir.mkdir()
    receipts = []
    push_audits = []
    for index, feature_id in enumerate(ids):
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        (repo / "tracked.txt").write_text(f"{feature_id}\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"complete {feature_id}",
                "-m",
                f"GDDP-Node-Id: {feature_id}",
            ],
            cwd=repo,
            check=True,
        )
        result_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "push",
                "origin",
                "HEAD:refs/heads/gddp/eng-status",
            ],
            cwd=repo,
            check=True,
        )
        worker_id = f"worker-{index}"
        progress.extend(
            [
                {
                    "timestamp": f"2026-08-07T00:0{index}:00Z",
                    "type": "worker_started",
                    "featureId": feature_id,
                    "workerSessionId": worker_id,
                },
                {
                    "timestamp": f"2026-08-07T00:0{index}:30Z",
                    "type": "worker_completed",
                    "featureId": feature_id,
                    "workerSessionId": worker_id,
                    "commitId": result_sha,
                    "successState": "success",
                },
            ]
        )
        (handoff_dir / f"{index}.json").write_text(
            json.dumps(
                {
                    "featureId": feature_id,
                    "workerSessionId": worker_id,
                    "commitId": result_sha,
                    "repoPath": str(repo),
                    "successState": "success",
                }
            )
        )
        receipts.append(
            {
                "node_id": feature_id,
                "base": base_sha,
                "result": result_sha,
                "git_head": result_sha,
                "git_branch": "gddp/eng-status",
                "git_toplevel": str(repo),
            }
        )
        push_audits.append(
            {
                "argv": [
                    "git",
                    "push",
                    "origin",
                    "HEAD:refs/heads/gddp/eng-status",
                ],
                "allowed": True,
                "reason": None,
                "engagement_branch": "gddp/eng-status",
                "commit_sha": result_sha,
                "origin_containing_refs": ["origin/gddp/eng-status"],
                "returncode": 0,
                "timestamp_utc": f"2026-08-07T00:0{index}:20Z",
            }
        )
    (mission_dir / "progress_log.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in progress)
    )
    (mission_dir / "receipts.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in receipts)
    )
    Path(record["push_audit_path"]).write_text(
        "".join(json.dumps(item) + "\n" for item in push_audits)
    )
    return ref


def _interrupt_beta(adapter: MissionAdapter, ref: SessionRef) -> tuple[dict, Path]:
    record_path = adapter.session_root / ref.session_id / "session.json"
    record = json.loads(record_path.read_text())
    record["process_returncode"] = None
    record_path.write_text(json.dumps(record))
    mission_dir = Path(record["mission_dir"])
    state = json.loads((mission_dir / "state.json").read_text())
    state["state"] = "running"
    (mission_dir / "state.json").write_text(json.dumps(state))

    (mission_dir / "handoffs" / "1.json").unlink()
    receipt_lines = [
        line
        for line in (mission_dir / "receipts.jsonl").read_text().splitlines()
        if json.loads(line)["node_id"] != "node-beta"
    ]
    (mission_dir / "receipts.jsonl").write_text(
        "".join(line + "\n" for line in receipt_lines)
    )
    progress = [
        json.loads(line)
        for line in (mission_dir / "progress_log.jsonl").read_text().splitlines()
        if json.loads(line).get("featureId") != "node-beta"
    ]
    progress.append(
        {
            "timestamp": "2026-08-07T00:10:00Z",
            "type": "worker_started",
            "featureId": "node-beta",
            "workerSessionId": "worker-beta",
        }
    )
    (mission_dir / "progress_log.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in progress)
    )
    return record, mission_dir


def test_collect_fans_out_node_scoped_results_with_manifests(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])

    results = adapter.collect_engagement(ref)
    record = json.loads(
        (adapter.session_root / ref.session_id / "session.json").read_text()
    )
    receipts = [
        json.loads(line)
        for line in Path(record["mission_dir"], "receipts.jsonl")
        .read_text()
        .splitlines()
    ]

    assert [result.feature_id for result in results] == ["node-alpha", "node-beta"]
    assert [result.result_commit_sha for result in results] == [
        receipt["result"] for receipt in receipts
    ]
    assert {result.result_ref for result in results} == {"gddp/eng-status"}
    for result in results:
        assert result.success is True
        assert result.evidence_manifest_path
        manifest = json.loads(Path(result.evidence_manifest_path).read_text())
        assert manifest["feature_id"] == result.feature_id
        assert manifest["result_sha"] == result.result_commit_sha
        assert manifest["mission_id"] == "mis_collect_fixture"
        assert manifest["receipt"]["node_id"] == result.feature_id
        assert manifest["handoff"]["commitId"] == result.result_commit_sha
        assert manifest["progress"]["outcome"] == "success"
        assert manifest["git_verified"]["verified"] is True
        assert manifest["push_verification"]["verified"] is True


def test_collect_requires_an_individual_successful_push_for_each_feature(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    record = json.loads(
        (adapter.session_root / ref.session_id / "session.json").read_text()
    )
    audit_path = Path(record["push_audit_path"])
    only_beta = [
        line
        for line in audit_path.read_text().splitlines()
        if json.loads(line)["commit_sha"]
        != json.loads(
            Path(record["mission_dir"], "handoffs", "0.json").read_text()
        )["commitId"]
    ]
    audit_path.write_text("".join(line + "\n" for line in only_beta))

    alpha, beta = adapter.collect_engagement(ref)

    assert alpha.success is False
    assert alpha.review_required is True
    alpha_manifest = json.loads(Path(alpha.evidence_manifest_path).read_text())
    assert alpha_manifest["push_verification"]["verified"] is False
    assert "feature_push_not_verified" in (alpha.error or "")
    assert beta.success is True


def test_collect_rejects_push_recorded_after_feature_reported_success(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha"])
    record = json.loads(
        (adapter.session_root / ref.session_id / "session.json").read_text()
    )
    audit_path = Path(record["push_audit_path"])
    audit = json.loads(audit_path.read_text())
    audit["timestamp_utc"] = "2026-08-07T00:00:40Z"
    audit_path.write_text(json.dumps(audit) + "\n")

    result = adapter.collect_engagement(ref)[0]
    manifest = json.loads(Path(result.evidence_manifest_path).read_text())

    assert result.success is False
    assert manifest["progress"]["completed_at"] == "2026-08-07T00:00:30Z"
    assert manifest["push_verification"]["verified"] is False
    assert "feature_push_not_verified" in (result.error or "")


def test_crash_collection_keeps_completed_evidence_and_reviews_partial_node(
    tmp_path,
):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    _record, _mission_dir = _interrupt_beta(adapter, ref)

    alpha, beta = adapter.collect_engagement(ref)

    assert alpha.success is True
    alpha_manifest = json.loads(Path(alpha.evidence_manifest_path).read_text())
    assert alpha_manifest["git_verified"]["verified"] is True
    assert alpha_manifest["mission_outcome"] == "crashed"
    assert beta.success is False
    assert beta.review_required is True
    beta_manifest = json.loads(Path(beta.evidence_manifest_path).read_text())
    assert beta_manifest["result_sha"] is None
    assert beta_manifest["mission_failure_reason"]
    assert "crashed" in (beta.error or "")


def test_nonzero_exit_preserves_completed_evidence_and_records_failure(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    record, _mission_dir = _interrupt_beta(adapter, ref)
    record["process_returncode"] = 23
    record_path = adapter.session_root / ref.session_id / "session.json"
    record_path.write_text(json.dumps(record))

    alpha, beta = adapter.collect_engagement(ref)

    assert alpha.success is True
    assert beta.review_required is True
    beta_manifest = json.loads(Path(beta.evidence_manifest_path).read_text())
    assert beta_manifest["mission_outcome"] == "failed"
    assert beta_manifest["mission_process"]["exit_code"] == 23
    assert "exit code 23" in beta_manifest["mission_failure_reason"]


def test_failed_feature_handoff_routes_only_that_node_to_review(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    record_path = adapter.session_root / ref.session_id / "session.json"
    record = json.loads(record_path.read_text())
    record["process_returncode"] = 0
    record_path.write_text(json.dumps(record))
    mission_dir = Path(record["mission_dir"])
    with (mission_dir / "progress_log.jsonl").open("a") as progress:
        progress.write(json.dumps({"type": "mission_completed"}) + "\n")
    handoff_path = mission_dir / "handoffs" / "0.json"
    handoff = json.loads(handoff_path.read_text())
    handoff["successState"] = "failure"
    handoff_path.write_text(json.dumps(handoff))

    alpha, beta = adapter.collect_engagement(ref)

    assert alpha.success is False
    assert alpha.review_required is True
    manifest = json.loads(Path(alpha.evidence_manifest_path).read_text())
    assert manifest["handoff"]["successState"] == "failure"
    assert "handoff_failure" in (alpha.error or "")
    assert beta.success is True


def test_dirty_crash_worktree_is_reported_without_becoming_a_result(tmp_path):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    record, _mission_dir = _interrupt_beta(adapter, ref)
    repo = Path(record["repo_path"])
    (repo / "tracked.txt").write_text("interrupted tracked edit\n")
    (repo / "untracked-draft.txt").write_text("partial work\n")

    alpha, beta = adapter.collect_engagement(ref)

    alpha_manifest = json.loads(Path(alpha.evidence_manifest_path).read_text())
    beta_manifest = json.loads(Path(beta.evidence_manifest_path).read_text())
    assert alpha.success is True
    assert alpha_manifest["worktree"]["dirty"] is True
    assert beta.review_required is True
    assert beta.result_commit_sha is None
    assert beta_manifest["worktree"]["changed_paths"] == [
        "tracked.txt",
        "untracked-draft.txt",
    ]
    assert "dirty_worktree" in (beta.error or "")


@pytest.mark.parametrize(
    "observed",
    [
        ["node-alpha"],
        ["node-alpha", "node-beta", "extra"],
        ["node-alpha", "renamed"],
        ["node-alpha", "node-alpha"],
        ["node-beta", "node-alpha"],
        ["Node-alpha", "node-beta"],
    ],
)
def test_collect_routes_feature_id_drift_to_review(tmp_path, observed):
    adapter = _make_adapter(tmp_path)
    ref = _completed_fixture(adapter, ["node-alpha", "node-beta"])
    record = json.loads(
        (adapter.session_root / ref.session_id / "session.json").read_text()
    )
    Path(record["mission_dir"], "features.json").write_text(
        json.dumps({"features": [{"id": feature_id} for feature_id in observed]})
    )

    results = adapter.collect_engagement(ref)

    assert len(results) == 2
    assert all(not result.success for result in results)
    assert all(result.review_required for result in results)
    assert all("Feature id drift" in (result.error or "") for result in results)
    assert all(result.result_commit_sha is None for result in results)


def test_cancel_kills_only_captured_process_group_and_preserves_evidence(tmp_path):
    adapter = _make_adapter(tmp_path)
    captured = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "time.sleep(30)"
            ),
        ],
        start_new_session=True,
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    ref = _write_session(adapter, pid=captured.pid, returncode=None)
    record_path = adapter.session_root / ref.session_id / "session.json"
    record = json.loads(record_path.read_text())
    record["process_identity"] = mission_adapter._process_identity(captured.pid)
    record_path.write_text(json.dumps(record))
    sentinel = Path(record["mission_dir"], "sentinel.txt")
    sentinel.write_text("evidence")

    try:
        assert adapter.cancel(ref) is True
        deadline = time.monotonic() + 5
        while captured.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert captured.poll() is not None
        assert unrelated.poll() is None
        assert sentinel.read_text() == "evidence"
        updated = json.loads(
            (adapter.session_root / ref.session_id / "session.json").read_text()
        )
        assert updated["cancelled"] is True
    finally:
        if captured.poll() is None:
            os.killpg(captured.pid, signal.SIGKILL)
        if unrelated.poll() is None:
            os.killpg(unrelated.pid, signal.SIGTERM)
        captured.wait(timeout=5)
        unrelated.wait(timeout=5)


def test_dispatcher_batches_jobs_through_engagement_capability(
    tmp_path, monkeypatch
):
    adapter = MagicMock()
    adapter.supports_engagement.return_value = True
    adapter.dispatch_engagement.return_value = EngagementDispatchResult(
        success=True,
        engagement_id="eng-batch",
        session_ref=SessionRef("factory_mission", "eng-batch"),
        feature_ids=("node-alpha", "node-beta"),
    )
    monkeypatch.setattr(
        dispatcher,
        "_build_adapter",
        lambda *args, **kwargs: adapter,
    )
    jobs = [
        {
            "job_id": f"job-{node_id}",
            "node_id": node_id,
            "title": node_id,
            "goal": node_id,
            "why": "why",
            "constraints": "[]",
            "acceptance_criteria": "[]",
            "required_artifacts": "[]",
            "attempt": 0,
            "executor": "factory_mission",
        }
        for node_id in ("node-alpha", "node-beta")
    ]

    result = dispatcher.dispatch_engagement(
        jobs, "owner/repo", str(tmp_path)
    )

    assert result.success is True
    packets = adapter.dispatch_engagement.call_args.args[0]
    assert [packet.node_id for packet in packets] == ["node-alpha", "node-beta"]
    assert all(isinstance(packet, NodePacket) for packet in packets)


def test_dispatch_inserts_model_flag_when_configured(tmp_path, monkeypatch):
    adapter = _make_adapter(
        tmp_path,
        droid_path="/opt/factory/droid",
        model="custom:Grok-4.5-sub-(Hermes)-0",
    )
    launched = _FakeProcess()
    popen = MagicMock(return_value=launched)

    def launch(*args, **kwargs):
        _create_factory_mission(adapter)
        return popen(*args, **kwargs)

    monkeypatch.setattr(mission_adapter, "_git_head", lambda path: None)
    monkeypatch.setattr(mission_adapter, "_process_identity", lambda pid: None)
    monkeypatch.setattr(mission_adapter.subprocess, "Popen", launch)
    adapter.dispatch_engagement([_packet("node-alpha")])

    argv = popen.call_args.args[0]
    assert "-m" in argv
    assert argv[argv.index("-m") + 1] == "custom:Grok-4.5-sub-(Hermes)-0"


def test_dispatch_omits_model_flag_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("GDDP_MISSION_MODEL", raising=False)
    adapter = _make_adapter(tmp_path, droid_path="/opt/factory/droid")
    launched = _FakeProcess()
    popen = MagicMock(return_value=launched)

    def launch(*args, **kwargs):
        _create_factory_mission(adapter)
        return popen(*args, **kwargs)

    monkeypatch.setattr(mission_adapter, "_git_head", lambda path: None)
    monkeypatch.setattr(mission_adapter, "_process_identity", lambda pid: None)
    monkeypatch.setattr(mission_adapter.subprocess, "Popen", launch)
    adapter.dispatch_engagement([_packet("node-alpha")])

    argv = popen.call_args.args[0]
    assert "-m" not in argv


def test_adapter_model_defaults_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GDDP_MISSION_MODEL", "custom:env-model-0")

    adapter = _make_adapter(tmp_path)

    assert adapter.model == "custom:env-model-0"
