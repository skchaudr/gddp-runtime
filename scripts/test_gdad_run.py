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


class SafetyFixTests(unittest.TestCase):
    def test_decider_argv_restricts_tools_and_skips_no_permissions_flag(self):
        argv = gdad_run.claude_invocation_argv("claude-fable-5-1", "packet", tools="")
        joined = " ".join(argv)
        self.assertIn("--tools", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(joined.find("dangerously-skip-permissions"), -1)

    def test_reviewer_argv_restricts_tools_and_skips_no_permissions_flag(self):
        argv = gdad_run.claude_invocation_argv("opus", "review", tools="")
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(" ".join(argv).find("dangerously-skip-permissions"), -1)

    def test_pi_bin_expands_tilde_from_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)
            (cfg / "runtime").mkdir()
            (cfg / "runtime" / "settings.env").write_text("GDAD_PI_BIN=~/.local/pi-1.0.4/bin\n")
            os.environ["GDDP_CONFIG_PATH"] = str(cfg)
            self.addCleanup(os.environ.pop, "GDDP_CONFIG_PATH", None)
            bindir = gdad_run.pi_bin()
            self.assertEqual(bindir, Path("~/.local/pi-1.0.4/bin").expanduser())

    def test_decider_and_worker_models_default_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)
            (cfg / "runtime").mkdir()
            settings = cfg / "runtime" / "settings.env"
            settings.write_text("GDAD_PI_BIN=~/.local/pi-1.0.4/bin\n")
            os.environ["GDDP_CONFIG_PATH"] = str(cfg)
            self.addCleanup(os.environ.pop, "GDDP_CONFIG_PATH", None)
            self.assertEqual(gdad_run.decider_model(), gdad_run.DEFAULT_DECIDER_MODEL)
            self.assertEqual(gdad_run.worker_model(), gdad_run.DEFAULT_WORKER_MODEL)
            settings.write_text(
                "GDAD_PI_BIN=~/.local/pi-1.0.4/bin\n"
                "GDAD_DECIDER_MODEL=custom-decider\n"
                "GDAD_WORKER_MODEL=custom-worker\n"
            )
            self.assertEqual(gdad_run.decider_model(), "custom-decider")
            self.assertEqual(gdad_run.worker_model(), "custom-worker")

    def test_scribe_agent_lives_outside_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            cfg = Path(tmp) / "config"
            root.mkdir()
            cfg.mkdir()
            os.environ["GDDP_RUNTIME_ROOT"] = str(root)
            os.environ["GDDP_CONFIG_PATH"] = str(cfg)
            self.addCleanup(os.environ.pop, "GDDP_RUNTIME_ROOT", None)
            self.addCleanup(os.environ.pop, "GDDP_CONFIG_PATH", None)
            def_dir = cfg / "graphs" / "gdad-demo" / "gdad" / "line-pair"
            def_dir.mkdir(parents=True)
            (def_dir / "first-prompt.txt").write_text("Write hello files.")
            node = gdad_run.node_dir("gdad-demo", "line-pair", root)
            node.mkdir(parents=True)
            run_id = "run-1"
            gdad_run._spec_for("gdad-demo", "line-pair", run_id, root, cfg)
            art = node / "runs" / run_id / "artifacts"
            run = node / "runs" / run_id
            scribe = run / ".pi" / "agents" / "scribe.md"
            self.assertTrue(scribe.is_file())
            self.assertFalse((art / ".pi").exists())
            spec = json.loads((run / "spec.json").read_text())
            self.assertEqual(spec["cwd"], str(run))


if __name__ == "__main__":
    unittest.main()
