"""
provisional_gate.py — System writer for the `provisional` node status.

Doctrine (docs/GDDP-rebuild.md, "Provisional flow — two review modes"):
`complete` is human-only graph truth; this module never writes it.
`provisional` is the scheduler-visible marker that work finished and the
evaluator passed it. The operator accepts (→ complete), rejects (→ ready),
or defers afterward; rejection re-blocks dependents automatically because
dependency satisfaction is computed live from the graph.

Mode 1 (default): provisional flow — a pass verdict with both integrity
lanes marks the node provisional and dependents unblock without waiting on
the operator. Mode 2 (explicit opt-in): the node YAML carries
`human_gate: true` and this writer skips it regardless of verdict, so it
waits for human acceptance like every node did before provisional flow.

The evaluator stays evidence-only: this writer runs in the heartbeat
reconcile phase, reading the recorded verification dict — the evaluator
itself never touches graph files.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import yaml

from ..gates import write_gate
from ..repo_resolver import resolve_project_repo_checkout
from .graph_reader import GraphReader

PROVISIONAL = "provisional"
TERMINAL_STATUSES = frozenset({"complete", "deferred"})


def provisional_eligible(verification: dict) -> bool:
    """True when the recorded verdict qualifies for provisional promotion.

    Requires a combined pass verdict plus both integrity lanes and no
    integrity-lane demand for human review. Confidence is deliberately not
    a gate: it is self-assessment for the operator's review ordering, not
    a permission check (operator decision, mode 1 default).
    """
    if verification.get("verdict") != "pass":
        return False
    integrity = verification.get("integrity") or {}
    if integrity.get("intent_preserved") is not True:
        return False
    if integrity.get("graph_integrity_preserved") is not True:
        return False
    if integrity.get("required_human_review"):
        return False
    return True


def _load_node_cli(config_root: Path):
    """Import gddp-config scripts/node_cli.py for its surgical status
    rewriters (formatting-preserving, no YAML re-serialization)."""
    path = config_root / "scripts" / "node_cli.py"
    spec = importlib.util.spec_from_file_location("gddp_node_cli", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load node_cli from {path}")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses resolve cls.__module__ via sys.modules
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _atomic_write(path: Path, data: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def maybe_mark_provisional(
    *,
    project_id: str,
    node_id: str,
    verification: dict,
    evidence_ref: str,
    config_path: str | None = None,
) -> bool:
    """Mark a node provisional when the verdict qualifies. Returns True on write.

    Never raises: a failed provisional write leaves the node in its prior
    status (the operator can still accept by hand) and must not break
    reconciliation. Failure modes are logged to the heartbeat log.
    """
    try:
        if not provisional_eligible(verification):
            return False

        reader = GraphReader(config_path=config_path)
        root = reader.config_path
        node_path = root / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
        project_path = root / "graphs" / project_id / "project.yaml"
        doc = yaml.safe_load(node_path.read_text()) or {}

        # Mode 2: operator declared this node human-gated; verdicts never
        # move it, only the operator does.
        if doc.get("human_gate") is True:
            print(f"  → provisional skipped: {node_id} is human_gate")
            return False

        current = doc.get("status")
        if current in TERMINAL_STATUSES:
            return False
        if current == PROVISIONAL:
            return False  # idempotent: already marked by an earlier attempt

        node_cli = _load_node_cli(root)
        new_node_text, _old = node_cli.replace_node_status(
            node_path.read_text(), PROVISIONAL
        )
        new_project_text, _ = node_cli.replace_project_index_status(
            project_path.read_text(), node_id, PROVISIONAL
        )
        _atomic_write(node_path, new_node_text)
        _atomic_write(project_path, new_project_text)
        print(f"  → provisional: {node_id} marked provisional (evidence: {evidence_ref})")

        # Gate token: write a per-node admission signal into the repo
        # checkout for mission-mode executors. Non-fatal by design — a
        # failed gate write leaves the node provisional and the operator
        # can still accept by hand.
        try:
            repo_checkout = resolve_project_repo_checkout(
                project_id, config_root=root
            )
            if repo_checkout is not None:
                write_gate(str(repo_checkout), node_id, verdict_receipt_path=evidence_ref)
        except Exception as gate_exc:
            print(f"  → gate token WARNING (non-fatal): {gate_exc}")

        return True
    except Exception as exc:  # non-fatal by design — see docstring
        print(f"  → provisional write ERROR (non-fatal): {exc}")
        return False
