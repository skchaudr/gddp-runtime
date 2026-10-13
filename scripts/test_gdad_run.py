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
                    "label": "gdad-gdad-demo-line-pair",
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


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["GDDP_RUNTIME_ROOT"] = str(self.root)
        self.addCleanup(self.tmp.cleanup)

    def dispatch(self):
        return gdad_run.journal(
            "gdad-demo", "line-pair", "dispatch",
            request_id="line-pair-1", wid="wid-1",
            root=self.root,
        )

    def test_missing_pane_triggers_dsa_resume(self):
        self.dispatch()
        calls: list[list[str]] = []

        def fake_dsa(*args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")

        with (
            mock.patch.object(gdad_run, "dsa_cmd", side_effect=fake_dsa),
            mock.patch.object(gdad_run, "launch_pi", return_value={"pane_id": "p1"}),
        ):
            gdad_run._perform_resume(
                "gdad-demo",
                "line-pair",
                {
                    "run_id": "line-pair-1",
                    "question": "resume?",
                    "resume_handle": {"wid": "wid-1", "qid": "q1", "rev": 0},
                },
                self.root,
            )
        self.assertTrue(any(c and c[0] == "resume" and c[1] == "wid-1" for c in calls))

    def test_write_packet_keeps_journal_and_files_in_lock(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "pause", note="hold", root=self.root)
        pkt = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="ambiguity",
            question="q?",
            done=["d"],
            options=[{"id": "resume", "label": "Resume", "consequence": "go"}],
            evidence="e",
            artifacts=[],
            checkpoint="",
            suggested="{}",
            root=self.root,
        )
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        self.assertTrue((directory / "packets" / f"{pkt['packet_id']}.json").is_file())
        lines = gdad_run._read_lines(directory)
        self.assertEqual(lines[-1]["type"], "packet")
        self.assertIn(pkt["packet_id"], lines[-1]["note"])

    def test_open_packets_sort_by_number(self):
        folder = gdad_run.node_dir("gdad-demo", "line-pair", self.root) / "packets"
        folder.mkdir(parents=True)
        for packet_id in ("pkt-10", "pkt-2"):
            (folder / f"{packet_id}.json").write_text(
                json.dumps({"packet_id": packet_id, "open": True, "kind": "ambiguity"}) + "\n",
                encoding="utf-8",
            )
        rows = gdad_run.open_packets("gdad-demo", "line-pair", self.root)
        self.assertEqual([row["packet_id"] for row in rows], ["pkt-2", "pkt-10"])

    def test_watch_seeds_cursor_and_filters_wid(self):
        directory = gdad_run.node_dir("gdad-demo", "line-pair", self.root)
        directory.mkdir(parents=True)
        (directory / "journal.jsonl").write_text("{}\n", encoding="utf-8")
        (directory / "status").write_text(
            "state: running\nwho: gdad-executor\nwhen: t\nrun_id: line-pair-1\n"
            "request_id: line-pair-1\nwid: wid-1\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def fake_dsa(*args, **kwargs):
            calls.append(list(args))
            body = "\n".join([
                json.dumps({"type": "head", "cursor": "100:1"}),
                json.dumps({"type": "question", "wid": "other-wid", "cursor": "100:2"}),
                json.dumps({"type": "question", "wid": "wid-1", "cursor": "100:3"}),
            ])
            return subprocess.CompletedProcess(list(args), 0, stdout=body, stderr="")

        with (
            mock.patch.object(gdad_run, "dsa_cmd", side_effect=fake_dsa),
            mock.patch.object(gdad_run.time, "sleep", side_effect=[None, StopIteration]),
        ):
            with self.assertRaises(StopIteration):
                gdad_run.watch_node("gdad-demo", "line-pair", root=self.root)
        self.assertNotIn("--all", calls[0])
        self.assertNotIn("--since", calls[0])
        self.assertIn("--since", calls[1])

    def test_retry_budget_blocks_extra_redispatch(self):
        cfg = self.root / "cfg"
        graph = cfg / "graphs" / "gdad-demo"
        graph.mkdir(parents=True)
        (graph / "project.yaml").write_text("execution_policy:\n  retry_budget: 1\n", encoding="utf-8")
        os.environ["GDDP_CONFIG_PATH"] = str(cfg)
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="reject", note="n", root=self.root)
        first = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="verdict",
            question="again?",
            done=["rejected"],
            options=[{"id": "redispatch", "label": "Redispatch", "consequence": "run"}],
            evidence="e",
            artifacts=[],
            checkpoint="",
            suggested="{}",
            root=self.root,
        )
        gdad_run.journal(
            "gdad-demo", "line-pair", "decision", who="fable",
            reply={"reply": "redispatch", "packet_id": first["packet_id"], "changes": "fix"},
            root=self.root,
        )
        gdad_run.journal(
            "gdad-demo", "line-pair", "dispatch",
            request_id="line-pair-2", wid="wid-2",
            root=self.root,
        )
        gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="reject", note="n2", root=self.root)
        second = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="verdict",
            question="again?",
            done=["rejected"],
            options=[{"id": "redispatch", "label": "Redispatch", "consequence": "run"}],
            evidence="e",
            artifacts=[],
            checkpoint="",
            suggested="{}",
            root=self.root,
        )
        with self.assertRaises(gdad_run.JournalError):
            gdad_run.decide(
                second["packet_id"],
                {"reply": "redispatch", "packet_id": second["packet_id"], "changes": "fix again"},
                root=self.root,
            )
        self.assertEqual(gdad_run.current_state("gdad-demo", "line-pair", self.root), "blocked")

    def test_dispatch_from_rejected(self):
        self.dispatch()
        gdad_run.journal("gdad-demo", "line-pair", "review", root=self.root)
        gdad_run.journal("gdad-demo", "line-pair", "verdict", verdict="reject", note="n", root=self.root)
        packet = gdad_run.write_packet(
            "gdad-demo", "line-pair",
            kind="verdict",
            question="Close?",
            done=["rejected"],
            options=[{"id": "close", "label": "Close", "consequence": "stop"}],
            evidence="n",
            artifacts=[],
            checkpoint="",
            suggested="{}",
            root=self.root,
        )
        gdad_run.journal(
            "gdad-demo", "line-pair", "decision", who="fable",
            reply={"reply": "next", "packet_id": packet["packet_id"], "workflow": None},
            root=self.root,
        )
        self.assertEqual(gdad_run.current_state("gdad-demo", "line-pair", self.root), "rejected")
        line = gdad_run.journal(
            "gdad-demo", "line-pair", "dispatch",
            request_id="line-pair-2", wid="wid-2",
            root=self.root,
        )
        self.assertEqual(line["state"], "running")


class JournalSchemaTests(unittest.TestCase):
    def test_demo_dispatch_line_matches_schema(self):
        runtime_wt = Path(__file__).resolve().parents[1]
        schema_path = (
            runtime_wt.parent.parent.parent
            / "gddp-config"
            / ".worktrees"
            / "gdad-fix-cleanup"
            / "schemas"
            / "gdad"
            / "journal.schema.json"
        )
        env_cfg = os.environ.get("GDDP_CONFIG_PATH")
        if not schema_path.is_file() and env_cfg:
            schema_path = Path(env_cfg) / "schemas" / "gdad" / "journal.schema.json"
        self.assertTrue(schema_path.is_file(), f"missing schema at {schema_path}")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        allowed = set(schema["properties"])
        required = set(schema["required"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        os.environ["GDDP_RUNTIME_ROOT"] = str(root)
        line = gdad_run.journal(
            "gdad-demo", "line-pair", "dispatch",
            request_id="line-pair-1", wid="wid-1",
            root=root,
        )
        self.assertTrue(required <= set(line))
        self.assertTrue(set(line) <= allowed)


if __name__ == "__main__":
    unittest.main()
