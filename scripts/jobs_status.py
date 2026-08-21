"""
jobs_status.py — Inspect and set runtime job state.

Usage:
    python3 scripts/jobs_status.py list [--state awaiting_review]
    python3 scripts/jobs_status.py show <job_id | node_id> [--full]
    python3 scripts/jobs_status.py results [--all]
    python3 scripts/jobs_status.py set <job_id | node_id> <state> --reason "..."
    python3 scripts/jobs_status.py retry <job_id | node_id> --reason "..."
    python3 scripts/jobs_status.py adopt --project <id> --node <id> --commit <sha> [--base <sha>]

This module owns runtime job state only. It never writes graph/node status.
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure adapters package is importable for the read-only local_subprocess
# status probe in cmd_show. Local execution is the only adapter that owns
# durable on-disk state, so a read-only comparison is meaningful here.
sys.path.insert(0, str(Path(__file__).parent.parent))

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"

QUEUE_STATES = (
    "intake",
    "classified",
    "blocked",
    "ready",
    "running",
    "awaiting_result",
    "awaiting_review",
    "complete",
    "failed",
    "deferred",
    "cancelled",
)
JOB_STATUSES = {
    "ready",
    "running",
    "awaiting_result",
    "awaiting_review",
    "complete",
    "failed",
    # Terminal operator-recovery states. Without these, `jobs set cancelled`
    # updated queue_state but left status active — and dispatch_blockers
    # checks BOTH columns, so the "settle and redispatch" path could never
    # actually clear a blocker.
    "cancelled",
    "deferred",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def resolve_job(con, ref: str):
    """Accept a job_id or node_id; node_id must match exactly one job."""
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (ref,)).fetchone()
    if job:
        return job
    rows = con.execute(
        "SELECT * FROM jobs WHERE node_id = ? ORDER BY created_at DESC", (ref,)
    ).fetchall()
    if not rows:
        sys.exit(f"No job found for '{ref}' (tried job_id, then node_id).")
    if len(rows) > 1:
        print(f"'{ref}' matches {len(rows)} jobs — use a job_id:")
        for r in rows:
            print(f"  {r['job_id']}  {r['queue_state']}  created {r['created_at']}")
        sys.exit(1)
    return rows[0]


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _state_ansi(state: str) -> str:
    """TTY emphasis for queue/job states operators scan first."""
    if not _stdout_is_tty():
        return ""
    key = (state or "").lower().replace(" ", "_")
    styles = {
        "awaiting_review": "\033[1;33m",  # bold yellow — human queue
        "awaiting_result": "\033[1;36m",  # bold cyan
        "ready": "\033[1;36m",
        "running": "\033[1;35m",          # bold magenta
        "complete": "\033[1;32m",         # bold green
        "failed": "\033[1;31m",           # bold red
        "blocked": "\033[33m",
        "deferred": "\033[35m",
        "cancelled": "\033[2m",
        "intake": "\033[2m",
        "classified": "\033[2m",
        "pass": "\033[1;32m",
        "fail": "\033[1;31m",
    }
    return styles.get(key, "\033[1m")


def _paint(value: str, style_key: str | None = None, *, width: int | None = None) -> str:
    """Color one field; pad before color so ANSI codes don't skew columns."""
    text = str(value)
    if width is not None:
        text = f"{text:<{width}}"
    color = _state_ansi(style_key if style_key is not None else value)
    if not color:
        return text
    return f"{color}{text}\033[0m"


def cmd_list(args):
    con = connect()
    q = "SELECT job_id, node_id, queue_state, attempt, max_attempts, created_at FROM jobs"
    params = ()
    if args.state:
        q += " WHERE queue_state = ?"
        params = (args.state,)
    q += " ORDER BY created_at DESC"
    rows = con.execute(q, params).fetchall()
    if not rows:
        print("No jobs." + (f" (state={args.state})" if args.state else ""))
        return
    for r in rows:
        state = r["queue_state"] or "?"
        print(
            f"{r['job_id']}  {_paint(state, width=16)} {r['node_id']:<26} "
            f"attempt {r['attempt']}/{r['max_attempts']}  {r['created_at'][:10]}"
        )


def parse_check(row):
    try:
        return json.loads(row["acceptance_check"]) if row["acceptance_check"] else {}
    except json.JSONDecodeError:
        return {}


def _format_lane_clock(lane: dict | None) -> str:
    lane = lane or {}
    status = lane.get("status") or "n/a"
    elapsed = lane.get("elapsed_s")
    tools = lane.get("tool_calls")
    clock = "-" if elapsed is None else f"{elapsed}s"
    calls = "0" if tools is None else str(tools)
    return f"{status} {clock} {calls} tools"


def _format_evaluation_timing(timing: dict) -> str:
    wall = timing.get("wall_s")
    wall_s = "-" if wall is None else f"{wall}s"
    return (
        f"timing: wall={wall_s}  "
        f"criteria={_format_lane_clock(timing.get('criteria'))}  "
        f"integrity={_format_lane_clock(timing.get('integrity'))}"
    )


def print_evaluation(check, full=False):
    """Print the evaluator's output for one result row — the thing under review."""
    if not check:
        print("          (no evaluator output on this result)")
        return
    integrity = check.get("integrity") or {}
    verdict = check.get("verdict") or "-"
    print(f"  verdict: {_paint(verdict)}")
    reasoning = integrity.get("reasoning") or check.get("reasoning")
    if reasoning:
        print("  why:")
        for line in str(reasoning).splitlines():
            print(f"    {line}")
    else:
        print("  why: (no overall evaluator reasoning recorded)")
    if check.get("required_next_action"):
        print(
            f"  next action: {check['required_next_action']}  "
            "(evaluator recommendation, not a decision)"
        )
    for f in check.get("criteria_findings") or []:
        print(f"  criterion: {f.get('criterion_id')}  ->  {f.get('judgment')}")
        if full and f.get("reasoning"):
            print(f"    reasoning: {f['reasoning']}")
        for ev in f.get("evidence") or []:
            print(f"    evidence: {ev}")
    for f in integrity.get("findings") or []:
        print(f"  integrity: [{f.get('severity')}] {f.get('summary')}")
    # Phase 3: graph observations (forward-looking, do not affect verdict)
    for o in integrity.get("graph_observations") or []:
        print(f"  graph observation: [{o.get('severity')}] {o.get('summary')}")
    for rec in integrity.get("graph_recommendations") or []:
        if not isinstance(rec, dict):
            continue
        action = rec.get("action") or "?"
        ids = ",".join(str(i) for i in (rec.get("affected_node_ids") or []))
        rationale = str(rec.get("rationale") or "")
        if len(rationale) > 120:
            rationale = rationale[:117] + "..."
        print(f"  graph recommendation: [{action}] {ids} — {rationale}")
    # Criteria-lane free-text intelligence + deterministic human-review questions.
    risks = check.get("semantic_risks")
    if risks:
        print("  risks:")
        for line in str(risks).splitlines():
            print(f"    {line}")
    followups = check.get("followup_candidates")
    if followups:
        print("  followups:")
        for line in str(followups).splitlines():
            print(f"    {line}")
    for q in check.get("human_review_questions") or []:
        cid = q.get("criterion_id") if isinstance(q, dict) else "?"
        question = q.get("question") if isinstance(q, dict) else str(q)
        print(f"  question ({cid}): {question}")
    print(
        f"  evaluator signals: criteria={check.get('criteria_verdict')} "
        f"@ {check.get('criteria_confidence')}  "
        f"integrity={integrity.get('verdict')} @ {integrity.get('confidence')}"
    )
    # Phase 1 provenance: show the exact tree the evaluator judged.
    tree_sha = check.get("evaluated_tree_sha")
    commit_sha = check.get("evaluated_commit_sha")
    merge_sha = check.get("merge_commit_sha")
    if commit_sha or tree_sha or merge_sha:
        if commit_sha:
            match = "  (match)" if merge_sha and commit_sha == merge_sha else "  (mismatch)" if merge_sha else ""
            print(f"  provenance: commit={commit_sha}  merge={merge_sha or 'n/a'}{match}")
        else:
            print(f"  provenance: tree={tree_sha or 'n/a'}  merge={merge_sha or 'n/a'}  (different SHA types; not compared)")
    if check.get("pr_ref"):
        print(f"  PR: {check['pr_ref']}")
    # Phase 2 coverage: quick signal for the operator
    cov = check.get("context_coverage")
    if cov:
        crit_raw = cov.get("criteria", "n/a")
        crit = crit_raw.get("rating", "n/a") if isinstance(crit_raw, dict) else crit_raw
        integ = cov.get("integrity", {}).get("rating", "n/a") if isinstance(cov.get("integrity"), dict) else "n/a"
        print(f"  coverage: criteria={crit}  integrity={integ}  overall={cov.get('overall', 'n/a')}")
    lane_status = check.get("lane_status") or {}
    harness_error = check.get("harness_error") or {}
    if lane_status:
        print(f"  lane status: criteria={lane_status.get('criteria', 'n/a')}  integrity={lane_status.get('integrity', 'n/a')}")
    for lane in ("criteria", "integrity"):
        if harness_error.get(lane):
            print(f"  harness error: {lane}={harness_error[lane]}")
    if check.get("receipt_path"):
        print(f"  receipt: {check['receipt_path']}")
    timing = check.get("evaluation_timing")
    if isinstance(timing, dict) and timing:
        print(f"  {_format_evaluation_timing(timing)}")


def _read_local_subprocess_status(session_id: str) -> tuple[str | None, str | None]:
    """Read-only durable adapter probe for one local_subprocess session.

    Resolves the spool root from $GDDP_LOCAL_SUBPROCESS_SPOOL_DIR when
    present, otherwise from the runtime default at
    RUNTIME_ROOT/jobs/local-subprocess-spool. Calls the adapter module's
    free read function directly, so a normal operator shell without
    dispatch argv or local_subprocess env can still see durable state.

    Returns (adapter_state, adapter_error) or (None, error_string) if the
    read couldn't run. Never mutates the spool, the adapter, or the DB.
    """
    try:
        from adapters.executor_protocol import SessionStatus  # noqa: F401  (sanity import)
        from adapters.local_subprocess_adapter import read_local_subprocess_status
    except Exception as exc:  # pragma: no cover
        return None, f"adapter import failed: {exc}"
    spool_env = os.environ.get("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR")
    spool_root = Path(spool_env) if spool_env else RUNTIME_ROOT / "jobs" / "local-subprocess-spool"
    try:
        status = read_local_subprocess_status(spool_root, session_id)
    except Exception as exc:
        return None, f"adapter probe failed: {exc}"
    return status.state, status.error


def _print_executor_attempts(con, job_id: str) -> None:
    """Print the per-attempt executor evidence: DB state + durable adapter view.

    Goal: when a job is `running`/`dispatched` in the DB but the worker is
    already terminal on disk (or vice versa), the operator sees the divergence
    without re-running the dispatcher.
    """
    sessions = con.execute(
        """
        SELECT attempt_index, executor, session_id, state, error,
               result_commit_sha, expected_base_commit_sha, created_at, updated_at
          FROM executor_sessions
         WHERE job_id = ?
         ORDER BY COALESCE(attempt_index, 0), created_at
        """,
        (job_id,),
    ).fetchall()
    if not sessions:
        print(f"  executor attempt: (none on record)")
        return
    for s in sessions:
        attempt = s["attempt_index"] if s["attempt_index"] is not None else "?"
        print(
            f"  executor attempt: idx={attempt}  executor={s['executor']}  "
            f"db_state={s['state']}  session_id={s['session_id']}"
        )
        if s["result_commit_sha"]:
            print(f"        result sha: {s['result_commit_sha']}")
        if s["expected_base_commit_sha"] and s["expected_base_commit_sha"] != s["result_commit_sha"]:
            print(f"        base sha:   {s['expected_base_commit_sha']}")
        if s["error"]:
            print(f"        db error:   {s['error']}")
        if s["executor"] == "local_subprocess":
            adapter_state, adapter_error = _read_local_subprocess_status(s["session_id"])
            if adapter_state is not None:
                agreement = "ok" if adapter_state == s["state"] else "DIVERGENT"
                print(
                    f"        adapter:    {adapter_state}  ({agreement})"
                )
                if adapter_error:
                    print(f"        adapter err: {adapter_error}")
            else:
                if adapter_error:
                    print(f"        adapter:    (probe failed) {adapter_error}")
        print(
            f"        timestamps: created={s['created_at']}  updated={s['updated_at']}"
        )


def cmd_show(args):
    con = connect()
    job = resolve_job(con, args.ref)
    results = con.execute(
        "SELECT received_at, outcome, status, acceptance_check "
        "FROM results WHERE job_id = ? ORDER BY received_at DESC",
        (job["job_id"],),
    ).fetchall()
    print("EVALUATOR RESULT")
    if not results:
        print("  MISSING — evaluator has not returned a result for this job.")
    for index, r in enumerate(results):
        if index:
            print("\nEARLIER EVALUATOR RESULT")
        print_evaluation(parse_check(r), full=args.full)
        print(f"  result record: {r['received_at']}  {r['outcome']}/{r['status']}")

    decisions = con.execute(
        "SELECT created_at, action, reason FROM decision_results WHERE node_id = ? ORDER BY created_at",
        (job["node_id"],),
    ).fetchall()
    if decisions:
        print("\nHUMAN DECISIONS")
        for d in decisions:
            print(f"  {d['created_at']}  {d['action']}  {d['reason'] or ''}")

    print("\nJOB RECORD")
    for key in ("title", "node_id", "job_id", "queue_state", "status", "executor",
                "job_type", "attempt", "max_attempts", "created_at", "artifacts_dir"):
        value = job[key]
        if key in ("queue_state", "status"):
            value = _paint(value or "?")
        print(f"  {key}: {value}")
    print("\nEXECUTOR RECORD")
    _print_executor_attempts(con, job["job_id"])


def config_root():
    return Path(os.environ.get("GDDP_CONFIG_PATH", str(RUNTIME_ROOT.parent / "gddp-config")))


def cmd_results(args):
    con = connect()
    rows = con.execute(
        "SELECT r.received_at, r.acceptance_check, j.node_id, j.project_id, r.job_id "
        "FROM results r JOIN jobs j ON j.job_id = r.job_id ORDER BY r.received_at",
    ).fetchall()
    if not rows:
        print("No evaluator results.")
        return

    if args.all:
        nodes = set()
        for r in rows:
            check = parse_check(r)
            verdict = check.get("verdict") or "-"
            nodes.add((r["project_id"], r["node_id"]))
            print(
                f"{r['received_at'][:19]}  {_paint(verdict, width=5)} "
                f"{r['project_id'] or '-':<14} "
                f"{r['node_id'] or '-':<26} {r['job_id']}"
            )
            if check.get("receipt_path"):
                print(f"{'':21}receipt: {check['receipt_path']}")
        print(f"\n{len(rows)} result row(s) across {len(nodes)} node(s).")
        return

    # Default: per-project summary — counts plus where the files live, so the
    # answer to "how many rows/receipts exist?" doesn't grow with each result.
    projects = {}
    for r in rows:
        p = projects.setdefault(r["project_id"] or "-", {"rows": 0, "nodes": set(), "latest": r})
        p["rows"] += 1
        p["nodes"].add(r["node_id"])
        p["latest"] = r  # rows are ordered by received_at

    live_root = config_root() / "verification"
    for project_id in sorted(projects):
        p = projects[project_id]
        latest_check = parse_check(p["latest"])
        latest_verdict = latest_check.get("verdict") or "-"
        print(f"{project_id:<16} {len(p['nodes'])} node(s)  {p['rows']} result row(s)  "
              f"latest: {latest_verdict} {p['latest']['node_id']} "
              f"({p['latest']['received_at'][:10]})")
        proj_dir = live_root / project_id
        # Receipts live in per-node subdirs (<project>/<node>/*.json); a
        # top-level glob undercounts and falsely reports zero.
        receipts = sorted(proj_dir.rglob("*.json")) if proj_dir.exists() else []
        print(f"{'':17}receipts: {len(receipts)} in {proj_dir}")
        evals = proj_dir / "evaluations.yaml"
        if evals.exists():
            print(f"{'':17}export:   {evals}")

    total_nodes = {(pid, n) for pid, p in projects.items() for n in p["nodes"]}
    print(f"\n{len(rows)} result row(s), {len(total_nodes)} node(s), "
          f"{len(projects)} project(s).  (--all for every row)")


def _apply_resolved_state_change(con, job, state: str, reason: str) -> int:
    old = job["queue_state"]
    if old == state:
        print(f"{job['job_id']} already '{old}' — nothing to do.")
        return 0

    con.execute(
        "UPDATE jobs SET queue_state = ? WHERE job_id = ?",
        (state, job["job_id"]),
    )
    if state in JOB_STATUSES:
        con.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (state, job["job_id"]),
        )
    con.execute(
        "UPDATE queue_records SET queue = ? WHERE job_id = ?",
        (state, job["job_id"]),
    )

    action = (
        "accept_node"
        if old == "awaiting_review" and state == "complete"
        else "manual_status_change"
    )
    con.execute(
        "INSERT INTO decision_results "
        "(result_id, action, node_id, project_id, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            f"dec_{uuid.uuid4().hex[:12]}",
            action,
            job["node_id"],
            job["project_id"],
            reason,
            now(),
        ),
    )
    con.commit()
    print(f"Done: {job['job_id']} -> {state}  (audit: {action})")
    return 0


def apply_state_change(*, ref: str, state: str, reason: str) -> int:
    """Apply one menu-confirmed job-state change."""
    if state not in QUEUE_STATES:
        raise ValueError(
            f"Invalid state {state!r}. Valid: {' '.join(QUEUE_STATES)}"
        )
    reason_text = reason.strip()
    if not reason_text:
        raise ValueError("A reason is required for every runtime state change.")
    con = connect()
    try:
        job = resolve_job(con, ref)
        return _apply_resolved_state_change(con, job, state, reason_text)
    finally:
        con.close()


def cmd_set(args):
    if args.state not in QUEUE_STATES:
        sys.exit(f"Invalid state '{args.state}'. Valid: {' '.join(QUEUE_STATES)}")
    reason = args.reason.strip()
    if not reason:
        sys.exit("A reason is required for every runtime state change.")

    con = connect()
    try:
        job = resolve_job(con, args.ref)
        old = job["queue_state"]
        if old == args.state:
            print(f"{job['job_id']} already '{old}' — nothing to do.")
            return 0
        print(f"{job['job_id']}  ({job['node_id']})")
        print(f"  {old}  ->  {args.state}")
        if not args.yes:
            if input("Proceed? [y/N] ").strip().lower() != "y":
                sys.exit("Aborted.")
        return _apply_resolved_state_change(con, job, args.state, reason)
    finally:
        con.close()


def apply_retry(*, ref: str, reason: str) -> int:
    """Reject the reviewed result and dispatch the next attempt."""
    reason_text = reason.strip()
    if not reason_text:
        raise ValueError("A reason is required for reject + retry.")

    con = connect()
    try:
        job = resolve_job(con, ref)
        job_id = str(job["job_id"])
        node_id = str(job["node_id"])
        project_id = str(job["project_id"])
        if (
            job["status"] != "awaiting_review"
            or job["queue_state"] != "awaiting_review"
        ):
            print(
                f"ERROR: {job_id} is {job['queue_state']}; "
                "reject + retry requires awaiting_review."
            )
            return 2
    finally:
        con.close()

    from scripts.runtime.return_router import retry_reviewed_job

    result = retry_reviewed_job(job_id, reason_text)
    status = str(result.get("status") or "retry_failed")
    if status == "retry_rejected":
        print(f"ERROR: retry rejected — {result.get('reason', 'unknown reason')}")
        return 1

    action = (
        "reject_and_retry"
        if status == "redispatched"
        else "reject_and_retry_failed"
    )
    con = connect()
    try:
        con.execute(
            "INSERT INTO decision_results "
            "(result_id, action, node_id, project_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"dec_{uuid.uuid4().hex[:12]}",
                action,
                node_id,
                project_id,
                reason_text,
                now(),
            ),
        )
        con.commit()
    finally:
        con.close()

    if status == "redispatched":
        print(f"Done: rejected reviewed result; {job_id} retry dispatched.")
        return 0
    print(
        f"ERROR: reviewed result rejected; retry dispatch failed — "
        f"{result.get('dispatch_error', status)}"
    )
    return 1


def cmd_adopt(args):
    from scripts.runtime.heartbeat.adoption import (
        AdoptionError,
        adopt,
        format_adopt_rows,
    )
    try:
        plan = adopt(
            project_id=args.project,
            node_id=args.node,
            commit=args.commit,
            base=args.base,
            executor=args.executor,
            dry_run=args.dry_run,
            runtime_root=RUNTIME_ROOT,
        )
    except AdoptionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(format_adopt_rows(plan))
    if args.dry_run:
        print("dry-run: no rows written")
    else:
        print(f"adopted {args.node} -> {plan['job']['job_id']}")
    return 0


def cmd_retry(args):
    reason = args.reason.strip()
    if not reason:
        sys.exit("A reason is required for reject + retry.")

    con = connect()
    try:
        job = resolve_job(con, args.ref)
        print(f"{job['job_id']}  ({job['node_id']})")
        print(f"  {job['queue_state']}  ->  reject result + retry")
    finally:
        con.close()
    if not args.yes:
        if input("Proceed? [y/N] ").strip().lower() != "y":
            sys.exit("Aborted.")
    return apply_retry(ref=args.ref, reason=reason)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list jobs and states")
    p_list.add_argument("--state", help="filter by queue_state")
    p_list.set_defaults(fn=cmd_list)

    p_show = sub.add_parser("show", help="show one job (accepts job_id or node_id)")
    p_show.add_argument("ref")
    p_show.add_argument(
        "--full", action="store_true", help="include criterion-level reasoning"
    )
    p_show.set_defaults(fn=cmd_show)

    p_results = sub.add_parser("results", help="evaluator output summary: counts + paths per project")
    p_results.add_argument("--all", action="store_true", help="list every result row instead of the summary")
    p_results.set_defaults(fn=cmd_results)

    p_set = sub.add_parser("set", help="set runtime job state")
    p_set.add_argument("ref", help="job ID or uniquely matching node ID")
    p_set.add_argument("state")
    p_set.add_argument("--reason", required=True, help="why — stored in the audit row")
    p_set.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    p_set.set_defaults(fn=cmd_set)

    p_retry = sub.add_parser(
        "retry", help="reject a reviewed result and retry the same job"
    )
    p_retry.add_argument("ref", help="job ID or uniquely matching node ID")
    p_retry.add_argument(
        "--reason", required=True, help="human fix-list injected into the retry"
    )
    p_retry.add_argument("--yes", action="store_true", help="skip confirmation")
    p_retry.set_defaults(fn=cmd_retry)

    p_adopt = sub.add_parser(
        "adopt",
        help="record out-of-runtime work as a collected session for evaluation",
    )
    p_adopt.add_argument("--project", required=True, help="graph project id")
    p_adopt.add_argument("--node", required=True, help="node id to adopt")
    p_adopt.add_argument("--commit", required=True, help="result commit sha")
    p_adopt.add_argument(
        "--base", default=None,
        help="expected base commit sha (warns if omitted)",
    )
    p_adopt.add_argument(
        "--executor", default="local_subprocess",
        help="ADAPTERS key; default local_subprocess",
    )
    p_adopt.add_argument(
        "--dry-run", action="store_true",
        help="print the three rows and exit without writing",
    )
    p_adopt.set_defaults(fn=cmd_adopt)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
