"""Tests for node_status_history integrity (append/read/lock semantics)."""

from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from node_status_history import (
    append_status_change,
    history_path,
    latest_reason,
    load_history,
)


class NodeStatusHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_append_and_latest(self) -> None:
        append_status_change(
            project_id="demo",
            node_id="alpha",
            from_status="ready",
            to_status="deferred",
            reason="quota; work is fine — do not block unlocks",
            kind="graph",
            source="test",
            runtime_root=self.root,
        )
        append_status_change(
            project_id="demo",
            node_id="alpha",
            from_status="deferred",
            to_status="ready",
            reason="quota restored",
            kind="graph",
            source="test",
            runtime_root=self.root,
        )
        rows = load_history("demo", "alpha", runtime_root=self.root)
        self.assertEqual(len(rows), 2)
        last = latest_reason("demo", "alpha", runtime_root=self.root)
        assert last is not None
        self.assertEqual(last["to_status"], "ready")
        self.assertEqual(last["reason"], "quota restored")
        path = history_path("demo", "alpha", runtime_root=self.root)
        self.assertTrue(path.is_file())

    def test_empty_reason_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_status_change(
                project_id="demo",
                node_id="alpha",
                from_status="ready",
                to_status="deferred",
                reason="  ",
                runtime_root=self.root,
            )

    def test_extra_cannot_overwrite_canonical_fields(self) -> None:
        append_status_change(
            project_id="demo",
            node_id="alpha",
            from_status="ready",
            to_status="deferred",
            reason="real reason",
            kind="graph",
            source="test",
            runtime_root=self.root,
            extra={
                "reason": "hijacked",
                "to_status": "complete",
                "job_id": "job_1",
            },
        )
        last = latest_reason("demo", "alpha", runtime_root=self.root)
        assert last is not None
        self.assertEqual(last["reason"], "real reason")
        self.assertEqual(last["to_status"], "deferred")
        self.assertEqual(last["job_id"], "job_1")

    def test_malformed_line_raises_strict(self) -> None:
        path = history_path("demo", "alpha", runtime_root=self.root)
        path.parent.mkdir(parents=True)
        path.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_history("demo", "alpha", runtime_root=self.root, strict=True)

    def test_matching_to_status_filters_stale(self) -> None:
        append_status_change(
            project_id="demo",
            node_id="alpha",
            from_status="ready",
            to_status="deferred",
            reason="paused for quota",
            kind="graph",
            source="test",
            runtime_root=self.root,
        )
        matched = latest_reason(
            "demo",
            "alpha",
            runtime_root=self.root,
            kind="graph",
            matching_to_status="ready",
        )
        self.assertIsNone(matched)
        matched_ok = latest_reason(
            "demo",
            "alpha",
            runtime_root=self.root,
            kind="graph",
            matching_to_status="deferred",
        )
        assert matched_ok is not None
        self.assertEqual(matched_ok["reason"], "paused for quota")

    def test_concurrent_appends_preserve_all_lines(self) -> None:
        def write_one(i: int) -> None:
            append_status_change(
                project_id="demo",
                node_id="alpha",
                from_status="ready",
                to_status="deferred",
                reason=f"reason-{i}",
                kind="graph",
                source="test",
                runtime_root=self.root,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write_one, range(20)))
        rows = load_history("demo", "alpha", runtime_root=self.root)
        self.assertEqual(len(rows), 20)
        reasons = {r["reason"] for r in rows}
        self.assertEqual(reasons, {f"reason-{i}" for i in range(20)})
        # each line still valid JSON
        path = history_path("demo", "alpha", runtime_root=self.root)
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
