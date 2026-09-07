"""
test_base_chaining.py — Provisional base-chaining at dispatch.

A node whose dependency is provisional must build on that dependency's
recorded result commit, not on HEAD — the dependency's work is not merged
yet. Multiple provisional deps refuse; complete deps leave base at HEAD.

Selection requires:
1. Candidate query scoped to project_id and node_id.
2. Terminal evaluated sessions only.
3. Persisted results.acceptance_check points to a receipt that passes
   read_validated_receipt subject binding and receipt_admits gate.
4. Newest validated passing candidate selected (tie-broken by updated_at / session_db_id).
   A later failed or incomplete attempt cannot replace an older valid pass.
5. Admitted SHA must exist as a commit in the declared repository; missing commit defers.
6. Ancestor-of-HEAD optimization uses HEAD only after receipt validation.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.runtime.heartbeat.runner import _chained_base
from scripts.runtime.verification.schemas import Verdict
from scripts.runtime.verification.test_admission import make_receipt_fixture

HEAD = "h" * 40
RESULT_A = "a" * 40
RESULT_B = "b" * 40
RESULT_C = "c" * 40


@pytest.fixture()
def con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            attempt INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            expected_base_commit_sha TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            executor TEXT NOT NULL,
            session_id TEXT NOT NULL,
            state TEXT DEFAULT 'dispatched',
            execution_attempt_id TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            expected_base_commit_sha TEXT,
            result_commit_sha TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE results (
            result_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL DEFAULT '1.0',
            job_id TEXT NOT NULL,
            executor TEXT NOT NULL,
            received_at TEXT NOT NULL,
            execution_duration_seconds INTEGER,
            outcome TEXT NOT NULL,
            status TEXT NOT NULL,
            changed_files TEXT,
            patch_path TEXT,
            summary_path TEXT,
            logs_path TEXT,
            acceptance_check TEXT,
            risks TEXT,
            followup_candidates TEXT,
            github_action TEXT
        );
        """
    )
    yield con
    con.close()


def _git(repo: Path | str, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _init_repo(path: Path) -> tuple[str, str]:
    """Init a git repo and create two commits (parent_sha and tip_sha)."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / "f.txt").write_text("one")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "parent result")
    parent_sha = _git(path, "rev-parse", "HEAD")
    (path / "f.txt").write_text("two")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "sibling result")
    tip_sha = _git(path, "rev-parse", "HEAD")
    return parent_sha, tip_sha


@pytest.fixture()
def chain_repo(tmp_path: Path):
    """A repo with HEAD two commits past the dep's result commit."""
    repo = tmp_path / "repo"
    parent_sha, tip_sha = _init_repo(repo)
    return str(repo), parent_sha, tip_sha


@pytest.fixture()
def two_repos(tmp_path: Path):
    """Two isolated repositories for cross-project testing."""
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    p1_parent, p1_tip = _init_repo(repo1)
    p2_parent, p2_tip = _init_repo(repo2)
    return (str(repo1), p1_parent, p1_tip), (str(repo2), p2_parent, p2_tip)


def _reader(statuses: dict[str, str]):
    nodes = [{"id": nid, "status": s} for nid, s in statuses.items()]
    return SimpleNamespace(
        load_project=lambda project_id: SimpleNamespace(nodes=nodes)
    )


def _node(*deps: str):
    return SimpleNamespace(depends_on=list(deps))


def _record_session_with_receipt(
    con: sqlite3.Connection,
    receipt_dir: Path,
    *,
    project_id: str = "proj",
    node_id: str = "dep-a",
    job_id: str | None = None,
    attempt_index: int = 0,
    result_sha: str = RESULT_A,
    expected_base_sha: str | None = HEAD,
    state: str = "evaluated",
    updated_at: str = "2026-07-30T00:00:00",
    verdict: Verdict | str = Verdict.PASS,
    criteria_verdict: Verdict | str | None = Verdict.PASS,
    completeness_status: str = "complete",
    intent_preserved: bool = True,
    graph_integrity_preserved: bool = True,
    required_human_review: bool = False,
    corrupt_receipt_json: bool = False,
    receipt_mutation: dict | None = None,
    omit_receipt: bool = False,
    omit_result_row: bool = False,
) -> tuple[str, str, Path | None]:
    if job_id is None:
        job_id = f"job_{project_id}_{node_id}_{result_sha[:6]}"
    session_db_id = f"ses_{job_id}_{attempt_index}"
    exec_attempt_id = f"{job_id}:attempt:{attempt_index}"

    con.execute(
        """
        INSERT INTO jobs (job_id, project_id, node_id, attempt, status,
                          expected_base_commit_sha, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'ready', ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            attempt = excluded.attempt,
            updated_at = excluded.updated_at
        """,
        (job_id, project_id, node_id, attempt_index, expected_base_sha, updated_at, updated_at),
    )

    con.execute(
        """
        INSERT INTO executor_sessions (
            session_db_id, job_id, executor, session_id, state,
            execution_attempt_id, attempt_index, expected_base_commit_sha,
            result_commit_sha, created_at, updated_at
        ) VALUES (?, ?, 'test_exec', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_db_id,
            job_id,
            f"session_{session_db_id}",
            state,
            exec_attempt_id,
            attempt_index,
            expected_base_sha,
            result_sha,
            updated_at,
            updated_at,
        ),
    )

    receipt_path: Path | None = None
    if not omit_receipt:
        receipt_path = receipt_dir / project_id / f"{node_id}_{session_db_id}.json"
        make_receipt_fixture(
            receipt_path,
            project_id=project_id,
            node_id=node_id,
            job_id=job_id,
            execution_attempt_id=exec_attempt_id,
            result_commit_sha=result_sha,
            expected_base_commit_sha=expected_base_sha,
            verdict=verdict,
            criteria_verdict=criteria_verdict,
            completeness_status=completeness_status,
            intent_preserved=intent_preserved,
            graph_integrity_preserved=graph_integrity_preserved,
            required_human_review=required_human_review,
        )
        if corrupt_receipt_json:
            receipt_path.write_text("{corrupt: json syntax error", encoding="utf-8")
        elif receipt_mutation:
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
            data.update(receipt_mutation)
            receipt_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    if not omit_result_row:
        acceptance_dict: dict = {}
        if receipt_path is not None:
            acceptance_dict["receipt_path"] = str(receipt_path)
            acceptance_dict["verdict"] = (
                verdict.value if isinstance(verdict, Verdict) else str(verdict)
            )
        outcome = (
            "pass"
            if verdict in (Verdict.PASS, "pass")
            and intent_preserved
            and not required_human_review
            else "fail"
        )
        con.execute(
            """
            INSERT INTO results (
                result_id, schema_version, job_id, executor, received_at,
                outcome, status, acceptance_check
            ) VALUES (?, '1.0', ?, 'test_exec', ?, ?, 'awaiting_review', ?)
            """,
            (
                f"res_{session_db_id}",
                job_id,
                updated_at,
                outcome,
                json.dumps(acceptance_dict) if acceptance_dict else None,
            ),
        )

    return job_id, session_db_id, receipt_path


def test_no_deps_uses_head(con):
    base, reason = _chained_base(con, _node(), "proj", _reader({}), HEAD)
    assert base == HEAD and reason is None


def test_complete_dep_uses_head(con):
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "complete"}), HEAD
    )
    assert base == HEAD and reason is None


def test_provisional_dep_chains_to_its_result(con, chain_repo, tmp_path):
    repo, parent_sha, _ = chain_repo
    _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-a", result_sha=parent_sha
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base == parent_sha and reason is None


def test_newest_valid_result_wins_over_newer_failed(con, chain_repo, tmp_path):
    """An older valid passing candidate is selected over a newer failed attempt."""
    repo, parent_sha, tip_sha = chain_repo
    # Attempt 0: older valid passing result A
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=0,
        result_sha=parent_sha,
        updated_at="2026-07-29T00:00:00",
        verdict=Verdict.PASS,
        criteria_verdict=Verdict.PASS,
        intent_preserved=True,
    )
    # Attempt 1: newer failed result B (integrity fail / verdict fail)
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=1,
        result_sha=tip_sha,
        updated_at="2026-07-30T00:00:00",
        verdict=Verdict.FAIL,
        criteria_verdict=Verdict.FAIL,
        intent_preserved=False,
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base == parent_sha and reason is None


def test_newest_valid_result_wins_over_newer_incomplete(con, chain_repo, tmp_path):
    """An older valid passing candidate is selected over a newer incomplete session."""
    repo, parent_sha, tip_sha = chain_repo
    # Attempt 0: valid passing result A
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=0,
        result_sha=parent_sha,
        updated_at="2026-07-29T00:00:00",
        verdict=Verdict.PASS,
    )
    # Attempt 1: newer session still running (not evaluated)
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=1,
        result_sha=tip_sha,
        state="running",
        updated_at="2026-07-30T00:00:00",
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base == parent_sha and reason is None


def test_newest_valid_result_wins_when_both_valid(con, chain_repo, tmp_path):
    """When multiple attempts are valid, the newest valid candidate wins."""
    repo, parent_sha, tip_sha = chain_repo
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=0,
        result_sha=parent_sha,
        updated_at="2026-07-29T00:00:00",
    )
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        job_id="job-chain",
        attempt_index=1,
        result_sha=tip_sha,
        updated_at="2026-07-30T00:00:00",
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base == tip_sha and reason is None


def test_multiple_provisional_deps_refuse(con):
    base, reason = _chained_base(
        con,
        _node("dep-a", "dep-b"),
        "proj",
        _reader({"dep-a": "provisional", "dep-b": "provisional"}),
        HEAD,
    )
    assert base is None and "refused" in reason


def test_provisional_dep_without_result_defers(con):
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}), HEAD
    )
    assert base is None and "no recorded result commit" in reason


def test_mixed_complete_and_provisional_chains(con, chain_repo, tmp_path):
    repo, parent_sha, _ = chain_repo
    _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-b", result_sha=parent_sha
    )
    base, reason = _chained_base(
        con,
        _node("dep-a", "dep-b"),
        "proj",
        _reader({"dep-a": "complete", "dep-b": "provisional"}),
        HEAD,
        repo_path=repo,
    )
    assert base == parent_sha and reason is None


def test_missing_graph_falls_back_to_head(con):
    class _Missing:
        def load_project(self, project_id):
            raise FileNotFoundError("no graph")

    base, reason = _chained_base(con, _node("dep-a"), "proj", _Missing(), HEAD)
    assert base == HEAD and reason is None


def test_cross_project_collision_isolated(con, two_repos, tmp_path):
    """Two projects with identical node IDs resolve only their own bound result."""
    (repo1, p1_parent, _), (repo2, p2_parent, _) = two_repos

    # Project 1 result A for node dep-a
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj-1",
        node_id="dep-a",
        job_id="job-p1-dep-a",
        result_sha=p1_parent,
        updated_at="2026-07-29T00:00:00",
    )
    # Project 2 result C for the same node dep-a
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj-2",
        node_id="dep-a",
        job_id="job-p2-dep-a",
        result_sha=p2_parent,
        updated_at="2026-07-30T00:00:00",
    )

    # proj-1 gets p1_parent, not the newer p2_parent from proj-2
    base1, reason1 = _chained_base(
        con, _node("dep-a"), "proj-1", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo1,
    )
    assert base1 == p1_parent and reason1 is None

    # proj-2 gets p2_parent, not p1_parent
    base2, reason2 = _chained_base(
        con, _node("dep-a"), "proj-2", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo2,
    )
    assert base2 == p2_parent and reason2 is None


def test_receipt_file_missing_invalidates_candidate(con, chain_repo, tmp_path):
    repo, parent_sha, _ = chain_repo
    _, _, rpath = _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-a", result_sha=parent_sha
    )
    assert rpath is not None and rpath.is_file()
    rpath.unlink()  # delete receipt file

    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base is None and "no recorded result commit" in reason


def test_receipt_file_corrupted_invalidates_candidate(con, chain_repo, tmp_path):
    repo, parent_sha, _ = chain_repo
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        result_sha=parent_sha,
        corrupt_receipt_json=True,
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base is None and "no recorded result commit" in reason


@pytest.mark.parametrize(
    "mutation",
    [
        {"project_id": "other-proj"},
        {"node_id": "wrong-node"},
        {"job_id": "wrong-job"},
        {"execution_attempt_id": "wrong:attempt:99"},
        {"merge_commit_sha": "f" * 40},
        {"evaluated_commit_sha": "f" * 40},
        {"expected_base_commit_sha": "0" * 40},
    ],
)
def test_receipt_identity_mismatch_invalidates_candidate(
    con, chain_repo, tmp_path, mutation
):
    repo, parent_sha, _ = chain_repo
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        result_sha=parent_sha,
        receipt_mutation=mutation,
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base is None and "no recorded result commit" in reason


def test_missing_git_commit_defers(con, chain_repo, tmp_path):
    """Candidate has valid receipt, but its commit SHA is missing from git repo."""
    repo, _, _ = chain_repo
    missing_sha = "e" * 40
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        result_sha=missing_sha,
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}),
        HEAD, repo_path=repo,
    )
    assert base is None
    assert "not found in repository" in reason


def test_provisional_result_ancestor_of_head_uses_tip(con, chain_repo, tmp_path):
    repo, parent_sha, tip_sha = chain_repo
    _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-a", result_sha=parent_sha
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj",
        _reader({"dep-a": "provisional"}), tip_sha, repo_path=repo,
    )
    assert base == tip_sha and reason is None


def test_provisional_result_not_ancestor_keeps_result(con, chain_repo, tmp_path):
    repo, parent_sha, tip_sha = chain_repo
    _git(repo, "checkout", "-q", "--orphan", "disjoint")
    (Path(repo) / "g.txt").write_text("diverged")
    _git(repo, "add", "g.txt")
    _git(repo, "commit", "-qm", "disjoint root")
    diverged_tip = _git(repo, "rev-parse", "HEAD")

    _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-a", result_sha=parent_sha
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj",
        _reader({"dep-a": "provisional"}), diverged_tip, repo_path=repo,
    )
    assert base == parent_sha and reason is None


def test_ancestor_of_head_uses_head_only_after_receipt_validation(
    con, chain_repo, tmp_path
):
    """An ancestor commit whose receipt fails admission does NOT trigger tip_sha."""
    repo, parent_sha, tip_sha = chain_repo
    # Candidate commit is parent_sha (ancestor of tip_sha), but receipt failed!
    _record_session_with_receipt(
        con,
        tmp_path,
        project_id="proj",
        node_id="dep-a",
        result_sha=parent_sha,
        verdict=Verdict.FAIL,
        criteria_verdict=Verdict.FAIL,
        intent_preserved=False,
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj",
        _reader({"dep-a": "provisional"}), tip_sha, repo_path=repo,
    )
    assert base is None and "no recorded result commit" in reason


def test_provisional_result_without_repo_path_keeps_result(con, chain_repo, tmp_path):
    _, parent_sha, tip_sha = chain_repo
    _record_session_with_receipt(
        con, tmp_path, project_id="proj", node_id="dep-a", result_sha=parent_sha
    )
    base, reason = _chained_base(
        con, _node("dep-a"), "proj",
        _reader({"dep-a": "provisional"}), tip_sha,
    )
    assert base == parent_sha and reason is None
