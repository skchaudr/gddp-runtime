"""
orchestrator_pack.py — Assemble the wake pack for the heartbeat orchestrator.

The orchestrator is stateless: every wake is a fresh session, so everything it
knows arrives in this pack. Six surfaces, each answering one question:

    worker      are the agents doing node work progressing?
    plumbing    is the pipe intact — handle, liveness, artifacts, return?
    node        is this node's cut the right size for the time it is taking?
    graph       what is ready, what is blocked, what is the run serving?
    evaluator   is the return path moving, or has a verdict stalled?
    human_gate  how much sits in the operator's queue?

Evaluator and human_gate stay separate from plumbing on purpose. A silent
evaluator and a full review queue are different conditions with different
responses, and merging them into "the pipe is unhealthy" loses both.

Discipline: counts, ids, ages, and paths. File bodies stay on disk and travel
as pointers, matching the evaluator's context policy. A pack that grows past
its target means the assembler started pasting where it should point.

Read-only. This module reads SQLite, graph YAML, and attempt spools; every
write in the system stays with the runtime that owns it.

Usage:
    python3 -m runtime.heartbeat.orchestrator_pack --project gddp-runtime
    python3 -m runtime.heartbeat.orchestrator_pack --project gddp-runtime --json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .graph_reader import GraphReader
from .orchestrator_decision import recent_decisions
from .scope_checker import SATISFIED_DEP_STATUSES

_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(
    os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root)
)
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"

# Job states that hold executor capacity, matching runner._active_job_count.
CAPACITY_JOB_STATES = ("ready", "running")

# Executor session states that mean an attempt is still in the runtime's hands.
LIVE_SESSION_STATES = (
    "dispatching",
    "dispatched",
    "running",
    "awaiting_reply",
    "needs_operator",
    "collected",
)

# Sessions whose work landed and now waits on the verification lane.
EVALUATOR_PENDING_STATES = ("collected",)

# Spool roots by executor, resolved from the same env the adapters read.
_SPOOL_ENV = {
    "cursor_cli": ("GDDP_CURSOR_CLI_SPOOL_DIR", "GDDP_LOCAL_SUBPROCESS_SPOOL_DIR"),
    "pi_rpc": ("GDDP_PI_RPC_SPOOL_DIR", "GDDP_LOCAL_SUBPROCESS_SPOOL_DIR"),
    "local_subprocess": ("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR",),
    "droid": ("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR",),
}
_SPOOL_DEFAULT = RUNTIME_ROOT / "jobs" / "local-subprocess-spool"


# ---------------------------------------------------------------------------
# Surfaces
# ---------------------------------------------------------------------------


@dataclass
class WorkerRow:
    """One in-flight attempt, seen as work in progress."""

    node_id: str
    job_id: str
    executor: str
    attempt_id: str
    session_state: str
    attempt_index: int | None
    age_s: int | None
    last_event_age_s: int | None
    event_count: int | None
    verdict: str = "unknown"


@dataclass
class PlumbingRow:
    """The same attempt, seen as a pipe: handle, liveness, artifacts, return."""

    attempt_id: str
    node_id: str
    handle_minted: bool
    spool_present: bool
    pid_alive: bool | None
    has_events: bool
    has_result: bool
    has_exit: bool
    anomaly: str | None = None


@dataclass
class NodeRow:
    """Node-level shape: is the cut right for the time it is consuming?"""

    node_id: str
    title: str
    status: str
    worker_budget: int | None
    live_workers: int
    wall_time_s: int | None
    attempt: int
    max_attempts: int


@dataclass
class GraphSurface:
    """Ready nodes split by what actually holds them.

    `ready_at_gate` stays separate from `ready_in_flight` because they call for
    opposite responses: a node whose job sits in review belongs to the operator
    and needs patience, while a node with a running job belongs to a worker and
    invites a health judgement. Collapsing them would have the orchestrator
    watch for progress on work that finished days ago.
    """

    total_nodes: int
    status_counts: dict[str, int]
    dispatchable: list[str] = field(default_factory=list)
    ready_in_flight: list[str] = field(default_factory=list)
    ready_at_gate: list[str] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)


@dataclass
class EvaluatorSurface:
    pending: list[dict] = field(default_factory=list)
    recent: list[dict] = field(default_factory=list)


@dataclass
class Capacity:
    max_concurrent_jobs: int | None
    active_jobs: int
    free_slots: int | None


@dataclass
class OrchestratorPack:
    project_id: str
    repo: str
    generated_at: str
    capacity: Capacity
    graph: GraphSurface
    workers: list[WorkerRow]
    plumbing: list[PlumbingRow]
    nodes: list[NodeRow]
    evaluator: EvaluatorSurface
    human_gate: list[dict]
    steer: list[dict]
    # What earlier wakes concluded and why. Sleep takes the inference; these
    # carry the operational continuity forward in its place.
    decisions: list[dict]
    pointers: dict[str, str]

    def to_json_value(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(db_path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _age_s(stamp: object, now: datetime) -> int | None:
    """Seconds since an ISO timestamp, or None when it is unreadable."""
    if isinstance(stamp, str) and stamp:
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((now - parsed).total_seconds()))
    return None


def _mtime_age_s(path: Path, now: datetime) -> int | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return max(0, int(now.timestamp() - stat.st_mtime))


def _line_count(path: Path, cap: int = 100_000) -> int | None:
    """Count lines cheaply, stopping at a cap so a runaway log stays bounded."""
    try:
        with path.open("rb") as handle:
            total = 0
            for _ in handle:
                total += 1
                if total >= cap:
                    break
            return total
    except OSError:
        return None


def _pid_alive(path: Path) -> bool | None:
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def spool_roots() -> dict[str, Path]:
    """Resolve each local executor's spool root from adapter env, with the
    runtime default as the shared fallback."""
    roots: dict[str, Path] = {}
    for executor, env_names in _SPOOL_ENV.items():
        configured = next(
            (os.environ[name] for name in env_names if os.environ.get(name)),
            None,
        )
        root = Path(configured).expanduser() if configured else _SPOOL_DEFAULT
        roots[executor] = root
    return roots


def _attempt_dir(executor: str, attempt_id: str, roots: dict[str, Path]) -> Path | None:
    """Locate one attempt directory, rejecting anything past a direct child."""
    root = roots.get(executor)
    if root is None or not attempt_id or Path(attempt_id).name != attempt_id:
        return None
    return root / attempt_id


def _worker_verdict(
    last_event_age_s: int | None,
    pid_alive: bool | None,
    has_exit: bool,
    stall_s: int,
) -> str:
    """Name what the numbers already say, so the model reads a judgement
    alongside the evidence for it."""
    if has_exit:
        return "finished"
    if pid_alive is False:
        return "gone"
    if last_event_age_s is not None and last_event_age_s >= stall_s:
        return "quiet"
    if last_event_age_s is not None:
        return "progressing"
    return "unknown"


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble_pack(
    con: sqlite3.Connection,
    reader: GraphReader,
    project_id: str,
    *,
    now: datetime | None = None,
    roots: dict[str, Path] | None = None,
    stall_s: int = 600,
    recent_verdicts: int = 5,
    recent_wakes: int = 5,
    receipts_root: Path | None = None,
) -> OrchestratorPack:
    """Build one wake pack for a project from graph YAML, SQLite, and spools."""
    now = now or datetime.now(timezone.utc)
    roots = roots if roots is not None else spool_roots()

    project = reader.load_project(project_id)
    repo = project.repo

    live = con.execute(
        f"""SELECT es.session_db_id, es.job_id, es.executor, es.session_id,
                   es.state, es.created_at, es.updated_at, es.attempt_index,
                   j.node_id, j.attempt, j.max_attempts, j.created_at AS job_created_at
              FROM executor_sessions es
              JOIN jobs j ON es.job_id = j.job_id
             WHERE es.state IN ({",".join("?" * len(LIVE_SESSION_STATES))})
               AND j.project_id = ?
             ORDER BY es.created_at""",
        (*LIVE_SESSION_STATES, project_id),
    ).fetchall()

    workers: list[WorkerRow] = []
    plumbing: list[PlumbingRow] = []
    live_per_node: dict[str, int] = {}
    wall_per_node: dict[str, int] = {}

    for row in live:
        attempt_id = row["session_id"]
        executor = row["executor"]
        directory = _attempt_dir(executor, attempt_id, roots)
        present = bool(directory and directory.is_dir())

        events = directory / "events.jsonl" if present else None
        last_event_age = _mtime_age_s(events, now) if events else None
        event_count = _line_count(events) if events else None
        has_events = bool(events and events.exists())
        has_result = bool(present and (directory / "result.json").exists())
        has_exit = bool(present and (directory / "exit.json").exists())
        pid_alive = _pid_alive(directory / "pid") if present else None
        if pid_alive is None and present:
            pid_alive = _pid_alive(directory / "supervisor.pid")

        age = _age_s(row["created_at"], now)
        node_id = row["node_id"]
        live_per_node[node_id] = live_per_node.get(node_id, 0) + 1
        job_age = _age_s(row["job_created_at"], now)
        if job_age is not None:
            wall_per_node[node_id] = max(wall_per_node.get(node_id, 0), job_age)

        workers.append(
            WorkerRow(
                node_id=node_id,
                job_id=row["job_id"],
                executor=executor,
                attempt_id=attempt_id,
                session_state=row["state"],
                attempt_index=row["attempt_index"],
                age_s=age,
                last_event_age_s=last_event_age,
                event_count=event_count,
                verdict=_worker_verdict(last_event_age, pid_alive, has_exit, stall_s),
            )
        )

        anomaly = None
        if present and has_exit and row["state"] in ("dispatched", "running"):
            anomaly = "attempt exited while the session record stays live"
        elif present and pid_alive is False and not has_exit:
            anomaly = "process gone with the terminal record still missing"
        elif not present:
            anomaly = "spool directory is absent for a live session"

        plumbing.append(
            PlumbingRow(
                attempt_id=attempt_id,
                node_id=node_id,
                handle_minted=bool(attempt_id),
                spool_present=present,
                pid_alive=pid_alive,
                has_events=has_events,
                has_result=has_result,
                has_exit=has_exit,
                anomaly=anomaly,
            )
        )

    # --- graph -------------------------------------------------------------
    status_by_id = {n["id"]: n.get("status", "pending") for n in project.nodes}
    status_counts: dict[str, int] = {}
    for status in status_by_id.values():
        status_counts[status] = status_counts.get(status, 0) + 1

    working_node_ids = {
        row["node_id"]
        for row in con.execute(
            """SELECT DISTINCT node_id FROM jobs
                WHERE project_id = ? AND status IN ('ready', 'running')""",
            (project_id,),
        ).fetchall()
    }
    gated_node_ids = {
        row["node_id"]
        for row in con.execute(
            """SELECT DISTINCT node_id FROM jobs
                WHERE project_id = ? AND status = 'awaiting_review'""",
            (project_id,),
        ).fetchall()
    }

    dispatchable: list[str] = []
    ready_in_flight: list[str] = []
    ready_at_gate: list[str] = []
    blocked: list[dict] = []
    for summary in project.nodes:
        node_id = summary["id"]
        status = summary.get("status", "pending")
        if status == "ready":
            if node_id in working_node_ids:
                ready_in_flight.append(node_id)
            elif node_id in gated_node_ids:
                ready_at_gate.append(node_id)
            else:
                dispatchable.append(node_id)
        elif status == "pending":
            try:
                node = reader.load_node(project_id, node_id)
            except (FileNotFoundError, KeyError):
                continue
            waiting = [
                dep
                for dep in node.depends_on
                if status_by_id.get(dep, "unknown") not in SATISFIED_DEP_STATUSES
            ]
            if waiting:
                blocked.append({"node_id": node_id, "waiting_on": waiting})

    graph = GraphSurface(
        total_nodes=len(project.nodes),
        status_counts=status_counts,
        dispatchable=dispatchable,
        ready_in_flight=ready_in_flight,
        ready_at_gate=ready_at_gate,
        blocked=blocked,
    )

    # --- node rows: every node with an attempt in flight --------------------
    job_rows = {
        row["node_id"]: row
        for row in con.execute(
            """SELECT node_id, attempt, max_attempts FROM jobs
                WHERE project_id = ? AND status IN ('ready', 'running')""",
            (project_id,),
        ).fetchall()
    }
    titles = {n["id"]: n.get("title", "") for n in project.nodes}
    node_rows = [
        NodeRow(
            node_id=node_id,
            title=titles.get(node_id, ""),
            status=status_by_id.get(node_id, "unknown"),
            # G3: worker_budget has no representation on the job yet. It reads
            # None until the dispatch envelope carries it.
            worker_budget=None,
            live_workers=count,
            wall_time_s=wall_per_node.get(node_id),
            attempt=int(job_rows[node_id]["attempt"]) if node_id in job_rows else 0,
            max_attempts=(
                int(job_rows[node_id]["max_attempts"]) if node_id in job_rows else 0
            ),
        )
        for node_id, count in sorted(live_per_node.items())
    ]

    # --- capacity ----------------------------------------------------------
    active_jobs = int(
        con.execute(
            f"""SELECT COUNT(*) FROM jobs
                 WHERE repo = ?
                   AND (status IN ({",".join("?" * len(CAPACITY_JOB_STATES))})
                        OR queue_state IN ({",".join("?" * len(CAPACITY_JOB_STATES))}))""",
            (repo, *CAPACITY_JOB_STATES, *CAPACITY_JOB_STATES),
        ).fetchone()[0]
    )
    cap = project.execution_policy.get("max_concurrent_jobs")
    capacity = Capacity(
        max_concurrent_jobs=cap,
        active_jobs=active_jobs,
        free_slots=max(0, cap - active_jobs) if isinstance(cap, int) else None,
    )

    # --- evaluator ---------------------------------------------------------
    pending = [
        {
            "node_id": row["node_id"],
            "job_id": row["job_id"],
            "waiting_s": _age_s(row["updated_at"], now),
        }
        for row in con.execute(
            f"""SELECT es.job_id, es.updated_at, j.node_id
                  FROM executor_sessions es
                  JOIN jobs j ON es.job_id = j.job_id
                 WHERE es.state IN ({",".join("?" * len(EVALUATOR_PENDING_STATES))})
                   AND j.project_id = ?""",
            (*EVALUATOR_PENDING_STATES, project_id),
        ).fetchall()
    ]
    recent = [
        {
            "node_id": row["node_id"],
            "outcome": row["outcome"],
            "age_s": _age_s(row["received_at"], now),
        }
        for row in con.execute(
            """SELECT r.outcome, r.received_at, j.node_id
                 FROM results r
                 JOIN jobs j ON r.job_id = j.job_id
                WHERE j.project_id = ?
                ORDER BY r.received_at DESC
                LIMIT ?""",
            (project_id, recent_verdicts),
        ).fetchall()
    ]
    evaluator = EvaluatorSurface(pending=pending, recent=recent)

    # --- human gate --------------------------------------------------------
    human_gate = [
        {
            "node_id": row["node_id"],
            "job_id": row["job_id"],
            "waiting_s": _age_s(row["created_at"], now),
        }
        for row in con.execute(
            """SELECT job_id, node_id, created_at FROM jobs
                WHERE project_id = ?
                  AND (status = 'awaiting_review' OR queue_state = 'awaiting_review')
                ORDER BY created_at""",
            (project_id,),
        ).fetchall()
    ]

    # --- operator steer ----------------------------------------------------
    steer: list[dict] = []
    for row in plumbing:
        if not row.spool_present:
            continue
        for executor, root in roots.items():
            candidate = root / row.attempt_id / "steer.jsonl"
            if candidate.exists():
                steer.append(
                    {
                        "attempt_id": row.attempt_id,
                        "path": str(candidate),
                        "age_s": _mtime_age_s(candidate, now),
                    }
                )
                break

    pointers = {
        "graph": str(reader.config_path / "graphs" / project_id),
        "spool_roots": json.dumps({k: str(v) for k, v in sorted(roots.items())}),
        "db": str(DB_PATH),
    }

    return OrchestratorPack(
        project_id=project_id,
        repo=repo,
        generated_at=now.isoformat(),
        capacity=capacity,
        graph=graph,
        workers=workers,
        plumbing=plumbing,
        nodes=node_rows,
        evaluator=evaluator,
        human_gate=human_gate,
        steer=steer,
        decisions=recent_decisions(
            project_id, recent_wakes, receipts_root=receipts_root
        ),
        pointers=pointers,
    )


# ---------------------------------------------------------------------------
# Rendering — the delta zone the model reads
# ---------------------------------------------------------------------------


def render_pack(pack: OrchestratorPack) -> str:
    """Compact text for the wake prompt's delta zone and for --dry-run."""
    out: list[str] = []
    add = out.append

    add(f"PROJECT {pack.project_id} ({pack.repo})  at {pack.generated_at}")
    cap = pack.capacity
    add(
        f"CAPACITY active={cap.active_jobs} cap={cap.max_concurrent_jobs} "
        f"free={cap.free_slots}"
    )

    g = pack.graph
    counts = " ".join(f"{k}={v}" for k, v in sorted(g.status_counts.items()))
    add(f"\nGRAPH {g.total_nodes} nodes  {counts}")
    add(f"  dispatchable: {', '.join(g.dispatchable) or '—'}")
    add(f"  ready, worker in flight: {', '.join(g.ready_in_flight) or '—'}")
    add(f"  ready, held at human gate: {', '.join(g.ready_at_gate) or '—'}")
    for row in g.blocked:
        add(f"  blocked {row['node_id']} waits on {', '.join(row['waiting_on'])}")

    add(f"\nWORKERS {len(pack.workers)}")
    for w in pack.workers:
        add(
            f"  {w.verdict:<12} {w.node_id} [{w.executor}] "
            f"age={w.age_s}s last_event={w.last_event_age_s}s "
            f"events={w.event_count} state={w.session_state} "
            f"attempt={w.attempt_index}"
        )

    anomalies = [p for p in pack.plumbing if p.anomaly]
    add(f"\nPLUMBING {len(pack.plumbing)} pipes, {len(anomalies)} anomalies")
    for p in anomalies:
        add(f"  {p.attempt_id[:16]} {p.node_id}: {p.anomaly}")

    add(f"\nNODES {len(pack.nodes)}")
    for n in pack.nodes:
        add(
            f"  {n.node_id} status={n.status} budget={n.worker_budget} "
            f"live={n.live_workers} wall={n.wall_time_s}s "
            f"attempt={n.attempt}/{n.max_attempts}"
        )

    e = pack.evaluator
    add(f"\nEVALUATOR pending={len(e.pending)}")
    for row in e.pending:
        add(f"  {row['node_id']} waiting {row['waiting_s']}s")
    for row in e.recent:
        add(f"  recent {row['node_id']} {row['outcome']} ({row['age_s']}s ago)")

    add(f"\nHUMAN GATE {len(pack.human_gate)} awaiting review")
    for row in pack.human_gate[:10]:
        add(f"  {row['node_id']} waiting {row['waiting_s']}s")
    if len(pack.human_gate) > 10:
        add(f"  … {len(pack.human_gate) - 10} more")

    add(f"\nSTEER {len(pack.steer)}")
    for row in pack.steer:
        add(f"  {row['attempt_id'][:16]} {row['path']} ({row['age_s']}s)")

    add(f"\nEARLIER WAKES {len(pack.decisions)} (newest first)")
    for row in pack.decisions:
        effected = "effected" if row.get("effected") else "advice"
        target = f" {row['node_id']}" if row.get("node_id") else ""
        add(f"  {row['action']}{target} [{effected}] — {row['reason']}")
        if row.get("next_wake_s"):
            add(f"      next wake advised in {row['next_wake_s']}s")
        if row.get("expect"):
            add(f"      expecting: {row['expect']}")

    add("\nPOINTERS")
    for key, value in sorted(pack.pointers.items()):
        add(f"  {key}: {value}")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble and print one orchestrator wake pack (read-only)."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--config-path", default=None)
    parser.add_argument("--db", default=None, help="override the queue DB path")
    parser.add_argument("--json", action="store_true", help="emit the raw pack")
    parser.add_argument(
        "--stall-s",
        type=int,
        default=600,
        help="event silence at or beyond this reads as 'quiet' (default 600)",
    )
    args = parser.parse_args(argv)

    reader = GraphReader(args.config_path)
    con = connect(Path(args.db) if args.db else None)
    try:
        pack = assemble_pack(con, reader, args.project, stall_s=args.stall_s)
    finally:
        con.close()

    if args.json:
        print(json.dumps(pack.to_json_value(), indent=2, sort_keys=True))
    else:
        rendered = render_pack(pack)
        print(rendered)
        chars = len(rendered)
        print(
            f"\n--- pack size: {chars} chars ≈ {chars // 4} tokens "
            f"(target ≤ 50000)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
