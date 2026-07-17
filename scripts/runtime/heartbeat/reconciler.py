"""
reconciler.py — Executor session reconciliation.

Runs every heartbeat tick BEFORE planning new events. Polls active executor
sessions, collects completed work, applies patches to isolated worktrees,
commits, and triggers evaluation.

This phase must run even when there are no new intake events, because CLI-based
executors (Jules CLI, Droid, etc.) complete asynchronously without webhooks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure adapters directory is importable (same pattern as dispatcher.py).
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.executor_protocol import SessionRef

from ..results_store import write_result
from ..verification.bridge import verify_job_return
from .dispatcher import ADAPTERS
from .state_recorder import (
    get_active_executor_sessions,
    mark_job_failed,
    update_executor_session_state,
)


def reconcile_sessions(
    con, repo_path: Path | None, repo: str | None = None
) -> None:
    """Main entry point for the reconcile phase.

    Polls every active executor session, collects completed work into isolated
    worktrees, commits, and triggers evaluation. Runs every heartbeat tick
    before planning new events.

    When *repo* (GitHub owner/name) is provided, only sessions whose job
    belongs to that repo are polled — cross-repo safety for multi-project
    heartbeats sharing a single DB.

    A failure reconciling one session does not stop others.
    """
    if repo_path is None:
        print("[reconcile] no repo_path available; skipping reconcile phase")
        return

    repo_path = Path(repo_path)
    sessions = get_active_executor_sessions(con, repo=repo)

    if not sessions:
        # No active sessions — nothing to reconcile. Normal and expected.
        return

    print(f"[reconcile] {len(sessions)} active executor session(s) to poll.")

    for session in sessions:
        try:
            _reconcile_one(con, session, repo_path)
        except Exception as exc:
            # A failed reconcile for one session must not stop others.
            print(
                f"[reconcile] ERROR reconciling {session['session_db_id']}: {exc}"
            )
            con.commit()

    con.commit()


def _reconcile_one(con, session, repo_path: Path) -> None:
    """Reconcile a single executor session."""
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]
    executor = session["executor"]
    session_id = session["session_id"]
    current_state = session["state"]

    # Look up the job row for repo and evaluation metadata.
    job_row = con.execute(
        "SELECT job_id, repo, node_id, project_id, attempt FROM jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if job_row is None:
        print(f"[reconcile] {session_db_id}: job {job_id} not found; skipping")
        return

    # Instantiate the adapter for this executor.
    adapter_cls = ADAPTERS.get(executor)
    if adapter_cls is None:
        print(
            f"[reconcile] {session_db_id}: unknown executor {executor!r}; skipping"
        )
        return

    adapter = adapter_cls(repo=job_row["repo"] or "")
    session_ref = SessionRef(executor=executor, session_id=session_id)

    # Poll the session. A transient polling error (CLI timeout, network blip)
    # must NOT kill the job — the session may be fine, we just couldn't reach
    # the executor this tick. Leave session and job as-is for the next tick.
    try:
        status = adapter.status(session_ref)
    except Exception as exc:
        print(
            f"[reconcile] {session_db_id}: poll error (transient, will retry "
            f"next tick): {exc}"
        )
        return

    print(
        f"[reconcile] {session_db_id} ({executor}/{session_id}): {status.state}"
    )

    if status.state == "completed":
        _handle_completed(con, adapter, session_ref, session, repo_path, job_row)
    elif status.state == "failed":
        _handle_failed(con, session_db_id, job_id, status.error)
    elif status.state == "needs_operator":
        _handle_needs_operator(con, session_db_id, job_id, status.error)
    elif status.state == "running":
        if current_state != "running":
            update_executor_session_state(con, session_db_id, state="running")
            con.commit()
    # "dispatched" → still queued; no action needed this tick.


def _handle_completed(
    con, adapter, session_ref, session, repo_path: Path, job_row
) -> None:
    """Collect patch, apply in an isolated worktree, commit, trigger evaluation.

    Any failure in the collect→apply→commit→evaluate sequence marks BOTH the
    session and the job as failed, so jobs are never stranded in 'running'.
    """
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]
    session_id = session["session_id"]
    base_commit = session["expected_base_commit_sha"]

    try:
        if not base_commit:
            raise ValueError("missing expected_base_commit_sha")

        # 1. Collect the patch from the executor.
        patch_fd, patch_path_str = tempfile.mkstemp(
            prefix=f"gddp-patch-{job_id}-", suffix=".diff"
        )
        os.close(patch_fd)
        dest_path = Path(patch_path_str)

        patch_result = adapter.collect(session_ref, dest_path)
        if not patch_result.success:
            raise RuntimeError(f"collect failed: {patch_result.error}")

        # 2. Create an isolated exec worktree at the expected base commit.
        worktree = _create_exec_worktree(repo_path, job_id, base_commit)
        if worktree is None:
            raise RuntimeError(f"could not create worktree at {base_commit}")

        try:
            # 3. Apply the patch and commit in the worktree.
            result_sha, commit_error = _apply_and_commit(
                worktree, dest_path, job_id, session_id
            )
            if result_sha is None:
                raise RuntimeError(commit_error or "apply/commit failed")

            # 4. Record the result commit and mark session as collected.
            update_executor_session_state(
                con, session_db_id, state="collected",
                result_commit_sha=result_sha,
                patch_path=str(dest_path),
            )
            con.commit()

            # 5. Create a durable ref so the result commit is not garbage
            #    collected after the worktree is removed.  The worktree shares
            #    the main repo's object store, so the commit SHA is valid here.
            #    The ref includes the session id so each session attempt gets
            #    its own ref; retries no longer collide with a dangling ref
            #    from a previous attempt.
            ref_name = f"gddp/result-{job_id}-{session['session_id']}"
            ref_proc = subprocess.run(
                ["git", "branch", ref_name, result_sha],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,  # non-fatal if it fails
            )
            if ref_proc.returncode != 0:
                print(
                    f"  ⚠ ref creation failed: {ref_proc.stderr.strip()}"
                )

            # 6. Trigger evaluation: run the evaluator, then mark job
            #    awaiting_review and session evaluated.
            _trigger_evaluation(con, session, job_row, result_sha)

            print(
                f"[reconcile] {session_db_id}: result commit {result_sha[:12]}, "
                f"job {job_id} → awaiting_review"
            )
        finally:
            # 7. Cleanup: the result commit is now durable via the ref above.
            _remove_exec_worktree(repo_path, worktree)

    except Exception as exc:
        print(f"[reconcile] {session_db_id}: collect/apply FAILED: {exc}")
        update_executor_session_state(
            con, session_db_id, state="failed", error=str(exc)
        )
        # Mark the JOB failed too, not just the session, so it is not
        # stranded in 'running'.
        mark_job_failed(con, job_id)
        con.commit()


def _handle_failed(
    con, session_db_id: str, job_id: str, error: str | None
) -> None:
    """Handle a session that the executor reports as failed."""
    mark_job_failed(con, job_id)
    update_executor_session_state(
        con, session_db_id, state="failed", error=error
    )
    con.commit()
    print(f"[reconcile] {session_db_id}: executor failed; job {job_id} → failed")


def _handle_needs_operator(
    con, session_db_id: str, job_id: str, error: str | None
) -> None:
    """Handle a session that needs human intervention. No auto-approval."""
    update_executor_session_state(
        con, session_db_id, state="needs_operator", error=error
    )
    con.commit()
    print(
        f"[reconcile] {session_db_id}: NEEDS OPERATOR (job {job_id}). "
        f"No auto-approval."
    )


def _trigger_evaluation(con, session, job, result_commit_sha) -> None:
    """Run the evaluator on the result commit and record the receipt.

    Calls ``verify_job_return`` (the same verification CLI a human would run)
    and prints the verdict.  The evaluator verdict is evidence for the human
    reviewer; it never advances graph truth.  The evaluator may fail (e.g., if
    the node YAML or project YAML cannot be found) — that is non-fatal; the job
    still goes to awaiting_review with whatever evidence was captured.  The
    human is the final gate.
    """
    project_id = job["project_id"]
    node_id = job["node_id"]
    job_id = job["job_id"]
    attempt = job["attempt"] if job["attempt"] is not None else 0

    try:
        verification = verify_job_return(
            project_id=project_id,
            node_id=node_id,
            merge_commit_sha=result_commit_sha,
            pr_ref=None,  # no PR for CLI path
            job_id=job_id,
            attempt=attempt,
        )
        print(
            f"  → evaluation: {verification.get('verification_status', 'unknown')}"
        )
        if verification.get("verdict"):
            print(f"  → verdict: {verification['verdict']}")
    except Exception as exc:
        print(f"  → evaluation ERROR (non-fatal): {exc}")
        verification = {"verification_status": "error", "error": str(exc)}

    # Write a results row so node_status.py can display the evaluator output
    # for human review. The verification dict from verify_job_return carries
    # verdict/criteria/risks evidence; fields the dict does not provide get
    # safe defaults. The important invariant is that a results row exists.
    result_id = f"res_{session['session_id'][:16]}"
    v_status = verification.get("verification_status", "unknown")
    # outcome reflects the evaluator's verdict; status reflects the job's
    # routing state. A verification error is still routed to awaiting_review
    # — the human is the final gate.
    outcome = verification.get("verdict") or v_status
    try:
        write_result(
            result_id=result_id,
            job_id=job_id,
            executor=session["executor"],
            outcome=outcome,
            status="awaiting_review",
            changed_files=verification.get("changed_files", []),
            acceptance_check=verification.get("acceptance_check"),
            risks=verification.get("risks"),
            followup_candidates=verification.get("followup_candidates"),
            github_action=verification.get("github_action"),
        )
    except Exception as exc:
        # Non-fatal: the verdict is already printed; a missing results row
        # is a display gap, not a graph-truth issue.
        print(f"  → write_result ERROR (non-fatal): {exc}")

    # Update session to evaluated.
    update_executor_session_state(con, session["session_db_id"], state="evaluated")
    # Mark job as awaiting_review (human decides graph truth).
    con.execute(
        "UPDATE jobs SET status = 'awaiting_review', queue_state = 'awaiting_review' WHERE job_id = ?",
        (job_id,),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'awaiting_review' WHERE job_id = ?",
        (job_id,),
    )
    con.commit()


# ------------------------------------------------------------------ #
# Worktree helpers — mirror verification/bridge.py pattern.
# Used for applying executor patches (not evaluation).
# ------------------------------------------------------------------ #

def _create_exec_worktree(
    repo_path: Path, job_id: str, base_commit: str
) -> Path | None:
    """Create an isolated git worktree at base_commit for patch application.

    Fetches from origin first so the base commit is available locally.
    Returns the worktree path or None on failure.
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(repo_path),
            capture_output=True,
            timeout=60,
            check=False,
        )
        tmpdir = tempfile.mkdtemp(prefix=f"gddp-exec-wt-{job_id}-")
        # git worktree add requires a non-existent path.
        os.rmdir(tmpdir)
        proc = subprocess.run(
            ["git", "worktree", "add", "--detach", tmpdir, base_commit],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return Path(tmpdir)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _remove_exec_worktree(repo_path: Path, worktree_path: Path) -> None:
    """Clean up an execution worktree. Best-effort."""
    removed = False
    try:
        proc = subprocess.run(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            cwd=str(repo_path),
            capture_output=True,
            timeout=15,
            check=False,
        )
        removed = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass

    if removed:
        return

    shutil.rmtree(worktree_path, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "worktree", "prune", "--expire", "now"],
            cwd=str(repo_path),
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _apply_and_commit(
    worktree_path: Path,
    patch_path: Path,
    job_id: str,
    session_id: str,
) -> tuple[str | None, str | None]:
    """Apply a unified diff in the worktree and commit.

    Returns (commit_sha, error). On success error is None.
    """
    # Apply the patch.
    proc = subprocess.run(
        ["git", "apply", str(patch_path)],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"git apply failed: {(proc.stderr or '').strip()}"

    # Stage all changes (including new files).
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(worktree_path),
        capture_output=True,
        check=False,
    )

    # Commit.
    commit_msg = f"result(job={job_id}, session={session_id})"
    proc = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"git commit failed: {(proc.stderr or '').strip()}"

    # Get the resulting commit SHA.
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"git rev-parse HEAD failed: {(proc.stderr or '').strip()}"

    return proc.stdout.strip(), None
