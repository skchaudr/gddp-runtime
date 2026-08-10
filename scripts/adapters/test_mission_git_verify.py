from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.adapters.executor_protocol import SessionRef
from scripts.adapters.mission_adapter import MissionAdapter
from scripts.adapters.mission_git_verify import (
    verify_engagement_history,
    verify_git_result,
)


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _commit(repo: Path, message: str, content: str) -> str:
    (repo / "tracked.txt").write_text(content)
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Git Verifier Test")
    _git(repo, "config", "user.email", "git-verifier@example.invalid")
    return repo, _commit(repo, "root", "root\n")


def test_result_object_must_be_a_commit(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "branch", "gddp/engagement", root)
    blob = _git(repo, "hash-object", "-w", "--stdin", input_text="blob\n")
    tree = _git(repo, "write-tree")

    commit_result = verify_git_result(
        repo, base_sha=root, result_sha=root, engagement_branch="gddp/engagement"
    )
    blob_result = verify_git_result(
        repo, base_sha=root, result_sha=blob, engagement_branch="gddp/engagement"
    )
    tree_result = verify_git_result(
        repo, base_sha=root, result_sha=tree, engagement_branch="gddp/engagement"
    )

    assert commit_result.commit_exists is True
    assert commit_result.verified is True
    assert blob_result.commit_exists is False
    assert blob_result.result_object_type == "blob"
    assert blob_result.review_required is True
    assert tree_result.commit_exists is False
    assert tree_result.result_object_type == "tree"


def test_base_must_be_ancestor_of_result(tmp_path):
    repo, root = _repo(tmp_path)
    base = _commit(repo, "base line", "base\n")
    _git(repo, "switch", "-c", "gddp/engagement", root)
    divergent = _commit(repo, "divergent result", "divergent\n")

    descendant = verify_git_result(
        repo, base_sha=root, result_sha=divergent, engagement_branch="gddp/engagement"
    )
    mismatch = verify_git_result(
        repo, base_sha=base, result_sha=divergent, engagement_branch="gddp/engagement"
    )

    assert descendant.ancestry_holds is True
    assert mismatch.commit_exists is True
    assert mismatch.ancestry_holds is False
    assert mismatch.reachable is True
    assert mismatch.review_required is False
    assert mismatch.completion_quarantine_reason is None


def test_result_must_be_reachable_from_exact_engagement_branch(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "switch", "-c", "other", root)
    other_result = _commit(repo, "other result", "other\n")
    _git(repo, "branch", "gddp/engagement", root)

    reachable = verify_git_result(
        repo, base_sha=root, result_sha=root, engagement_branch="gddp/engagement"
    )
    unreachable = verify_git_result(
        repo,
        base_sha=root,
        result_sha=other_result,
        engagement_branch="gddp/engagement",
    )

    assert reachable.reachable is True
    assert unreachable.commit_exists is True
    assert unreachable.ancestry_holds is True
    assert unreachable.reachable is False
    assert unreachable.review_required is False
    assert unreachable.completion_quarantine_reason is None


def test_result_must_be_reachable_from_origin_engagement_ref(tmp_path):
    remote = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(remote))
    repo, root = _repo(tmp_path)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "switch", "-c", "gddp/engagement")
    result = _commit(repo, "feature result", "result\n")

    local_only = verify_git_result(
        repo,
        base_sha=root,
        result_sha=result,
        engagement_branch="gddp/engagement",
        origin_remote="origin",
    )

    assert local_only.reachable is True
    assert local_only.origin_reachable is False
    assert local_only.verified is False
    assert local_only.review_required is False
    assert local_only.completion_quarantine_reason is None

    _git(
        repo,
        "push",
        "origin",
        "HEAD:refs/heads/gddp/engagement",
    )
    pushed = verify_git_result(
        repo,
        base_sha=root,
        result_sha=result,
        engagement_branch="gddp/engagement",
        origin_remote="origin",
    )

    assert pushed.origin_reachable is True
    assert pushed.origin_containing_refs == ("origin/gddp/engagement",)
    assert pushed.verified is True


def test_missing_result_preserves_claim_and_routes_to_review(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "branch", "gddp/engagement", root)
    missing = "f" * 40

    verification = verify_git_result(
        repo,
        base_sha=root,
        result_sha=missing,
        engagement_branch="gddp/engagement",
    )

    assert verification.result_sha == missing
    assert verification.commit_exists is False
    assert verification.ancestry_holds is False
    assert verification.reachable is False
    assert verification.review_required is True
    assert missing in (verification.completion_quarantine_reason or "")


def test_result_commit_must_have_exact_node_trailer(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "switch", "-c", "gddp/engagement")
    wrong = _commit(
        repo,
        "complete alpha\n\nGDDP-Node-Id: node-beta",
        "wrong\n",
    )

    verification = verify_git_result(
        repo,
        base_sha=root,
        result_sha=wrong,
        engagement_branch="gddp/engagement",
        expected_node_id="node-alpha",
    )

    assert verification.trailer_node_ids == ("node-beta",)
    assert verification.trailer_matches is False
    assert verification.verified is False
    assert verification.review_required is False
    assert verification.completion_quarantine_reason is None


def test_engagement_history_is_one_topological_commit_per_node(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "switch", "-c", "gddp/engagement")
    alpha = _commit(
        repo,
        "complete alpha\n\nGDDP-Node-Id: node-alpha",
        "alpha\n",
    )
    beta = _commit(
        repo,
        "complete beta\n\nGDDP-Node-Id: node-beta",
        "beta\n",
    )

    valid = verify_engagement_history(
        repo,
        base_sha=root,
        engagement_branch="gddp/engagement",
        demanded_node_ids=("node-alpha", "node-beta"),
    )

    assert valid.verified is True
    assert valid.commit_shas == (alpha, beta)
    assert valid.node_ids == ("node-alpha", "node-beta")

    _commit(repo, "out-of-contract cleanup", "extra\n")
    invalid = verify_engagement_history(
        repo,
        base_sha=root,
        engagement_branch="gddp/engagement",
        demanded_node_ids=("node-alpha", "node-beta"),
    )

    assert invalid.verified is False
    assert invalid.completion_quarantine_reason is None


def _write_collect_fixture(
    tmp_path: Path,
    repo: Path,
    *,
    base_sha: str,
    result_sha: str,
    engagement_branch: str,
    push_result: bool = True,
) -> tuple[MissionAdapter, SessionRef]:
    if push_result:
        remote = tmp_path / "collect-origin.git"
        _git(tmp_path, "init", "--bare", str(remote))
        _git(repo, "remote", "add", "origin", str(remote))
        object_type = subprocess.run(
            ["git", "cat-file", "-t", result_sha],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if object_type.returncode == 0:
            _git(
                repo,
                "push",
                "origin",
                f"{result_sha}:refs/heads/{engagement_branch}",
            )
    mission_root = tmp_path / "factory-missions"
    mission_dir = mission_root / "mis-git"
    handoffs = mission_dir / "handoffs"
    handoffs.mkdir(parents=True)
    (mission_dir / "features.json").write_text(
        json.dumps({"features": [{"id": "node-alpha"}]})
    )
    (mission_dir / "state.json").write_text(
        json.dumps({"missionId": "mis-git", "state": "completed"})
    )
    (mission_dir / "progress_log.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-08-07T12:00:00Z",
                "type": "worker_started",
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
            }
        )
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-08-07T12:01:00Z",
                "type": "worker_completed",
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
                "successState": "success",
            }
        )
        + "\n"
    )
    (handoffs / "alpha.json").write_text(
        json.dumps(
            {
                "featureId": "node-alpha",
                "workerSessionId": "worker-alpha",
                "commitId": result_sha,
                "repoPath": str(repo),
                "successState": "success",
            }
        )
    )

    adapter = MissionAdapter(
        repo="owner/repo",
        cwd=repo,
        session_root=tmp_path / "sessions",
        mission_root=mission_root,
    )
    session_dir = adapter.session_root / "engagement"
    session_dir.mkdir(parents=True)
    receipts_path = session_dir / "receipts.jsonl"
    receipts_path.write_text(
        json.dumps(
            {
                "node_id": "node-alpha",
                "base": base_sha,
                "result": result_sha,
                "git_head": result_sha,
                "git_branch": engagement_branch,
                "git_toplevel": str(repo),
            }
        )
        + "\n"
    )
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "engagement_id": "engagement",
                "mission_dir": str(mission_dir),
                "process_pid": 999999,
                "process_returncode": 0,
                "engagement_branch": engagement_branch,
                "feature_ids": ["node-alpha"],
                "receipts_path": str(receipts_path),
            }
        )
    )
    return adapter, SessionRef("factory_mission", "engagement")


def test_collect_records_ancestry_mismatch_without_suppressing(tmp_path):
    repo, root = _repo(tmp_path)
    base = _commit(repo, "base line", "base\n")
    _git(repo, "switch", "-c", "gddp/engagement", root)
    result = _commit(
        repo,
        "divergent result\n\nGDDP-Node-Id: node-alpha",
        "result\n",
    )
    adapter, session_ref = _write_collect_fixture(
        tmp_path,
        repo,
        base_sha=base,
        result_sha=result,
        engagement_branch="gddp/engagement",
    )

    collected = adapter.collect_engagement(session_ref)[0]
    manifest = json.loads(Path(collected.evidence_manifest_path).read_text())

    assert collected.success is True
    assert collected.review_required is False
    assert collected.result_commit_sha == result
    assert collected.completion_quarantine_reason is None
    assert manifest["result_sha"] == result
    assert manifest["git_verified"]["commit_exists"] is True
    assert manifest["git_verified"]["ancestry_holds"] is False
    assert manifest["git_verified"]["reachable"] is True


def test_collect_missing_commit_preserves_claim_and_reviews(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "branch", "gddp/engagement", root)
    missing = "e" * 40
    adapter, session_ref = _write_collect_fixture(
        tmp_path,
        repo,
        base_sha=root,
        result_sha=missing,
        engagement_branch="gddp/engagement",
    )

    collected = adapter.collect_engagement(session_ref)[0]
    manifest = json.loads(Path(collected.evidence_manifest_path).read_text())

    assert collected.success is False
    assert collected.review_required is True
    assert collected.result_commit_sha == missing
    assert manifest["result_sha"] == missing
    assert manifest["git_verified"]["result_sha"] == missing
    assert manifest["git_verified"]["commit_exists"] is False


def test_collect_records_local_only_commit_without_suppressing(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "switch", "-c", "gddp/engagement")
    result = _commit(
        repo,
        "local-only result\n\nGDDP-Node-Id: node-alpha",
        "result\n",
    )
    adapter, session_ref = _write_collect_fixture(
        tmp_path,
        repo,
        base_sha=root,
        result_sha=result,
        engagement_branch="gddp/engagement",
        push_result=False,
    )

    collected = adapter.collect_engagement(session_ref)[0]
    manifest = json.loads(Path(collected.evidence_manifest_path).read_text())

    assert collected.success is True
    assert collected.review_required is False
    assert manifest["git_verified"]["origin_reachable"] is False
    assert collected.completion_quarantine_reason is None


def test_collect_records_handoff_result_disagreement(tmp_path):
    repo, root = _repo(tmp_path)
    _git(repo, "switch", "-c", "gddp/engagement")
    result = _commit(
        repo,
        "valid result\n\nGDDP-Node-Id: node-alpha",
        "result\n",
    )
    adapter, session_ref = _write_collect_fixture(
        tmp_path,
        repo,
        base_sha=root,
        result_sha=result,
        engagement_branch="gddp/engagement",
    )
    record = json.loads(
        (
            adapter.session_root
            / session_ref.session_id
            / "session.json"
        ).read_text()
    )
    handoff_path = Path(record["mission_dir"], "handoffs", "alpha.json")
    handoff = json.loads(handoff_path.read_text())
    handoff["commitId"] = root
    handoff_path.write_text(json.dumps(handoff))

    collected = adapter.collect_engagement(session_ref)[0]
    manifest = json.loads(Path(collected.evidence_manifest_path).read_text())

    assert manifest["git_verified"]["verified"] is True
    assert collected.success is True
    assert collected.review_required is False
    assert manifest["cross_check"]["receipt_matches_handoff"] is False
