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


def test_mentioned_paths_recognizes_txt_and_unknown_extensions():
    from .probes import mentioned_paths_from_text
    paths = mentioned_paths_from_text(
        'gate-smoke/a.txt exists and out/data.csv is written'
    )
    assert "gate-smoke/a.txt" in paths
    assert "out/data.csv" in paths


def test_path_content_check_exact_pass(tmp_path: Path):
    smoke = tmp_path / "gate-smoke"
    smoke.mkdir()
    (smoke / "a.txt").write_text("A passed\n")
    result = _eval(
        tmp_path,
        {
            "id": "marker-a-exact",
            "criterion": 'gate-smoke/a.txt exists and contains exactly "A passed\\n"',
        },
    )
    assert result.status == "pass"
    assert result.method == "path_content_check"


def test_path_content_check_exact_fail_on_mismatch(tmp_path: Path):
    smoke = tmp_path / "gate-smoke"
    smoke.mkdir()
    (smoke / "a.txt").write_text("wrong content\n")
    result = _eval(
        tmp_path,
        {
            "id": "marker-a-exact",
            "criterion": 'gate-smoke/a.txt exists and contains exactly "A passed\\n"',
        },
    )
    assert result.status == "fail"
    assert result.method == "path_content_check"


def test_path_content_check_substring_when_not_exact(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "usage.md").write_text("# Usage\n\nRun echo hello world to test.\n")
    result = _eval(
        tmp_path,
        {
            "id": "docs-mention",
            "criterion": 'docs/usage.md documents "echo hello world"',
        },
    )
    assert result.status == "pass"
    assert result.method == "path_content_check"


def test_path_without_quoted_literal_falls_through(tmp_path: Path):
    smoke = tmp_path / "gate-smoke"
    smoke.mkdir()
    (smoke / "a.txt").write_text("A passed\n")
    result = _eval(
        tmp_path,
        {
            "id": "bounded-change",
            "criterion": "The attempt changes only gate-smoke/a.txt",
        },
    )
    assert result.status == "indeterminate"  # no quoted literal → keyword scan
    assert result.method == "keyword_scan_source"


def test_path_content_check_ignores_literal_in_sibling_file(tmp_path: Path):
    """The literal is verified only in the criterion-named path. A sibling
    file containing the phrase must not produce a pass."""
    smoke = tmp_path / "gate-smoke"
    smoke.mkdir()
    (smoke / "a.txt").write_text("something else\n")
    (smoke / "b.txt").write_text("A passed\n")  # literal only in sibling
    result = _eval(
        tmp_path,
        {
            "id": "marker-a-exact",
            "criterion": 'gate-smoke/a.txt exists and contains exactly "A passed\\n"',
        },
    )
    assert result.status == "fail"
    assert result.method == "path_content_check"


def test_path_content_check_real_smoke_criteria(tmp_path: Path):
    """Regression against the actual run-1 fixture criteria (result tree
    0deaab2: a.txt inherited unchanged, b.txt added)."""
    smoke = tmp_path / "gate-smoke"
    smoke.mkdir()
    (smoke / "a.txt").write_text("A passed\n")
    (smoke / "b.txt").write_text("B passed\n")
    r1 = _eval(
        tmp_path,
        {
            "id": "marker-a-inherited",
            "criterion": 'gate-smoke/a.txt exists unchanged and contains exactly "A passed\\n"',
        },
    )
    r2 = _eval(
        tmp_path,
        {
            "id": "marker-b-exact",
            "criterion": 'gate-smoke/b.txt exists and contains exactly "B passed\\n"',
        },
    )
    assert (r1.status, r1.method) == ("pass", "path_content_check")
    assert (r2.status, r2.method) == ("pass", "path_content_check")


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
    """Individual files still work (regression)."""
    (tmp_path / "decision.md").write_text("# decision\n")
    node = {"required_artifacts": ["decision.md", "merged_pr"]}
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["merged_pr"] is False


def test_check_artifacts_condensed_receipt_all_present(tmp_path: Path):
    """Condensed receipt with all four artifacts satisfied."""
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## decision.md\n"
        "## plan.md\n"
        "## feedback.md\n"
        "## review.md\n"
    )
    node = {
        "required_artifacts": [
            "decision.md",
            "plan.md",
            "feedback.md",
            "review.md",
        ]
    }
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["plan.md"] is True
    assert present["feedback.md"] is True
    assert present["review.md"] is True


def test_check_artifacts_condensed_receipt_missing_heading(tmp_path: Path):
    """Condensed receipt without a required artifact leaves it absent."""
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## decision.md\n"
        "## plan.md\n"
    )
    node = {"required_artifacts": ["decision.md", "plan.md", "feedback.md"]}
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["plan.md"] is True
    assert present["feedback.md"] is False


def test_check_artifacts_individual_files_in_subdirs(tmp_path: Path):
    """Individual files in .gddp/ and docs/ still work."""
    (tmp_path / ".gddp").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".gddp" / "decision.md").write_text("# decision\n")
    (tmp_path / "docs" / "plan.md").write_text("# plan\n")
    node = {"required_artifacts": ["decision.md", "plan.md"]}
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["plan.md"] is True


def test_check_artifacts_mixed_individual_and_condensed(tmp_path: Path):
    """Some artifacts as individual files, some via condensed receipt."""
    (tmp_path / "decision.md").write_text("# decision\n")
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## plan.md\n"
        "## feedback.md\n"
    )
    node = {
        "required_artifacts": [
            "decision.md",
            "plan.md",
            "feedback.md",
            "review.md",
        ]
    }
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True  # individual file
    assert present["plan.md"] is True  # from receipt
    assert present["feedback.md"] is True  # from receipt
    assert present["review.md"] is False  # not present anywhere


def test_check_artifacts_merged_pr_always_false_even_in_receipt(tmp_path: Path):
    """merged_pr always False, even if listed as H2 in receipt."""
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## merged_pr\n"
        "## decision.md\n"
    )
    node = {"required_artifacts": ["merged_pr", "decision.md"]}
    present = check_artifacts(node, tmp_path)
    assert present["merged_pr"] is False  # special-cased, always False
    assert present["decision.md"] is True  # from receipt


def test_check_artifacts_receipt_in_subdirs(tmp_path: Path):
    """executor-receipt.md in .gddp/ or docs/ also works."""
    (tmp_path / ".gddp").mkdir()
    receipt = tmp_path / ".gddp" / "executor-receipt.md"
    receipt.write_text("# Execution Receipt\n## plan.md\n")
    node = {"required_artifacts": ["plan.md"]}
    present = check_artifacts(node, tmp_path)
    assert present["plan.md"] is True


def test_check_artifacts_heading_with_trailing_whitespace(tmp_path: Path):
    """H2 heading match allows trailing whitespace."""
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## decision.md  \n"  # trailing spaces
        "## plan.md\t\n"  # trailing tab
    )
    node = {"required_artifacts": ["decision.md", "plan.md"]}
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is True
    assert present["plan.md"] is True


def test_check_artifacts_heading_must_match_exactly(tmp_path: Path):
    """H2 heading must match exactly; no partial or case mismatches."""
    receipt = tmp_path / "executor-receipt.md"
    receipt.write_text(
        "# Execution Receipt\n"
        "## Decision.md\n"  # case mismatch
        "## plan.md extra\n"  # extra text
        "### feedback.md\n"  # H3 instead of H2
        "## review.md"
    )
    node = {
        "required_artifacts": [
            "decision.md",
            "plan.md",
            "feedback.md",
            "review.md",
        ]
    }
    present = check_artifacts(node, tmp_path)
    assert present["decision.md"] is False  # case mismatch
    assert present["plan.md"] is False  # extra text
    assert present["feedback.md"] is False  # H3 not H2
    assert present["review.md"] is True  # exact match


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
