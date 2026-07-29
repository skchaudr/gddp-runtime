"""
reconciler.py — Executor session reconciliation.

Runs every heartbeat tick BEFORE planning new events. Polls active executor
sessions, collects completed work, applies patches to isolated worktrees,
commits, and queues evaluation.

This phase must run even when there are no new intake events, because CLI-based
executors (Jules CLI, Droid, etc.) complete asynchronously without webhooks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure adapters directory is importable (same pattern as dispatcher.py).
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.executor_protocol import SessionRef

from ..results_store import write_result
from ..verification.bridge import verify_job_return
from .dispatcher import ADAPTERS, cancel_remote_session, dispatch
from .state_recorder import (
    allocate_retry_attempt,
    finalize_executor_session_dispatch,
    get_active_executor_sessions,
    mark_job_cancelled,
    mark_job_failed,
    mark_job_running,
    recover_stale_dispatching_sessions,
    update_executor_session_state,
)

DEFAULT_MAX_CONCURRENT_EVALUATIONS = 2


@dataclass(frozen=True)
class PendingEvaluation:
    """Plain-data evaluator input safe to pass to a worker thread."""

    session_db_id: str
    session_id: str
    executor: str
    project_id: str
    node_id: str
    job_id: str
    attempt: int
    result_commit_sha: str


class EvaluationBatch:
    """Bounded verifier work with coordinator-owned result persistence.

    Worker threads only run ``verify_job_return``. The heartbeat coordinator
    later drains the futures and performs every SQLite write serially.
    Sessions remain ``collected`` until finalization, so a process crash leaves
    the durable result SHA/ref available for the existing resume path.
    """

    def __init__(self, max_workers: int = DEFAULT_MAX_CONCURRENT_EVALUATIONS):
        if isinstance(max_workers, bool) or max_workers < 1:
            raise ValueError("evaluation worker capacity must be a positive integer")
        self._max_workers = max_workers
        self._pending: list[PendingEvaluation] = []
        self._executor: ThreadPoolExecutor | None = None
        self._futures: dict[Future, PendingEvaluation] = {}
        self._started = False
        self._finalized = False

    def add(self, session, job, result_commit_sha: str) -> None:
        if self._started:
            raise RuntimeError("cannot add evaluations after the batch starts")
        self._pending.append(
            PendingEvaluation(
                session_db_id=str(session["session_db_id"]),
                session_id=str(session["session_id"]),
                executor=str(session["executor"]),
                project_id=str(job["project_id"] or ""),
                node_id=str(job["node_id"]),
                job_id=str(job["job_id"]),
                attempt=int(job["attempt"] or 0),
                result_commit_sha=result_commit_sha,
            )
        )

    def start(self) -> None:
        """Start all queued verifiers without waiting for them."""
        if self._started:
            return
        self._started = True
        if not self._pending:
            return
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="gddp-evaluator",
        )
        self._futures = {
            self._executor.submit(_run_evaluation, pending): pending
            for pending in self._pending
        }

    def finalize(self, con) -> None:
        """Drain verifiers and serialize their DB/result finalization."""
        if self._finalized:
            return
        self.start()
        try:
            for future in as_completed(self._futures):
                pending = self._futures[future]
                try:
                    verification = future.result()
                except Exception as exc:
                    verification = {
                        "verification_status": "error",
                        "error": f"evaluator worker failed: {exc}",
                    }
                try:
                    _finalize_evaluation(con, pending, verification)
                except Exception as exc:
                    # Leave this session collected so the next heartbeat can
                    # retry evaluation from its already-durable result commit.
                    con.rollback()
                    print(
                        f"[reconcile] {pending.session_db_id}: "
                        f"evaluation finalization ERROR: {exc}"
                    )
        finally:
            if self._executor is not None:
                self._executor.shutdown(wait=True)
            self._finalized = True


def reconcile_sessions(
    con,
    repo_path: Path | None,
    repo: str | None = None,
    *,
    current_time: datetime | None = None,
    dispatching_stale_after: timedelta = timedelta(minutes=30),
    missing_stale_after: timedelta = timedelta(minutes=30),
    evaluation_batch: EvaluationBatch | None = None,
    max_concurrent_evaluations: int = DEFAULT_MAX_CONCURRENT_EVALUATIONS,
) -> None:
    """Main entry point for the reconcile phase.

    Polls every active executor session, collects completed work into isolated
    worktrees, commits, and triggers evaluation. Runs every heartbeat tick
    before planning new events.

    When *repo* (GitHub owner/name) is provided, only sessions whose job
    belongs to that repo are polled — cross-repo safety for multi-project
    heartbeats sharing a single DB.

    A failure reconciling one session does not stop others. When the caller
    supplies ``evaluation_batch``, verifier work starts here but the caller
    owns finalization; ``run_heartbeat`` uses that window to plan and dispatch.
    Legacy callers that omit the batch still receive fully finalized results
    before this function returns.
    """
    owns_evaluation_batch = evaluation_batch is None
    batch = evaluation_batch or EvaluationBatch(
        max_workers=max_concurrent_evaluations
    )
    current_time = current_time or datetime.now(timezone.utc)
    recovered = recover_stale_dispatching_sessions(
        con,
        current_time=current_time,
        stale_after=dispatching_stale_after,
        repo=repo,
    )
    if recovered:
        con.commit()
        print(
            f"[reconcile] recovered {len(recovered)} stale dispatch "
            "reservation(s) as dispatch_failed; operator recovery required"
        )

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
            _reconcile_one(
                con,
                session,
                repo_path,
                current_time=current_time,
                missing_stale_after=missing_stale_after,
                evaluation_batch=batch,
            )
        except Exception as exc:
            # A failed reconcile for one session must not stop others.
            print(
                f"[reconcile] ERROR reconciling {session['session_db_id']}: {exc}"
            )
            con.commit()

    con.commit()
    batch.start()
    if owns_evaluation_batch:
        batch.finalize(con)


def cancel_executor_session(con, session_db_id: str) -> str:
    """Persist a logical cancellation and stop local lifecycle processing."""
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = ?",
        (session_db_id,),
    ).fetchone()
    if session is None:
        raise ValueError(f"executor session not found: {session_db_id}")
    if session["state"] not in {
        "dispatching",
        "dispatched",
        "running",
        "needs_operator",
    }:
        return session["state"]

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (session["job_id"],)
    ).fetchone()
    if job is None:
        raise ValueError(f"job not found: {session['job_id']}")

    executor = session["executor"]
    adapter_cls = ADAPTERS.get(executor)
    result_state = "cancel_failed"
    error = f"cancellation failed: unknown executor {executor!r}"
    if adapter_cls is not None:
        error = "local executor cancellation was not accepted"
        adapter = adapter_cls(repo=job["repo"] or "")
        session_ref = SessionRef(
            executor=executor,
            session_id=session["session_id"],
        )
        try:
            accepted = adapter.cancel(session_ref)
        except Exception as exc:
            accepted = False
            error = f"cancellation failed: {exc}"

        if accepted:
            result_state = "cancelled"
            error = "local executor cancellation accepted"
        elif executor == "jules_cli":
            result_state = "cancel_unsupported"
            error = (
                "Jules CLI cancellation is unsupported; remote execution "
                "may continue and its result will not be collected"
            )
        elif not error.startswith("cancellation failed: "):
            error = "local executor cancellation was not accepted"

        if not accepted and executor != "jules_cli":
            try:
                durable_status = adapter.status(session_ref)
            except Exception:
                durable_status = None
            if durable_status is not None and durable_status.state in {
                "completed",
                "failed",
            }:
                update_executor_session_state(
                    con,
                    session_db_id,
                    state=durable_status.state,
                    error=(
                        "cancellation requested after executor was already "
                        f"{durable_status.state}; result will not be collected"
                    ),
                )
                mark_job_cancelled(con, session["job_id"])
                con.commit()
                return "already_terminal"

    update_executor_session_state(
        con,
        session_db_id,
        state=result_state,
        error=error,
    )
    mark_job_cancelled(con, session["job_id"])
    con.commit()
    return result_state


def _reconcile_one(
    con,
    session,
    repo_path: Path,
    *,
    current_time: datetime,
    missing_stale_after: timedelta,
    evaluation_batch: EvaluationBatch,
) -> None:
    """Reconcile a single executor session."""
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]
    executor = session["executor"]
    session_id = session["session_id"]
    current_state = session["state"]

    job_row = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?",
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

    # Resume: this session's collect/apply/commit already succeeded and is
    # durable (result_commit_sha + git ref), but a prior process was
    # interrupted before evaluation completed. Re-polling the executor and
    # re-collecting would be wasteful and would leave an orphaned duplicate
    # commit; go straight to evaluation using the already-recorded SHA.
    if current_state == "collected":
        result_sha = session["result_commit_sha"]
        if not result_sha:
            print(
                f"[reconcile] {session_db_id}: collected with no "
                "result_commit_sha; marking failed"
            )
            update_executor_session_state(
                con, session_db_id, state="failed",
                error="collected session missing result_commit_sha",
            )
            mark_job_failed(con, job_id)
            con.commit()
            return
        print(f"[reconcile] {session_db_id}: resuming evaluation (collected)")
        evaluation_batch.add(session, job_row, result_sha)
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
        _handle_completed(
            con,
            adapter,
            session_ref,
            session,
            repo_path,
            job_row,
            evaluation_batch,
        )
    elif status.state == "failed":
        _handle_failed(con, session, job_row, status.error, repo_path)
    elif status.state == "missing":
        created_at = datetime.fromisoformat(
            str(session["created_at"]).replace("Z", "+00:00")
        )
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if current_time - created_at < missing_stale_after:
            print(
                f"[reconcile] {session_db_id}: missing from successful executor "
                f"list within {missing_stale_after} grace; will retry next tick"
            )
            return
        _handle_failed(con, session, job_row, status.error, repo_path)
    elif status.state == "poll_error":
        print(
            f"[reconcile] {session_db_id}: poll error (transient, will retry "
            f"next tick): {status.error or 'executor unavailable'}"
        )
    elif status.state == "needs_operator":
        _handle_needs_operator(con, session_db_id, job_id, status.error)
    elif status.state == "running":
        if current_state != "running":
            update_executor_session_state(con, session_db_id, state="running")
            con.commit()
    # "dispatched" → still queued; no action needed this tick.


def _handle_completed(
    con,
    adapter,
    session_ref,
    session,
    repo_path: Path,
    job_row,
    evaluation_batch: EvaluationBatch,
) -> None:
    """Collect result, record commit SHA, trigger evaluation.

    Local commit-ref handoff: consume result_commit_sha directly (verify it
    descends from expected_base_commit_sha); no reconstruction worktree.
    Patch-only executors (Jules/remote): apply in an isolated worktree, commit.

    Any failure in the collect→(apply)→commit→evaluate sequence marks BOTH the
    session and the job as failed, so jobs are never stranded in 'running'.
    """
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]
    session_id = session["session_id"]
    base_commit = session["expected_base_commit_sha"]

    try:
        if not base_commit:
            raise ValueError("missing expected_base_commit_sha")

        # 1. Collect the handoff from the executor.
        patch_fd, patch_path_str = tempfile.mkstemp(
            prefix=f"gddp-patch-{job_id}-", suffix=".diff"
        )
        os.close(patch_fd)
        dest_path = Path(patch_path_str)

        patch_result = adapter.collect(session_ref, dest_path)
        if not patch_result.success:
            raise RuntimeError(f"collect failed: {patch_result.error}")

        # Commit-ref path (local_subprocess): skip reconstruction worktree.
        if getattr(patch_result, "result_commit_sha", None):
            result_sha = patch_result.result_commit_sha
            result_ref = getattr(patch_result, "result_ref", None)
            if not result_ref:
                raise RuntimeError("commit-ref handoff missing result_ref")
            resolved = _resolve_ref(repo_path, result_ref)
            if resolved != result_sha:
                raise RuntimeError(
                    f"result_ref {result_ref} resolves to "
                    f"{resolved or 'nothing'}, expected {result_sha}"
                )
            if not _is_ancestor(repo_path, base_commit, result_sha):
                raise RuntimeError(
                    f"result {result_sha} does not descend from "
                    f"expected base {base_commit}"
                )
            update_executor_session_state(
                con, session_db_id, state="collected",
                result_commit_sha=result_sha,
                patch_path=(
                    patch_result.patch_path
                    or getattr(patch_result, "result_ref", None)
                    or str(dest_path)
                ),
            )
            con.commit()
            _ensure_result_ref(
                repo_path, job_id, session_id, result_sha
            )
            evaluation_batch.add(session, job_row, result_sha)
            print(
                f"[reconcile] {session_db_id}: result commit {result_sha[:12]} "
                f"(commit-ref), job {job_id} queued for evaluation"
            )
            return

        # 2. Patch path (Jules/remote): create the worktree at the base the
        #    executor actually built on. A patch is only meaningful against its
        #    own base, and the executor's base is the retrievable fact — the
        #    locally-recorded expectation is not.
        #
        #    This deliberately does NOT compare the two. A base difference is
        #    an integration concern, never a reason to discard work unread.
        #    Refusing to evaluate returned work is evidence suppression, and it
        #    destroyed three nodes' worth of real output on 2026-07-29.
        patch_base = getattr(patch_result, "base_commit_sha", None)
        worktree_base = patch_base or base_commit

        worktree = _create_exec_worktree(repo_path, job_id, worktree_base)
        if worktree is None:
            raise RuntimeError(f"could not create worktree at {worktree_base}")

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
            #    collected after the worktree is removed.
            _ensure_result_ref(repo_path, job_id, session_id, result_sha)

            # 6. Queue evaluation. Worker threads run only the verifier; the
            #    heartbeat coordinator later serializes all state writes.
            evaluation_batch.add(session, job_row, result_sha)

            print(
                f"[reconcile] {session_db_id}: result commit {result_sha[:12]}, "
                f"job {job_id} queued for evaluation"
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


def _handle_failed(con, session, job, error: str | None, repo_path: Path) -> None:
    """Persist one authoritative failure, then allocate at most one retry."""
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]
    update_executor_session_state(
        con, session_db_id, state="failed", error=error
    )

    session_attempt = int(session["attempt_index"])
    current_attempt = int(job["attempt"] or 0)
    if session_attempt != current_attempt:
        con.commit()
        print(
            f"[reconcile] {session_db_id}: executor failed on superseded "
            f"attempt {session_attempt}; current attempt is {current_attempt}"
        )
        return

    mark_job_failed(con, job_id)
    expected_base = _get_head_sha(repo_path) or session["expected_base_commit_sha"]
    allocated = allocate_retry_attempt(
        con,
        job,
        executor=session["executor"],
        expected_base_commit_sha=expected_base,
    )
    if allocated is None:
        con.commit()
        print(
            f"[reconcile] {session_db_id}: executor failed; job {job_id} "
            f"exhausted at attempt {current_attempt}"
        )
        return

    retry_job, replacement_id = allocated
    retry_job["executor"] = session["executor"]
    con.commit()

    try:
        dispatch_result = dispatch(retry_job, retry_job["repo"])
    except Exception as exc:
        dispatch_result = None
        dispatch_error = f"retry dispatch raised exception: {exc}"
    else:
        dispatch_error = dispatch_result.error or "retry dispatch failed"

    if dispatch_result is not None and dispatch_result.success:
        session_ref = dispatch_result.session_ref
        if session_ref is not None:
            finalized = finalize_executor_session_dispatch(
                con,
                replacement_id,
                state="dispatched",
                executor=session_ref.executor,
                session_id=session_ref.session_id,
                expected_base_commit_sha=expected_base,
            )
        else:
            finalized = finalize_executor_session_dispatch(
                con,
                replacement_id,
                state="mediated",
                session_id=dispatch_result.issue_url,
                expected_base_commit_sha=expected_base,
            )
        if not finalized:
            cancellation = "reservation is no longer dispatching"
            if session_ref is not None:
                _, cancellation = cancel_remote_session(
                    session_ref, retry_job["repo"]
                )
            con.commit()
            print(
                f"[reconcile] {replacement_id}: late retry dispatch result "
                f"ignored; {cancellation}"
            )
            return
        mark_job_running(con, job_id)
        con.commit()
        print(
            f"[reconcile] {session_db_id}: executor failed; job {job_id} "
            f"redispatched as attempt {retry_job['attempt']}"
        )
        return

    finalized = finalize_executor_session_dispatch(
        con,
        replacement_id,
        state="dispatch_failed",
        error=dispatch_error,
        expected_base_commit_sha=expected_base,
    )
    if finalized:
        mark_job_failed(con, job_id)
    con.commit()
    if finalized:
        print(
            f"[reconcile] {session_db_id}: executor failed; retry dispatch "
            f"for job {job_id} failed: {dispatch_error}"
        )
    else:
        print(
            f"[reconcile] {replacement_id}: late retry dispatch failure ignored; "
            "reservation is no longer dispatching"
        )


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


def _run_evaluation(pending: PendingEvaluation) -> dict:
    """Run one verifier without touching the runtime database."""
    try:
        verification = verify_job_return(
            project_id=pending.project_id,
            node_id=pending.node_id,
            merge_commit_sha=pending.result_commit_sha,
            pr_ref=None,  # no PR for CLI path
            job_id=pending.job_id,
            attempt=pending.attempt,
        )
    except Exception as exc:
        return {"verification_status": "error", "error": str(exc)}
    return verification


def _finalize_evaluation(
    con,
    pending: PendingEvaluation,
    verification: dict,
) -> None:
    """Persist one evaluator outcome on the coordinator thread.

    Evaluator evidence never advances graph truth. A verifier error is still
    routed to awaiting review so the human sees the explicit failure record.
    """
    status = verification.get("verification_status", "unknown")
    print(f"  → evaluation: {status}")
    if verification.get("verdict"):
        print(f"  → verdict: {verification['verdict']}")
    elif status == "error":
        print(f"  → evaluation ERROR (non-fatal): {verification.get('error', '')}")

    # Write a results row so jobs_status.py can display the evaluator output
    # for human review. The verification dict from verify_job_return carries
    # verdict/criteria/risks evidence; fields the dict does not provide get
    # safe defaults. The important invariant is that a results row exists.
    # session_db_id is the full primary key for this attempt. Truncating the
    # executor's session_id caused distinct local sessions to share a result.
    result_id = f"res_{pending.session_db_id}"
    v_status = status
    # outcome reflects the evaluator's verdict; status reflects the job's
    # routing state. A verification error is still routed to awaiting_review
    # — the human is the final gate.
    outcome = verification.get("verdict") or v_status
    try:
        write_result(
            result_id=result_id,
            job_id=pending.job_id,
            executor=pending.executor,
            outcome=outcome,
            status="awaiting_review",
            changed_files=verification.get("changed_files", []),
            # The CLI summary has no top-level "acceptance_check" key — it
            # returns verdict/criteria_verdict/integrity/lane_status/etc.
            # directly. The mediated path (return_router.py) stores the
            # whole verification dict as acceptance_check; mirror that here
            # so jobs_status.py show has something to display instead of
            # silently storing None on every direct-path result.
            acceptance_check=verification,
            risks=verification.get("risks"),
            followup_candidates=verification.get("followup_candidates"),
            github_action=verification.get("github_action"),
        )
    except Exception as exc:
        # Non-fatal: the verdict is already printed; a missing results row
        # is a display gap, not a graph-truth issue.
        print(f"  → write_result ERROR (non-fatal): {exc}")

    # Update session to evaluated.
    update_executor_session_state(
        con,
        pending.session_db_id,
        state="evaluated",
    )
    # Mark job as awaiting_review (human decides graph truth).
    con.execute(
        "UPDATE jobs SET status = 'awaiting_review', queue_state = 'awaiting_review' WHERE job_id = ?",
        (pending.job_id,),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'awaiting_review' WHERE job_id = ?",
        (pending.job_id,),
    )
    con.commit()


def _get_head_sha(repo_path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


# ------------------------------------------------------------------ #
# Commit-ref helpers (local_subprocess) and worktree helpers (patch).
# ------------------------------------------------------------------ #

def _is_ancestor(repo_path: Path, base_sha: str, result_sha: str) -> bool:
    """True when result_sha descends from base_sha (inclusive)."""
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_sha, result_sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_ref(repo_path: Path, ref_name: str) -> str | None:
    """Resolve refs/heads/{ref_name} to a commit SHA, or None."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{ref_name}^{{commit}}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ensure_result_ref(
    repo_path: Path, job_id: str, session_id: str, result_sha: str
) -> None:
    """Ensure gddp/result-{job}-{session} points at result_sha (best-effort)."""
    ref_name = f"gddp/result-{job_id}-{session_id}"
    try:
        ref_proc = subprocess.run(
            ["git", "update-ref", f"refs/heads/{ref_name}", result_sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if ref_proc.returncode != 0:
            # Fall back to branch create for older environments.
            ref_proc = subprocess.run(
                ["git", "branch", "-f", ref_name, result_sha],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        if ref_proc.returncode != 0:
            print(f"  ⚠ ref creation failed: {ref_proc.stderr.strip()}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  ⚠ ref creation failed: {exc}")


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
