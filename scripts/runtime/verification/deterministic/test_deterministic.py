"""Tests for the deterministic verification floor."""

from __future__ import annotations

from pathlib import Path

import pytest

from ..schemas import DeterministicResult
from . import assemble
from .artifacts import check_artifacts
from .constraints import evaluate_constraint
from .deps import dependency_status
from .probes import CHECK_PROBES, evaluate_criterion


def _eval(
    repo: Path,
    item: dict,
    node_id: str = "",
    config_root: Path | None = None,
):
    return evaluate_criterion(item, repo, node_id, config_root=config_root)


def test_probe_symbol_pass(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text(
        "AA_ROOT=/x\nAA_DATA_HOME=/d\nAA_STATE_HOME=/s\nAA_SCHEMA=1\n"
    )
    result = _eval(
        tmp_path,
        {"id": "aa-root-and-state-paths", "criterion": "roots exist"},
    )
    assert result.status == "pass"
    assert result.method == "symbol"


def test_probe_func_pass(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text(
        "aa_require_jq() {\n  command -v jq\n  aa_die\n}\n"
    )
    result = _eval(
        tmp_path,
        {"id": "aa-require-jq-errors", "criterion": "jq required"},
    )
    assert result.status == "pass"
    assert result.method == "func"


def test_probe_path_pass(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "acceptance.zsh").write_text("# grk sync smoke\n")
    result = _eval(
        tmp_path,
        {"id": "acceptance-test-covers-grk", "criterion": "grk test"},
    )
    assert result.status == "pass"
    assert result.method == "path"


def test_probe_path_absent_needs_evidence(tmp_path: Path):
    result = _eval(
        tmp_path,
        {"id": "acceptance-test-covers-grk", "criterion": "grk test"},
    )
    assert result.status == "indeterminate"
    assert result.needs_evidence is True


def test_probe_paths_pass(tmp_path: Path):
    for rel in [
        "incoming/_example/description.txt",
        "incoming/_example/meta.yaml",
        "incoming/_example/photos/.gitkeep",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    result = _eval(
        tmp_path,
        {"id": "example-folder-present", "criterion": "example folder"},
    )
    assert result.status == "pass"
    assert result.method == "paths"


def test_probe_paths_fail(tmp_path: Path):
    result = _eval(
        tmp_path,
        {"id": "example-folder-present", "criterion": "example folder"},
    )
    assert result.status == "fail"
    assert result.mismatch_kind == "source_path"


def test_probe_tier_distinct_pass(tmp_path: Path):
    (tmp_path / "targets.conf").write_text("grk default sync grk\n")
    result = _eval(
        tmp_path,
        {"id": "grk-default-tier", "criterion": "default tier present"},
    )
    assert result.status == "pass"
    assert result.method == "tier_distinct"


def test_probe_tier_distinct_indeterminate(tmp_path: Path):
    (tmp_path / "targets.conf").write_text(
        "grk default sync grk\n"
        "grk speed sync grk\n"
        "grk frontier sync grk --model grok-frontier\n"
    )
    result = _eval(
        tmp_path,
        {"id": "grk-tier-variants", "criterion": "distinct tiers"},
    )
    assert result.status == "indeterminate"
    assert result.mismatch_kind == "tier_distinct"


def test_probe_human_review(tmp_path: Path):
    result = _eval(
        tmp_path,
        {"id": "publish-click-scaffold", "criterion": "publish scaffold"},
    )
    assert result.status == "indeterminate"
    assert result.method == "human_review"
    assert result.human_question


def test_probe_project_policy_pass(tmp_path: Path):
    policy = tmp_path / "graphs" / "sell-valuables"
    policy.mkdir(parents=True)
    (policy / "project.yaml").write_text(
        "require_human_review_before_overnight: true\n"
    )
    result = _eval(
        tmp_path,
        {"id": "human-review-required-policy", "criterion": "policy"},
        config_root=tmp_path,
    )
    assert result.status == "pass"
    assert result.method == "project_policy"


def test_probe_any_of(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(
        CHECK_PROBES,
        "any-of-test",
        {
            "type": "any_of",
            "files": ["marker.txt"],
            "patterns": [r"alpha", r"beta"],
            "all": False,
        },
    )
    (tmp_path / "marker.txt").write_text("has alpha only\n")
    result = _eval(tmp_path, {"id": "any-of-test", "criterion": "any marker"})
    assert result.status == "pass"
    assert result.method == "any_of"


def test_probe_keyword_scan_source_keeps_zsh_layout(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text("function aa_custom_helper() {}\n")
    result = _eval(
        tmp_path,
        {
            "id": "unregistered-criterion",
            "criterion": "aa_custom_helper must exist in lib",
        },
    )
    assert result.status == "indeterminate"  # keyword scan is weak evidence
    assert result.method == "keyword_scan_source"


def test_probe_missing_named_path_does_not_scan_elsewhere(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "other.py").write_text("submit_verdict = True\n")
    result = _eval(
        tmp_path,
        {
            "id": "missing-specific-path",
            "criterion": "scripts/runtime/verification/semantic/pi_runner.py provides submit_verdict",
        },
    )
    assert result.status == "indeterminate"
    assert result.method == "path_mentioned_missing"
    assert result.mismatch_kind == "source_path"
    assert "pi_runner.py absent" in result.mismatch_detail


def test_probe_no_probe(tmp_path: Path):
    result = _eval(
        tmp_path,
        {"id": "plain-criterion", "criterion": "something vague"},
    )
    assert result.status == "indeterminate"
    assert result.method == "no_probe"


# ── command_proof tests ────────────────────────────────────────────────────


def test_command_proof_pass(tmp_path: Path):
    result = _eval(
        tmp_path,
        {
            "id": "suite-green",
            "criterion": "pytest passes",
            "command": "python3 -c 'print(\"ok\")'",
        },
    )
    assert result.status == "pass"
    assert result.confidence == 0.95
    assert result.method == "command_proof"
    assert any("exit 0" in e for e in result.evidence)
    assert any("$" in e for e in result.evidence)


def test_command_proof_fail(tmp_path: Path):
    result = _eval(
        tmp_path,
        {
            "id": "suite-green",
            "criterion": "pytest fails",
            "command": "python3 -c 'exit(1)'",
        },
    )
    assert result.status == "fail"
    assert result.confidence == 0.9
    assert result.method == "command_proof"
    assert any("exit 1" in e for e in result.evidence)


def test_command_proof_timeout(tmp_path: Path, monkeypatch):
    import subprocess

    orig_run = subprocess.run

    def _fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", ""), timeout=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = _eval(
        tmp_path,
        {
            "id": "suite-green",
            "criterion": "slow test",
            "command": "sleep 10",
        },
    )
    assert result.status == "indeterminate"
    assert result.confidence == 0.3
    assert result.method == "command_proof_error"


def test_command_proof_oserror(tmp_path: Path, monkeypatch):
    import subprocess

    def _fake_run(*args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = _eval(
        tmp_path,
        {
            "id": "suite-green",
            "criterion": "bad cmd",
            "command": "nonexistent_cmd",
        },
    )
    assert result.status == "indeterminate"
    assert result.confidence == 0.3
    assert result.method == "command_proof_error"
    assert any("OSError" in e for e in result.evidence)


def test_command_proof_no_command_key_falls_through(tmp_path: Path):
    """No command key -> existing behavior untouched (regression)."""
    result = _eval(
        tmp_path,
        {"id": "plain-criterion", "criterion": "something vague"},
    )
    assert result.status == "indeterminate"
    assert result.method == "no_probe"


def test_constraint_scan_clear(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text("AA_TARGETS_CONF=targets.conf\n")
    check = evaluate_constraint(
        "preserve targets.conf default",
        tmp_path,
        ["lib/common.zsh"],
    )
    assert check.status == "clear"


def test_constraint_scan_violated(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text("source grok.zsh\n")
    check = evaluate_constraint(
        "do not source executor-specific modules",
        tmp_path,
        ["lib/common.zsh"],
    )
    assert check.status == "violated"
    assert check.evidence


def test_check_artifacts(tmp_path: Path):
    (tmp_path / "decision.md").write_text("# decision\n")
    node = {"required_artifacts": ["decision.md", "merged_pr"]}
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["merged_pr"] is False


def test_dependency_status():
    project = {
        "nodes": [
            {"id": "a", "status": "complete"},
            {"id": "b", "status": "pending"},
        ]
    }
    deps = dependency_status(project, ["a", "b", "missing"])
    assert deps == {"a": "complete", "b": "pending", "missing": "unknown"}


def test_assemble_returns_deterministic_result(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text("AA_ROOT=1\nAA_DATA_HOME=2\nAA_STATE_HOME=3\nAA_SCHEMA=4\n")
    (tmp_path / "decision.md").write_text("ok")

    node_yaml = {
        "node_id": "test-node",
        "acceptance_criteria": [
            {"id": "aa-root-and-state-paths", "criterion": "roots"},
        ],
        "constraints": ["do not source executor-specific modules"],
        "depends_on": ["dep-a"],
        "required_artifacts": ["decision.md"],
    }
    project_yaml = {
        "nodes": [{"id": "dep-a", "status": "complete"}],
    }

    result = assemble(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=tmp_path,
    )

    assert isinstance(result, DeterministicResult)
    assert len(result.criteria) == 1
    assert result.criteria[0].status == "pass"
    assert result.constraints[0].status == "clear"
    assert result.deps_status == {"dep-a": "complete"}
    assert result.artifacts_present == {"decision.md": True}
