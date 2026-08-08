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
from .completion_discipline import submit_completion
from .dispatcher import ADAPTERS, cancel_remote_session, dispatch
from .provisional_gate import maybe_mark_provisional
from .state_recorder import (
    allocate_plumbing_retry,
    allocate_retry_attempt,
    finalize_executor_session_dispatch,
    get_active_executor_sessions,
    mark_job_cancelled,
    mark_job_failed,
    mark_job_running,
    mark_jobs_awaiting_review,
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
    expected_base_commit_sha: str | None = None


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

    def add(
        self,
        session,
        job,
        result_commit_sha: str,
        *,
        expected_base_commit_sha: str | None = None,
    ) -> None:
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
                expected_base_commit_sha=(
                    expected_base_commit_sha
                    if expected_base_commit_sha is not None
                    else session["expected_base_commit_sha"]
                ),
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

    session_groups: dict[tuple[str, str], list] = {}
    for session in sessions:
        session_groups.setdefault(
            (str(session["executor"]), str(session["session_id"])), []
        ).append(session)

    for group in session_groups.values():
        try:
            engagement_group = [
                candidate for candidate in group
                if candidate["state"] != "collected"
            ]
            adapter_cls = ADAPTERS.get(group[0]["executor"])
            adapter = None
            if adapter_cls is not None and engagement_group:
                job = con.execute(
                    "SELECT repo FROM jobs WHERE job_id = ?",
                    (engagement_group[0]["job_id"],),
                ).fetchone()
                adapter = adapter_cls(
                    repo=str(job["repo"] or "") if job is not None else ""
                )
                supports_engagement = getattr(
                    adapter, "supports_engagement", lambda: False
                )
                if supports_engagement():
                    _reconcile_engagement_group(
                        con,
                        adapter,
                        engagement_group,
                        repo_path,
                        batch,
                    )
                    engagement_group = []
            for session in group:
                if session in engagement_group or session["state"] == "collected":
                    _reconcile_one(
                        con,
                        session,
                        repo_path,
                        current_time=current_time,
                        missing_stale_after=missing_stale_after,
                        evaluation_batch=batch,
                        adapter=adapter,
                    )
        except Exception as exc:
            # A failed reconcile for one session must not stop others.
            print(
                f"[reconcile] ERROR reconciling {group[0]['session_db_id']}: {exc}"
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
            supports_engagement = getattr(
                adapter, "supports_engagement", lambda: False
            )
            if supports_engagement():
                engagement_sessions = con.execute(
                    "SELECT session_db_id, job_id FROM executor_sessions "
                    "WHERE executor = ? AND session_id = ?",
                    (executor, session["session_id"]),
                ).fetchall()
                for related in engagement_sessions:
                    update_executor_session_state(
                        con,
                        related["session_db_id"],
                        state="cancelled",
                        error="engagement cancellation accepted",
                    )
                    mark_job_cancelled(con, related["job_id"])
                con.commit()
                return "cancelled"
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
    adapter=None,
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

    if adapter is None:
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
    elif status.state in {"failed", "crashed"}:
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
    elif status.state == "awaiting_reply":
        _handle_awaiting_reply(
            con, adapter, session_ref, session_db_id, job_id, current_state
        )
    elif status.state == "needs_operator":
        _handle_needs_operator(con, session_db_id, job_id, status.error)
    elif status.state == "running":
        if current_state != "running":
            update_executor_session_state(con, session_db_id, state="running")
            con.commit()
    # "dispatched" → still queued; no action needed this tick.


def _reconcile_engagement_group(
    con,
    adapter,
    sessions,
    repo_path: Path,
    evaluation_batch: EvaluationBatch,
) -> None:
    """Poll and collect one shared engagement, then fan out by feature id."""
    if not sessions:
        return
    session_ref = SessionRef(
        executor=str(sessions[0]["executor"]),
        session_id=str(sessions[0]["session_id"]),
    )
    status = adapter.status(session_ref)
    if status.state in {"dispatched", "running"}:
        for session in sessions:
            if session["state"] != status.state:
                update_executor_session_state(
                    con, session["session_db_id"], state=status.state
                )
        con.commit()
        return
    if status.state in {"failed", "crashed", "missing"}:
        for session in sessions:
            job = con.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (session["job_id"],)
            ).fetchone()
            if job is not None:
                _handle_failed(con, session, job, status.error, repo_path)
        return
    if status.state != "completed":
        return

    results = adapter.collect_engagement(session_ref)
    by_feature = {
        result.feature_id: result
        for result in results
        if isinstance(result.feature_id, str)
    }
    jobs_by_node = {}
    for session in sessions:
        job = con.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (session["job_id"],)
        ).fetchone()
        if job is not None:
            jobs_by_node[str(job["node_id"])] = (session, job)

    if len(by_feature) != len(results) or set(by_feature) != set(jobs_by_node):
        reason = (
            "engagement collect feature ids do not match reserved node ids; "
            "human review required"
        )
        for session, job in jobs_by_node.values():
            _route_engagement_result_to_review(
                con, session, job, None, reason
            )
        con.commit()
        return

    completion_decisions = {}
    quarantined_session_ids: set[str] = set()
    for feature_id, (session, _job) in jobs_by_node.items():
        result = by_feature[feature_id]
        if result.completion_id is None:
            continue
        decision = submit_completion(
            con,
            session_db_id=session["session_db_id"],
            completion_id=result.completion_id,
            completion_digest_sha256=result.completion_digest_sha256,
            result_commit_sha=result.result_commit_sha,
            evidence_manifest_path=result.evidence_manifest_path,
        )
        completion_decisions[feature_id] = decision
        quarantined_session_ids.update(decision.quarantined_session_db_ids)

    for feature_id, (session, job) in jobs_by_node.items():
        result = by_feature[feature_id]
        decision = completion_decisions.get(feature_id)
        if (
            decision is not None
            and decision.action == "duplicate"
            and decision.existing_session_db_id != session["session_db_id"]
        ):
            continue
        if session["session_db_id"] in quarantined_session_ids:
            continue
        if (
            not result.success
            or result.review_required
            or not result.result_commit_sha
            or not result.result_ref
        ):
            _route_engagement_result_to_review(
                con,
                session,
                job,
                result,
                result.error or "engagement result requires human review",
            )
            continue

        branch_tip = _resolve_ref(repo_path, result.result_ref)
        base = session["expected_base_commit_sha"]
        if branch_tip is None:
            _route_engagement_result_to_review(
                con,
                session,
                job,
                result,
                f"engagement result ref {result.result_ref} cannot be resolved",
            )
            continue
        if not _is_ancestor(repo_path, result.result_commit_sha, branch_tip):
            _route_engagement_result_to_review(
                con,
                session,
                job,
                result,
                (
                    f"result {result.result_commit_sha} is not reachable from "
                    f"engagement ref {result.result_ref}"
                ),
            )
            continue
        if not base or not _is_ancestor(
            repo_path, base, result.result_commit_sha
        ):
            _route_engagement_result_to_review(
                con,
                session,
                job,
                result,
                (
                    f"result {result.result_commit_sha} does not descend from "
                    f"expected base {base or 'missing'}"
                ),
            )
            continue

        update_executor_session_state(
            con,
            session["session_db_id"],
            state="collected",
            result_commit_sha=result.result_commit_sha,
            patch_path=(
                result.evidence_manifest_path
                or result.patch_path
                or result.result_ref
            ),
        )
        _ensure_result_ref(
            repo_path,
            job["job_id"],
            session["session_id"],
            result.result_commit_sha,
        )
        evaluation_batch.add(
            session,
            job,
            result.result_commit_sha,
            expected_base_commit_sha=(
                _parent_commit(repo_path, result.result_commit_sha)
                or session["expected_base_commit_sha"]
            ),
        )
    con.commit()


def _route_engagement_result_to_review(
    con,
    session,
    job,
    result,
    reason: str,
) -> None:
    """Preserve incomplete engagement evidence and park graph truth for review."""
    update_executor_session_state(
        con,
        session["session_db_id"],
        state="evaluated",
        error=reason,
        patch_path=(
            getattr(result, "evidence_manifest_path", None)
            if result is not None
            else None
        ),
    )
    mark_jobs_awaiting_review(con, (job["job_id"],))


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


"""Executor-credential failure signals. When auth is dead, every retry fails
identically — burning attempts against a wall that cannot move (node-07
exhausted three attempts in 15 minutes on a revoked xAI token, 2026-08-02).
Auth-blocked failures park for the operator instead of retrying."""
_AUTH_BLOCK_PATTERNS = (
    "invalid_grant",
    "refresh token has been revoked",
    "run /login",
    "account migration",
    "authentication failed",
    "invalid api key",
    "401 unauthorized",
    "403 forbidden",
)


"""Plumbing failure signals: the executor died before producing durable exit
state (cgroup reap, host fault, spawn error). The work was never attempted,
so the retry draws on the plumbing budget, not the work-attempt budget
(policy: 3 work attempts + 3 plumbing retries, 2026-08-05)."""
_PLUMBING_PATTERNS = (
    "exited without durable exit state",
    "invalid local subprocess exit state",
)


def classify_plumbing_failure(error: str | None) -> bool:
    """True when the session failed before the executor could report — infra
    noise, not evidence about the node's work."""
    text = (error or "").lower()
    return any(pattern in text for pattern in _PLUMBING_PATTERNS)


def classify_executor_failure(error: str | None) -> str:
    """'auth_blocked' when executor credentials/login are the failure (retry
    cannot succeed and must not consume budget); 'retryable' otherwise."""
    text = (error or "").lower()
    if any(pattern in text for pattern in _AUTH_BLOCK_PATTERNS):
        return "auth_blocked"
    return "retryable"


def _handle_failed(con, session, job, error: str | None, repo_path: Path) -> None:
    """Persist one authoritative failure, then allocate at most one retry.

    Auth-blocked failures park instead: session -> needs_operator, job stays
    running (scope still blocks duplicate dispatch, capacity stays held), no
    attempt is consumed. The operator restores credentials and releases the
    job; unattended, the node waits rather than exhausting."""
    session_db_id = session["session_db_id"]
    job_id = session["job_id"]

    if classify_executor_failure(error) == "auth_blocked":
        if session["state"] == "needs_operator":
            return  # already parked; stay quiet between ticks
        update_executor_session_state(
            con, session_db_id, state="needs_operator", error=error
        )
        con.commit()
        print(
            f"[reconcile] {session_db_id}: AUTH BLOCKED (job {job_id}); "
            "parked without consuming retry budget. Restore executor auth, "
            f"then: gddp jobs set {job_id} failed --reason 'auth restored' "
            "--yes, and re-dispatch the node."
        )
        return

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
    plumbing = classify_plumbing_failure(error)
    if plumbing:
        allocated = allocate_plumbing_retry(
            con,
            job,
            executor=session["executor"],
            expected_base_commit_sha=expected_base,
        )
    else:
        allocated = allocate_retry_attempt(
            con,
            job,
            executor=session["executor"],
            expected_base_commit_sha=expected_base,
        )
    if allocated is None:
        con.commit()
        if plumbing:
            print(
                f"[reconcile] {session_db_id}: executor died before durable "
                f"exit state; job {job_id} plumbing budget exhausted"
            )
        else:
            print(
                f"[reconcile] {session_db_id}: executor failed; job {job_id} "
                f"exhausted at attempt {current_attempt}"
            )
        return

    retry_job, replacement_id = allocated
    retry_job["executor"] = session["executor"]
    con.commit()

    try:
        dispatch_result = dispatch(
            retry_job, retry_job["repo"], str(repo_path)
        )
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
        if plumbing:
            print(
                f"[reconcile] {session_db_id}: executor died before durable "
                f"exit state; job {job_id} redispatched as plumbing retry "
                f"{retry_job['plumbing_attempt']} (attempt "
                f"{retry_job['attempt']} unchanged)"
            )
        else:
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


"""Standing answer to an executor that finished and asked for permission.

Every parked question observed so far was already answered by the node packet
the executor was given, so restate that authority instead of waking a human.
"""
_PROCEED_REPLY = (
    "Proceed as specified in the node packet you were given; it carries full "
    "authority and no further approval is required. Do not ask whether to "
    "finalize, commit, or open a PR — commit your work and open the PR. "
    "If the packet describes an expected or intentional failure, produce that "
    "failure rather than fixing it. If the work already exists on the base "
    "branch, say so in the PR body and change nothing. If you cannot proceed "
    "because information is genuinely missing from the packet, state exactly "
    "which field is missing and stop."
)


def _handle_awaiting_reply(
    con, adapter, session_ref, session_db_id: str, job_id: str, current_state: str
) -> None:
    """Answer a question once; escalate only if the answer did not unstick it."""
    if current_state == "awaiting_reply" or not hasattr(adapter, "reply"):
        _handle_needs_operator(
            con,
            session_db_id,
            job_id,
            "executor still asking after standing reply"
            if current_state == "awaiting_reply"
            else "executor asked a question but adapter cannot reply",
        )
        return

    if not adapter.reply(session_ref, _PROCEED_REPLY):
        print(
            f"[reconcile] {session_db_id}: reply failed; will retry next tick"
        )
        return

    update_executor_session_state(con, session_db_id, state="awaiting_reply")
    con.commit()
    print(
        f"[reconcile] {session_db_id}: answered executor question (job {job_id})"
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
            expected_base_commit_sha=pending.expected_base_commit_sha,
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
    mark_jobs_awaiting_review(con, (pending.job_id,))
    con.commit()

    # Provisional flow (mode 1 default): a qualifying verdict marks the node
    # provisional so dependents unblock without waiting on the operator.
    # complete remains human-only; this never writes it. human_gate nodes
    # (mode 2) are skipped inside. Non-fatal by design.
    maybe_mark_provisional(
        project_id=pending.project_id,
        node_id=pending.node_id,
        verification=verification,
        evidence_ref=result_id,
    )


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


def _parent_commit(repo_path: Path, result_sha: str) -> str | None:
    """Resolve the feature commit's first parent for node-scoped evaluation."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", f"{result_sha}^{{commit}}^"],
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
