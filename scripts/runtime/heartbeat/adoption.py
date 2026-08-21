"""Birth path for work completed outside the runtime.

Writes event `mapped` + job `awaiting_result` + executor_session `collected`
in one transaction. The heartbeat evaluates them on the next tick.
"""

from __future__ import annotations

import json, secrets, sqlite3, subprocess, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..repo_resolver import resolution_candidates, resolve_repo_checkout
from .dispatcher import ADAPTERS
from .graph_reader import GraphReader
from .job_factory import build_job
from .provisional_status import TERMINAL_STATUSES
from .state_recorder import insert_executor_session, insert_job, now as rec_now

NON_TERMINAL_JOB_STATUSES = (
    "ready", "running", "awaiting_result", "awaiting_review",
)
BASE_OMITTED_WARNING = (
    "WARNING: --base omitted; the verifier loses its diff boundary and will "
    "evaluate the whole tree instead of the node's change."
)
_EVENT_COLS = (
    "event_id, schema_version, received_at, source, event_type, actor, url, "
    "project_id, project_node_candidates, scope_status, priority, risk_level, "
    "routing, status, repo"
)


class AdoptionError(Exception):
    """Guard failure. Message is operator-facing."""


@dataclass(frozen=True)
class AdoptionPlan:
    event: dict
    job: dict
    session: dict


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True,
    )


def _sha(repo: Path, rev: str, label: str) -> str:
    r = _git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")
    if r.returncode != 0:
        raise AdoptionError(f"{label} {rev!r} does not resolve in {repo}")
    return r.stdout.strip()


def _checkout(project, config_path: Path) -> Path:
    path = resolve_repo_checkout(project.repo, config_root=config_path)
    if path is not None:
        return path
    tried = ", ".join(str(p) for p in resolution_candidates(
        project.repo, config_root=config_path
    ))
    raise AdoptionError(
        f"cannot resolve repo {project.repo!r} (tried: {tried or 'none'})"
    )


def _guard_rows(con, project_id, node_id, commit_sha):
    ph = ",".join("?" * len(NON_TERMINAL_JOB_STATUSES))
    row = con.execute(
        f"SELECT job_id, status FROM jobs WHERE project_id=? AND node_id=? "
        f"AND status IN ({ph}) LIMIT 1",
        (project_id, node_id, *NON_TERMINAL_JOB_STATUSES),
    ).fetchone()
    if row is not None:
        raise AdoptionError(
            f"non-terminal job {row['job_id']} already exists for "
            f"({project_id}, {node_id}) status={row['status']}"
        )
    row = con.execute(
        "SELECT session_db_id, job_id FROM executor_sessions "
        "WHERE result_commit_sha=? LIMIT 1", (commit_sha,),
    ).fetchone()
    if row is not None:
        raise AdoptionError(
            f"session {row['session_db_id']} already carries "
            f"result_commit_sha={commit_sha} (job {row['job_id']}); re-run is a no-op"
        )


def adopt(
    *,
    con: sqlite3.Connection,
    project_id: str,
    node_id: str,
    commit: str,
    base: str | None = None,
    executor: str = "local_subprocess",
    dry_run: bool = False,
    config_path: str | Path | None = None,
    runtime_root: Path,
) -> AdoptionPlan:
    """Resolve the node, run guards, write or preview the three rows."""
    if executor not in ADAPTERS:
        raise AdoptionError(
            f"executor {executor!r} is not an ADAPTERS key; "
            f"_reconcile_one would skip it before the collected branch. "
            f"known: {sorted(ADAPTERS)}"
        )
    if not base:
        print(BASE_OMITTED_WARNING, file=sys.stderr)
    reader = GraphReader(config_path=str(config_path) if config_path else None)
    try:
        project = reader.load_project(project_id)
        node = reader.load_node(project_id, node_id)
    except FileNotFoundError as exc:
        raise AdoptionError(str(exc)) from exc
    if node.status in TERMINAL_STATUSES:
        raise AdoptionError(
            f"node {node.node_id} status is {node.status!r} (terminal); "
            "adoption refuses to rewrite finished graph work"
        )
    checkout = _checkout(project, reader.config_path)
    commit_sha = _sha(checkout, commit, "commit")
    base_sha = _sha(checkout, base, "base") if base else None
    if base_sha and _git(checkout, "merge-base", "--is-ancestor",
                         base_sha, commit_sha).returncode:
        raise AdoptionError(f"base {base_sha} is not an ancestor of commit {commit_sha}")
    _guard_rows(con, project_id, node_id, commit_sha)

    stamp = datetime.now(timezone.utc)
    event = {
        "event_id": f"evt_adopt_{stamp.strftime('%Y%m%dT%H%M%S')}_{node_id}_{secrets.token_hex(3)}",
        "schema_version": "1.0", "received_at": stamp.isoformat(),
        "source": "adopt_manual", "event_type": "issue.opened", "actor": "operator",
        "url": f"adopt://node: {node_id}", "project_id": project.project_id,
        "project_node_candidates": json.dumps([node_id]), "scope_status": "in_scope",
        "priority": "pending", "risk_level": "pending",
        "routing": json.dumps({"selected_executor": executor}),
        "status": "mapped", "repo": project.repo,
    }
    job = build_job(node, event, project_id, project.repo, runtime_root, executor)
    job["status"] = job["queue_state"] = "awaiting_result"
    job["executor"] = executor
    session_id = f"adopt_{node_id}_{commit_sha[:12]}"
    session = {
        "executor": executor, "session_id": session_id, "state": "collected",
        "result_commit_sha": commit_sha, "expected_base_commit_sha": base_sha,
    }
    plan = AdoptionPlan(event=event, job=job, session=session)
    if dry_run:
        print(json.dumps({"event": event, "job": job, "session": session},
                         indent=2, default=str))
        return plan
    placeholders = ", ".join(f":{c.strip()}" for c in _EVENT_COLS.split(","))
    try:
        con.execute(
            f"INSERT INTO events ({_EVENT_COLS}) VALUES ({placeholders})", event,
        )
        insert_job(con, job)
        sid = insert_executor_session(
            con, job["job_id"], executor, session_id, state="collected",
        )
        con.execute(
            "UPDATE executor_sessions SET result_commit_sha=?, "
            "expected_base_commit_sha=?, updated_at=? WHERE session_db_id=?",
            (commit_sha, base_sha, rec_now(), sid),
        )
        session["session_db_id"] = sid
        con.commit()
    except Exception:
        con.rollback()
        raise
    return plan
