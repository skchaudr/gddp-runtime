#!/usr/bin/env python3
"""Export evaluator outputs to verification/<project>/evaluations.yaml.

Runtime wins for nodes this DB knows: values are copied verbatim from the
results table (pass/fail, booleans, runtime field names). No translation into
viewer vocabulary — the viewer adapts to what the runtime recorded. The full
acceptance_check JSON is embedded so nothing is lost between the DB row and
the reading surface.

The committed YAML is file-truth. A host's queue.db is a cache and may be a
subset. Export merges DB rows onto the existing file and never drops a node
just because this DB does not have it. generated_at is bumped only when the
evaluations mapping actually changes, so a no-op refresh leaves git clean.

Usage:
    python3 scripts/export_evaluations.py [--db PATH] [--config PATH] [--dry-run]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "db" / "queue.db"
DEFAULT_CONFIG = REPO_ROOT.parent / "gddp-config"
EXPORT_SOURCE = "gddp-runtime db/queue.db (results + decision_results)"


def load_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT r.result_id, r.job_id, r.executor, r.received_at,
                   r.acceptance_check, j.node_id, j.project_id
            FROM results r
            JOIN jobs j ON j.job_id = r.job_id
            WHERE j.node_id IS NOT NULL
            ORDER BY r.received_at
            """
        ).fetchall()
        decisions = conn.execute(
            """
            SELECT node_id, project_id, action, reason, created_at
            FROM decision_results
            WHERE node_id IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows], [dict(d) for d in decisions]


def build_projects(rows: list[dict], decisions: list[dict]) -> dict[str, dict]:
    # Latest human decision per (project, node) — kept separate from the
    # evaluator verdict; verdict is fact-recording, decision is judgment.
    latest_decision: dict[tuple, dict] = {}
    for d in decisions:
        latest_decision[(d["project_id"], d["node_id"])] = d

    projects: dict[str, dict] = {}
    attempts: dict[tuple, int] = {}
    for row in rows:
        key = (row["project_id"], row["node_id"])
        attempts[key] = attempts.get(key, 0) + 1
        try:
            check = json.loads(row["acceptance_check"]) if row["acceptance_check"] else {}
        except json.JSONDecodeError:
            check = {"parse_error": "acceptance_check was not valid JSON"}

        integrity = check.get("integrity") or {}
        evidence_refs = [
            ev
            for finding in check.get("criteria_findings") or []
            for ev in finding.get("evidence") or []
        ]

        evaluation = {
            "verdict": check.get("verdict"),
            "evaluated_at": row["received_at"],
            "executor": row["executor"],
            "job_id": row["job_id"],
            "result_id": row["result_id"],
            "attempts": attempts[key],
            "receipt_ref": check.get("receipt_path"),
            "intent_preserved": integrity.get("intent_preserved"),
            "graph_integrity_preserved": integrity.get("graph_integrity_preserved"),
            "evaluator_note": integrity.get("reasoning"),
            "evidence_refs": evidence_refs,
            "acceptance_check": check,
        }
        decision = latest_decision.get(key)
        if decision:
            evaluation["human_decision"] = f"{decision['action']}: {decision['reason'] or ''}".strip(": ")

        # Rows are ordered by received_at, so the last write per node wins —
        # latest_evaluation is exactly the most recent attempt.
        projects.setdefault(row["project_id"], {})[row["node_id"]] = evaluation
    return projects


def load_existing_doc(path: Path) -> dict | None:
    if path.is_file() is False:
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if isinstance(doc, dict) is False:
        return None
    return doc


def merge_evaluations(existing: dict, from_db: dict) -> dict:
    """Keep file-only nodes; DB overwrites nodes it knows."""
    merged = dict(existing)
    merged.update(from_db)
    return merged


def dump_doc(doc: dict) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)


def build_export_doc(
    project_id: str,
    evaluations: dict,
    generated_at: str,
) -> dict:
    return {
        "schema_type": "node_evaluations",
        "schema_version": "1.0",
        "project_id": project_id,
        "generated_at": generated_at,
        "source": EXPORT_SOURCE,
        "evaluations": evaluations,
    }


def resolve_export(
    project_id: str,
    from_db: dict,
    existing_doc: dict | None,
    now: str,
) -> tuple[dict, bool]:
    """Return (doc, changed). changed is False when the file should be left alone."""
    existing_evals = dict((existing_doc or {}).get("evaluations") or {})
    merged = merge_evaluations(existing_evals, from_db)
    if existing_doc is not None and merged == existing_evals:
        generated_at = existing_doc.get("generated_at") or now
        return build_export_doc(project_id, existing_evals, generated_at), False
    return build_export_doc(project_id, merged, now), True


def export_project(
    project_id: str,
    from_db: dict,
    out_path: Path,
    *,
    now: str,
    dry_run: bool,
) -> str:
    """Merge DB evaluations onto the existing file. Return skip|wrote|would-write."""
    existing_doc = load_existing_doc(out_path)
    doc, changed = resolve_export(project_id, from_db, existing_doc, now)
    if changed is False:
        print(f"{'--- would skip' if dry_run else 'skipped'} {out_path} (no changes)")
        return "skip"
    text = dump_doc(doc)
    if dry_run:
        print(f"--- would write {out_path} ---")
        print(text)
        return "would-write"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path} ({len(doc['evaluations'])} node(s))")
    return "wrote"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: db not found: {args.db}", file=sys.stderr)
        return 1
    if not args.config.exists():
        print(f"ERROR: gddp-config not found: {args.config}", file=sys.stderr)
        return 1

    rows, decisions = load_rows(args.db)
    projects = build_projects(rows, decisions)
    if not projects:
        print("No evaluator results with node_ids found; nothing to export.")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for project_id, evaluations in sorted(projects.items()):
        out_path = args.config / "verification" / project_id / "evaluations.yaml"
        export_project(
            project_id,
            evaluations,
            out_path,
            now=now,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
