"""Unit tests for the GDAD journal writer."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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

    def test_next_on_second_run_ignores_first_run_accept_verdict(self):
        lines = [
            {"type": "dispatch", "run_id": "line-pair-1", "state": "running"},
            {"type": "review", "run_id": "line-pair-1", "state": "review"},
            {"type": "verdict", "run_id": "line-pair-1", "state": "review", "note": "accept: ok"},
            {"type": "dispatch", "run_id": "line-pair-2", "state": "running"},
            {"type": "packet", "run_id": "line-pair-2", "state": "awaiting-decision"},
        ]
        reply = {"reply": "next", "packet_id": "pkt-2", "workflow": None}
        self.assertEqual(gdad_run._decision_state(reply, lines), "rejected")
        self.assertEqual(gdad_run._latest_verdict(lines, "line-pair-2"), None)

    def test_gate_refuses_non_accept_verdict_json(self):
        receipt = self.root / "verdict.json"
        receipt.write_text(json.dumps({"verdict": "reject", "reasons": ["count=3"]}), encoding="utf-8")
        with self.assertRaises(gdad_run.JournalError):
            gdad_run._issue_gate(self.root, "line-pair", receipt)

    def test_resume_on_verdict_packet_writes_nothing(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        gdad_run.ambiguity_packet("gdad-demo", "line-pair", root=self.root)
        gdad_run.journal(
            "gdad-demo", "line-pair", "decision", who="fable",
            reply={"reply": "resume", "packet_id": "pkt-1", "option_id": "resume"},
            root=self.root,
        )
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
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        before = (directory / "journal.jsonl").read_bytes()
        with self.assertRaises(gdad_run.JournalError):
            gdad_run.decide(
                packet["packet_id"],
                {"reply": "resume", "packet_id": packet["packet_id"], "option_id": "redispatch"},
                root=self.root,
            )
        self.assertEqual((directory / "journal.jsonl").read_bytes(), before)
        self.assertTrue(gdad_run.load_packet("gdad-demo", "line-pair", packet["packet_id"], self.root)["open"])

    def test_resume_rejects_unknown_option_without_journal(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        packet = gdad_run.ambiguity_packet("gdad-demo", "line-pair", root=self.root)
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        before = (directory / "journal.jsonl").read_bytes()
        with self.assertRaises(gdad_run.JournalError):
            gdad_run.decide(
                packet["packet_id"],
                {"reply": "resume", "packet_id": packet["packet_id"], "option_id": "nope"},
                root=self.root,
            )
        self.assertEqual((directory / "journal.jsonl").read_bytes(), before)

    def test_follow_journals_blocked_when_fable_fails(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        gdad_run.ambiguity_packet("gdad-demo", "line-pair", root=self.root)
        with mock.patch.object(gdad_run, "_run_claude", return_value=(1, "bad stdout")):
            state = gdad_run.follow("gdad-demo", "line-pair", decider="fable", timeout=2.0, root=self.root)
        self.assertEqual(state, "blocked")
        lines = gdad_run._read_lines(gdad_run.node_dir("gdad-demo", "line-pair", self.root))
        self.assertEqual(lines[-1]["type"], "blocked")
        raw = gdad_run.node_dir("gdad-demo", "line-pair", self.root) / "runs" / "line-pair-1" / "artifacts" / "decider-raw.txt"
        self.assertTrue(raw.is_file())
        self.assertEqual(raw.read_text(encoding="utf-8"), "bad stdout")

    def test_resume_blocks_when_send_not_applied(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="checkpoint after-workers", root=self.root)
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        packet_id = "pkt-resume"
        packet = {
            "packet_id": packet_id,
            "project": "gdad-demo",
            "node": "line-pair",
            "run_id": "line-pair-1",
            "kind": "ambiguity",
            "done": ["Workers finished"],
            "question": "Resume?",
            "options": [{"id": "resume", "label": "Resume", "consequence": "continue"}],
            "evidence": "ask",
            "artifacts": [],
            "resume_handle": {"wid": "wid-1", "qid": "q-test", "rev": 1, "to": "wid-1/gate"},
            "open": True,
        }
        folder = directory / "packets"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{packet_id}.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        gdad_run.journal("gdad-demo", "line-pair", "packet", note=f"{packet_id} ambiguity", root=self.root)

        def fake_dsa(*args: str, wait_ms: int | None = None) -> subprocess.CompletedProcess[str]:
            if args and args[0] == "send":
                body = json.dumps({"request": "answer-q-test", "applied": False, "reason": "held"})
                return subprocess.CompletedProcess(list(args), 1, stdout=body, stderr="")
            return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")

        with mock.patch.object(gdad_run, "dsa_cmd", fake_dsa):
            with self.assertRaises(gdad_run.JournalError):
                gdad_run.decide(
                    packet_id,
                    {"reply": "resume", "packet_id": packet_id, "option_id": "resume"},
                    root=self.root,
                )
        self.assertEqual(gdad_run.current_state("gdad-demo", "line-pair", self.root), "blocked")
        self.assertTrue(gdad_run.load_packet("gdad-demo", "line-pair", packet_id, self.root)["open"])
        payload_path = directory / "runs" / "line-pair-1" / "artifacts" / "resume-send-payload.json"
        self.assertTrue(payload_path.is_file())
        saved = json.loads(payload_path.read_text(encoding="utf-8"))
        self.assertFalse(saved.get("applied"))


class PaneLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["GDDP_RUNTIME_ROOT"] = str(self.root)
        self.addCleanup(self.tmp.cleanup)
        self.tabs: dict[str, str] = {}
        self.pi: set[str] = set()
        self.seq = 0
        self.peak = 0

    def _note(self) -> None:
        self.peak = max(self.peak, len(self.tabs))

    def _herdr(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self._note()
        if args[:2] == ["tab", "list"]:
            rows = [{"tab_id": "wN:t0", "label": "1", "workspace_id": "wN", "focused": True}]
            for tab_id, pane_id in self.tabs.items():
                rows.append({
                    "tab_id": tab_id,
                    "label": "gdad-line-pair",
                    "workspace_id": "wN",
                    "focused": False,
                    "pane_id": pane_id,
                })
            return self._cp(0, {"result": {"tabs": rows}})
        if args[:2] == ["tab", "create"]:
            self.seq += 1
            tab_id = f"wN:t{self.seq}"
            pane_id = f"wN:p{self.seq}"
            self.tabs[tab_id] = pane_id
            self._note()
            return self._cp(0, {
                "result": {
                    "root_pane": {"pane_id": pane_id, "focused": False},
                    "tab": {"tab_id": tab_id, "focused": False},
                },
            })
        if args[:2] == ["tab", "close"]:
            pane_id = self.tabs.pop(args[2], None)
            if pane_id:
                self.pi.discard(pane_id)
            self._note()
            return self._cp(0, {"result": {}})
        if args[:2] == ["pane", "get"]:
            if args[2] in self.pi or args[2] in self.tabs.values():
                return self._cp(0, {"result": {"pane": {"pane_id": args[2]}}})
            return self._cp(1, {"error": {"code": "pane_not_found"}})
        if args[:2] == ["pane", "process-info"]:
            pane_id = args[args.index("--pane") + 1]
            procs = [{"name": "pi", "argv": ["pi"], "pid": 424242}] if pane_id in self.pi else []
            return self._cp(0, {"result": {"process_info": {"foreground_processes": procs}}})
        if args[:2] == ["pane", "run"]:
            self.pi.add(args[2])
            return self._cp(0, "")
        return self._cp(1, f"unexpected herdr {' '.join(args)}")

    def _cp(self, code: int, payload: object) -> subprocess.CompletedProcess[str]:
        out = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(["herdr"], code, stdout=out, stderr="" if code == 0 else out)

    def _dsa(self, *args: str, wait_ms: int | None = None) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "run":
            body = {"wid": "wid-demo"}
        else:
            body = {}
        return subprocess.CompletedProcess(list(args), 0, stdout=json.dumps(body), stderr="")

    def _kill(self, pid: int, sig: int) -> None:
        self.assertEqual(pid, 424242)
        self.pi.clear()

    def test_two_dispatches_leave_at_most_one_gdad_tab(self):
        with (
            mock.patch.object(gdad_run, "_herdr_proc", self._herdr),
            mock.patch.object(gdad_run, "dsa_cmd", self._dsa),
            mock.patch.object(gdad_run.os, "kill", self._kill),
        ):
            gdad_run._launch_and_dispatch("gdad-demo", "line-pair", "line-pair-1", self.root)
            reused = gdad_run.ensure_pi_pane("gdad-demo", "line-pair", "line-pair-1", root=self.root)
            self.assertEqual(len(self.tabs), 1)
            self.assertEqual(self.seq, 1)
            self.assertEqual(gdad_run.live_pane_id("gdad-demo", "line-pair", self.root), reused["pane_id"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                gdad_run.show_node("gdad-demo", "line-pair", root=self.root)
            self.assertIn(f"## pane\n{reused['pane_id']}", buf.getvalue())

            gdad_run.journal("gdad-demo", "line-pair", "pause", note="subagent question", root=self.root)
            gdad_run.write_packet(
                "gdad-demo", "line-pair",
                kind="ambiguity",
                question="Workers finished. Resume to review?",
                done=["waiting"],
                options=[{"id": "resume", "label": "Resume", "consequence": "continue"}],
                evidence="ask",
                artifacts=[],
                checkpoint="",
                suggested="{}",
                root=self.root,
            )
            self.assertEqual(len(self.tabs), 1)

            gdad_run.journal(
                "gdad-demo", "line-pair", "decision", who="fable",
                reply={"reply": "resume", "packet_id": "pkt-1", "option_id": "resume"},
                root=self.root,
            )
            gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
            gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="reject", note="count=3", root=self.root)
            verdict = gdad_run.write_packet(
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
            self.assertEqual(len(self.tabs), 0)
            self.assertEqual(gdad_run.live_pane_id("gdad-demo", "line-pair", self.root), "none")
            buf = io.StringIO()
            with redirect_stdout(buf):
                gdad_run.show_node("gdad-demo", "line-pair", root=self.root)
            self.assertIn("## pane\nnone", buf.getvalue())

            gdad_run.journal(
                "gdad-demo", "line-pair", "decision", who="fable",
                reply={"reply": "redispatch", "packet_id": verdict["packet_id"], "changes": "write two lines"},
                root=self.root,
            )
            gdad_run._launch_and_dispatch("gdad-demo", "line-pair", "line-pair-2", self.root)
            self.assertLessEqual(self.peak, 1)
            self.assertEqual(len(self.tabs), 1)


if __name__ == "__main__":
    unittest.main()
