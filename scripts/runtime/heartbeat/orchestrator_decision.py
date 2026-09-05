"""
orchestrator_decision.py — Carry one wake's decision into an actual dispatch.

A stateless orchestrator wakes, reads the pack, and concludes something like
"run pi-evaluator-guard". Without a channel that conclusion dies with the
session. This module is the channel: a typed decision, a durable receipt, and
an applier that turns a dispatch decision into an events row.

Routing through `events` keeps every existing guard in force. The classifier
still resolves the node, `check_scope` still refuses a second job on a node
that already has one, and the BEGIN IMMEDIATE transaction in the runner still
owns the concurrency ceiling. The orchestrator advises; the runtime reserves.

Receipts carry rationale, not only the action. Sleep wipes context, so "why
six workers" and "what am I waiting to confirm" survive only by being written
down. Persisted receipts are what stands in for held inference state.

Graph truth stays where it is. This module writes to `events` and to its own
receipt directory, and to nothing else.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(
    os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root)
)
RECEIPTS_ROOT = RUNTIME_ROOT / "jobs" / "orchestrator-decisions"

# Closed vocabulary. An unrecognized action is an error, so a confused wake
# fails loudly here instead of inventing a job type the runtime never agreed
# to run.
ACTIONS = frozenset(
    {
        "hold",  # the current allocation is fine
        "dispatch",  # start work on a node
        "slice",  # the advised cut is too coarse — propose finer, then wait
        "reduce",  # the advised cut is too fine — propose fewer, then wait
        "steer",  # send a message into a live local attempt
        "replace",  # cancel one attempt and let the next wake redispatch
        "escalate",  # hand to the operator
    }
)

# Actions the runtime effects on the orchestrator's behalf. Everything else is
# recorded as advice for the operator and for the next wake to read.
EFFECTING_ACTIONS = frozenset({"dispatch"})

# Actions that name a node they act on.
NODE_ACTIONS = frozenset({"dispatch", "slice", "reduce", "steer", "replace"})

# Event rows the pipeline has yet to consume.
PENDING_EVENT_STATUSES = ("received", "claimed")

# Job states that mean a node is already spoken for.
OCCUPIED_JOB_STATUSES = ("ready", "running", "awaiting_review")


class DecisionError(ValueError):
    """A decision the runtime declines to read as a decision."""


@dataclass(frozen=True)
class Decision:
    """One wake's conclusion, with the reasoning the next wake will lack."""

    action: str
    reason: str
    wake_id: str
    node_id: str | None = None
    from_n: int | None = None
    to_n: int | None = None
    # Seconds until the next wake, when the run's interval is the
    # orchestrator's to set (the operator's fixed interval wins when set).
    next_wake_s: int | None = None
    expect: str | None = None
    surfaces: dict[str, str] = field(default_factory=dict)

    def to_json_value(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Applied:
    """What the runtime did with a decision, and why when it did nothing."""

    decision: Decision
    effected: bool
    event_id: str | None = None
    detail: str = ""
    receipt_path: str | None = None

    def to_json_value(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_json_value(),
            "effected": self.effected,
            "event_id": self.event_id,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _require_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise DecisionError(f"decision requires a non-empty {key}")


def _optional_count(raw: dict, key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DecisionError(f"{key} must be a positive integer when present")
    return value


def parse_decision(raw: object, *, wake_id: str | None = None) -> Decision:
    """Read one decision, refusing anything the runtime would have to guess at.

    Rationale is mandatory. A receipt saying `slice 3 -> 6` with no reason
    tells the next wake what happened while withholding the only part it
    needed, so a decision without a reason is malformed rather than terse.
    """
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecisionError(f"decision is unreadable JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise DecisionError("decision must be a JSON object")

    action = _require_text(raw, "action")
    if action not in ACTIONS:
        raise DecisionError(
            f"unknown action {action!r}; the vocabulary is {sorted(ACTIONS)}"
        )

    reason = _require_text(raw, "reason")
    node_id = raw.get("node_id")
    if action in NODE_ACTIONS:
        node_id = _require_text(raw, "node_id")
    elif node_id is not None and not isinstance(node_id, str):
        raise DecisionError("node_id must be a string when present")

    surfaces = raw.get("surfaces") or {}
    if not isinstance(surfaces, dict):
        raise DecisionError("surfaces must be an object when present")

    expect = raw.get("expect")
    if expect is not None and not isinstance(expect, str):
        raise DecisionError("expect must be a string when present")

    resolved_wake = wake_id or raw.get("wake_id") or _mint_wake_id()
    return Decision(
        action=action,
        reason=reason,
        wake_id=str(resolved_wake),
        node_id=node_id,
        from_n=_optional_count(raw, "from_n"),
        to_n=_optional_count(raw, "to_n"),
        next_wake_s=_optional_count(raw, "next_wake_s"),
        expect=expect,
        surfaces={str(k): str(v) for k, v in surfaces.items()},
    )


def _mint_wake_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S")
    return f"wake_{stamp}_{secrets.token_hex(3)}"


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def _node_is_spoken_for(con, project_id: str, node_id: str) -> str | None:
    """Name the thing already claiming this node, when something does.

    A stateless orchestrator re-reaches the same conclusion on every pulse.
    Without this, a node that takes three ticks to start collects three
    dispatch events, and the wake that meant "start this once" quietly
    becomes a queue.
    """
    placeholders = ",".join("?" * len(PENDING_EVENT_STATUSES))
    pending = con.execute(
        f"""SELECT event_id FROM events
             WHERE project_id = ?
               AND status IN ({placeholders})
               AND project_node_candidates LIKE ?
             LIMIT 1""",
        (project_id, *PENDING_EVENT_STATUSES, f'%"{node_id}"%'),
    ).fetchone()
    if pending:
        return f"event {pending[0]} is already pending for this node"

    job_placeholders = ",".join("?" * len(OCCUPIED_JOB_STATUSES))
    job = con.execute(
        f"""SELECT job_id, status FROM jobs
             WHERE project_id = ? AND node_id = ?
               AND status IN ({job_placeholders})
             LIMIT 1""",
        (project_id, node_id, *OCCUPIED_JOB_STATUSES),
    ).fetchone()
    if job:
        return f"job {job[0]} holds this node ({job[1]})"
    return None


def _inject_dispatch_event(
    con, project, decision: Decision, now: datetime
) -> str:
    """Insert a dispatch event in the schema the rest of the pipeline reads.

    Mirrors frontier._inject_dispatch_event so classify/scope/plan handle an
    orchestrator dispatch identically to an operator-injected one. The source
    differs so the origin of any job stays legible after the fact.

    The worker budget rides in routing as `worker_budget` when the decision
    carries one. The classifier ignores unknown routing keys, so this is
    inert until the dispatch envelope renders it into the executor's prompt —
    and recorded here from the first wake that proposes one, so the receipt
    and the event agree about what was advised.
    """
    node_id = decision.node_id
    wake_id = decision.wake_id
    event_id = (
        f"evt_orch_{now.strftime('%Y%m%dT%H%M%S')}_{node_id}_{secrets.token_hex(3)}"
    )
    routing: dict[str, Any] = {}
    default_executor = project.execution_policy.get("default_executor")
    if default_executor:
        routing["selected_executor"] = default_executor
    if decision.to_n is not None:
        routing["worker_budget"] = decision.to_n
    con.execute(
        "INSERT INTO events (event_id, schema_version, received_at, source, "
        "event_type, actor, url, project_id, project_node_candidates, "
        "scope_status, priority, risk_level, routing, status, repo) "
        "VALUES (?, '1.0', ?, 'orchestrator', 'issue.opened', ?, ?, ?, ?, "
        "'pending', 'pending', 'pending', ?, 'received', ?)",
        (
            event_id,
            now.isoformat(),
            wake_id,
            f"orchestrator-dispatch://node: {node_id}",
            project.project_id,
            json.dumps([node_id]),
            json.dumps(routing),
            project.repo,
        ),
    )
    return event_id


def apply_decision(
    con,
    project,
    decision: Decision,
    *,
    now: datetime | None = None,
    receipts_root: Path | None = None,
) -> Applied:
    """Effect a decision the runtime can effect, and record every decision.

    Only `dispatch` reaches the runtime, and it reaches it as an event rather
    than as a dispatch call, so `check_scope` and the capacity transaction keep
    the last word. The remaining actions are advice: they persist as receipts
    for the operator and for the next wake, and they change no runtime state
    here.
    """
    now = now or datetime.now(timezone.utc)

    if decision.action in EFFECTING_ACTIONS:
        occupied = _node_is_spoken_for(con, project.project_id, decision.node_id)
        if occupied:
            applied = Applied(
                decision=decision,
                effected=False,
                detail=f"dispatch declined: {occupied}",
            )
        else:
            event_id = _inject_dispatch_event(con, project, decision, now)
            applied = Applied(
                decision=decision,
                effected=True,
                event_id=event_id,
                detail=f"dispatch event {event_id} queued for the next plan phase",
            )
    else:
        applied = Applied(
            decision=decision,
            effected=False,
            detail=f"{decision.action} recorded as advice",
        )

    path = write_receipt(
        project.project_id, applied, now=now, receipts_root=receipts_root
    )
    return Applied(
        decision=applied.decision,
        effected=applied.effected,
        event_id=applied.event_id,
        detail=applied.detail,
        receipt_path=str(path),
    )


# ---------------------------------------------------------------------------
# Receipts — the continuity a wipe would otherwise take
# ---------------------------------------------------------------------------


def receipts_dir(project_id: str, receipts_root: Path | None = None) -> Path:
    return (receipts_root or RECEIPTS_ROOT) / project_id


def write_receipt(
    project_id: str,
    applied: Applied,
    *,
    now: datetime | None = None,
    receipts_root: Path | None = None,
) -> Path:
    """Persist one decision plus its outcome, named so time orders the dir."""
    now = now or datetime.now(timezone.utc)
    directory = receipts_dir(project_id, receipts_root)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        **applied.to_json_value(),
        "recorded_at": now.isoformat(),
        "project_id": project_id,
    }
    path = directory / f"{now.strftime('%Y%m%dT%H%M%S')}-{applied.decision.wake_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def recent_decisions(
    project_id: str,
    limit: int = 5,
    *,
    receipts_root: Path | None = None,
) -> list[dict]:
    """The last few decisions, newest first, for the next wake's pack.

    Unreadable receipts are skipped rather than raised on: a corrupt file is
    one lost memory, and letting it abort the assembly would cost the wake
    every other memory too.
    """
    directory = receipts_dir(project_id, receipts_root)
    try:
        paths = sorted(directory.glob("*.json"), reverse=True)
    except OSError:
        return []
    out: list[dict] = []
    for path in paths[:limit]:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        decision = payload.get("decision", {})
        out.append(
            {
                "wake_id": decision.get("wake_id"),
                "action": decision.get("action"),
                "node_id": decision.get("node_id"),
                "reason": decision.get("reason"),
                "expect": decision.get("expect"),
                "next_wake_s": decision.get("next_wake_s"),
                "effected": payload.get("effected"),
                "at": payload.get("recorded_at"),
            }
        )
    return out
