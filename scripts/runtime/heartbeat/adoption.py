"""Birth path for work completed outside the runtime.

One transaction: event mapped + job awaiting_result + session collected.
The heartbeat evaluates via the ordinary collected-resume path.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .dispatcher import ADAPTERS
from .graph_reader import GraphReader
from .job_factory import build_job
from .provisional_status import TERMINAL_STATUSES
from .state_recorder import insert_executor_session, insert_job, now
from ..repo_resolver import resolve_repo_checkout

RUNTIME_ROOT = Path(
    os.environ.get("GDDP_RUNTIME_ROOT")
    or os.environ.get("OPCLAW_ROOT", Path(__file__).resolve().parents[3])
)
ACTIVE_JOB_STATUSES = ("ready", "running", "awaiting_result", "awaiting_review")
DEFAULT_EXECUTOR = "local_subprocess"


class AdoptionError(Exception):
    """Guard failure; no rows written."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _resolve_commit(repo: Path, ref: str) -> str:
    proc = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    sha = proc.stdout.strip()
    if proc.returncode != 0 or not sha:
        raise AdoptionError(
            f"commit {ref!r} does not resolve in {repo}: "
            f"{(proc.stderr or proc.stdout or 'unknown git error').strip()}"
        )
    return sha


def format_adopt_rows(plan: dict) -> str:
    e, j, s = plan["event"], plan["job"], plan["session"]
    return (
        f"event:\n  event_id: {e['event_id']}\n  source:   {e['source']}\n"
        f"  status:   {e['status']}\n  url:      {e['url']}\n  repo:     {e['repo']}\n"
        f"job:\n  job_id:      {j['job_id']}\n  node_id:     {j['node_id']}\n"
        f"  project_id:  {j['project_id']}\n  repo:        {j['repo']}\n"
        f"  executor:    {j['executor']}\n  status:      {j['status']}\n"
        f"  queue_state: {j['queue_state']}\n"
        f"session:\n  session_id:               {s['session_id']}\n"
        f"  state:                    {s['state']}\n"
        f"  result_commit_sha:        {s['result_commit_sha']}\n"
        f"  expected_base_commit_sha: {s['expected_base_commit_sha']}"
    )


def adopt(
    *,
    project_id: str,
    node_id: str,
    commit: str,
    base: str | None = None,
    executor: str = DEFAULT_EXECUTOR,
    dry_run: bool = False,
    config_path: str | None = None,
    runtime_root: Path | None = None,
    db_path: Path | None = None,
    con: sqlite3.Connection | None = None,
) -> dict:
    """Resolve the node, run guards, write (or preview) the three adopt rows."""
    if executor not in ADAPTERS:
        raise AdoptionError(
            f"executor {executor!r} is not an ADAPTERS key; known: {sorted(ADAPTERS)}"
        )
    if not base:
        print(
            "WARNING: --base omitted. The verifier will not have a diff boundary "
            "and may evaluate the whole tree instead of the node's change.",
            file=sys.stderr,
        )
    root = Path(runtime_root) if runtime_root else RUNTIME_ROOT
    reader = GraphReader(config_path=config_path)
    try:
        project = reader.load_project(project_id)
        node = reader.load_node(project_id, node_id)
    except FileNotFoundError as exc:
        raise AdoptionError(str(exc)) from exc
    if node.status in TERMINAL_STATUSES:
        raise AdoptionError(
            f"node {node_id} status is {node.status!r}; "
            f"refusing terminal statuses {sorted(TERMINAL_STATUSES)}"
        )
    checkout = resolve_repo_checkout(project.repo, config_root=reader.config_path)
    if checkout is None:
        raise AdoptionError(f"cannot resolve checkout for repo {project.repo!r}")
    commit_sha = _resolve_commit(checkout, commit)
    base_sha = _resolve_commit(checkout, base) if base else None
    if base_sha and _git(checkout, "merge-base", "--is-ancestor", base_sha, commit_sha).returncode:
        raise AdoptionError(f"base {base_sha} is not an ancestor of commit {commit_sha}")

    owns = con is None
    if owns:
        con = sqlite3.connect(Path(db_path) if db_path else root / "db" / "queue.db")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
    try:
        return _write_rows(
            con, project=project, node=node, commit_sha=commit_sha,
            base_sha=base_sha, executor=executor, dry_run=dry_run,
            runtime_root=root,
        )
    finally:
        if owns:
            con.close()


def _write_rows(con, *, project, node, commit_sha, base_sha, executor, dry_run, runtime_root):
    project_id, node_id = project.project_id, node.node_id
    placeholders = ",".join("?" * len(ACTIVE_JOB_STATUSES))
    active = con.execute(
        f"SELECT job_id, status FROM jobs WHERE project_id = ? AND node_id = ? "
        f"AND status IN ({placeholders}) LIMIT 1",
        (project_id, node_id, *ACTIVE_JOB_STATUSES),
    ).fetchone()
    if active:
        raise AdoptionError(
            f"non-terminal job {active['job_id']} already exists for "
            f"({project_id}, {node_id}) status={active['status']}"
        )
    existing = con.execute(
        "SELECT session_db_id FROM executor_sessions WHERE result_commit_sha = ? LIMIT 1",
        (commit_sha,),
    ).fetchone()
    if existing:
        raise AdoptionError(
            f"session {existing['session_db_id']} already records "
            f"result_commit_sha={commit_sha}"
        )

    ts = datetime.now(timezone.utc)
    event_id = f"evt_adopt_{ts.strftime('%Y%m%dT%H%M%S')}_{node_id}_{secrets.token_hex(3)}"
    event = {
        "event_id": event_id, "source": "adopt_manual", "status": "mapped",
        "url": f"adopt://node: {node_id}", "project_id": project_id,
        "repo": project.repo, "project_node_candidates": json.dumps([node_id]),
        "received_at": ts.isoformat(), "actor": "adopt",
        "routing": json.dumps({"selected_executor": executor}),
    }
    job = build_job(node, event, project_id, project.repo, runtime_root, executor)
    job["status"] = job["queue_state"] = "awaiting_result"
    session = {
        "session_id": f"adopt_{node_id}_{commit_sha[:7]}", "state": "collected",
        "result_commit_sha": commit_sha, "expected_base_commit_sha": base_sha,
        "executor": executor, "job_id": job["job_id"],
    }
    plan = {"event": event, "job": job, "session": session, "dry_run": dry_run}
    if dry_run:
        return plan
    try:
        con.execute(
            "INSERT INTO events (event_id, schema_version, received_at, source, "
            "event_type, actor, url, project_id, project_node_candidates, "
            "scope_status, priority, risk_level, routing, status, repo) "
            "VALUES (?, '1.0', ?, 'adopt_manual', 'issue.opened', ?, ?, ?, ?, "
            "'pending', 'pending', 'pending', ?, 'mapped', ?)",
            (event_id, event["received_at"], event["actor"], event["url"],
             project_id, event["project_node_candidates"], event["routing"],
             project.repo),
        )
        insert_job(con, job)
        session_db_id = insert_executor_session(
            con, job["job_id"], executor, session["session_id"], state="collected",
        )
        con.execute(
            "UPDATE executor_sessions SET result_commit_sha = ?, "
            "expected_base_commit_sha = ?, updated_at = ? WHERE session_db_id = ?",
            (commit_sha, base_sha, now(), session_db_id),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    session["session_db_id"] = session_db_id
    return plan
