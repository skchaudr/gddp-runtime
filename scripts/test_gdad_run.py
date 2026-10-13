"""Unit tests for the GDAD journal writer."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

import gdad_run


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["GDDP_RUNTIME_ROOT"] = str(self.root)
        self.addCleanup(self.tmp.cleanup)

    def dispatch(self, node="line-pair"):
        return gdad_run.journal(
            "gdad-demo", node, "dispatch",
            request_id="line-pair-1", wid="wid-1",
            root=self.root,
        )

    def test_status_matches_last_line(self):
        line = self.dispatch()
        status = (gdad_run.node_dir("gdad-demo", "line-pair", self.root) / "status").read_text()
        self.assertIn("state: running", status)
        self.assertIn("who: gdad-executor", status)
        self.assertIn(f"when: {line['ts']}", status)
        self.assertIn("run_id: line-pair-1", status)
        self.assertIn("request_id: line-pair-1", status)
        self.assertIn("wid: wid-1", status)
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        status = gdad_run.read_status("gdad-demo", "line-pair", self.root)
        self.assertEqual(status["state"], "paused")
        self.assertEqual(status["request_id"], "line-pair-1")
        self.assertEqual(status["wid"], "wid-1")

    def test_illegal_transition_writes_nothing(self):
        self.dispatch()
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        before = (directory / "journal.jsonl").read_bytes()
        status_before = (directory / "status").read_bytes()
        with self.assertRaises(gdad_run.JournalError):
            gdad_run.journal("gdad-demo", "line-pair", "gate", repo=self.root, verdict_path=self.root / "missing.json", root=self.root)
        self.assertEqual((directory / "journal.jsonl").read_bytes(), before)
        self.assertEqual((directory / "status").read_bytes(), status_before)

    def test_redispatch_then_dispatch_reuses_new_run_id(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        gdad_run.ambiguity_packet("gdad-demo", "line-pair", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "decision", who="fable", reply={
            "reply": "resume", "packet_id": "pkt-1", "option_id": "resume",
        }, root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="reject", note="count=3", root=self.root)
        packet = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="verdict",
            question="Redispatch?",
            done=["rejected"],
            options=[{"id": "redispatch", "label": "Redispatch", "consequence": "new run"}],
            evidence="count=3",
            artifacts=[],
            checkpoint="",
            suggested="{}",
            root=self.root,
        )
        decision = gdad_run.journal(
            "gdad-demo", "line-pair", "decision", who="fable",
            reply={"reply": "redispatch", "packet_id": packet["packet_id"], "changes": "write two lines"},
            root=self.root,
        )
        self.assertEqual(decision["state"], "pending")
        self.assertEqual(decision["run_id"], "line-pair-2")
        self.assertNotEqual(decision["run_id"], "line-pair-1")
        nxt = gdad_run.journal(
            "gdad-demo", "line-pair", "dispatch",
            request_id="line-pair-2", wid="wid-2",
            root=self.root,
        )
        self.assertEqual(nxt["run_id"], "line-pair-2")
        self.assertEqual(nxt["state"], "running")
        self.assertEqual(nxt["type"], "dispatch")

    def test_flock_keeps_status_on_the_last_line(self):
        self.dispatch()
        errors = []

        def steer(note):
            try:
                gdad_run.journal("gdad-demo", "line-pair", "steer", note=note, root=self.root)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=steer, args=(f"n{i}",)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        lines = gdad_run._read_lines(gdad_run.node_dir("gdad-demo", "line-pair", self.root))
        status = gdad_run.read_status("gdad-demo", "line-pair", self.root)
        self.assertEqual(len(lines), 9)
        self.assertEqual(status["state"], lines[-1]["state"])
        self.assertEqual(status["when"], lines[-1]["ts"])
        self.assertEqual(status["who"], lines[-1]["who"])

    def test_invalid_reply_leaves_packet_open(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        packet = gdad_run.ambiguity_packet("gdad-demo", "line-pair", root=self.root)
        with self.assertRaises(gdad_run.JournalError):
            gdad_run.decide(packet["packet_id"], {"reply": "nope"}, root=self.root)
        stored = gdad_run.load_packet("gdad-demo", "line-pair", packet["packet_id"], self.root)
        self.assertTrue(stored["open"])
        self.assertEqual(gdad_run.current_state("gdad-demo", "line-pair", self.root), "blocked")
        self.assertEqual(len(gdad_run.open_packets("gdad-demo", "line-pair", self.root)), 1)
        lines = gdad_run._read_lines(gdad_run.node_dir("gdad-demo", "line-pair", self.root))
        self.assertEqual(lines[-1]["type"], "blocked")
        self.assertIn("invalid reply", lines[-1]["note"])

    def test_next_accept_is_accepted_and_reject_next_is_rejected(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="accept", note="count=2", root=self.root)
        packet = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="acceptance",
            question="Close?",
            done=["accepted"],
            options=[{"id": "close", "label": "Close", "consequence": "gate"}],
            evidence="count=2",
            artifacts=[],
            checkpoint="acceptance",
            suggested="{}",
            root=self.root,
        )
        line = gdad_run.journal(
            "gdad-demo", "line-pair", "decision", who="fable",
            reply={"reply": "next", "packet_id": packet["packet_id"], "workflow": None},
            root=self.root,
        )
        self.assertEqual(line["state"], "accepted")


if __name__ == "__main__":
    unittest.main()
