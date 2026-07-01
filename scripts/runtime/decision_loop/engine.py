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

import yaml

from ..heartbeat.graph_reader import GraphReader
from ..results_store import write_decision_result
from ..verification import orchestrator as verification_orchestrator
from ..verification.receipt_sink import receipt_exists, write_receipt
from ..verification.schemas import DeterministicResult, Verdict, VerdictReceipt
from ..verification.semantic.agent import OpenAICompatibleRunner
from ..verification.semantic.tools import SemanticToolbox
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

    # Expire stale events (events table uses received_at, not created_at)
    cur.execute("""
        UPDATE events SET status = 'expired'
        WHERE status = 'received'
        AND received_at < datetime('now', '-6 hours')
    """)
    cleaned += cur.rowcount

    con.commit()

    if cleaned > 0:
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
    """Persist the decision to the decision_results table."""
    import uuid
    result_id = f"dl_{uuid.uuid4().hex[:8]}"
    result_dict = result.model_dump()

    write_decision_result(
        result_id=result_id,
        action=result_dict["action"],
        node_id=result_dict.get("node_id"),
        project_id=project_id,
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
            setattr(ctx, "config_path", reader.config_path)
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

        # 3a.5. Complete node awaiting recommend-only verification?
        node_to_verify = next(
            (
                node
                for node in ctx.project.complete_nodes
                if not receipt_exists(project_id, node.node_id)
            ),
            None,
        )
        if node_to_verify is not None:
            result = _run_verification(ctx, node_to_verify, project_id)
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


def _run_verification(ctx: DecisionContext, node, project_id: str) -> DecisionResult:
    config_path = getattr(ctx, "config_path", None)
    config_root = Path(config_path) if config_path is not None else GraphReader().config_path
    graph_root = config_root / "graphs" / project_id
    project_yaml = yaml.safe_load((graph_root / "project.yaml").read_text(encoding="utf-8"))
    node_yaml = yaml.safe_load((graph_root / "nodes" / f"{node.node_id}.yaml").read_text(encoding="utf-8"))
    repo = _resolve_repo(ctx.project.repo, config_root)
    if repo is None:
        receipt = VerdictReceipt(
            project_id=project_id,
            node_id=node.node_id,
            verdict=Verdict.NEEDS_HUMAN_REVIEW,
            confidence=0.0,
            deterministic=DeterministicResult(
                criteria=[],
                constraints=[],
                artifacts_present={},
                deps_status={},
                criteria_mismatches=[],
                missing_evidence=[],
                human_review_questions=[],
            ),
            semantic=None,
            decision_reasoning="repo checkout unresolved",
            required_next_action="resolve_repo_checkout",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        write_receipt(receipt, project_id)
        return escalate(
            reason="repo_unresolved: resolve_repo_checkout",
            node_id=node.node_id,
            project_id=project_id,
        )

    receipt = verification_orchestrator.verify(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=repo,
        runner=_LazyRunner(),
        toolbox=_build_toolbox(repo),
        config_root=config_root,
    )
    write_receipt(receipt, project_id)

    if receipt.verdict == Verdict.PASS:
        return NoOpResult(
            action="no_op",
            reason=f"verified_pass: {node.node_id}",
            ok=True,
        )
    return escalate(
        reason=f"verification_{receipt.verdict.value}: {receipt.required_next_action}",
        node_id=node.node_id,
        project_id=project_id,
    )


class _LazyRunner:
    """Builds a semantic runner lazily, using the same env-based provider
    resolution as the verification CLI. Falls back to an offline finalizer
    when no provider is available, so the decision loop never crashes on a
    missing optional dependency (e.g. anthropic)."""

    def __init__(self) -> None:
        self._runner = None

    def chat(self, messages, tools):
        if self._runner is None:
            self._runner = _build_decision_loop_runner()
        return self._runner.chat(messages, tools)


def _build_decision_loop_runner():
    """Resolve a semantic runner from the environment.

    Priority: DEEPSEEK_API_KEY > GLM_API_KEY > anthropic (if installed) > offline.
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        return OpenAICompatibleRunner(
            api_key=deepseek_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )

    glm_key = os.environ.get("GLM_API_KEY")
    if glm_key:
        return OpenAICompatibleRunner(
            api_key=glm_key,
            base_url=os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            model=os.environ.get("GLM_MODEL", "glm-4-flash"),
        )

    try:
        import anthropic
        from ..verification.semantic.agent import AnthropicRunner
        return AnthropicRunner(anthropic.Anthropic())
    except ImportError:
        pass

    # Offline fallback: finalizes indeterminate criteria without network.
    from ..verification.cli import OfflineFinalizingRunner
    return OfflineFinalizingRunner()


def _build_toolbox(repo: Path) -> SemanticToolbox:
    return SemanticToolbox(repo)


def _resolve_repo(repo_value: str, config_root: Path) -> Path | None:
    repo = Path(repo_value)
    if repo.is_absolute() and repo.exists():
        return repo

    basename = repo_value.split("/")[-1]
    repo_root = os.environ.get("GDDP_REPO_ROOT")
    if repo_root:
        candidate = Path(repo_root) / basename
        if candidate.exists():
            return candidate

    candidate = config_root / ".." / basename
    if candidate.exists():
        return candidate

    return None


def main(argv: list[str] | None = None) -> int:
    """CLI entry point so cron can drive the verification-wired decision loop.

    Usage (from gddp-runtime repo root):
        python3 -m scripts.runtime.decision_loop.engine \
            --project vault-doctor \
            [--config-path /path/to/gddp-config]
    """
    import argparse

    parser = argparse.ArgumentParser(description="GDDP decision loop (cron trigger)")
    parser.add_argument("--project", required=True, help="Project graph id to evaluate")
    # Optional; falls back to GDDP_CONFIG_PATH env / sibling dir via GraphReader.
    parser.add_argument("--config-path", default=None, help="Override path to gddp-config")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    result = handle_cron(args.project, config_path=args.config_path)
    print(f"{result.action}: {result.reason}")
    # Non-zero only on hard failure so cron surfaces real breakage, not escalations.
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
