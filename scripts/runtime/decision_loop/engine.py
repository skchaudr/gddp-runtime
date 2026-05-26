"""
engine.py - runtime decision loop.

Wake → read context → decide → act → write result → exit.

Decision priority:
1. Clean stale state (jobs/events stuck > 6 hours)
2. PR just merged → pass through to return router (already handled by classifier)
3. Eligible node to dispatch → dispatch_next
4. Stuck job (in_progress > 24 hours) → escalate
5. Nothing to do → no_op
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..heartbeat.graph_reader import GraphReader
from ..results_store import write_result
from .context_reader import read_context, DecisionContext
from .powers import dispatch_next
from .powers.escalate import run as escalate
from .schema import DecisionResult, NoOpResult

logger = logging.getLogger("decision_loop.engine")

# Environment
_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _clean_stale_state(con: sqlite3.Connection) -> int:
    """Mark stale jobs and events as expired. Returns count of rows cleaned."""
    cur = con.cursor()
    cleaned = 0

    # Expire stale jobs
    cur.execute("""
        UPDATE jobs SET status = 'expired'
        WHERE status IN ('dispatched', 'running')
        AND created_at < datetime('now', '-6 hours')
    """)
    cleaned += cur.rowcount

    # Expire stale events
    cur.execute("""
        UPDATE events SET status = 'expired'
        WHERE status = 'received'
        AND created_at < datetime('now', '-6 hours')
    """)
    cleaned += cur.rowcount

    if cleaned > 0:
        con.commit()
        logger.info("Cleaned %d stale rows (jobs + events older than 6 hours)", cleaned)

    return cleaned


def _check_stuck_jobs(ctx: DecisionContext) -> bool:
    """Check if any active job has been running > 24 hours."""
    for job in ctx.activity.active_jobs:
        created = job.get("created_at", "")
        if not created:
            continue
        try:
            created_dt = datetime.fromisoformat(created)
            age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
            if age_hours > 24:
                return True
        except (ValueError, TypeError):
            continue
    return False


def _write_decision_result(result: DecisionResult, project_id: str) -> None:
    """Persist the decision to SQLite results table."""
    import uuid
    result_id = f"dl_{uuid.uuid4().hex[:8]}"
    result_dict = result.model_dump()

    write_result(
        result_id=result_id,
        repo_name=project_id,
        node_id=result_dict.get("node_id"),
        status=result_dict["action"],
        reason=result_dict.get("reason"),
    )


def handle_event(trigger: dict, project_id: str, config_path: str = None) -> DecisionResult:
    """
    Main entry point — called by webhook router or cron.

    Args:
        trigger: The event that woke the decision loop
        project_id: Which project graph to read
        config_path: Override path to gddp-config (uses env var otherwise)
    """
    logger.info("Decision loop woke: trigger=%s project=%s", trigger.get("event", "unknown"), project_id)

    try:
        reader = GraphReader(config_path=config_path)
    except FileNotFoundError as e:
        result = escalate(reason=f"graph_read_failed: {e}", project_id=project_id)
        _write_decision_result(result, project_id)
        return result

    con = _connect()

    try:
        # Step 1: Clean stale state
        _clean_stale_state(con)

        # Step 2: Read context
        try:
            ctx = read_context(reader, con, project_id, trigger)
        except Exception as e:
            result = escalate(reason=f"context_read_failed: {e}", project_id=project_id)
            _write_decision_result(result, project_id)
            return result

        # Step 3: Decision logic (priority order from spec)

        # 3a. Stuck job?
        if _check_stuck_jobs(ctx):
            stuck_job = ctx.activity.active_jobs[0]
            result = escalate(
                reason=f"stuck_job: job {stuck_job.get('job_id', '?')} running > 24 hours",
                node_id=stuck_job.get("node_id"),
                project_id=project_id,
            )
            _write_decision_result(result, project_id)
            return result

        # 3b. Eligible node to dispatch?
        if ctx.project.pending_nodes:
            result = dispatch_next.run(ctx)
            _write_decision_result(result, project_id)
            return result

        # 3c. All nodes complete?
        total = len(ctx.project.nodes)
        complete = len(ctx.project.complete_nodes)
        if total > 0 and complete == total:
            result = NoOpResult(
                action="no_op",
                reason=f"project_complete: all {total} nodes are complete",
                ok=True,
            )
            _write_decision_result(result, project_id)
            return result

        # 3d. Nothing actionable
        result = NoOpResult(
            action="no_op",
            reason="nothing_actionable: no pending nodes with met dependencies",
            ok=True,
        )
        _write_decision_result(result, project_id)
        return result

    except Exception as e:
        logger.exception("Unhandled exception in decision loop")
        result = escalate(reason=f"unhandled_exception: {e}", project_id=project_id)
        _write_decision_result(result, project_id)
        return result
    finally:
        con.close()


def handle_cron(project_id: str, config_path: str = None) -> DecisionResult:
    """Cron entry point — same logic, cron trigger."""
    trigger = {
        "event": "cron",
        "reason": "scheduled_check",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return handle_event(trigger, project_id, config_path)
