"""Merge/skip behavior for verification/<project>/evaluations.yaml export."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.export_evaluations import (
    dump_doc,
    export_project,
    merge_evaluations,
    resolve_export,
)


def _eval(verdict: str, **extra) -> dict:
    row = {
        "verdict": verdict,
        "evaluated_at": "2026-08-09T08:12:32Z",
        "executor": "pi_rpc",
        "job_id": "job_1",
        "result_id": "res_1",
        "attempts": 1,
        "receipt_ref": None,
        "intent_preserved": True,
        "graph_integrity_preserved": True,
        "evaluator_note": "ok",
        "evidence_refs": [],
        "acceptance_check": {"verdict": verdict},
    }
    row.update(extra)
    return row


class MergeEvaluationsTests(unittest.TestCase):
    def test_db_overwrites_known_nodes_and_keeps_file_only_nodes(self):
        existing = {
            "node-keep": _eval("pass"),
            "node-update": _eval("fail"),
        }
        from_db = {
            "node-update": _eval("pass", job_id="job_2"),
            "node-new": _eval("pass", job_id="job_3"),
        }
        merged = merge_evaluations(existing, from_db)
        self.assertEqual(set(merged), {"node-keep", "node-update", "node-new"})
        self.assertEqual(merged["node-keep"]["verdict"], "pass")
        self.assertEqual(merged["node-update"]["job_id"], "job_2")
        self.assertEqual(merged["node-new"]["job_id"], "job_3")


class ResolveExportTests(unittest.TestCase):
    def test_skip_when_db_subset_matches_existing_nodes(self):
        existing_evals = {
            "node-keep": _eval("pass"),
            "node-also": _eval("pass", job_id="job_also"),
        }
        existing_doc = {
            "schema_type": "node_evaluations",
            "generated_at": "2026-08-21T09:56:11Z",
            "evaluations": existing_evals,
        }
        doc, changed = resolve_export(
            "pi-harness-execution",
            {"node-keep": _eval("pass")},
            existing_doc,
            now="2026-09-06T06:00:29Z",
        )
        self.assertFalse(changed)
        self.assertEqual(doc["generated_at"], "2026-08-21T09:56:11Z")
        self.assertEqual(set(doc["evaluations"]), {"node-keep", "node-also"})

    def test_write_when_db_updates_a_node(self):
        existing_doc = {
            "generated_at": "2026-08-21T09:56:11Z",
            "evaluations": {"node-keep": _eval("fail")},
        }
        doc, changed = resolve_export(
            "pi-harness-execution",
            {"node-keep": _eval("pass")},
            existing_doc,
            now="2026-09-06T06:00:29Z",
        )
        self.assertTrue(changed)
        self.assertEqual(doc["generated_at"], "2026-09-06T06:00:29Z")
        self.assertEqual(doc["evaluations"]["node-keep"]["verdict"], "pass")

    def test_skip_ignores_generated_at_and_dump_formatting(self):
        evaluations = {"node-keep": _eval("pass")}
        existing_doc = {
            "schema_type": "node_evaluations",
            "schema_version": "1.0",
            "project_id": "demo",
            "generated_at": "2026-01-01T00:00:00Z",
            "source": "gddp-runtime db/queue.db (results + decision_results)",
            "evaluations": evaluations,
        }
        doc, changed = resolve_export("demo", evaluations, existing_doc, now="2026-09-10T00:00:00Z")
        self.assertFalse(changed)
        self.assertEqual(doc["generated_at"], "2026-01-01T00:00:00Z")


class ExportProjectFileTests(unittest.TestCase):
    def test_partial_db_does_not_rewrite_or_drop_file_nodes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "evaluations.yaml"
            existing = {
                "schema_type": "node_evaluations",
                "schema_version": "1.0",
                "project_id": "demo",
                "generated_at": "2026-08-21T09:56:11Z",
                "source": "gddp-runtime db/queue.db (results + decision_results)",
                "evaluations": {
                    "node-keep": _eval("pass"),
                    "node-file-only": _eval("pass", job_id="job_file"),
                },
            }
            original = dump_doc(existing)
            path.write_text(original, encoding="utf-8")
            status = export_project(
                "demo",
                {"node-keep": _eval("pass")},
                path,
                now="2026-09-06T06:00:29Z",
                dry_run=False,
            )
            self.assertEqual(status, "skip")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_new_file_writes_db_nodes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "verification" / "demo" / "evaluations.yaml"
            status = export_project(
                "demo",
                {"node-new": _eval("pass")},
                path,
                now="2026-09-10T00:00:00Z",
                dry_run=False,
            )
            self.assertEqual(status, "wrote")
            text = path.read_text(encoding="utf-8")
            self.assertIn("node-new", text)
            self.assertIn("2026-09-10T00:00:00Z", text)


if __name__ == "__main__":
    unittest.main()
