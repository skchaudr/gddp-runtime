import json
import os
import sys
from pathlib import Path

import pytest

from scripts.runtime.verification import cli
from scripts.runtime.verification.capture import EvaluationCapture
from scripts.runtime.verification.semantic import integrity_runner, pi_runner


def inputs(tmp_path):
    node = tmp_path / "node.yaml"
    graph = tmp_path / "project.yaml"
    node.write_text("node_id: example\nacceptance_criteria:\n  - id: behavior\n    criterion: The bridge preserves the request intent.\n")
    graph.write_text("project_id: example-project\nnodes: []\n")
    args = cli.build_parser().parse_args([
        "--node-yaml", str(node), "--project-yaml", str(graph),
        "--repo", str(tmp_path), "--receipt-dir", str(tmp_path / "receipts"),
        "--job-id", "job-one", "--attempt", "0", "--merge-commit-sha", "subject",
    ])
    return args, cli._load_yaml(node), cli._load_yaml(graph)


@pytest.mark.parametrize("lane", ["criteria", "integrity"])
@pytest.mark.parametrize("mode", ["success", "crash", "no-verdict", "timeout"])
def test_real_subprocess_capture_survives_success_and_failure(tmp_path, monkeypatch, lane, mode):
    args, node, graph = inputs(tmp_path)
    capture = EvaluationCapture.start(args, node, graph)
    module = pi_runner if lane == "criteria" else integrity_runner
    runner_type = pi_runner.PiHarnessRunner if lane == "criteria" else integrity_runner.IntegrityHarnessRunner
    verdict = ({"judgments": [], "overall_reasoning": "fixture", "risks": None,
                "followup_candidates": None, "budget_exhausted": False}
               if lane == "criteria" else
               {"verdict": "pass", "intent_preserved": True, "graph_integrity_preserved": True,
                "required_human_review": False, "confidence": 0.9, "findings": [], "reasoning": "fixture"})
    program = tmp_path / "fake-pi"
    program.write_text(f'''#!{sys.executable}
import json, os, sys, time
from pathlib import Path
out = Path(os.environ.get("GDDP_VERDICT_OUT") or os.environ["GDDP_INTEGRITY_OUT"])
request = json.loads((out.parent / "request.json").read_text())
assert request["system_prompt"] == sys.argv[sys.argv.index("--system-prompt") + 1]
assert request["user_prompt"] in sys.argv
print(json.dumps({{"type": "tool_execution_end", "result": {{"content": [{{"type": "text", "text": "full tool output Ω"}}]}}}}), flush=True)
print("fixture stderr", file=sys.stderr, flush=True)
if {mode!r} == "timeout": time.sleep(30)
if {mode!r} == "success": out.write_text({json.dumps(verdict)!r})
sys.exit(1 if {mode!r} == "crash" else 0)
''')
    program.chmod(0o755)
    monkeypatch.setattr(module, "build_pi_environment", lambda *_: dict(os.environ))
    monkeypatch.setattr(module, "evaluator_pi_argv0", lambda *_: str(program))
    monkeypatch.setattr(module, "PI_TIMEOUT_SECONDS", 0.5 if mode == "timeout" else 5)
    result = runner_type(provider="fixture", model="fixture-model", capture=capture).run(
        node=node, graph=graph, deterministic_result={}, repo=tmp_path,
    )
    folder = next(capture.path.glob(lane + "-*"))
    assert "full tool output Ω" in json.loads((folder / "events.jsonl").read_text())["result"]["content"][0]["text"]
    assert (folder / "stderr.log").read_text() == "fixture stderr\n"
    assert json.loads((folder / "request.json").read_text())["model"] == "fixture-model"
    assert json.loads((folder / "command.json").read_text())[0] == str(program)
    assert result.lane_status.value == {
        "success": "completed", "crash": "crashed", "no-verdict": "no-verdict", "timeout": "timed-out",
    }[mode]
    if mode == "success":
        assert json.loads((folder / "verdict.json").read_text()) == verdict
    else:
        assert str(folder) in result.harness_error


def test_snapshots_and_reruns_are_independent(tmp_path):
    args, node, graph = inputs(tmp_path)
    first = EvaluationCapture.start(args, node, graph)
    args.node_yaml.write_text("node_id: changed\n")
    second = EvaluationCapture.start(args, node, graph)
    assert first.path != second.path
    assert first.path.parent == args.receipt_dir / "example-project" / "example"
    assert "node_id: example" in (first.path / "node.yaml").read_text()
    assert json.loads((first.path / "input.json").read_text())["merge_commit_sha"] == "subject"


def test_capture_setup_failure_is_visible_and_allows_evaluation(tmp_path, capsys):
    args, node, graph = inputs(tmp_path)
    args.receipt_dir.write_text("occupied")
    capture = EvaluationCapture.start(args, node, graph)
    assert capture.path is None
    assert capture.errors
    assert "capture incomplete" in capsys.readouterr().err


def test_cli_links_capture_and_keeps_final_receipt(tmp_path, monkeypatch, capsys):
    args, _, _ = inputs(tmp_path)
    # Exercise the real CLI + verifier with a local stand-in for each Pi subprocess.
    from scripts.runtime.verification.schemas import SemanticOutput
    monkeypatch.setattr(pi_runner.PiHarnessRunner, "run", lambda *a, **kw: SemanticOutput(
        judgments=[], overall_reasoning="fixture", risks=None, followup_candidates=None,
        budget_exhausted=False,
    ))
    cli.main([
        "--node-yaml", str(args.node_yaml), "--project-yaml", str(args.project_yaml),
        "--repo", str(tmp_path), "--receipt-dir", str(args.receipt_dir),
        "--job-id", "job-one", "--attempt", "0", "--semantic-mode", "live",
        "--semantic-provider", "deepseek",
    ])
    summary = json.loads(capsys.readouterr().out)
    receipt = json.loads(Path(summary["receipt_path"]).read_text())
    folder = Path(receipt["evaluation_capture_path"])
    assert json.loads((folder / "receipt.json").read_text()) == receipt
    assert receipt["evaluation_capture_errors"] == []


def test_cli_preserves_startup_error(tmp_path, monkeypatch):
    args, _, _ = inputs(tmp_path)
    def unavailable(_args):
        raise RuntimeError("fixture provider unavailable")
    monkeypatch.setattr(cli, "_pi_provider", unavailable)
    with pytest.raises(RuntimeError, match="fixture provider unavailable"):
        cli.main([
            "--node-yaml", str(args.node_yaml), "--project-yaml", str(args.project_yaml),
            "--repo", str(tmp_path), "--receipt-dir", str(args.receipt_dir),
            "--semantic-mode", "live",
        ])
    errors = list(args.receipt_dir.rglob("error.json"))
    assert len(errors) == 1
    assert json.loads(errors[0].read_text())["message"] == "fixture provider unavailable"
